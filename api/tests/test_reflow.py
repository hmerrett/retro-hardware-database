"""What the manual promises a narrow screen (MANUAL.md, "On a narrow screen").

Nothing surfaces a page that scrolls sideways on a phone except reading that page
on a phone: it takes one column too many in one list, and the person who added
the column was looking at a desktop. The files list had six and scrolled the page
by 683px at 320, with the box you re-file a file in off the right-hand edge --
which is the worst of it, because a page that has moved under you is hardest to
forgive while you are typing into it.

So the promise is held as a structural invariant rather than by measuring a
layout, which the suite has no browser to do: a table with more columns than a
phone has room for either comes down the page as blocks, or scrolls inside its
own box. Both answers exist in the stylesheet already; what was missing was
anything that noticed a third table doing neither.
"""

import re
from html.parser import HTMLParser
from pathlib import Path

import pytest

STYLESHEET = Path(__file__).parents[1] / "app" / "static" / "app.css"

# A 320px phone spends 24 of it on the page's gutters. Four columns would have 74
# each, which is five characters of a monospace font and a padding either side.
MOST_A_PHONE_HOLDS = 3


class Tables(HTMLParser):
    """Every table on the page, with the two facts that decide whether it fits:
    what it is called, and whether something above it scrolls on purpose."""

    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.tables = []
        self._open = []
        self._scrolling = 0

    def handle_starttag(self, tag, attrs):
        got = dict(attrs)
        classes = (got.get("class") or "").split()
        if tag == "div" and "hscroll" in classes:
            self._scrolling += 1
            self._open.append(("hscroll", None))
            return
        if tag == "table":
            table = {"classes": classes, "scrolls": self._scrolling > 0, "widest": 0, "row": 0}
            self.tables.append(table)
            self._open.append(("table", table))
        elif tag == "tr" and self._open and self._open[-1][0] == "table":
            self._open[-1][1]["row"] = 0
        elif tag in ("td", "th"):
            for kind, table in reversed(self._open):
                if kind == "table":
                    span = got.get("colspan")
                    table["row"] += int(span) if span and span.isdigit() else 1
                    table["widest"] = max(table["widest"], table["row"])
                    break

    def handle_endtag(self, tag):
        if tag == "table" and self._open and self._open[-1][0] == "table":
            self._open.pop()
        elif tag == "div" and self._open and self._open[-1][0] == "hscroll":
            self._open.pop()
            self._scrolling -= 1


def tables_on(html: str):
    parser = Tables()
    parser.feed(html)
    return parser.tables


def stacks_on_a_phone(css: str, classes: list[str]) -> bool:
    """A table that answers a narrow screen by coming down the page: its cells are
    told to be blocks inside a `max-width` block, the way .projtable and
    .ordertable are."""
    for narrow in re.finditer(r"@media\s*\(max-width:\s*\d+px\)\s*\{(.*?)\n  \}", css, re.S):
        body = narrow.group(1)
        for name in classes:
            if re.search(rf"\.{re.escape(name)}\b[^{{]*\{{[^}}]*display:\s*block", body):
                return True
    return False


def describe(table) -> str:
    return ".".join(table["classes"]) or "<table> with no class"


@pytest.fixture
def furnished(client, computer, part):
    """Enough in the register that the list pages render their tables at all: an
    empty list says "nothing yet" and would pass every check below by having
    nothing to check."""
    made = computer(manufacturer="Amstrad", model="PC1512")
    card = part(
        manufacturer="Trident", model="TVGA8900", type="video", computer_id=made["asset_id"]
    )
    client.post(
        "/files",
        files={"uploads": ("tvga8900-drivers.zip", b"driver bytes")},
        data={"aid": card["asset_id"], "note": "DOS and Windows 3.1 drivers"},
        follow_redirects=False,
    )
    client.post(
        "/projects", data={"title": "Recap the PC1512", "status": "active"}, follow_redirects=False
    )
    return {"computer": made["asset_id"], "part": card["asset_id"]}


def pages(ids):
    return [
        "/",
        "/files",
        "/projects",
        "/machines",
        "/stats",
        "/for-sale",
        f"/computers/{ids['computer']}",
        f"/computers/{ids['computer']}/edit",
        f"/parts/{ids['part']}",
        f"/parts/{ids['part']}/edit",
    ]


def test_no_list_is_wider_than_the_phone_it_is_read_on(client, furnished):
    """The invariant, stated once over every page that has a table on it: more
    columns than fit means the table has been given one of the two answers."""
    css = STYLESHEET.read_text(encoding="utf-8")
    too_wide = []
    for path in pages(furnished):
        page = client.get(path)
        assert page.status_code == 200, f"{path} did not render: {page.status_code}"
        for table in tables_on(page.text):
            if table["widest"] <= MOST_A_PHONE_HOLDS or table["scrolls"]:
                continue
            if not stacks_on_a_phone(css, table["classes"]):
                too_wide.append(f"{path}: {describe(table)}, {table['widest']} columns")
    assert too_wide == [], "these tables neither stack nor scroll, so the page does: " + "; ".join(
        too_wide
    )


def test_the_files_list_is_rows_and_not_a_table(client, furnished):
    """The files list was the widest table on the site, six columns when logged in,
    and it pushed a phone 683px sideways. It is a list of rows now (ADR-0028), each
    saying its own size and date in words, so there is no table on it to stack and
    no heading for a stacked cell to have lost."""
    page = client.get("/files").text
    assert '<ul class="filerows">' in page
    assert "<table" not in page.split("<main", 1)[1]


def test_the_box_you_type_into_asks_for_a_width_rather_than_demanding_one():
    """A `min-width` on a control is a floor the row around it cannot go below: 200px
    of it on the old re-file box held the files list open. The boxes on a file's
    page ask for a width and accept less -- `width` is a size a row may compress,
    `min-width` is one it may not."""
    css = STYLESHEET.read_text(encoding="utf-8")
    rule = re.search(r"\.linkform input, \.notebox input\s*\{[^}]*\}", css)
    assert rule, "the boxes on a file's page have lost their rule; this test is looking at nothing"
    demanded = re.search(r"min-width:\s*(\d+)px", rule.group(0))
    assert not demanded or demanded.group(1) == "0", (
        f"the box demands {demanded.group(0)}, which its row cannot go below"
    )


def test_a_long_filename_cannot_hold_the_list_open():
    """`overflow-wrap: break-word` on a cell breaks a word that has already been
    given its column, but leaves the column's minimum width at the whole word --
    so the longest filename on the page decided how narrow the table could be. It
    is a filename: it may break anywhere, because nobody reads one as a word."""
    css = STYLESHEET.read_text(encoding="utf-8")
    rule = re.search(r"\.fname\s*\{[^}]*\}", css)
    assert rule, "nothing lets a filename break, so the widest one sets the list's width"
    assert "overflow-wrap: anywhere" in rule.group(0)
