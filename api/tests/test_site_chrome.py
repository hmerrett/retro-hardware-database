"""What the manual promises of the banner, its menu and the phone's bar (MANUAL.md,
"The header" and "The header on a phone").

The chrome is the one piece of markup on every page, and the one a narrow screen
rearranges most: the sections fold into the menu on a tablet and move to a bar on a
phone. Which of those a width gets is decided in the stylesheet, so those promises
are read off the declarations; what each rendering offers is read off the page.
"""

import re
from html.parser import HTMLParser
from pathlib import Path

import pytest

from app import machines, settings
from conftest import log_out

CSS = Path(__file__).parents[1] / "app" / "static" / "css"
COMPONENTS = CSS / "components.css"
TEMPLATES = Path(__file__).parents[1] / "app" / "templates"

# What a browser sends: the error page is drawn only for a reader that asked for HTML.
HTML = {"accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8"}

SECTIONS = [
    ("/", "Browse"),
    ("/projects", "Projects"),
    ("/stats", "Numbers"),
    ("/machines", "Models"),
    ("/files", "Files"),
]

# The lists of places beside the banner's own, each of which marks where you are
# for itself: the rail, the ⋯ menu and the phone's More.
LISTS = {"rail": {"cls": "rail"}, "menu": {"cls": "hdr-more"}, "more": {"id": "sheet"}}


class Region(HTMLParser):
    """The text and links inside the first element carrying `cls` (or `id`)."""

    def __init__(self, *, cls: str = "", id: str = "") -> None:
        super().__init__()
        self.cls, self.id = cls, id
        self.depth = 0
        self.links: list[tuple[str, dict[str, str | None]]] = []
        self.words: list[str] = []
        self._open: dict[str, str | None] | None = None
        self._done = False

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        a = dict(attrs)
        if self.depth:
            if tag not in ("input", "hr", "img", "br"):
                self.depth += 1
            if tag == "a":
                self._open = a
                self.links.append(("", a))
            return
        if self._done:
            return
        if (self.cls and self.cls in (a.get("class") or "").split()) or (
            self.id and a.get("id") == self.id
        ):
            self.depth = 1

    def handle_endtag(self, tag: str) -> None:
        if self.depth:
            self.depth -= 1
            if tag == "a":
                self._open = None
            if not self.depth:
                self._done = True

    def handle_data(self, data: str) -> None:
        if not self.depth or not data.strip():
            return
        self.words.append(data.strip())
        if self._open is not None:
            href, attrs = self.links[-1]
            self.links[-1] = (href + data.strip(), attrs)


def region(html: str, **where: str) -> Region:
    found = Region(**where)
    found.feed(html)
    assert found.words, f"nothing rendered inside {where}"
    return found


def marked(html: str, **where: str) -> list[str | None]:
    """Where a list of places says you are: the links it marks as the current page."""
    links = region(html, **where).links
    return [attrs.get("href") for _, attrs in links if attrs.get("aria-current") == "page"]


def rules(selector: str, css: str) -> list[str]:
    """The body of every rule whose selector list names `selector` exactly."""
    return [
        body
        for head, body in re.findall(r"([^{}@]+)\{([^{}]*)\}", css)
        if selector in [s.strip() for s in head.split(",")]
    ]


def rule(selector: str, css: str) -> str:
    """The body of the first rule whose selector list names `selector` exactly."""
    found = rules(selector, css)
    assert found, f"no rule for {selector}"
    return found[0]


def media(query: str, css: str) -> str:
    """Every `@media` block with this query, joined: the rules a width gets."""
    blocks = []
    for found in re.finditer(r"@media\s*" + re.escape(query) + r"\s*\{", css):
        depth, at = 1, found.end()
        while depth:
            depth += {"{": 1, "}": -1}.get(css[at], 0)
            at += 1
        blocks.append(css[found.end() : at - 1])
    assert blocks, f"no @media {query} block"
    return "\n".join(blocks)


def stylesheet() -> str:
    return re.sub(r"/\*.*?\*/", "", COMPONENTS.read_text(encoding="utf-8"), flags=re.S)


@pytest.fixture
def owner(monkeypatch):
    """A site with a login, seen by its owner: every row the menus can hold."""


