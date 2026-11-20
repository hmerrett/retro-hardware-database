"""Every item on one page, as MANUAL.md section 2 promises it ("Every item on one
page"): the whole collection as one list at /items, by name, each line leading to
the item's page. Public, named in the sitemap, and the same on every visit, which is
what makes it the way a search engine is given to every item while the gallery's
shuffled pages are kept from crawlers.

The robots.txt promises are read the way a crawler reads the file rather than by
looking for a line in it: a rule that is there and does not match the addresses the
gallery writes would keep nothing from anybody.
"""

import html
import re

from app import entry
from app.routers import gallery
from conftest import content, log_out
from test_accounts import close_the_site

ITEM = r"(?:computers|parts)/RH-[0-9A-Z]{4}"


def row(page: str, aid: str) -> str:
    """The line of the list that names this tag, as markup."""
    (found,) = [r for r in re.findall(r"<tr>.*?</tr>", content(page), re.S) if f">{aid}<" in r]
    return found


def tags(page: str) -> list[str]:
    """The tags on the list, top to bottom."""
    return re.findall(r'class="aid" href="/(?:computers|parts)/(RH-[0-9A-Z]{4})"', content(page))


def disallowed(robots: str, url: str) -> bool:
    """Whether a crawler reading this robots.txt leaves `url` alone, as Google reads
    one: `*` is any run of characters, `$` is the end, the longest rule that matches
    wins, and Allow wins a tie. The file has one group, for every crawler."""
    best, verdict = "", "allow"
    for line in robots.splitlines():
        field, _, value = line.partition(":")
        field, rule = field.strip().lower(), value.strip()
        if field not in ("allow", "disallow") or not rule:
            continue
        body = "".join(".*" if ch == "*" else re.escape(ch) for ch in rule.removesuffix("$"))
        if not re.match(body + ("$" if rule.endswith("$") else ""), url):
            continue
        if len(rule) > len(best) or (len(rule) == len(best) and field == "allow"):
            best, verdict = rule, field
    return verdict == "disallow"


class TestTheList:
    def test_it_lists_every_computer_and_every_part(self, client, computer, part):
        made = [computer()["asset_id"], part()["asset_id"], part(type="video")["asset_id"]]
        assert sorted(tags(client.get("/items").text)) == sorted(made)

    def test_it_is_in_alphabetical_order_of_name(self, client, computer, part):
        """Whatever the case a name was typed in."""
        made = {
            computer(name="Commodore Amiga 500")["asset_id"]: "c",
            part(name="adaptec AHA-1542")["asset_id"]: "a",
            part(name="Boca Research IO/AT")["asset_id"]: "b",
        }
        assert [made[t] for t in tags(client.get("/items").text)] == ["a", "b", "c"]

    def test_each_line_is_the_tag_the_name_and_the_kind(self, client, computer, part):
        c = computer(name="Amstrad PC1512")["asset_id"]
        p = part(name="Trident TVGA8900", type="video")["asset_id"]
        page = client.get("/items").text
        assert f">{c}</a>" in row(page, c) and f">{p}</a>" in row(page, p)
        assert ">Amstrad PC1512</a>" in row(page, c) and ">Computer</td>" in row(page, c)
        assert ">Trident TVGA8900</a>" in row(page, p)
        assert f">{entry.type_label('video')}</td>" in row(page, p)

    def test_the_tag_and_the_name_both_lead_to_the_item_s_page(self, client, computer, part):
        c = computer()["asset_id"]
        p = part()["asset_id"]
        page = client.get("/items").text
        assert row(page, c).count(f'href="/computers/{c}"') == 2
        assert row(page, p).count(f'href="/parts/{p}"') == 2

    def test_a_disposed_item_is_listed_and_says_so(self, client, part):
        gone = part(name="Gone")["asset_id"]
        kept = part(name="Kept")["asset_id"]
        client.patch(f"/api/parts/{gone}", json={"disposed": True})
        page = client.get("/items").text
        assert "Disposed" in row(page, gone)
        assert "Disposed" not in row(page, kept)

    def test_there_are_no_pages_to_turn(self, client, computer, monkeypatch):
        """However many pages the gallery would spread them across."""
        monkeypatch.setattr(gallery, "PAGE_SIZE", 2)
        made = [computer()["asset_id"] for _ in range(5)]
        assert 'class="pager"' in client.get("/").text
        page = client.get("/items").text
        assert sorted(tags(page)) == sorted(made)
        assert 'class="pager"' not in page

    def test_it_names_no_project_and_no_location(self, client, part):
        """The register's one pool of tags holds both, and each has rules of its own
        about who is told it exists: a private project, Show locations. The list is
        of the two kinds whose pages anybody may open."""
        p = part()["asset_id"]
        made = client.post("/projects/new", data={"name": "Recap"}, follow_redirects=False)
        project = made.headers["location"].rsplit("/", 1)[-1]
        shelf = client.post("/api/locations", json={"name": "Shelf", "kind": "shelf"}).json()
        page = content(client.get("/items").text)
        assert p in page
        assert project not in page and shelf["asset_id"] not in page

    def test_the_gallery_leads_to_it(self, client, part):
        part()
        assert 'href="/items"' in content(client.get("/").text)


