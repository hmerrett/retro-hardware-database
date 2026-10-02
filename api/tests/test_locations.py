"""Where a thing is kept (MANUAL §5 "Where it is kept"; ADR-0027, ADR-0034).

The register has always said what a thing is and where it came from; this is where
it is now. A machine or a part is kept in a location -- a record of its own since
ADR-0034, with tests of its own in test_storage_locations.py -- and the switch Show
locations decides whether a visitor is told.

What is held here is the half that is easy to get wrong: a part with no location of
its own is wherever what it is fitted in is, and a location kept off the page is
still kept out of the search.
"""

from pathlib import Path

import pytest

from app import settings
from app.models import Computer, Part
from conftest import content, log_out

CRATE = "Loft, blue crate 3"


def visitor(client):
    """Turn the site into what an anonymous reader sees."""
    log_out(client)


def save(client, **fields):
    """Post the Server tab the way the page does: an unticked box sends nothing,
    which is how a switch is turned off."""
    data = {k: v for k, v in fields.items() if v is not None}
    r = client.post("/settings/server", data=data, follow_redirects=False)
    assert r.status_code == 303, r.text
    return r


class TestRecordingWhereSomethingIs:
    """The box itself: it holds a location, on either kind of thing, whichever door
    the answer came in by."""

    def test_a_machine_records_one_and_shows_it(self, client, computer):
        aid = computer(location=CRATE)["asset_id"]
        assert client.get(f"/api/computers/{aid}").json()["location_path"] == CRATE
        assert CRATE in client.get(f"/computers/{aid}").text

    def test_a_part_does_too(self, client, part):
        aid = part(location="Garage shelf B")["asset_id"]
        assert client.get(f"/api/parts/{aid}").json()["location_path"] == "Garage shelf B"
        assert "Garage shelf B" in client.get(f"/parts/{aid}").text

    def test_an_item_starts_with_nowhere_recorded(self, client, db, computer, part):
        """Nothing is inferred. A register that has never been told where anything
        is says so rather than guessing."""
        assert db.get(Computer, computer()["asset_id"]).location_id is None
        assert db.get(Part, part()["asset_id"]).location_id is None

    def test_the_machine_form_saves_one(self, client, computer):
        aid = computer()["asset_id"]
        client.post(
            f"/computers/{aid}/edit",
            data={"manufacturer": "Acme", "model": "Test", "location": CRATE},
            follow_redirects=False,
        )
        assert client.get(f"/api/computers/{aid}").json()["location_path"] == CRATE

    def test_the_part_form_saves_one(self, client, part):
        aid = part()["asset_id"]
        client.post(
            f"/parts/{aid}/edit",
            data={"type": "other", "model": "Widget", "location": "Under the bench"},
            follow_redirects=False,
        )
        assert client.get(f"/api/parts/{aid}").json()["location_path"] == "Under the bench"

    @pytest.mark.parametrize(
        "kind,extra", [("computers", {"model": "Test"}), ("parts", {"type": "other"})]
    )
    def test_the_form_can_take_it_back_off(self, client, computer, part, kind, extra):
        """Things move out of a crate as well as into one, and a place that is no
        longer true is worse than none."""
        aid = (computer(location=CRATE) if kind == "computers" else part(location=CRATE))[
            "asset_id"
        ]
        client.post(f"/{kind}/{aid}/edit", data=extra | {"location": ""}, follow_redirects=False)
        assert client.get(f"/api/{kind}/{aid}").json()["location"] == ""

    @pytest.mark.parametrize("kind", ["computers", "parts"])
    def test_a_duplicate_does_not_carry_it_across(self, client, computer, part, kind):
        """A duplicate copies what describes the model, not where this one sits. A
        second card is not in the same slot, and it is not in the same crate."""
        made = computer(location=CRATE) if kind == "computers" else part(location=CRATE)
        copy = (
            client.post(f"/{kind}/{made['asset_id']}/duplicate", follow_redirects=False)
            .headers["location"]
            .rsplit("/", 1)[-1]
        )
        assert client.get(f"/api/{kind}/{copy}").json()["location"] == ""

    def test_a_parts_own_answer_stands_beside_where_it_is_installed(self, client, computer, part):
        """The card-in-a-drawer case. Two rows, because a part can be fitted in a
        machine and still be kept somewhere else -- a board out on the bench is
        still the board out of that machine."""
        cid = computer(location="Loft")["asset_id"]
        pid = part(computer_id=cid, location="Spares drawer")["asset_id"]
        page = content(client.get(f"/parts/{pid}").text)
        assert "<dt>Location</dt>" in page
        assert "Spares drawer" in page
        assert "Loft" not in page, "its own answer wins over the one it is offered"
        assert "Fitted in" in page and cid in page


