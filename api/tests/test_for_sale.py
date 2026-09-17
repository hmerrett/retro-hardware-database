"""The for-sale shortlist (ADR-0018): might go, and nobody but the owner sees it.

Between keeping a thing and having disposed of it there is "this one could go".
The flag is four lines; what these tests are really about is the half of privacy
that is easy to miss. A column kept off the page is still in the search, because
_haystack reads every column off the model -- so most of what follows is about
where a boolean shows up when nobody decided it should.
"""

import pytest

from app import main
from app.models import Computer, Part


def visitor(monkeypatch):
    """Turn the site into what an anonymous reader sees."""
    monkeypatch.setattr(main.auth, "AUTH_ENABLED", True)


def flag(client, kind, aid, on=True):
    """Tick or untick, the way the page does."""
    data = {"for_sale": "1"} if on else {}
    r = client.post(f"/{kind}/{aid}/for-sale", data=data, follow_redirects=False)
    assert r.status_code == 303, r.text
    return r


class TestTickingAnItem:
    def test_an_item_starts_unflagged(self, client, db, part, computer):
        """A fresh install has never thought about selling anything."""
        assert db.get(Part, part()["asset_id"]).for_sale is False
        assert db.get(Computer, computer()["asset_id"]).for_sale is False

    @pytest.mark.parametrize("kind,model", [("parts", Part), ("computers", Computer)])
    def test_the_tick_sets_it_and_unticking_takes_it_back(
        self, client, db, part, computer, kind, model
    ):
        aid = (part() if kind == "parts" else computer())["asset_id"]
        flag(client, kind, aid)
        db.expire_all()
        assert db.get(model, aid).for_sale is True
        flag(client, kind, aid, on=False)
        db.expire_all()
        assert db.get(model, aid).for_sale is False

    def test_an_unticked_box_sends_nothing_and_that_means_no(self, client, db, part):
        """The one form control whose off state has to be read from its silence --
        the same reading files.public already takes of the same gesture."""
        aid = part()["asset_id"]
        flag(client, "parts", aid)
        client.post(f"/parts/{aid}/for-sale", data={}, follow_redirects=False)
        db.expire_all()
        assert db.get(Part, aid).for_sale is False

    def test_the_tick_comes_back_to_the_item(self, client, part):
        aid = part()["asset_id"]
        r = flag(client, "parts", aid)
        assert r.headers["location"] == f"/parts/{aid}"

    def test_ticking_something_that_is_not_there_is_a_404(self, client):
        assert client.post("/parts/RH-9999/for-sale", data={"for_sale": "1"}).status_code == 404


class TestTheShortlist:
    def test_it_lists_what_is_ticked_and_nothing_else(self, client, part):
        kept = part(model="Keeping")["asset_id"]
        going = part(model="Going")["asset_id"]
        flag(client, "parts", going)
        page = client.get("/for-sale").text
        assert going in page
        assert kept not in page

    def test_it_holds_machines_and_parts_together(self, client, part, computer):
        p, c = part(model="Card")["asset_id"], computer(model="Tower")["asset_id"]
        flag(client, "parts", p)
        flag(client, "computers", c)
        page = client.get("/for-sale").text
        assert p in page and c in page

    def test_an_empty_shortlist_says_so_rather_than_erroring(self, client, part):
        part()
        assert client.get("/for-sale").status_code == 200

    def test_it_is_kept_out_of_the_index(self, client, part):
        """A private page is not one a crawler should be told about, and the card a
        link to it previews as is the site's own -- there is nothing to advertise."""
        flag(client, "parts", part()["asset_id"])
        page = client.get("/for-sale").text
        assert 'name="robots" content="noindex' in page
        assert "/static/og-image.png" in page