class TestTheBanner:
    def test_the_sections_are_written_in_sentence_case(self, client):
        nav = region(client.get("/machines").text, cls="site-header")
        names = [words for words, attrs in nav.links if not attrs.get("class")]
        assert names[:5] == [name for _, name in SECTIONS]

    @pytest.mark.parametrize("path, name", SECTIONS)
    def test_the_section_you_are_in_is_the_one_marked(self, client, path, name):
        nav = region(client.get(path).text, cls="site-header")
        current = [
            words
            for words, attrs in nav.links
            if attrs.get("aria-current") == "page" and not attrs.get("class")
        ]
        assert current == [name]

    def test_the_section_you_are_in_is_said_in_weight_not_colour_alone(self):
        body = rule('.site-header nav a[aria-current="page"]', stylesheet())
        assert "font-weight: 600" in body

    def test_the_menu_is_named_for_a_screen_reader(self, client):
        page = client.get("/").text
        assert re.search(r'class="menu hdr-more">\s*<summary[^>]*aria-label="More"', page)

    def test_new_is_offered_only_to_the_owner(self, client, monkeypatch):
        assert "hdr-new" in client.get("/").text
        log_out(client)
        assert "hdr-new" not in client.get("/").text


class TestTheMenu:
    def test_it_offers_the_owner_might_sell_traffic_and_log_out(self, client, owner):
        menu = region(client.get("/").text, cls="hdr-more")
        assert {"Might sell", "Traffic", "Log out"} <= set(menu.words)

    def test_it_offers_a_visitor_log_in(self, client, monkeypatch):
        log_out(client)
        menu = region(client.get("/").text, cls="hdr-more")
        assert "Log in" in menu.words and "Log out" not in menu.words

    def test_it_holds_the_five_sections_folded_away_at_its_top(self, client):
        menu = region(client.get("/").text, cls="hdr-more")
        folded = [words for words, attrs in menu.links if "fold" in (attrs.get("class") or "")]
        assert folded == [name for _, name in SECTIONS]
        assert menu.links[0][1].get("class") == "fold", "the sections are not at the top"

    def test_a_visitor_is_not_offered_the_api_docs(self, client, part):
        """`/docs` is behind the login, and what it answers a visitor is the
        browser's own password box rather than the site's login page. Its link is on
        Your account, which a visitor cannot open, so no page offers it to one --
        the phone's More sheet included."""
        aid = part()["asset_id"]
        log_out(client)
        for path in ("/", f"/parts/{aid}"):
            assert 'href="/docs' not in client.get(path).text, path

    def test_the_phone_sheet_offers_everything_the_menu_does(self, client, owner):
        """One list, two renderings: a row added to one and not the other is a
        thing a phone or a desktop cannot reach."""
        page = client.get("/").text
        menu = {attrs.get("href") for _, attrs in region(page, cls="hdr-more").links}
        sheet = {attrs.get("href") for _, attrs in region(page, id="sheet").links}
        assert menu - {"/"} <= sheet


class TestTheFootOfThePage:
    def test_no_page_carries_a_footer(self, client, part):
        """The name is in the banner or the rail, and the API docs are beside the
        tokens they are for, so there is nothing left for a footer to hold."""
        aid = part()["asset_id"]
        for path in ("/", f"/parts/{aid}"):
            assert "<footer" not in client.get(path).text, path
        log_out(client)
        assert "<footer" not in client.get("/login").text
        assert not rules(".site-footer", stylesheet())


class TestTheBrowsersTab:
    def test_every_page_is_titled_with_the_installations_name(self, client, db):
        """The tab is one of the places the Name setting reaches, so every page ends
        its title with this collection's name -- a model's page and the page for an
        address that leads nowhere included, which ended theirs with the software's."""
        settings.save(db, {"site_name": "The Retro Loft"})
        settings.forget()
        for path in (f"/machines/{machines.models()[0]['key']}", "/no-such-address"):
            found = re.search(r"<title>(.*?)</title>", client.get(path, headers=HTML).text, re.S)
            assert found, path
            assert found.group(1).endswith(" — The Retro Loft"), (path, found.group(1))
        for template in sorted(TEMPLATES.glob("*.html")):
            text = template.read_text(encoding="utf-8")
            for title in re.findall(r"{% block title %}(.*?){% endblock %}", text, re.S):
                assert "Retro Hardware Database" not in title, template.name


