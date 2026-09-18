"""What the manual promises a keyboard, a screen reader and a reduced-motion
setting (MANUAL.md, "Using it from the keyboard").

What these have in common is that no single change surfaces them: a skip link is
invisible until it has focus, a missing `scope` reads correctly to everyone who
can see the table, motion is only wrong for the people who asked for less of it,
and a control scrolled to under the tab bar is only wrong for somebody arriving
at it with the Tab key. So they are checked against the markup and the stylesheet
themselves, the way test_stylesheet.py checks declarations rather than pages.
"""
import re
from html.parser import HTMLParser
from pathlib import Path

import pytest

TEMPLATES = Path(__file__).parents[1] / "app" / "templates"
BASE = TEMPLATES / "base.html"
STYLESHEET = Path(__file__).parents[1] / "app" / "static" / "app.css"

FOCUSABLE = re.compile(r"<(?:a\s[^>]*href=|button\b|input\b|select\b|textarea\b|summary\b)", re.I)
HEADING_CELL = re.compile(r"<th(\s[^>]*)?>")


def first_focusable(html: str) -> str:
    """The markup at the first thing on the page the Tab key can reach."""
    body = html[html.index("<body") :]
    found = FOCUSABLE.search(body)
    assert found, "the page has nothing focusable on it at all"
    return body[found.start() : found.start() + 160]


@pytest.mark.parametrize("path", ["/", "/machines", "/files", "/projects", "/stats"])
def test_the_first_thing_tab_reaches_skips_to_the_content(client, path):
    """A keyboard user tabs the whole header -- brand, five sections, search box,
    menus -- before reaching the page, on every page, unless the first stop is a
    link past it."""
    first = first_focusable(client.get(path).text)
    assert 'href="#main"' in first, f"{path} opens on {first!r}, not the skip link"
    assert "Skip to content" in first


def test_an_item_page_skips_to_the_content_too(client, computer):
    """The page a printed label opens is the one most often reached cold."""
    made = computer()
    first = first_focusable(client.get(f"/computers/{made['asset_id']}").text)
    assert 'href="#main"' in first


def test_the_skip_link_has_somewhere_to_land(client):
    """A skip link whose target is not an id on the page moves focus nowhere and
    fails silently, which is the failure this whole invariant is about."""
    html = client.get("/").text
    assert re.search(r"<main\b[^>]*\bid=\"main\"", html), "no <main id=\"main\"> to skip to"


def test_every_heading_cell_says_which_way_its_table_runs():
    """A screen reader announces a cell with the heading it sits under only when
    the heading says whether it runs across the top or down the side. The item
    pages read down the side and the lists read across the top, so neither
    direction can be assumed and `scope` has to be stated on every one."""
    missing = [
        f"{path.name}: {cell.group(0)}"
        for path in sorted(TEMPLATES.glob("*.html"))
        for cell in HEADING_CELL.finditer(path.read_text(encoding="utf-8"))
        if not re.search(r'scope="(?:col|row)"', cell.group(0))
    ]
    assert missing == [], "these heading cells do not say which way they run: " + "; ".join(missing)


def test_no_movement_starts_without_asking_whether_motion_is_wanted():
    """The register's one piece of motion of its own -- Find, scrolling a phone
    back to the search box -- asks for it in JavaScript, where the CSS cannot
    reach: a `behavior: 'smooth'` passed to scrollTo outranks `scroll-behavior`
    in the stylesheet, so the media query alone would leave it moving."""
    source = BASE.read_text(encoding="utf-8")
    unguarded = [
        found.start()
        for found in re.finditer(r"behavior\s*:", source)
        if "prefers-reduced-motion" not in source[max(0, found.start() - 300) : found.start() + 300]
    ]
    assert unguarded == [], "a scroll is animated without reading the motion preference"


