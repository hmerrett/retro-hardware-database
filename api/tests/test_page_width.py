"""How wide a page is drawn, and from what.

The design draws every page in one column, `.page`: `--content-max` wide and
centred, with gutters from the spacing scale, which are the gutters the banner's
flash is placed by. Until the column was put on `<main>`, 0.1's own rule held every
page instead -- `main { max-width: 1000px; padding: 18px }`, unlayered, so it
outranked the design's layer whatever the specificity -- and the token capped
nothing while the banner assumed a gutter the page did not have.

Nothing on a rendered page says which rule sized it, so these read the two halves
apart: that `<main>` carries the column, and that no stylesheet sizes `<main>` behind
its back.
"""

import json
import re
from html.parser import HTMLParser
from pathlib import Path

from test_stylesheet_lint import COMPONENTS, LEGACY, UTILITIES, declarations, text

APP = Path(__file__).parents[1] / "app"
TEMPLATES = APP / "templates"
STATIC = APP / "static"
TOKENS = STATIC / "css" / "tokens.css"
# What a browser asks for, without which an error is answered as the API would.
HTML = {"accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8"}
# What decides how wide a box is and where its content starts.
SIZING = re.compile(r"^(?:(?:max-|min-)?width|(?:margin|padding)(?:-[\w-]+)?)$")


class Mains(HTMLParser):
    """The class attributes of each `<main>` on a page, as written. A list and not a
    dict, because a browser keeps the first of two and a dict would keep the last."""

    def __init__(self):
        super().__init__()
        self.found: list[list[str]] = []

    def handle_starttag(self, tag, attrs):
        if tag == "main":
            self.found.append([value or "" for name, value in attrs if name == "class"])


def subjects(head: str) -> list[str]:
    """What each selector in a rule's head styles: its last compound, read outside any
    brackets -- `main` in `main:not(.v2)`, `.panel` in `main:not(.v2) .panel`."""
    found, depth, last, current = [], 0, "", ""
    for ch in head + ",":
        depth += (ch == "(") - (ch == ")")
        if depth or ch not in " >+~,":
            current += ch
            continue
        last, current = current or last, ""
        if ch == ",":
            found.append(last)
            last = ""
    return found


def test_every_page_is_drawn_in_the_page_column(client, a_page_of_everything):
    """Every page's `<main>` is the design's page column -- one class attribute, and
    it names `page` -- on the pages still drawn with 0.1's components as much as on
    those moved onto v0.2's. base.html is the one template that writes a `<main>`, and a
    page adds to its classes by name alone, so the pages walked here stand for the rest."""
    templates = {
        str(t.relative_to(TEMPLATES)): t.read_text(encoding="utf-8")
        for t in TEMPLATES.rglob("*.html")
    }
    assert [name for name, text in templates.items() if "<main" in text] == ["base.html"]
    # base.html writes what a page adds inside its own class attribute, after `page`. A
    # page that wrote `class="v2"` there would open a second attribute in the middle of
    # the first, and the browser would read neither as it was meant.
    added = {
        name: extra
        for name, text in templates.items()
        for extra in re.findall(r"{% block main_class %}(.*?){% endblock %}", text)
        if not re.fullmatch(r"( [\w-]+)*", extra)
    }
    assert added == {}
    for path in [*a_page_of_everything, "/computers/RH-9999"]:
        mains = Mains()
        mains.feed(client.get(path, headers=HTML).text)
        assert len(mains.found) == 1, f"{path} has {len(mains.found)} <main> elements"
        (classes,) = mains.found
        assert len(classes) == 1 and "page" in classes[0].split(), f"{path}: {classes}"


def test_no_stylesheet_gives_the_page_a_width_or_gutter_of_its_own():
    """The width of a page and its gutters are `.page`'s alone. A rule on `<main>`
    itself would decide them instead -- 0.1's did, from outside the design's layer --
    and the column, the token it is drawn from and the banner's flash would go on
    describing a page that is not there."""
    stated = [
        f"{path.name}: {selector} {{ {prop}: {value} }}"
        for path in sorted(STATIC.rglob("*.css"))
        for selector, prop, value in declarations(path)
        if SIZING.match(prop)
        and any(re.match(r"main(?![\w-])|.*#main(?![\w-])", s) for s in subjects(selector))
    ]
    assert stated == []


