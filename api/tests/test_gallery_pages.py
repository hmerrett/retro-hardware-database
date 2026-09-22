"""The gallery's toolbar and pages, as MANUAL.md section 2 ("The gallery") promises
them: a GET form whose every view is a link, 48 cards a page with a pager, the
sorts done on the server, a shuffle that is dealt once and held, and the whole
list handed to the item pages' prev/next rather than the page on screen.

The page size is patched down to two here, so a handful of items makes several
pages; that the real size is 48 is its own test.
"""

import html
import json
import re

import pytest

from app.routers import gallery

CARD = re.compile(r'class="card(?: is-disposed)?" href="/(?:computers|parts)/([A-Z0-9-]+)"')


def cards(page: str) -> list[str]:
    return CARD.findall(page)


def links(page: str, rel: str) -> list[str]:
    return [html.unescape(h) for h in re.findall(rf'href="([^"]+)" rel="{rel}"', page)]


def handed_over(page: str) -> list[list[str]]:
    blob = re.search(r'<script type="application/json" id="index-data">(.*?)</script>', page, re.S)
    assert blob
    order: list[list[str]] = json.loads(blob.group(1))["order"]
    return order


@pytest.fixture
def two_a_page(monkeypatch):
    monkeypatch.setattr(gallery, "PAGE_SIZE", 2)


@pytest.fixture
def five(computer, two_a_page):
    """Five computers, named so that A-Z and asset order are both easy to state."""
    made = [computer(name=n, year=1980 + i) for i, n in enumerate("EDCBA")]
    return [c["asset_id"] for c in made]


class TestPages:
    def test_a_page_holds_48_cards(self):
        # Two, three and four across all fill their last row.
        assert gallery.PAGE_SIZE == 48

    def test_more_than_a_page_draws_the_pager(self, client, five):
        page = client.get("/?sort=aid").text
        assert len(cards(page)) == 2
        assert '<nav class="pager" aria-label="Pages">' in page
        assert "Page 1 of 3" in page
        assert links(page, "next") and not links(page, "prev")

    def test_one_page_draws_no_pager(self, client, computer):
        computer()
        assert 'class="pager"' not in client.get("/").text

    def test_the_pages_together_hold_every_item_once(self, client, five):
        seen = [aid for n in (1, 2, 3) for aid in cards(client.get(f"/?sort=aid&page={n}").text)]
        assert seen == sorted(five)

    def test_a_page_past_the_end_shows_the_last(self, client, five):
        page = client.get("/?sort=aid&page=99").text
        assert "Page 3 of 3" in page and cards(page) == sorted(five)[4:]

    def test_a_page_that_is_not_a_number_is_the_first(self, client, five):
        assert "Page 1 of 3" in client.get("/?sort=aid&page=two").text

    def test_the_figures_count_everything_not_just_the_page(self, client, five):
        assert "5 computers · 0 parts" in client.get("/").text

    def test_the_pager_carries_the_whole_view(self, client, five):
        page = client.get("/?cat=computer&sort=name&q=Acme").text
        (nxt,) = links(page, "next")
        assert nxt.startswith("/?") and nxt.endswith("&page=2")
        for part in ("cat=computer", "sort=name", "q=Acme", "disposed=0"):
            assert part in nxt, part

    def test_a_browse_page_keeps_its_own_view_through_the_pager(self, client, part, two_a_page):
        for _ in range(3):
            part(model="gone", disposed=True)
        (nxt,) = links(client.get("/browse?f=disposed").text, "next")
        assert nxt.startswith("/browse?f=disposed&v=") and "disposed=1" in nxt