class TestAPartIsWhereWhatItIsFittedInIs:
    """A part fitted in a machine is wherever that machine is, so most parts never
    need the box filled in at all. Worked out at the moment it is shown and never
    written down, which is what makes carrying the machine upstairs one edit."""

    def test_a_part_in_a_machine_is_shown_the_machines_location(self, client, computer, part):
        cid = computer(location=CRATE)["asset_id"]
        pid = part(computer_id=cid)["asset_id"]
        page = client.get(f"/parts/{pid}").text
        assert "<dt>Location</dt>" in page
        assert CRATE in page

    def test_the_page_says_whose_answer_it_is_showing(self, client, computer, part):
        """Otherwise it reads as something somebody chose for this part, and the
        first thing anybody would do about a wrong one is edit the part -- which is
        the one record that cannot fix it."""
        cid = computer(location=CRATE)["asset_id"]
        pid = part(computer_id=cid)["asset_id"]
        page = client.get(f"/parts/{pid}").text
        assert f'where <a href="/computers/{cid}">{cid}</a> is' in page

    def test_a_chip_on_a_board_in_a_machine_is_in_the_machine(self, client, computer, part):
        """The chain runs as far as it has to."""
        cid = computer(location=CRATE)["asset_id"]
        board = part(type="motherboard", computer_id=cid)["asset_id"]
        chip = part(type="cpu", parent_id=board)["asset_id"]
        assert CRATE in client.get(f"/parts/{chip}").text

    def test_what_it_is_mounted_on_answers_before_what_it_is_installed_in(
        self, client, computer, part
    ):
        """A chip on a board is where the board is, even when the machine the board
        is in says something else: the nearer answer is the more specific one, and
        a board out on the bench has its own parts on the bench with it."""
        cid = computer(location="Loft")["asset_id"]
        board = part(type="motherboard", location="On the bench")["asset_id"]
        chip = part(type="cpu", parent_id=board, computer_id=cid)["asset_id"]
        page = content(client.get(f"/parts/{chip}").text)
        assert "On the bench" in page
        assert "Loft" not in page

    def test_a_part_that_says_for_itself_is_not_given_an_answer(self, client, computer, part):
        cid = computer(location=CRATE)["asset_id"]
        pid = part(computer_id=cid, location="Spares drawer")["asset_id"]
        page = content(client.get(f"/parts/{pid}").text)
        assert "Spares drawer" in page
        assert "blue crate 3" not in page

    def test_clearing_the_box_hands_the_part_back_to_its_machine(self, client, computer, part):
        """The way round the manual promises: choose an answer and it wins, take it
        out and the part follows what it is fitted in again."""
        cid = computer(location=CRATE)["asset_id"]
        pid = part(computer_id=cid, location="Spares drawer")["asset_id"]
        client.patch(f"/api/parts/{pid}", json={"location": ""})
        assert CRATE in client.get(f"/parts/{pid}").text

    def test_a_standalone_part_is_shown_nothing(self, client, part):
        page = client.get(f"/parts/{part()['asset_id']}").text
        assert "<dt>Location</dt>" not in page

    def test_a_part_in_a_machine_nobody_has_placed_is_shown_nothing(self, client, computer, part):
        """A chain that runs out yields nothing rather than an empty row. A part in
        a machine nobody has placed is a part nobody has placed."""
        cid = computer()["asset_id"]
        pid = part(computer_id=cid)["asset_id"]
        page = client.get(f"/parts/{pid}").text
        assert "<dt>Location</dt>" not in page

    def test_moving_the_machine_moves_everything_in_it(self, client, computer, part):
        """One edit, because nothing was written against the parts to go stale."""
        cid = computer(location=CRATE)["asset_id"]
        pid = part(computer_id=cid)["asset_id"]
        client.patch(f"/api/computers/{cid}", json={"location": "Garage shelf B"})
        assert "Garage shelf B" in client.get(f"/parts/{pid}").text

    def test_an_inherited_answer_is_not_written_to_the_part(self, client, computer, part):
        """Derived, and the column is the evidence: nothing stored means nothing to
        correct when the machine moves."""
        cid = computer(location=CRATE)["asset_id"]
        pid = part(computer_id=cid)["asset_id"]
        assert client.get(f"/api/parts/{pid}").json()["location"] == ""

    def test_a_part_mounted_on_itself_does_not_hang_the_page(self, client, db, part):
        """Nothing in the register can build one -- the forms do not offer it -- but
        a walk that trusts that is a page that never finishes loading if one ever
        exists."""
        a = part(type="other")["asset_id"]
        b = part(type="other", parent_id=a)["asset_id"]
        db.get(Part, a).parent_id = b
        db.commit()
        assert client.get(f"/parts/{a}").status_code == 200
        assert client.get(f"/parts/{b}").status_code == 200
        assert client.get("/?q=anything").status_code == 200


