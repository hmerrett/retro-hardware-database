"""One page or tabs on an item page, each person's choice (MANUAL §4, "One page or
tabs").

One page is every panel down the page and is what anybody gets until they choose;
Tabs is the same panels a tab at a time, under a row of links the server draws.
Both are the same templates, so the tests here ask each promise of both."""

import re
from pathlib import Path

import pytest

from conftest import as_viewer, content
from test_item_page_controls import _png
from test_item_page_names import Node, Tree, tree

COMPONENTS = Path(__file__).resolve().parents[1] / "app" / "static" / "css" / "components.css"
COOKIE = "rhdb_itemlayout"
KINDS = pytest.mark.parametrize("kind", ["computers", "parts"])


@pytest.fixture
def items(client, computer, part):
    """A machine and a card, each with a job, a file, two notes and photographs."""
    pc = computer(name="Lounge PC")["asset_id"]
    card = part(type="io", model="Controller")["asset_id"]
    part(type="sound", model="SB16", computer_id=pc)
    for kind, aid in (("computers", pc), ("parts", card)):
        client.post(f"/{kind}/{aid}/photo", files={"photos": ("p.png", _png(), "image/png")})
        client.post(f"/{kind}/{aid}/note", data={"message": "Tested"})
        client.post(f"/{kind}/{aid}/note", data={"message": "Recapped"})
        client.post("/files", files={"uploads": (f"{aid}.img", b"\0" * 100)}, data={"aid": aid})
        client.post("/projects/quick", data={"aid": aid, "job": "Recap it"})
    return {"computers": pc, "parts": card}


def panels(page: str) -> list[str]:
    """The titles of the panels in the main column, in order."""
    t = tree(page)
    body = next(n for n in t.root.walk() if "itembody" in n.classes())
    return [n.text() for n in body.walk() if n.tag == "h3"]


def side(page: str) -> list[str]:
    t = tree(page)
    return [
        n.text()
        for n in t.root.walk()
        if n.tag == "h3" and any(a.classes() & {"itemphotos", "itemside"} for a in n.ancestors())
    ]


def strip(page: str) -> Node | None:
    t = tree(page)
    return next((n for n in t.root.walk() if n.tag == "nav" and "tabs" in n.classes()), None)


def tabs_of(page: str) -> list[tuple[str, str, bool]]:
    nav = strip(page)
    assert nav is not None, "no row of tabs"
    return [
        (a.text(), a.get("href"), a.get("aria-current") == "page")
        for a in nav.walk()
        if a.tag == "a"
    ]


def tabbed(client, kind, aid, tab=""):
    return client.get(f"/{kind}/{aid}?layout=tabs" + (f"&tab={tab}" if tab else ""))


class TestTheSwitch:
    @KINDS
    def test_one_page_or_tabs_sits_in_the_top_row_before_edit(self, client, items, kind):
        t = tree(client.get(f"/{kind}/{items[kind]}").text)
        row = next(n for n in t.root.walk() if "ctlrow" in n.classes())
        switch = next(n for n in row.walk() if "viewswitch" in n.classes())
        assert switch.get("aria-label") == "Show as"
        assert [a.text() for a in switch.walk() if a.tag == "a"] == ["One page", "Tabs"]
        order = [n.text() for n in row.walk() if n.tag in ("a", "button")]
        assert order.index("Tabs") < order.index("Edit")

    @KINDS
    def test_a_visitor_has_it_too(self, client, items, kind):
        as_viewer(client)
        t = tree(client.get(f"/{kind}/{items[kind]}").text)
        assert any("viewswitch" in n.classes() for n in t.root.walk())

    @KINDS
    def test_one_page_is_what_anybody_gets_until_they_choose(self, client, items, kind):
        page = client.get(f"/{kind}/{items[kind]}")
        assert strip(page.text) is None
        assert re.search(r'<a href="\?layout=page" aria-current="page">One page', page.text)
        assert COOKIE not in page.headers.get("set-cookie", "")

    def test_choosing_tabs_is_remembered_in_a_cookie(self, client, items):
        page = client.get(f"/computers/{items['computers']}?layout=tabs")
        cookie = page.headers["set-cookie"]
        assert cookie.startswith(f"{COOKIE}=tabs;") and "HttpOnly" in cookie
        assert "samesite=lax" in cookie.lower()

    def test_and_holds_on_every_machine_and_part(self, client, items):
        client.get(f"/computers/{items['computers']}?layout=tabs")
        assert strip(client.get(f"/parts/{items['parts']}").text) is not None

    def test_until_one_page_is_chosen_again(self, client, items):
        client.get(f"/computers/{items['computers']}?layout=tabs")
        client.get(f"/parts/{items['parts']}?layout=page")
        assert strip(client.get(f"/computers/{items['computers']}").text) is None

    def test_reading_a_page_stores_nothing(self, client, items):
        client.get(f"/computers/{items['computers']}?layout=tabs")
        again = client.get(f"/computers/{items['computers']}?tab=files")
        assert COOKIE not in again.headers.get("set-cookie", "")

    def test_the_cookie_notice_names_the_choice(self, fresh_client):
        assert "one page or tabs" in fresh_client.get("/login").text