def rules_by_media(path: Path) -> list[tuple[tuple[str, ...], str, str]]:
    """Every rule in a stylesheet as (the `@media` queries around it, its selector, its
    body), in source order. Which widths a declaration holds at is decided by the
    blocks it sits in, which `declarations` leaves behind."""
    css, found, opened, start = text(path), [], [], 0
    for at, ch in enumerate(css):
        if ch == "{":
            opened.append((" ".join(css[start:at].split()), at + 1))
        elif ch == "}":
            head, begun = opened.pop()
            if not head.startswith("@"):
                queries = tuple(
                    h.removeprefix("@media ") for h, _ in opened if h.startswith("@media")
                )
                found.append((queries, head, css[begun:at]))
        if ch in "{};":
            start = at + 1
    return found


def by_media(path: Path, selector: str, side) -> dict[tuple[str, ...], str]:
    """What `side` reads off `selector`'s rules, in px, keyed by the `@media` queries
    it is stated under -- `()` for every width."""
    scale = dict(re.findall(r"(--[\w-]+):\s*([^;]+);", text(TOKENS)))
    found = {}
    for queries, head, body in rules_by_media(path):
        if selector in [s.strip() for s in head.split(",")]:
            for prop, value in (d.split(":", 1) for d in body.split(";") if ":" in d):
                if (read := side(prop.strip(), value.split())) is not None:
                    found[queries] = re.sub(r"var\((--[\w-]+)\)", lambda m: scale[m[1]], read)
    return found


def test_the_banner_s_flash_is_placed_by_the_page_under_it():
    """The rule under the banner is not inside the page, so it cannot ask the page
    where its column ends: `.stripe` puts the banner's flash above the panels' by
    arithmetic. Both read the one inset worked out on `:root`, so they cannot drift
    apart again. 0.1's page was padded 18px while the stripe assumed 24px, and the
    banner's flash stood 6px off the line the panels' flashes are on."""
    after = [
        v
        for sel, prop, v in declarations(COMPONENTS)
        if sel == ".stripe::after" and prop == "right"
    ]
    assert after and after[-1].startswith("calc(var(--page-inset)"), after
    pads = [
        value
        for queries, head, body in rules_by_media(UTILITIES)
        if ".page" in [h.strip() for h in head.split(",")]
        for prop, value in (d.split(":", 1) for d in body.split(";") if ":" in d)
        if prop.strip() == "padding"
    ]
    assert pads and all(v.split()[1] == "var(--page-inset)" for v in pads), pads


# Each page that extends base.html, and the width it is drawn at: decided here, not
# defaulted, so a new page fails until somebody says which it is.
WIDE = {
    "index.html",  # Browse, and /browse, /for-sale and a search, which are Browse
    "machines.html",
    "model.html",
    "stats.html",
    "computer_form.html",
    "part_form.html",
    "project_form.html",
    # Settings and the account pages, one row of tabs across them.
    "settings.html",
    "settings_users.html",
    "settings_user.html",
    "settings_account.html",
}
READING = {
    "computer.html",
    "part.html",
    "project.html",
    "file.html",
    "projects.html",
    "files.html",
    "login.html",
    "setup.html",
    "delete.html",
    "detach.html",
    "error.html",
    "forbidden.html",
}


def width_block(name: str) -> str | None:
    found = re.findall(r"{% block width %}(.*?){% endblock %}", (TEMPLATES / name).read_text())
    return found[0] if found else None


def test_each_page_s_width_is_decided_not_defaulted():
    pages = {
        t.name
        for t in TEMPLATES.glob("*.html")
        if '{% extends "base.html" %}' in t.read_text(encoding="utf-8")
    }
    assert pages == WIDE | READING, "a page whose width nobody has decided"
    assert not WIDE & READING
    assert {name: width_block(name) for name in WIDE} == dict.fromkeys(WIDE, " wide")
    assert {name: width_block(name) for name in READING} == dict.fromkeys(READING)
    assert "{% block width %}{% endblock %}" in (TEMPLATES / "base.html").read_text()


