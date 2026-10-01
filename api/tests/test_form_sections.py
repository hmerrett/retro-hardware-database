"""The sections of a long form, listed at its top (MANUAL: "Adding a computer",
"Adding a part", "When a save is refused").

The machine and part forms run to several screens even on a wide one. Rather than
tabs, which would hide what is not showing and hide an error with it, the form
lists its sections at the top as links to them, and after a refused save says
beside each section how many things in it there are to fix. It is navigation, a
`nav` of links, and needs no script."""

import re
from html.parser import HTMLParser
from pathlib import Path

import pytest

COMPONENTS = Path(__file__).parents[1] / "app" / "static" / "css" / "components.css"


class Form(HTMLParser):
    """The list of sections (its links, in order, with any words beside them) and the
    form's fieldsets (their ids and legends, in order)."""

    def __init__(self):
        super().__init__()
        self.links: list[list[str]] = []
        self.fieldsets: list[dict[str, str]] = []
        self.in_nav = self.in_legend = False
        self.nav_label = ""

    def handle_starttag(self, tag, attrs):
        a = dict(attrs)
        if tag == "nav" and "formsections" in (a.get("class") or ""):
            self.in_nav, self.nav_label = True, a.get("aria-label") or ""
        elif tag == "a" and self.in_nav:
            self.links.append([a.get("href") or "", ""])
        elif tag == "fieldset":
            self.fieldsets.append({"id": a.get("id") or "", "legend": "", "hidden": "hidden" in a})
        elif tag == "legend" and self.fieldsets:
            self.in_legend = True

    def handle_endtag(self, tag):
        if tag == "nav":
            self.in_nav = False
        elif tag == "legend":
            self.in_legend = False

    def handle_data(self, data):
        if self.in_nav and self.links:
            self.links[-1][1] += data
        elif self.in_legend:
            self.fieldsets[-1]["legend"] += data


def read(html):
    form = Form()
    form.feed(html)
    return form


def words(text):
    return " ".join(text.split())


@pytest.fixture
def forms(client, computer, part):
    made = computer(model="PC1512")["asset_id"]
    card = part(type="sound", model="Sound Blaster")["asset_id"]
    return {
        "computer new": "/computers/new",
        "computer edit": f"/computers/{made}/edit",
        "part new": "/parts/new?type=storage",
        "part edit": f"/parts/{card}/edit",
    }


@pytest.mark.parametrize("which", ["computer new", "computer edit", "part new", "part edit"])
def test_the_form_lists_its_sections_at_the_top(client, forms, which):
    form = read(client.get(forms[which]).text)
    assert form.nav_label, "the list of sections has no name"
    named = [words(text) for _, text in form.links]
    assert named == [words(f["legend"]) for f in form.fieldsets if f["id"]]
    assert len(named) >= 5


@pytest.mark.parametrize("which", ["computer new", "computer edit", "part new", "part edit"])
def test_each_entry_is_a_link_to_its_section(client, forms, which):
    form = read(client.get(forms[which]).text)
    ids = [f["id"] for f in form.fieldsets]
    assert [href for href, _ in form.links] == [f"#{i}" for i in ids if i]
    assert len(set(ids) - {""}) == len([i for i in ids if i])


def test_without_script_every_section_shows(client, forms):
    for path in forms.values():
        assert not [f for f in read(client.get(path).text).fieldsets if f["hidden"]], path


def test_a_section_with_something_to_fix_is_marked_in_the_list(client):
    r = client.post(
        "/computers/new",
        data={"manufacturer": "Acme", "model": "Test", "year": "85", "acquired_date": "soon"},
        follow_redirects=False,
    )
    assert r.status_code == 400
    marked = {words(text) for _, text in read(r.text).links}
    assert "Identity 1 to fix" in marked
    assert "Tracking 1 to fix" in marked
    assert "Memory" in marked


def test_a_part_s_own_section_is_marked_too(client):
    r = client.post(
        "/parts/new",
        data={"type": "storage", "kind": "Hard disk", "model": "ST-225", "year": "85"},
        follow_redirects=False,
    )
    assert r.status_code == 400
    marked = {words(text) for _, text in read(r.text).links}
    assert {"Identity 1 to fix", "Storage 1 to fix"} <= marked, marked


def test_every_link_in_the_summary_lands_on_a_box_that_can_take_the_focus(client):
    r = client.post("/computers/new", data={"model": "Test", "year": "85"}, follow_redirects=False)
    for target in re.findall(r'<div class="errsum".*?</div>', r.text, re.S)[0].split('href="#')[1:]:
        key = target.split('"')[0]
        box = re.search(rf'<(input|select|textarea)[^>]*\bid="{re.escape(key)}"[^>]*>', r.text)
        assert box and "hidden" not in box.group(0) and 'type="hidden"' not in box.group(0), key


def test_an_entry_is_a_thumb_s_height_on_a_touch_screen():
    css = re.sub(r"/\*.*?\*/", "", COMPONENTS.read_text(encoding="utf-8"), flags=re.S)
    coarse = re.search(r"@media \(pointer: coarse\) \{(.*?)\n  \}", css, re.S)
    assert coarse and re.search(
        r"\.formsections a[^{]*\{[^}]*min-height:\s*var\(--tap\)", coarse.group(1)
    )