class TestNobodyElseSeesIt:
    """Owner-only everywhere, and everywhere is the decision (ADR-0018)."""

    def test_the_shortlist_asks_a_visitor_to_log_in(self, client, part, monkeypatch):
        flag(client, "parts", part()["asset_id"])
        visitor(monkeypatch)
        r = client.get("/for-sale", follow_redirects=False)
        assert r.status_code == 303
        assert r.headers["location"].startswith("/login?next=")

    def test_a_visitor_cannot_tick_one(self, client, part, monkeypatch):
        aid = part()["asset_id"]
        visitor(monkeypatch)
        r = client.post(f"/parts/{aid}/for-sale", data={"for_sale": "1"}, follow_redirects=False)
        assert r.status_code == 303
        assert r.headers["location"].startswith("/login?next=")

    def test_the_item_page_shows_a_visitor_neither_tick_nor_marker(self, client, part, monkeypatch):
        aid = part()["asset_id"]
        flag(client, "parts", aid)
        assert "for-sale" in client.get(f"/parts/{aid}").text, "the owner sees it"
        visitor(monkeypatch)
        page = client.get(f"/parts/{aid}").text
        assert "for-sale" not in page
        assert "might sell" not in page.lower()

    def test_a_visitors_search_does_not_match_on_it(self, client, part, monkeypatch):
        """The one that would have gone unnoticed. _haystack reads every column off
        the model, so a boolean column joins the anonymous search by existing: a
        stranger searching "true" was handed the whole shortlist off a page that
        shows no such thing."""
        flagged = part(model="Flagged")["asset_id"]
        flag(client, "parts", flagged)
        visitor(monkeypatch)
        assert flagged not in client.get("/?q=true").text
        assert flagged not in client.get("/suggest?q=true").text

    def test_the_owners_search_does_match_on_it(self, client, part):
        """The other direction, so the fix is a rule about who is asking rather than
        a column quietly dropped from the search for everybody."""
        flagged = part(model="Flagged")["asset_id"]
        flag(client, "parts", flagged)
        assert flagged in client.get("/?q=true").text

    def test_the_flag_is_not_in_the_json_api(self, client, part):
        """It is set where the decision is made, so nothing carries it to a caller
        -- which also leaves the pinned contract (ADR-0010) alone."""
        aid = part()["asset_id"]
        flag(client, "parts", aid)
        assert "for_sale" not in client.get(f"/api/parts/{aid}").text
        assert "for_sale" not in client.get("/api/parts").text

    def test_the_gallery_card_does_not_carry_it(self, client, part, monkeypatch):
        """The cards hold a condensed blob for the type-ahead filter. It is built
        from named fields, and this is not one of them."""
        aid = part(model="Flagged")["asset_id"]
        flag(client, "parts", aid)
        visitor(monkeypatch)
        assert "for_sale" not in client.get("/").text


class TestTheNamedSetRatherThanAHabit:
    """The actual deliverable: the next owner-only column has somewhere to go, and
    a test holds the haystack to it."""

    def test_the_haystack_leaves_out_every_owner_only_column_for_a_visitor(self, db, part):
        from app.common import OWNER_ONLY
        from app.models import Part
        from app.search import _haystack

        aid = part()["asset_id"]
        row = db.get(Part, aid)
        for name in OWNER_ONLY:
            setattr(row, name, True)
        db.commit()
        assert OWNER_ONLY, "the set is the mechanism; an empty one tests nothing"
        assert "true" not in _haystack(db, row, {}, authed=False)
        assert "true" in _haystack(db, row, {}, authed=True)

    def test_for_sale_is_in_the_set(self):
        from app.common import OWNER_ONLY

        assert "for_sale" in OWNER_ONLY

    def test_an_unflagged_item_reads_identically_for_both(self, db, part):
        """The owner-only columns are blanked, not dropped, so who is asking changes
        what the haystack says and never how many fields it has. Otherwise the two
        strings differ for every item in the register, flagged or not, and the seams
        a quoted phrase must not match across move depending on the reader."""
        from app.models import Part
        from app.search import _haystack

        row = db.get(Part, part()["asset_id"])
        assert _haystack(db, row, {}, authed=False) == _haystack(db, row, {}, authed=True)


class TestItSurvivesTheRestOfTheSite:
    def test_disposing_a_flagged_item_leaves_the_flag_alone(self, client, db, part):
        """Two different facts. Something can be on its way out and also sold, and
        the shortlist is the owner's note to themselves either way."""
        aid = part()["asset_id"]
        flag(client, "parts", aid)
        client.post(
            f"/parts/{aid}/dispose",
            data={"note": "sold", "date": "2026-01-01"},
            follow_redirects=False,
        )
        db.expire_all()
        row = db.get(Part, aid)
        assert row.disposed is True and row.for_sale is True

    def test_the_decision_is_written_down(self):
        from pathlib import Path

        root = Path(__file__).parents[2]
        assert (root / "adr" / "0018-a-sale-flag-is-the-owners-alone.md").exists()
        assert "0018" in (root / "adr" / "README.md").read_text(encoding="utf-8")
        assert "ADR-0018" in (root / "docs" / "architecture.md").read_text(encoding="utf-8")
