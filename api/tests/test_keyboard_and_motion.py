"""What the manual promises a keyboard, a screen reader and a reduced-motion
setting (MANUAL.md, "Using it from the keyboard").

Three gaps that no single change surfaces: a skip link is invisible until it has
focus, a missing `scope` reads correctly to everyone who can see the table, and
motion is only wrong for the people who asked for less of it. So they are checked
against the markup and the stylesheet themselves, the way test_stylesheet.py
checks declarations rather than pages.
"""
import re
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