def test_the_stylesheet_answers_a_request_to_reduce_motion():
    """Nothing in the stylesheet animates today, which is exactly when the block
    is cheap to add: it covers the transition somebody writes next, rather than
    being remembered at the moment it is needed."""
    css = STYLESHEET.read_text(encoding="utf-8")
    block = re.search(r"@media\s*\(prefers-reduced-motion:\s*reduce\)\s*\{(.*?)\n  \}", css, re.S)
    assert block, "the stylesheet does not answer prefers-reduced-motion"
    for declaration in ("animation-duration", "transition-duration", "scroll-behavior"):
        assert declaration in block.group(1), f"the block leaves {declaration} alone"


def media_block_holding(css: str, needle: str) -> str:
    """The `@media` block a declaration sits in, read the way the tests above read
    the stylesheet: by its text, since there is no browser here to ask."""
    at = css.index(needle)
    opened = css.rindex("@media", 0, at)
    return css[opened : css.index("\n  }", at) + 4]


def px(text: str, declaration: str) -> int:
    """The first pixel figure in a declaration, whether or not it is inside a
    `calc()` with a safe-area inset added to it."""
    found = re.search(rf"{declaration}:\s*(?:calc\()?\s*(\d+)px", text)
    assert found, f"no {declaration} to read in {text[:80]!r}"
    return int(found.group(1))


def test_a_bar_fixed_across_the_bottom_does_not_swallow_the_focus_ring():
    """Reaching a control below the fold, the browser scrolls it into view and
    stops it at the edge of the viewport -- which on a phone is exactly where the
    tab bar is fixed, so the control arrives underneath it. Measured before this
    was written: twenty stops on an item page, twenty-one on a machine's form, the
    year field and "mark disposed" among the ones hidden outright.

    `body`'s padding holds the last card clear of the bar and says nothing about
    where a scroll stops; the scroll container has to be told separately. WCAG 2.2
    calls this 2.4.11, and the minimum is that focus is not *entirely* hidden."""
    css = STYLESHEET.read_text(encoding="utf-8")
    phone = media_block_holding(css, ".tabbar { position: fixed")
    reserved = px(phone, "padding-bottom")
    assert "scroll-padding-bottom" in phone, (
        "the bar is fixed over the bottom of the page and nothing keeps a scroll clear of it")
    assert px(phone, "scroll-padding-bottom") >= reserved, (
        "a scroll stops closer to the bottom than the bar is tall, so focus lands behind it")


def test_the_cookie_notice_does_not_swallow_it_either():
    """The notice is fixed above the bar and is taller than it -- 167px on a 320px
    screen, where the text wraps to five lines. It is in the markup only while it
    is showing, so `:has` is the whole of the condition and no script is needed to
    put the room back when it goes."""
    css = STYLESHEET.read_text(encoding="utf-8")
    while_showing = [
        rule for rule in re.finditer(r"html:has\(#cookienote\)[^{]*\{[^}]*\}", css)
        if "scroll-padding-bottom" in rule.group(0)
    ]
    assert while_showing, "nothing keeps a scroll clear of the cookie notice"
    phone = media_block_holding(css, ".tabbar { position: fixed")
    inside = [rule for rule in while_showing if rule.group(0) in phone]
    assert inside, "the phone's allowance has to cover the notice and the bar together"
    assert px(inside[0].group(0), "scroll-padding-bottom") > px(phone, "padding-bottom"), (
        "the notice sits on top of the bar, so it needs more room than the bar alone")


def test_the_login_boxes_say_what_they_are_for():
    """A password manager fills a form it can read: `autocomplete="username"` and
    `current-password` are what tell it which entry this is and which box the
    password goes in. Without them the one credential this register has must be
    typed from memory or carried between windows, which is what WCAG 2.2's 3.3.8
    is about."""
    html = (TEMPLATES / "login.html").read_text(encoding="utf-8")
    assert re.search(r'<input[^>]*name="username"[^>]*autocomplete="username"', html), (
        "the username box does not say what it is for")
    assert re.search(r'<input[^>]*name="password"[^>]*autocomplete="current-password"', html), (
        "the password box does not say what it is for")