def main_classes(client, path: str) -> list[str]:
    mains = Mains()
    mains.feed(client.get(path, headers=HTML).text)
    ((classes,),) = mains.found
    return classes.split()


def test_the_lists_and_forms_use_a_wide_screen(client, a_page_of_everything):
    wide = [
        p
        for p in a_page_of_everything
        if p in ("/", "/machines", "/stats", "/for-sale")
        or p.startswith(("/machines/", "/settings"))
        or p.endswith(("/edit", "/new"))
    ]
    assert len(wide) >= 9, wide
    for path in [*wide, "/browse?f=all", "/?q=vic"]:
        assert "wide" in main_classes(client, path), path


def test_the_pages_you_read_keep_the_column(client, a_page_of_everything):
    reading = [
        p
        for p in a_page_of_everything
        if p.startswith(("/computers/RH", "/parts/RH", "/files", "/projects"))
        and not p.endswith(("/edit", "/new"))
    ]
    assert len(reading) >= 5, reading
    for path in reading:
        assert "wide" not in main_classes(client, path), path


def test_the_small_pages_stay_small(client):
    for path in ("/computers/RH-9999",):
        assert "wide" not in main_classes(client, path), path
    caps = {
        sel: v
        for sel, prop, v in declarations(COMPONENTS)
        if sel in (".loginbox", ".confirm", ".errorpage") and prop == "max-width"
    }
    assert set(caps) == {".loginbox", ".confirm", ".errorpage"}
    assert all(int(v.removesuffix("px")) < 1000 for v in caps.values()), caps


def scale(name: str) -> str:
    sizes = json.loads((APP / "design" / "scales.json").read_text())["size"]["tokens"]
    return {t["name"]: t["value"] for t in sizes}[name]


def test_the_page_widths_are_tokens_in_the_design_data():
    assert (scale("content-max"), scale("wide-max")) == ("1000px", "1440px")
    assert scale("measure").endswith("em")
    page_max = [
        (sel, v)
        for path in (UTILITIES, COMPONENTS)
        for sel, prop, v in declarations(path)
        if prop == "--page-max"
    ]
    assert sorted(page_max) == [
        (":root", "var(--content-max)"),
        (":root:has(main.page.wide)", "var(--wide-max)"),
    ]
    literal = [
        (path.name, sel, prop, v)
        for path in STATIC.rglob("*.css")
        if path != TOKENS
        for sel, prop, v in declarations(path)
        if re.search(r"\b(1000|1440)px", v)
    ]
    assert literal == []
    assert not [p for sel, p, v in declarations(UTILITIES) if sel == ".page" and p == "max-width"]


def px(token: str) -> int:
    return int(re.search(rf"{re.escape(token)}:\s*(\d+)px", text(TOKENS))[1])


def test_four_cards_across_at_the_column_and_six_at_the_wide_width():
    track = int(re.search(r"\.grid \{[^}]*minmax\(min\((\d+)px", text(COMPONENTS))[1])
    gap, gutter = px("--space-5"), px("--space-6")

    def across(page: int) -> int:
        return (page - 2 * gutter + gap) // (track + gap)

    assert (across(px("--content-max")), across(px("--wide-max"))) == (4, 6)


def test_a_form_row_holds_five_boxes_at_most():
    grid = re.search(r"\.formgrid \{[^}]*minmax\(min\((\d+)px", text(COMPONENTS)) or re.search(
        r"\.formgrid \{[^}]*minmax\((\d+)px", text(COMPONENTS)
    )
    track, gap, gutter, inner = int(grid[1]), px("--space-5"), px("--space-6"), px("--space-5")
    row = px("--wide-max") - 2 * gutter - 2 * inner
    assert (row + gap) // (track + gap) <= 5


def test_what_you_read_keeps_a_measure():
    capped = {
        one.strip()
        for sel, prop, v in declarations(COMPONENTS)
        if prop == "max-width" and v == "var(--measure)"
        for one in sel.split(",")
    }
    assert {".prose", ".lead", ".hint", ".banner > span", "#cookienote p"} <= capped, capped
    in_ch = [
        (path.name, sel)
        for path in STATIC.rglob("*.css")
        for sel, prop, v in declarations(path)
        if prop == "max-width" and v.endswith("ch")
    ]
    assert in_ch == []