class TestWhereYouAre:
    @pytest.mark.parametrize("where", list(LISTS.values()), ids=list(LISTS))
    def test_one_place_is_current_at_a_time(self, client, where):
        """Your account's address begins with Settings', so both entries could
        claim it; two marked is a screen reader told it is on two pages at once.
        An administrator reaches Your account as a tab of Settings and is not
        offered Account as well, so it is Settings that is marked (MANUAL §18)."""
        assert marked(client.get("/settings/account").text, **where) == ["/settings"]

    @pytest.mark.parametrize("path", ["/settings", "/settings/users"])
    @pytest.mark.parametrize("where", list(LISTS.values()), ids=list(LISTS))
    def test_the_other_settings_pages_still_mark_settings(self, client, where, path):
        """Account takes the mark on its own page and nowhere else."""
        assert marked(client.get(path).text, **where) == ["/settings"]

    @pytest.mark.parametrize("where", list(LISTS.values()), ids=list(LISTS))
    def test_the_shortlist_marks_might_sell(self, client, where):
        """It is drawn in the site's chrome like any other page, so it says where you
        are like any other. Traffic cannot: its page is GoAccess's, with no chrome."""
        assert marked(client.get("/for-sale").text, **where) == ["/for-sale"]


class TestHowItFoldsWithTheWidth:
    def test_on_a_tablet_the_sections_leave_the_banner(self):
        tablet = media("(max-width: 900px)", stylesheet())
        assert "display: none" in rule(".site-header nav", tablet)

    def test_and_are_found_in_the_menu_instead(self):
        css = stylesheet()
        assert "display: none" in rule(".menupop .fold", css)
        assert "display: block" in rule(".menupop .fold", media("(max-width: 900px)", css))

    def test_on_a_phone_the_banner_keeps_the_name(self):
        """With no footer, the banner is the only place on a phone's page that says
        whose collection a scanned label has opened. On one line and clipped, so a
        long name costs its own end rather than a second row of banner."""
        phone = media("(max-width: 620px)", stylesheet())
        name = rules(".site-header .brand span", phone)
        assert name, "the phone block says nothing of the name"
        assert not any("display: none" in body for body in name), "the phone hides the name"
        said = " ".join(name)
        for clipped in ("white-space: nowrap", "overflow: hidden", "text-overflow: ellipsis"):
            assert clipped in said, clipped
        # A flex item will not shrink below its content unless it is told it may, so
        # without this the name is never clipped: it pushes the search box instead.
        assert "min-width: 0" in rule(".site-header .brand", phone)

    def test_on_a_phone_the_bar_takes_over_and_scan_goes_with_it(self):
        phone = media("(max-width: 620px)", stylesheet())
        for gone in (".site-header .hdr-new", ".site-header .hdr-more", ".site-header .hdr-scan"):
            assert "display: none" in rule(gone, phone), gone
        assert "position: fixed" in rule(".tabbar", phone)

    def test_the_bar_is_nowhere_but_a_phone(self):
        assert "display: none" in rule(".tabbar", stylesheet())

    def test_the_bar_sits_above_the_home_indicator(self):
        phone = media("(max-width: 620px)", stylesheet())
        assert "safe-area-inset-bottom" in rule(".tabbar", phone)


def declared(selector: str) -> dict[str, str]:
    """What components.css states for `selector` outside any @media block, all of
    that selector's rules together."""
    text = re.sub(r"/\*.*?\*/", "", COMPONENTS.read_text(encoding="utf-8"), flags=re.S)
    bodies = re.findall(rf"^  {re.escape(selector)} \{{([^}}]*)\}}", text, re.M)
    assert bodies, f"components.css has no rule for {selector}"
    return dict(re.findall(r"([\w-]+)\s*:\s*([^;]+?)\s*;", " ".join(bodies)))


class TestTheBannerStaysOneRow:
    """The banner wrapped: its items kept their own widths, 1041px of them with the
    sections showing, so below that the menu dropped to a second row at the left and
    opened off the window's edge. The design keeps it one row, and so does the
    manual."""

    def test_the_banner_never_wraps(self):
        assert declared(".site-header")["flex-wrap"] == "nowrap"

    def test_the_search_box_gives_way_first_down_to_a_floor(self):
        wrap = declared(".site-header .searchwrap")
        assert wrap["flex"] == "0 1 230px"
        assert int(wrap["min-width"].removesuffix("px")) >= 160
        assert declared(".site-header .search")["width"] == "100%"

    def test_then_a_long_name_is_cut_short_and_the_logo_stays(self):
        brand = declared(".site-header .brand")
        assert brand["min-width"] == "0"
        assert float(brand["flex-shrink"]) < 0.01, "the name would give way with the box"
        name = declared(".site-header .brand span")
        assert (name["overflow"], name["text-overflow"], name["white-space"]) == (
            "hidden",
            "ellipsis",
            "nowrap",
        )
        assert declared(".site-header .brand img")["flex"] == "none"