class TestTheToolbar:
    def test_it_is_a_form_that_submits_with_get(self, client, computer):
        computer()
        page = client.get("/").text
        assert '<form class="toolbar" method="get" action="/"' in page

    def test_apply_is_there_for_a_browser_running_no_script(self, client, computer):
        computer()
        assert '<button class="btn sm" type="submit">Apply</button>' in client.get("/").text

    def test_the_view_in_the_link_is_the_view_the_menus_show(self, client, computer):
        computer()
        page = client.get("/?cat=computer&sort=name&disposed=1").text
        assert '<option value="computer" selected>' in page
        assert '<option value="name" selected>' in page
        assert 'id="showdisposed" name="disposed" value="1" checked>' in page

    def test_a_search_is_kept_when_the_menus_change(self, client, computer):
        computer()
        assert '<input type="hidden" name="q" value="Acme">' in client.get("/?q=Acme").text

    def test_a_browse_view_keeps_its_figure_when_the_menus_change(self, client, part):
        part(model="gone", disposed=True)
        page = client.get("/browse?f=disposed").text
        assert '<form class="toolbar" method="get" action="/browse"' in page
        assert '<input type="hidden" name="f" value="disposed">' in page

    def test_the_shortlist_submits_to_itself(self, client, computer):
        aid = computer()["asset_id"]
        client.post(f"/computers/{aid}/for-sale", data={"for_sale": "1"})
        assert 'action="/for-sale"' in client.get("/for-sale").text


class TestFilters:
    def test_a_category_keeps_to_its_kind(self, client, computer, part):
        c = computer()["asset_id"]
        part(model="card")
        assert cards(client.get("/?cat=computer").text) == [c]

    def test_a_category_the_page_does_not_offer_is_ignored(self, client, computer):
        c = computer()["asset_id"]
        assert cards(client.get("/?cat=nonsense").text) == [c]

    def test_disposed_items_are_hidden_on_the_gallery_by_default(self, client, computer):
        computer(disposed=True)
        kept = computer()["asset_id"]
        assert cards(client.get("/").text) == [kept]

    def test_the_box_shows_them(self, client, computer):
        gone = computer(disposed=True)["asset_id"]
        assert gone in cards(client.get("/?disposed=1").text)

    def test_a_submitted_form_without_the_box_hides_them_on_a_browse_page(self, client, part):
        # An unticked box sends nothing, so the sort that every submission carries
        # is what says the form was used rather than the page just arrived at.
        part(model="gone", disposed=True)
        assert cards(client.get("/browse?f=disposed&sort=aid").text) == []

    def test_held_back_items_are_counted_as_a_fraction(self, client, computer):
        computer(disposed=True)
        computer()
        assert "(showing 1 of 2)" in client.get("/").text

    def test_nothing_held_back_says_nothing(self, client, computer):
        computer()
        assert "showing" not in client.get("/").text

    def test_no_match_says_so(self, client, computer):
        computer(disposed=True)
        assert '<p id="empty" class="muted">No matching items.</p>' in client.get("/").text