class TestWhoMayReadIt:
    def test_a_visitor_may(self, client, part):
        p = part()["asset_id"]
        log_out(client)
        page = client.get("/items")
        assert page.status_code == 200 and p in content(page.text)

    def test_a_site_closed_to_visitors_keeps_it_behind_the_login(self, client):
        close_the_site(client)
        log_out(client)
        r = client.get("/items", follow_redirects=False)
        assert r.status_code == 303 and r.headers["location"] == "/login?next=/items"


class TestTheWayInForSearchEngines:
    def test_it_is_named_in_the_sitemap(self, client):
        assert "<loc>https://example.test/items</loc>" in client.get("/sitemap.xml").text

    def test_it_lists_every_item_the_sitemap_names(self, client, computer, part):
        """The two lists of what a crawler may read are one list. An item page the
        sitemap names and nothing links to is a page the crawler has only been told
        about, which is the state most of the collection was found in."""
        computer()
        part()
        client.patch(f"/api/parts/{part()['asset_id']}", json={"disposed": True})
        named = set(re.findall(rf"/({ITEM})</loc>", client.get("/sitemap.xml").text))
        listed = set(re.findall(rf'href="/({ITEM})"', content(client.get("/items").text)))
        assert len(named) == 3 and listed == named

    def test_it_is_the_same_on_every_visit(self, client, computer, part):
        computer()
        for n in range(5):
            part(name=f"Part {n}")
        log_out(client)
        first, again = client.get("/items"), client.get("/items")
        assert first.status_code == 200 and len(tags(first.text)) == 6
        assert content(first.text) == content(again.text)

    def test_it_is_its_own_canonical(self, client):
        page = client.get("/items").text
        assert '<link rel="canonical" href="https://example.test/items">' in page
        assert '<meta name="robots" content="index, follow">' in page

    def test_a_crawler_is_let_in_to_it_and_to_everything_on_it(self, client, computer, part):
        computer()
        part()
        robots = client.get("/robots.txt").text
        listed = re.findall(rf'href="(/{ITEM})"', content(client.get("/items").text))
        assert listed
        for url in ["/items", *listed]:
            assert not disallowed(robots, url), url

    def test_a_crawler_is_asked_to_leave_the_shuffle_alone(self, client, computer, monkeypatch):
        """Every link the gallery makes back into itself carries the hand, and that
        is what robots.txt names. The front page is still let in: it is where the
        way to the list is."""
        monkeypatch.setattr(gallery, "PAGE_SIZE", 2)
        for _ in range(3):
            computer()
        log_out(client)
        robots = client.get("/robots.txt").text
        hrefs = re.findall(r'href="([^"]*)"', content(client.get("/").text))
        own = [html.unescape(h) for h in hrefs if h.startswith("/?")]
        assert own, "the gallery drew no links into itself to ask about"
        for url in own:
            assert "deal=" in url and disallowed(robots, url), url
        assert not disallowed(robots, "/")