def test_no_box_on_a_page_grows_past_the_measure():
    assert (".page :is(.input, .select)", "max-width", "var(--measure)") in declarations(COMPONENTS)
    unscoped = [
        sel
        for sel, prop, v in declarations(LEGACY)
        if prop == "max-width" and re.fullmatch(r"(select|input|textarea)", sel.strip())
    ]
    assert unscoped == []


def test_the_banner_and_the_footer_stand_on_the_wide_page_s_edges():
    for selector in (".site-header", ".site-footer"):
        inline = [
            value
            for queries, head, body in rules_by_media(COMPONENTS)
            if selector in [h.strip() for h in head.split(",")]
            for prop, value in (d.split(":", 1) for d in body.split(";") if ":" in d)
            if prop.strip() in ("padding", "padding-inline")
        ]
        assert inline, selector
        assert all("var(--frame-inset)" in v for v in inline), (selector, inline)
    roots = {(sel, v) for sel, prop, v in declarations(UTILITIES) if prop == "--frame-inset"}
    assert roots and all(
        sel == ":root" and "--wide-max" in v and "--gutter" in v for sel, v in roots
    )
    gutters = {
        sel
        for path in STATIC.rglob("*.css")
        for sel, prop, v in declarations(path)
        if prop == "--gutter"
    }
    assert gutters == {":root"}, gutters


def test_the_models_list_runs_to_three_columns():
    columns = [
        v for sel, prop, v in declarations(COMPONENTS) if sel == ".models" and prop == "columns"
    ]
    assert columns == ["3 320px"]


def test_a_drive_s_bezel_menus_share_its_row():
    column = [
        sel
        for sel, prop, v in declarations(COMPONENTS)
        if "bezel-cell" in sel and prop == "flex-direction" and v == "column"
    ]
    assert column == []


def test_a_card_asks_for_the_width_it_is_drawn_at():
    """The browser picks a card's picture before layout, from `sizes`: too small a
    figure and a 2x screen gets the 300px copy of a 244px card."""
    track = int(re.search(r"\.grid \{[^}]*minmax\(min\((\d+)px", text(COMPONENTS))[1])
    gap = px("--space-5")
    widest = track + (track + gap) / 4
    figure = int(
        re.search(
            r'sizes="\(max-width: 460px\) 100vw, (\d+)px"', (TEMPLATES / "_ui.html").read_text()
        )[1]
    )
    assert widest <= figure <= 250


class Boxes(HTMLParser):
    """How many single-line boxes and menus each fieldset stands one under another:
    those outside a grid (.formgrid, or .countgrid for a board's counts) and a table."""

    def __init__(self):
        super().__init__()
        self.stack: list[str] = []
        self.loose: list[int] = []

    def handle_starttag(self, tag, attrs):
        a = dict(attrs)
        if tag in ("fieldset", "div"):
            self.stack.append(
                "grid" if {"formgrid", "countgrid"} & set((a.get("class") or "").split()) else tag
            )
            if tag == "fieldset":
                self.loose.append(0)
        single = (
            tag == "input" and a.get("type") in (None, "text", "number", "date")
        ) or tag == "select"
        if single and self.loose and "grid" not in self.stack and "table" not in self.stack:
            self.loose[-1] += 1
        if tag == "table":
            self.stack.append("table")

    def handle_endtag(self, tag):
        if tag in ("fieldset", "div", "table") and self.stack:
            self.stack.pop()


def test_a_section_of_short_questions_lays_them_across(client):
    """On a wide page the short questions of a part's own section stand side by side,
    as Identity's and Tracking's do, rather than one under another down the form."""
    for ptype in ("cpu", "ram", "video", "sound", "network", "io", "motherboard"):
        boxes = Boxes()
        boxes.feed(client.get(f"/parts/new?type={ptype}", headers=HTML).text)
        assert max(boxes.loose, default=0) < 3, (ptype, boxes.loose)