class TestOnePage:
    def test_every_panel_is_down_the_page(self, client, items):
        assert panels(client.get(f"/computers/{items['computers']}").text) == [
            "Details",
            "Motherboard",
            "Parts",
            "Work",
            "Files",
            "History",
        ]

    def test_a_tab_s_address_still_shows_it_all(self, client, items):
        """A link to a tab sent to somebody reading one page is still a link to the
        item: they get the whole page."""
        page = client.get(f"/computers/{items['computers']}?tab=files").text
        assert "History" in panels(page) and strip(page) is None


class TestTabs:
    @KINDS
    def test_a_row_of_four_tabs_with_the_counts(self, client, items, kind):
        got = tabs_of(tabbed(client, kind, items[kind]).text)
        words = [w for w, _, _ in got]
        assert words[0] == "Details"
        assert re.fullmatch(r"Work 0/1", words[1]), words
        assert words[2] == "Files 1"
        assert re.fullmatch(r"History \d+", words[3]), words

    @KINDS
    def test_each_is_a_link_with_its_own_address(self, client, items, kind):
        got = tabs_of(tabbed(client, kind, items[kind]).text)
        assert [h for _, h, _ in got] == ["?tab=details", "?tab=work", "?tab=files", "?tab=history"]

    @KINDS
    def test_a_page_opens_on_details(self, client, items, kind):
        got = tabs_of(tabbed(client, kind, items[kind]).text)
        assert [on for _, _, on in got] == [True, False, False, False]

    def test_the_row_ends_the_head(self, client, items):
        t = tree(tabbed(client, "computers", items["computers"]).text)
        head = next(n for n in t.root.walk() if "itemhead" in n.classes())
        last = [c for c in head.children if isinstance(c, Node)][-1]
        assert last.tag == "nav" and "tabs" in last.classes()
        assert last.get("aria-label") == "Sections"

    def test_details_on_a_machine(self, client, items):
        page = tabbed(client, "computers", items["computers"]).text
        assert panels(page) == ["Details", "Motherboard", "Parts"]

    def test_details_on_a_part(self, client, items):
        got = panels(tabbed(client, "parts", items["parts"]).text)
        assert got[0] == "Details" and "Fitted in" in got and "Mounted parts" in got
        assert not {"Work", "Files", "History"} & set(got)

    @pytest.mark.parametrize(
        "tab, title", [("work", "Work"), ("files", "Files"), ("history", "History")]
    )
    @KINDS
    def test_each_other_tab_holds_its_panel(self, client, items, kind, tab, title):
        page = tabbed(client, kind, items[kind], tab).text
        assert panels(page) == [title]
        assert [on for _, _, on in tabs_of(page)].index(True) == [
            "details",
            "work",
            "files",
            "history",
        ].index(tab)

    @pytest.mark.parametrize("tab", ["details", "work", "files", "history"])
    def test_the_head_and_the_side_column_stay_put(self, client, items, tab):
        page = tabbed(client, "computers", items["computers"], tab).text
        assert "Lounge PC" in content(page).split('class="itemhead"', 1)[1].split("</h1>", 1)[0]
        assert side(page)[0] == "Photographs"
        assert "Label" in side(page)

    def test_an_unknown_tab_opens_details(self, client, items):
        page = tabbed(client, "computers", items["computers"], "nonsense").text
        assert panels(page)[0] == "Details"

    def test_work_is_not_there_for_a_visitor_when_there_is_none_to_see(self, client, computer):
        aid = computer(name="Bare PC")["asset_id"]
        client.get(f"/computers/{aid}?layout=tabs")
        as_viewer(client)
        got = [w for w, _, _ in tabs_of(client.get(f"/computers/{aid}").text)]
        assert [w.split()[0] for w in got] == ["Details", "Files", "History"]
        # And its address opens Details rather than an empty column.
        assert panels(client.get(f"/computers/{aid}?tab=work").text)[0] == "Details"

    def test_the_switch_keeps_the_tab_it_leaves_from(self, client, items):
        """Going back to one page from a tab is going back to the item."""
        page = tabbed(client, "computers", items["computers"], "files").text
        t = Tree(content(page))
        switch = next(n for n in t.root.walk() if "viewswitch" in n.classes())
        assert [a.get("href") for a in switch.walk() if a.tag == "a"] == [
            "?layout=page",
            "?layout=tabs&tab=files",
        ]