class TestWhoIsToldWhereThingsAre:
    """Off by default, because a public page saying which loft the rare machine is
    in is an address as much as a description."""

    def test_a_site_keeps_locations_to_itself_by_default(self, client):
        assert settings.on("public_locations") is False

    @pytest.mark.parametrize("kind", ["computers", "parts"])
    def test_a_visitor_is_shown_no_location_row(self, client, computer, part, kind):
        aid = (computer(location=CRATE) if kind == "computers" else part(location=CRATE))[
            "asset_id"
        ]
        assert CRATE in client.get(f"/{kind}/{aid}").text, "the owner sees it"
        visitor(client)
        page = client.get(f"/{kind}/{aid}").text
        assert CRATE not in page
        assert "<dt>Location</dt>" not in page

    def test_a_visitors_search_does_not_match_on_it(self, client, computer):
        """The half that is easy to miss. _haystack reads every column off the
        model, so a column kept off the page joins the anonymous search by merely
        existing -- and a stranger searching "loft" would be handed the list of what
        is in yours."""
        aid = computer(location=CRATE)["asset_id"]
        visitor(client)
        assert aid not in client.get("/?q=loft").text
        assert aid not in client.get("/suggest?q=loft").text

    def test_the_owners_search_does_match_on_it(self, client, computer):
        """The other direction, so what is private is a rule about who is asking
        rather than a column quietly dropped from the search for everybody."""
        aid = computer(location=CRATE)["asset_id"]
        assert aid in client.get("/?q=loft").text

    @pytest.mark.parametrize("who", ["owner", "visitor"])
    def test_the_gallery_carries_it_to_nobody(self, client, computer, who):
        """A card says where nothing is kept, owner included: the tiles are a wall
        of photographs, and the table is where the owner looks for that."""
        computer(location=CRATE)
        if who == "visitor":
            visitor(client)
        assert "blue crate 3" not in client.get("/").text

    @pytest.mark.parametrize("kind", ["computers", "parts"])
    def test_turning_it_on_shows_a_visitor_the_row(self, client, computer, part, kind):
        aid = (computer(location=CRATE) if kind == "computers" else part(location=CRATE))[
            "asset_id"
        ]
        save(client, public_locations="1")
        visitor(client)
        assert CRATE in client.get(f"/{kind}/{aid}").text

    def test_turning_it_on_lets_a_visitor_search_on_it(self, client, computer):
        aid = computer(location=CRATE)["asset_id"]
        save(client, public_locations="1")
        visitor(client)
        assert aid in client.get("/?q=loft").text

    def test_a_visitor_is_shown_no_inherited_location_either(self, client, computer, part):
        """The gate is on the answer and not on the column, or a part would publish
        what its machine keeps back."""
        cid = computer(location=CRATE)["asset_id"]
        pid = part(computer_id=cid)["asset_id"]
        assert CRATE in client.get(f"/parts/{pid}").text, "the owner sees it"
        visitor(client)
        page = client.get(f"/parts/{pid}").text
        assert CRATE not in page
        assert "<dt>Location</dt>" not in page

    def test_a_visitors_search_does_not_match_on_an_inherited_one(self, client, computer, part):
        cid = computer(location=CRATE)["asset_id"]
        pid = part(computer_id=cid)["asset_id"]
        visitor(client)
        assert pid not in content(client.get("/?q=loft").text)
        assert pid not in client.get("/suggest?q=loft").text

    def test_turning_it_on_shows_and_finds_an_inherited_one(self, client, computer, part):
        cid = computer(location=CRATE)["asset_id"]
        pid = part(computer_id=cid)["asset_id"]
        save(client, public_locations="1")
        visitor(client)
        assert CRATE in client.get(f"/parts/{pid}").text
        assert pid in client.get("/?q=loft").text

    def test_the_owner_is_shown_it_either_way(self, client, computer):
        aid = computer(location=CRATE)["asset_id"]
        assert CRATE in client.get(f"/computers/{aid}").text
        save(client, public_locations="1")
        assert CRATE in client.get(f"/computers/{aid}").text

    def test_the_pick_list_is_never_offered_to_a_visitor(self, client, computer):
        """Whichever way the switch is set. The list is on the forms, and the forms
        are behind the login -- a page of everywhere the collection keeps anything
        is a different disclosure from one item's own row."""
        computer(location=CRATE)
        cid = computer()["asset_id"]
        save(client, public_locations="1")
        visitor(client)
        assert "dl_locations" not in client.get(f"/computers/{cid}").text


