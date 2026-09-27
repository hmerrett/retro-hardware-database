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

import re
from html.parser import HTMLParser
from pathlib import Path

from test_stylesheet_lint import declarations

APP = Path(__file__).parents[1] / "app"
TEMPLATES = APP / "templates"
STATIC = APP / "static"
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
