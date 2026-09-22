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

from app import main

CSS = Path(__file__).parents[1] / "app" / "static" / "css"
COMPONENTS = CSS / "components.css"

SECTIONS = [
    ("/", "Browse"),
    ("/projects", "Projects"),
    ("/stats", "Numbers"),
    ("/machines", "Models"),
    ("/files", "Files"),
]


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


def rule(selector: str, css: str) -> str:
    """The body of the first rule whose selector list names `selector` exactly."""
    for head, body in re.findall(r"([^{}@]+)\{([^{}]*)\}", css):
        if selector in [s.strip() for s in head.split(",")]:
            return body
    raise AssertionError(f"no rule for {selector}")


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
    monkeypatch.setitem(main.templates.env.globals, "auth_enabled", True)


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
        monkeypatch.setattr(main.auth, "AUTH_ENABLED", True)
        monkeypatch.setitem(main.templates.env.globals, "auth_enabled", True)
        assert "hdr-new" not in client.get("/").text


class TestTheMenu:
    def test_it_offers_the_owner_might_sell_traffic_and_log_out(self, client, owner):
        menu = region(client.get("/").text, cls="hdr-more")
        assert {"Might sell", "Traffic", "Log out"} <= set(menu.words)

    def test_it_offers_a_visitor_log_in(self, client, monkeypatch):
        monkeypatch.setattr(main.auth, "AUTH_ENABLED", True)
        monkeypatch.setitem(main.templates.env.globals, "auth_enabled", True)
        menu = region(client.get("/").text, cls="hdr-more")
        assert "Log in" in menu.words and "Log out" not in menu.words

    def test_it_holds_the_five_sections_folded_away_at_its_top(self, client):
        menu = region(client.get("/").text, cls="hdr-more")
        folded = [words for words, attrs in menu.links if "fold" in (attrs.get("class") or "")]
        assert folded == [name for _, name in SECTIONS]
        assert menu.links[0][1].get("class") == "fold", "the sections are not at the top"

    def test_the_phone_sheet_offers_everything_the_menu_does(self, client, owner):
        """One list, two renderings: a row added to one and not the other is a
        thing a phone or a desktop cannot reach."""
        page = client.get("/").text
        menu = {attrs.get("href") for _, attrs in region(page, cls="hdr-more").links}
        sheet = {attrs.get("href") for _, attrs in region(page, id="sheet").links}
        assert menu - {"/"} <= sheet


class TestHowItFoldsWithTheWidth:
    def test_on_a_tablet_the_sections_leave_the_banner(self):
        tablet = media("(max-width: 900px)", stylesheet())
        assert "display: none" in rule(".site-header nav", tablet)

    def test_and_are_found_in_the_menu_instead(self):
        css = stylesheet()
        assert "display: none" in rule(".menupop .fold", css)
        assert "display: block" in rule(".menupop .fold", media("(max-width: 900px)", css))

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


class TestNotices:
    def test_running_open_is_a_warning_not_an_alarm(self, client, monkeypatch):
        """Spec 15: the no-login banner is `warning`, not `danger`. It is a state
        the operator may well have meant, and a notice that shouts on every page
        is one that stops being read."""
        monkeypatch.setitem(main.templates.env.globals, "auth_open_warning", True)
        page = client.get("/").text
        assert re.search(r'<div class="banner warning"[^>]*id="openwarn"[^>]*role="status"', page)
