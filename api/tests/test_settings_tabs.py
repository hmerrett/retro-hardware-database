"""One row of tabs across Settings and the account pages (MANUAL §19, "Settings").

Settings was one long form, reached beside two account pages by a line of links.
It is now five tabs, each a page of its own -- Appearance, Labels and Server, then
Accounts and Your account -- and each page's Save saves that page and nothing else.
The tabs are navigation, a `nav` of links with the current one marked as the page,
not a widget, and need no script."""

import re
from html.parser import HTMLParser
from pathlib import Path

import pytest

from conftest import as_viewer

COMPONENTS = Path(__file__).parents[1] / "app" / "static" / "css" / "components.css"
HTML = {"accept": "text/html"}
TABS = [
    ("/settings", "Appearance"),
    ("/settings/labels", "Labels"),
    ("/settings/server", "Server"),
    ("/settings/users", "Accounts"),
    ("/settings/account", "Your account"),
]


class Strip(HTMLParser):
    """The row of tabs: each link's address, words and whether it is the current page;
    and every place elsewhere on the page that is marked as the current page."""

    def __init__(self):
        super().__init__()
        self.tabs: list[list] = []
        self.label = ""
        self.depth = 0
        self.current_elsewhere: list[str] = []

    def handle_starttag(self, tag, attrs):
        a = dict(attrs)
        if tag == "nav" and "tabs" in (a.get("class") or "").split():
            self.depth, self.label = 1, a.get("aria-label") or ""
        elif self.depth and tag == "a":
            self.tabs.append([a.get("href"), "", a.get("aria-current") == "page"])
        elif a.get("aria-current") == "page" and not self.depth:
            self.current_elsewhere.append(a.get("href") or tag)

    def handle_endtag(self, tag):
        if tag == "nav" and self.depth:
            self.depth = 0

    def handle_data(self, data):
        if self.depth and self.tabs:
            self.tabs[-1][1] += data


def strip(client, path):
    s = Strip()
    s.feed(client.get(path, headers=HTML).text)
    return s


@pytest.mark.parametrize("path,name", TABS)
def test_settings_is_a_row_of_tabs_with_the_one_you_are_on_marked(client, path, name):
    s = strip(client, path)
    assert s.label, "the row of tabs has no name"
    assert [(href, " ".join(words.split())) for href, words, _ in s.tabs] == TABS
    assert [" ".join(words.split()) for _, words, current in s.tabs if current] == [name]


def test_each_section_is_a_page_of_its_own(client):
    def legends(path):
        return re.findall(r"<legend>([^<]+)</legend>", client.get(path, headers=HTML).text)

    sections = {"Appearance", "Labels", "Server options"}
    assert sections & set(legends("/settings")) == {"Appearance"}
    assert sections & set(legends("/settings/labels")) == {"Labels"}
    assert sections & set(legends("/settings/server")) == {"Server options"}
    assert 'id="device-box"' in client.get("/settings/labels", headers=HTML).text
    assert 'id="device-box"' not in client.get("/settings", headers=HTML).text


@pytest.mark.parametrize("path", ["/settings", "/settings/labels", "/settings/server"])
def test_each_page_saves_to_itself(client, path):
    page = client.get(path, headers=HTML).text
    assert f'action="{path}"' in page
    r = client.post(path, data={}, follow_redirects=False)
    assert r.status_code == 303 and r.headers["location"] == f"{path}?saved=1"


def test_saving_one_section_leaves_the_others_alone(client):
    client.post("/settings/server", data={"block_search_engines": "on"})
    client.post("/settings/labels", data={"label_destination": "print"})
    # Appearance's form carries no server tick; silence on its page is not "off".
    client.post("/settings", data={"site_name": "Henry's shelf"})
    server = client.get("/settings/server", headers=HTML).text
    assert re.search(r'name="block_search_engines"[^>]*checked', server)
    assert "Henry" in client.get("/settings", headers=HTML).text


def test_a_viewer_sees_no_row_of_tabs(client):
    as_viewer(client)
    s = strip(client, "/settings/account")
    assert s.tabs == []


def test_an_administrator_s_menus_offer_settings_and_mark_it_on_every_tab(client):
    for path, _ in TABS:
        page = client.get(path, headers=HTML).text
        assert 'href="/settings/account"' not in re.sub(
            r'<nav class="tabs".*?</nav>', "", page, flags=re.S
        ), path
        s = strip(client, path)
        assert set(s.current_elsewhere) == {"/settings"}, (path, s.current_elsewhere)


def test_a_viewer_s_menus_offer_account_and_mark_it(client):
    as_viewer(client)
    page = client.get("/settings/account", headers=HTML).text
    assert 'href="/settings"' not in page.replace('href="/settings/account"', "")
    assert set(strip(client, "/settings/account").current_elsewhere) == {"/settings/account"}


def css():
    return re.sub(r"/\*.*?\*/", "", COMPONENTS.read_text(encoding="utf-8"), flags=re.S)


def test_the_tab_you_are_on_is_bold_and_underlined_not_coloured_alone():
    rule = re.search(r'nav\.tabs a\[aria-current="page"\]\s*\{([^}]*)\}', css())
    assert rule and "font-weight: 600" in rule[1] and "inset 0 -3px 0" in rule[1]


def test_the_row_wraps_and_each_tab_is_a_thumb_s_height_on_a_touch_screen():
    assert re.search(r"nav\.tabs\s*\{[^}]*flex-wrap:\s*wrap", css())
    coarse = re.search(r"@media \(pointer: coarse\) \{(.*?)\n  \}", css(), re.S)
    assert coarse and re.search(r"nav\.tabs a[^{]*\{[^}]*min-height:\s*var\(--tap\)", coarse[1])