class Controls(HTMLParser):
    """Every control on the page and whether anything gives it a name: an
    `aria-label`, a `<label>` wrapped round it or pointed at its id, or, for a
    button, the words on it."""

    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.controls = []
        self.labelled_ids = set()
        self.images = []
        self._in_label = 0
        self._button = None

    def handle_starttag(self, tag, attrs):
        got = dict(attrs)
        if tag == "label":
            self._in_label += 1
            if got.get("for"):
                self.labelled_ids.add(got["for"])
        elif tag == "img":
            if got.get("alt") is None:
                self.images.append(got.get("src", "")[-50:])
        elif tag in ("input", "select", "textarea", "button"):
            if got.get("type") == "hidden":
                return
            named = bool(got.get("aria-label") or got.get("aria-labelledby") or got.get("title"))
            named = named or self._in_label > 0
            if got.get("type") in ("submit", "button", "reset") and got.get("value"):
                named = True
            control = {"tag": tag, "id": got.get("id", ""), "name": got.get("name", ""),
                       "named": named, "words": ""}
            self.controls.append(control)
            if tag == "button":
                self._button = control

    def handle_data(self, data):
        if self._button is not None:
            self._button["words"] += data

    def handle_endtag(self, tag):
        if tag == "label" and self._in_label:
            self._in_label -= 1
        elif tag == "button":
            self._button = None

    def unnamed(self):
        return [
            f"<{c['tag']} name={c['name'] or '-'} id={c['id'] or '-'}>"
            for c in self.controls
            if not c["named"] and not (c["tag"] == "button" and c["words"].strip())
            and c["id"] not in self.labelled_ids
        ]


def test_every_control_says_what_it_is(client, a_page_of_everything):
    """A control with no name is read out as "edit text, blank" and nothing else,
    which on the drives grid was eight of them to a row. A column heading is not a
    name: nothing in HTML carries it from the `<th>` to the box underneath, so
    each box says which row and which column it is itself."""
    nameless = []
    for path in a_page_of_everything:
        page = client.get(path)
        assert page.status_code == 200, f"{path} did not render: {page.status_code}"
        parser = Controls()
        parser.feed(page.text)
        nameless += [f"{path}: {one}" for one in parser.unnamed()]
    assert nameless == [], "these controls are read out with nothing to say what they are: " + \
        "; ".join(nameless[:12])


def test_every_image_says_what_it_is_or_says_it_is_decoration(client, a_page_of_everything):
    """`alt=""` is an answer -- it tells a screen reader to pass over a swatch or a
    rule. A missing `alt` is not: it reads the filename out instead."""
    silent = []
    for path in a_page_of_everything:
        parser = Controls()
        parser.feed(client.get(path).text)
        silent += [f"{path}: {one}" for one in parser.images]
    assert silent == [], "these images have no alt at all: " + "; ".join(silent[:12])


def test_nothing_hides_where_the_keyboard_is():
    """The browser's own focus ring is what most of this site relies on, and one
    line of CSS anywhere would take it away everywhere it applies. There is one
    rule that does suppress it, deliberately: the skip link lands on `<main>`, and
    a ring drawn round the whole page says nothing -- the eye should be following
    the link. Anything else turning an outline off is the thing this asserts
    against, and has to justify itself here first."""
    css = STYLESHEET.read_text(encoding="utf-8")
    allowed = "main:focus"
    suppressed = [
        css[max(0, found.start() - 60) : found.start()].strip().splitlines()[-1]
        for found in re.finditer(r"outline:\s*(?:none|0)\b", css)
    ]
    assert [one for one in suppressed if allowed not in one] == [], (
        "these rules take the focus ring away: " + "; ".join(suppressed))
    assert re.search(r"main:focus\s*\{[^}]*outline:\s*none", css), (
        "the one allowed suppression has moved; this test is now guarding nothing")