class TestSorts:
    """The rules index.js used to apply in the browser, applied to the rows."""

    @staticmethod
    def row(aid, **over):
        class Obj:
            asset_id = aid

        base = {
            "image": "",
            "updated": "",
            "added": "",
            "acquired": "",
            "year": "",
            "name": aid,
            "maker": "",
            "catsort": 0,
        }
        return {"obj": Obj(), **base, **over}

    def ids(self, rows):
        return [r["obj"].asset_id for r in rows]

    def test_name_is_a_to_z_ignoring_case(self):
        rows = [self.row("1", name="beta"), self.row("2", name="Alpha")]
        assert self.ids(gallery.order(rows, "name", 0)) == ["2", "1"]

    def test_recently_updated_puts_photographs_first(self):
        rows = [
            self.row("1", updated="2026-09-02"),
            self.row("2", updated="2026-09-01", image="x.jpg"),
        ]
        assert self.ids(gallery.order(rows, "updated", 0)) == ["2", "1"]

    def test_recently_updated_is_newest_first_and_keeps_the_order_of_a_tie(self):
        rows = [
            self.row(a, updated=u)
            for a, u in (("1", "2026-09-01"), ("2", "2026-09-03"), ("3", "2026-09-01"))
        ]
        assert self.ids(gallery.order(rows, "updated", 0)) == ["2", "1", "3"]

    def test_undated_items_go_last_both_ways_round(self):
        rows = [self.row("1"), self.row("2", year=1982), self.row("3", year=1990)]
        assert self.ids(gallery.order(rows, "yearnew", 0)) == ["3", "2", "1"]
        assert self.ids(gallery.order(rows, "yearold", 0)) == ["2", "3", "1"]

    def test_maker_is_a_to_z_with_the_name_settling_a_tie(self):
        rows = [
            self.row("1", maker="ibm", name="b"),
            self.row("2", maker="acorn"),
            self.row("3", maker="ibm", name="a"),
            self.row("4"),
        ]
        assert self.ids(gallery.order(rows, "maker", 0)) == ["2", "3", "1", "4"]

    def test_category_follows_the_catalogue_order(self):
        rows = [self.row("1", catsort=3), self.row("2", catsort=0)]
        assert self.ids(gallery.order(rows, "cat", 0)) == ["2", "1"]

    def test_asset_number(self):
        rows = [self.row("RH-B"), self.row("RH-A")]
        assert self.ids(gallery.order(rows, "aid", 0)) == ["RH-A", "RH-B"]

    def test_random_puts_photographs_first(self):
        rows = [self.row(str(i)) for i in range(20)] + [self.row("p", image="x.jpg")]
        assert self.ids(gallery.order(rows, "random", 7))[0] == "p"

    def test_the_same_deal_is_the_same_shuffle(self):
        rows = [self.row(str(i)) for i in range(20)]
        assert gallery.order(rows, "random", 7) == gallery.order(rows[::-1], "random", 7)

    def test_a_different_deal_is_a_different_shuffle(self):
        rows = [self.row(str(i)) for i in range(20)]
        assert gallery.order(rows, "random", 7) != gallery.order(rows, "random", 8)

    def test_filtering_keeps_each_item_where_the_hand_put_it(self):
        rows = [self.row(str(i)) for i in range(20)]
        whole = self.ids(gallery.order(rows, "random", 7))
        some = self.ids(gallery.order(rows[::2], "random", 7))
        assert some == [a for a in whole if a in some]


class TestTheDeal:
    def test_arriving_on_random_deals_a_hand_and_the_pager_carries_it(self, client, five):
        (nxt,) = links(client.get("/").text, "next")
        deal = re.search(r"deal=(\d+)", nxt)
        assert deal and "sort=random" in nxt
        first = cards(client.get(f"/?sort=random&deal={deal.group(1)}").text)
        rest = [
            aid
            for n in (2, 3)
            for aid in cards(client.get(f"/?sort=random&deal={deal.group(1)}&page={n}").text)
        ]
        assert sorted(first + rest) == sorted(five)

    def test_the_hand_is_kept_when_the_menus_change(self, client, five):
        page = client.get("/?sort=random&deal=42").text
        assert '<input type="hidden" name="deal" value="42">' in page

    def test_another_sort_carries_no_hand(self, client, five):
        page = client.get("/?sort=name&deal=42").text
        assert 'name="deal"' not in page and "deal=" not in "".join(links(page, "next"))


class TestTheSortCookie:
    def test_a_link_with_no_sort_opens_in_the_one_last_chosen(self, client, five):
        client.cookies.set("rhdb_sort", "name")
        assert cards(client.get("/").text) == five[::-1][:2]

    def test_the_link_outranks_the_cookie(self, client, five):
        client.cookies.set("rhdb_sort", "name")
        assert cards(client.get("/?sort=aid").text) == sorted(five)[:2]


class TestTheHandOff:
    def test_prev_and_next_are_handed_every_page_of_the_list(self, client, five):
        order = handed_over(client.get("/?sort=aid").text)
        assert [p for p, _ in order] == [f"/computers/{a}" for a in sorted(five)]

    def test_each_is_handed_over_under_the_name_on_its_card(self, client, computer):
        computer(name="Big Box")
        assert handed_over(client.get("/").text)[0][1] == "Big Box"