class TestOnAPhone:
    def test_the_photographs_come_with_details_only(self, client, items):
        for tab, mark in (("details", "on-details"), ("files", "on-files")):
            t = tree(tabbed(client, "computers", items["computers"], tab).text)
            cols = next(n for n in t.root.walk() if "itemcols" in n.classes())
            assert {"tabbed", mark} <= cols.classes()

    def test_the_stylesheet_hides_them_on_the_others(self):
        css = COMPONENTS.read_text()
        assert re.search(
            r"@media \(max-width: 860px\) \{[^}]*\.itemcols\.tabbed:not\(\.on-details\) > \.itemphotos"
            r" \{ display: none; \}",
            css,
        )


class TestSendingBringsYouBackToTheTab:
    @pytest.mark.parametrize("tab", ["details", "work", "files", "history"])
    @KINDS
    def test_every_form_on_a_tab_says_which(self, client, items, kind, tab):
        """In the address it posts to, or in the `next` it carries back. Duplicate and
        the Work box answer with another page -- the copy, the project -- so there is
        no tab of this one to come back to."""
        page = content(tabbed(client, kind, items[kind], tab).text)
        forms = re.findall(r"<form\b[^>]*>.*?</form>", page, re.S)
        elsewhere = ("/duplicate", "/projects/quick")
        posting = [
            f
            for f in forms
            if 'method="post"' in f and not any(e in f.split(">", 1)[0] for e in elsewhere)
        ]
        assert posting
        lost = [
            f[:120]
            for f in posting
            if f"tab={tab}" not in re.search(r"<form\b[^>]*>", f)[0]
            and not re.search(rf'name="next" value="[^"]*tab={tab}"', f)
        ]
        assert lost == []

    def test_one_page_s_forms_say_nothing_of_tabs(self, client, items):
        page = content(client.get(f"/computers/{items['computers']}").text)
        assert "tab=" not in page

    @KINDS
    def test_a_note_from_history(self, client, items, kind):
        aid = items[kind]
        r = client.post(
            f"/{kind}/{aid}/note?tab=history", data={"message": "Cleaned"}, follow_redirects=False
        )
        assert r.headers["location"] == f"/{kind}/{aid}?tab=history"

    @KINDS
    def test_a_photograph_from_files(self, client, items, kind):
        aid = items[kind]
        r = client.post(
            f"/{kind}/{aid}/photo?tab=files",
            files={"photos": ("q.png", _png(), "image/png")},
            follow_redirects=False,
        )
        assert r.headers["location"] == f"/{kind}/{aid}?tab=files"

    def test_what_else_the_answer_says_travels_with_it(self, client, computer):
        """A fetch that finds nothing still says so, on the tab it was sent from."""
        aid = computer(name="Lounge PC")["asset_id"]
        r = client.post(f"/computers/{aid}/fetch-image?tab=work", follow_redirects=False)
        assert r.headers["location"] == f"/computers/{aid}?tab=work&imgerr=1"

    def test_a_file_from_files(self, client, items):
        aid = items["computers"]
        page = content(tabbed(client, "computers", aid, "files").text)
        nxt = re.search(r'action="/files"[^>]*>.*?name="next" value="([^"]+)"', page, re.S)[1]
        r = client.post(
            "/files",
            files={"uploads": ("z.img", b"\0" * 10)},
            data={"aid": aid, "next": nxt},
            follow_redirects=False,
        )
        assert r.headers["location"] == f"/computers/{aid}?tab=files"

    def test_a_job_ticked_on_work(self, client, items):
        aid = items["computers"]
        page = content(tabbed(client, "computers", aid, "work").text)
        assert re.search(rf'name="next" value="/computers/{aid}\?tab=work"', page)

    def test_a_tab_that_is_not_one_is_not_carried(self, client, items):
        aid = items["computers"]
        r = client.post(
            f"/computers/{aid}/note?tab=%2F%2Fevil.example",
            data={"message": "x"},
            follow_redirects=False,
        )
        assert r.headers["location"] == f"/computers/{aid}"