class TestFindingWhatIsInThere:
    """A search for the loft finds what is in the loft, which is the machine and
    everything fitted in it. The page says the word; the search has to know it."""

    def test_an_installed_part_is_found_by_its_machines_location(self, client, computer, part):
        cid = computer(location=CRATE)["asset_id"]
        pid = part(computer_id=cid, model="Inside")["asset_id"]
        page = client.get("/?q=loft").text
        assert cid in page and pid in page

    def test_the_suggestion_list_agrees_with_the_search(self, client, computer, part):
        """The two are meant to be one answer seen twice, so a part findable in one
        and not the other is the pair disagreeing."""
        cid = computer(location=CRATE)["asset_id"]
        pid = part(computer_id=cid)["asset_id"]
        assert pid in client.get("/suggest?q=loft").text

    def test_a_chip_deep_in_a_machine_is_found_too(self, client, computer, part):
        cid = computer(location=CRATE)["asset_id"]
        board = part(type="motherboard", computer_id=cid)["asset_id"]
        chip = part(type="cpu", parent_id=board)["asset_id"]
        assert chip in client.get("/?q=loft").text

    def test_a_part_kept_somewhere_else_is_not_found_by_its_machines_location(
        self, client, computer, part
    ):
        """It is not there, and the page does not say it is."""
        cid = computer(location=CRATE)["asset_id"]
        pid = part(computer_id=cid, location="Spares drawer")["asset_id"]
        assert pid not in content(client.get("/?q=loft").text)

    @pytest.mark.parametrize("who", ["owner", "visitor"])
    def test_no_card_carries_the_inherited_answer_either(self, client, computer, part, who):
        """The inherited answer is findable by searching for it, which the tests
        above hold; what it is not is written into the gallery's markup."""
        cid = computer(location=CRATE)["asset_id"]
        part(computer_id=cid)
        if who == "visitor":
            visitor(client)
        assert "blue crate 3" not in client.get("/").text


class TestTheHiddenColumnsAreAskedForRatherThanAssumed:
    """The mechanism, held to directly: OWNER_ONLY is one answer to "what may this
    reader not search on", and no longer the whole of it."""

    def test_a_setting_gated_column_joins_the_owner_only_ones_for_a_visitor(self, client):
        from app.common import OWNER_ONLY
        from app.search import _hidden_columns

        assert _hidden_columns(authed=True) == frozenset()
        assert "location_id" in _hidden_columns(authed=False)
        assert _hidden_columns(authed=False) >= OWNER_ONLY

    def test_turning_the_setting_on_takes_it_back_out(self, client):
        from app.common import OWNER_ONLY
        from app.search import _hidden_columns

        save(client, public_locations="1")
        assert _hidden_columns(authed=False) == OWNER_ONLY

    def test_an_item_with_nowhere_recorded_reads_identically_for_both(self, db, part):
        """Hidden columns are blanked and not dropped, so who is asking changes what
        the haystack says and never how many fields it has -- otherwise the seams a
        quoted phrase must not match across move depending on the reader."""
        from app.search import _haystack

        row = db.get(Part, part()["asset_id"])
        assert _haystack(db, row, {}, authed=False) == _haystack(db, row, {}, authed=True)


class TestThePageSaysWhatThisIs:
    def test_the_switch_is_on_the_settings_page_with_its_reason(self, client):
        """A control says what it is and the reason is behind it (interface-text)."""
        page = client.get("/settings/server").text
        assert 'name="public_locations"' in page and "> Show locations</label>" in page
        assert 'class="field" title="Whether somebody who is not signed in is told' in page

    def test_it_is_a_server_option(self, client):
        assert settings.BY_KEY["public_locations"].section == settings.SERVER

    def test_the_remembered_list_and_its_switch_are_gone(self, client):
        """A location is a record that stays when it is emptied, so there is nothing
        left to remember (ADR-0034)."""
        assert "remember_locations" not in settings.BY_KEY
        assert 'name="remember_locations"' not in client.get("/settings/server").text


class TestTheDecisionsAreWrittenDown:
    def test_the_adrs_are_there_and_indexed(self):
        root = Path(__file__).parents[2]
        old = "0027-a-remembered-vocabulary-is-deleted-when-it-is-turned-off.md"
        new = "0034-a-location-is-a-record-in-the-register.md"
        assert (root / "adr" / old).exists() and (root / "adr" / new).exists()
        index = (root / "adr" / "README.md").read_text(encoding="utf-8")
        assert "0027" in index and "0034" in index
        assert "ADR-0034" in (root / "docs" / "architecture.md").read_text(encoding="utf-8")
        assert "Superseded by" in (root / "adr" / old).read_text(encoding="utf-8")
