"""Where a thing is kept (ADR-0027).

The register has always said what a thing is and where it came from, never where
it is now. `location` is that answer, on machines and on parts alike, and two
switches decide what becomes of it: whether a visitor is told, and whether the
register remembers a place after the last thing in it has moved out.

Most of what follows is about those two. The column itself is a free-text box
like any other; what is worth testing is the half that is easy to get wrong --
a column kept off the page is still in the search, and a memory turned off has
to be a memory deleted rather than a memory ignored.
"""

import re

import pytest

from app import main, settings
from app.models import Computer, Location, Part

CRATE = "Loft, blue crate 3"


def visitor(monkeypatch):
    """Turn the site into what an anonymous reader sees."""
    monkeypatch.setattr(main.auth, "AUTH_ENABLED", True)


def save(client, **fields):
    """Post the settings form the way the page does, with the defaults for
    everything the caller did not name -- a browser sends the whole form, and an
    unticked box sends nothing at all, which is how a switch is turned off."""
    data = {
        "site_name": "",
        "theme": "system",
        "watermark": "1",
        "remember_locations": "1",
    } | {k: v for k, v in fields.items() if v is not None}
    for blank in [k for k, v in fields.items() if v is None]:
        data.pop(blank, None)
    r = client.post("/settings", data=data, follow_redirects=False)
    assert r.status_code == 303, r.text
    return r


def offered(client, path, list_id):
    """The values one of a form's datalists offers."""
    html = client.get(path).text
    m = re.search(rf'<datalist id="{list_id}">(.*?)</datalist>', html, re.S)
    return re.findall(r'<option value="([^"]*)"', m.group(1)) if m else None


def machine_offers(client):
    return offered(client, "/computers/new", "dl_location")


def part_offers(client):
    return offered(client, "/parts/new", "dl_locations")


class TestRecordingWhereSomethingIs:
    """The box itself: it holds what was typed, on either kind of thing, whichever
    door the answer came in by."""

    def test_a_machine_records_one_and_shows_it(self, client, computer):
        aid = computer(location=CRATE)["asset_id"]
        assert client.get(f"/api/computers/{aid}").json()["location"] == CRATE
        assert CRATE in client.get(f"/computers/{aid}").text

    def test_a_part_does_too(self, client, part):
        aid = part(location="Garage shelf B")["asset_id"]
        assert client.get(f"/api/parts/{aid}").json()["location"] == "Garage shelf B"
        assert "Garage shelf B" in client.get(f"/parts/{aid}").text

    def test_an_item_starts_with_nowhere_recorded(self, client, db, computer, part):
        """Nothing is inferred. A register that has never been told where anything
        is says so rather than guessing."""
        assert db.get(Computer, computer()["asset_id"]).location == ""
        assert db.get(Part, part()["asset_id"]).location == ""

    def test_the_machine_form_saves_one(self, client, computer):
        aid = computer()["asset_id"]
        client.post(
            f"/computers/{aid}/edit",
            data={"manufacturer": "Acme", "model": "Test", "location": CRATE},
            follow_redirects=False,
        )
        assert client.get(f"/api/computers/{aid}").json()["location"] == CRATE

    def test_the_part_form_saves_one(self, client, part):
        aid = part()["asset_id"]
        client.post(
            f"/parts/{aid}/edit",
            data={"type": "other", "model": "Widget", "location": "Under the bench"},
            follow_redirects=False,
        )
        assert client.get(f"/api/parts/{aid}").json()["location"] == "Under the bench"

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

    def test_a_parts_location_is_not_the_machine_it_is_installed_in(self, client, computer, part):
        """Two rows and two questions. A card fitted in a machine is wherever that
        machine is; a card in a drawer is in the drawer, and neither answer can be
        worked out from the other."""
        cid = computer()["asset_id"]
        pid = part(computer_id=cid, location="Spares drawer")["asset_id"]
        page = client.get(f"/parts/{pid}").text
        assert '<th scope="row">Location</th>' in page
        assert "Spares drawer" in page
        assert "Installed in" in page and cid in page


class TestBeingOfferedWhereThingsGo:
    """The pick list. One crate spelt one way is the whole point of it."""

    def test_both_forms_offer_a_location_already_used(self, client, computer):
        computer(location=CRATE)
        assert machine_offers(client) == [CRATE]
        assert part_offers(client) == [CRATE]

    def test_machines_and_parts_share_one_list(self, client, computer, part):
        """One crate holds both, so one list names it."""
        computer(location=CRATE)
        part(location="Garage shelf B")
        assert set(machine_offers(client)) == {CRATE, "Garage shelf B"}

    def test_an_edit_form_offers_them_as_well(self, client, computer, part):
        """An edit is where a spelling turns into a second one."""
        computer(location=CRATE)
        cid = computer()["asset_id"]
        pid = part()["asset_id"]
        assert offered(client, f"/computers/{cid}/edit", "dl_location") == [CRATE]
        assert offered(client, f"/parts/{pid}/edit", "dl_locations") == [CRATE]

    def test_the_box_does_not_offer_the_browsers_own_memory_instead(self, client):
        """A box called `location` is one every other site on the web has too, and
        the browser's memory of those would be offered over the register's answers."""
        page = client.get("/computers/new").text
        assert 'id="location" name="location" type="text" value=""' in page
        assert 'list="dl_location" autocomplete="off"' in page
        assert 'id="location" name="location" list="dl_locations" autocomplete="off"' in (
            client.get("/parts/new").text
        )


class TestRememberingWhereNothingIsKeptNow:
    """The reason there is a table at all: the derived list loses a crate the
    moment the last thing leaves it."""

    def test_a_location_cleared_off_its_last_item_is_still_offered(self, client, computer):
        aid = computer(location=CRATE)["asset_id"]
        client.patch(f"/api/computers/{aid}", json={"location": ""})
        assert machine_offers(client) == [CRATE]
        assert part_offers(client) == [CRATE]

    def test_a_place_in_use_is_offered_once_rather_than_twice(self, client, computer):
        """It is in the register and in the memory of the register, and those are
        one answer to the question the box asks."""
        computer(location=CRATE)
        assert machine_offers(client) == [CRATE]

    def test_what_is_in_use_comes_before_what_is_only_remembered(self, client, computer):
        """The crate something is in now is the likelier answer than the one it was
        in last year."""
        old = computer(location="Old shed")["asset_id"]
        client.patch(f"/api/computers/{old}", json={"location": ""})
        computer(location=CRATE)
        assert machine_offers(client) == [CRATE, "Old shed"]

    def test_the_gui_teaches_it_as_well_as_the_api(self, client, computer):
        """Both doors, because the forms are where most of these are typed."""
        aid = computer()["asset_id"]
        client.post(
            f"/computers/{aid}/edit",
            data={"manufacturer": "Acme", "model": "Test", "location": "Bench shelf"},
            follow_redirects=False,
        )
        client.patch(f"/api/computers/{aid}", json={"location": ""})
        assert machine_offers(client) == ["Bench shelf"]

    def test_a_part_teaches_it_too(self, client, part):
        aid = part(location="Spares drawer")["asset_id"]
        client.patch(f"/api/parts/{aid}", json={"location": ""})
        assert part_offers(client) == ["Spares drawer"]

    def test_nothing_is_written_while_the_switch_is_off(self, client, db, computer):
        save(client, remember_locations=None)
        computer(location=CRATE)
        assert db.query(Location).count() == 0

    def test_a_cleared_location_is_not_offered_while_the_switch_is_off(self, client, computer):
        """Off is not a broken mode: it is the behaviour every other pick list on
        this site has, which is the register asked a question about itself."""
        save(client, remember_locations=None)
        aid = computer(location=CRATE)["asset_id"]
        assert machine_offers(client) == [CRATE], "in use, so still offered"
        client.patch(f"/api/computers/{aid}", json={"location": ""})
        assert machine_offers(client) == []


class TestTurningItOffForgetsRatherThanHides:
    """The promise the manual makes in those words, and the one worth a test: a
    register told to stop remembering where somebody's things are has not been
    asked to keep the list somewhere quieter."""

    def test_switching_off_deletes_what_was_remembered(self, client, db, computer):
        aid = computer(location=CRATE)["asset_id"]
        client.patch(f"/api/computers/{aid}", json={"location": ""})
        assert db.query(Location).count() == 1
        save(client, remember_locations=None)
        assert db.query(Location).count() == 0

    def test_switching_back_on_does_not_bring_it_back(self, client, computer):
        """The whole shape of the promise, end to end: used, cleared, forgotten,
        and still gone when remembering is asked for again."""
        aid = computer(location=CRATE)["asset_id"]
        client.patch(f"/api/computers/{aid}", json={"location": ""})
        save(client, remember_locations=None)
        save(client, remember_locations="1")
        assert machine_offers(client) == []

    def test_a_later_save_while_it_is_off_purges_again(self, client, db, computer):
        """The delete runs on every save made while the switch is off rather than on
        the save that turned it off, so the promise does not turn on a transition
        nobody can see."""
        save(client, remember_locations=None)
        db.add(Location(name="Left over", used_at=None))
        db.commit()
        save(client, site_name="Henry's shelf", remember_locations=None)
        assert db.query(Location).count() == 0

    def test_it_is_on_to_begin_with(self, client):
        assert settings.on("remember_locations") is True


class TestWhoIsToldWhereThingsAre:
    """Off by default, because a public page saying which loft the rare machine is
    in is an address as much as a description."""

    def test_a_site_keeps_locations_to_itself_by_default(self, client):
        assert settings.on("public_locations") is False

    @pytest.mark.parametrize("kind", ["computers", "parts"])
    def test_a_visitor_is_shown_no_location_row(self, client, computer, part, monkeypatch, kind):
        aid = (computer(location=CRATE) if kind == "computers" else part(location=CRATE))[
            "asset_id"
        ]
        assert CRATE in client.get(f"/{kind}/{aid}").text, "the owner sees it"
        visitor(monkeypatch)
        page = client.get(f"/{kind}/{aid}").text
        assert CRATE not in page
        assert '<th scope="row">Location</th>' not in page

    def test_a_visitors_search_does_not_match_on_it(self, client, computer, monkeypatch):
        """The half that is easy to miss. _haystack reads every column off the
        model, so a column kept off the page joins the anonymous search by merely
        existing -- and a stranger searching "loft" would be handed the list of what
        is in yours."""
        aid = computer(location=CRATE)["asset_id"]
        visitor(monkeypatch)
        assert aid not in client.get("/?q=loft").text
        assert aid not in client.get("/suggest?q=loft").text

    def test_the_owners_search_does_match_on_it(self, client, computer):
        """The other direction, so what is private is a rule about who is asking
        rather than a column quietly dropped from the search for everybody."""
        aid = computer(location=CRATE)["asset_id"]
        assert aid in client.get("/?q=loft").text

    def test_the_gallery_card_does_not_carry_it_to_a_visitor(self, client, computer, monkeypatch):
        """The cards hold a condensed blob the browser filters on. It is markup, so
        a card that answered to "loft" would be the same leak with a step in it."""
        computer(location=CRATE)
        visitor(monkeypatch)
        assert "blue crate 3" not in client.get("/").text

    def test_the_gallery_card_carries_it_for_the_owner(self, client, computer):
        computer(location=CRATE)
        assert "blue crate 3" in client.get("/").text

    @pytest.mark.parametrize("kind", ["computers", "parts"])
    def test_turning_it_on_shows_a_visitor_the_row(self, client, computer, part, monkeypatch, kind):
        aid = (computer(location=CRATE) if kind == "computers" else part(location=CRATE))[
            "asset_id"
        ]
        save(client, public_locations="1")
        visitor(monkeypatch)
        assert CRATE in client.get(f"/{kind}/{aid}").text

    def test_turning_it_on_lets_a_visitor_search_on_it(self, client, computer, monkeypatch):
        aid = computer(location=CRATE)["asset_id"]
        save(client, public_locations="1")
        visitor(monkeypatch)
        assert aid in client.get("/?q=loft").text
        assert "blue crate 3" in client.get("/").text

    def test_the_owner_is_shown_it_either_way(self, client, computer):
        aid = computer(location=CRATE)["asset_id"]
        assert CRATE in client.get(f"/computers/{aid}").text
        save(client, public_locations="1")
        assert CRATE in client.get(f"/computers/{aid}").text

    def test_the_pick_list_is_never_offered_to_a_visitor(self, client, computer, monkeypatch):
        """Whichever way the switch is set. The lists are on the forms, and the
        forms are behind the login -- a page of everywhere the collection keeps
        anything is a different disclosure from one item's own row."""
        computer(location=CRATE)
        cid = computer()["asset_id"]
        save(client, public_locations="1")
        visitor(monkeypatch)
        assert "dl_location" not in client.get(f"/computers/{cid}").text


class TestTheHiddenColumnsAreAskedForRatherThanAssumed:
    """The mechanism, held to directly: OWNER_ONLY is one answer to "what may this
    reader not search on", and no longer the whole of it."""

    def test_a_setting_gated_column_joins_the_owner_only_ones_for_a_visitor(self, client):
        from app.common import OWNER_ONLY
        from app.search import _hidden_columns

        assert _hidden_columns(authed=True) == frozenset()
        assert "location" in _hidden_columns(authed=False)
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


class TestThePageSaysWhatTheseAre:
    def test_both_switches_are_on_the_settings_page_with_their_reasons(self, client):
        """A control says what it is and the reason is behind it (interface-text)."""
        page = client.get("/settings").text
        assert 'name="public_locations"' in page and "> Show locations</label>" in page
        assert 'name="remember_locations"' in page and "> Remember old locations</label>" in page
        assert 'class="srow" title="Whether somebody who is not signed in is told' in page
        assert 'class="srow" title="Keeps a place on the pick list after the last thing' in page

    def test_they_are_server_options(self, client):
        assert settings.BY_KEY["public_locations"].section == settings.SERVER
        assert settings.BY_KEY["remember_locations"].section == settings.SERVER


class TestTheDecisionIsWrittenDown:
    def test_the_adr_is_there_and_indexed(self):
        from pathlib import Path

        root = Path(__file__).parents[2]
        name = "0027-a-remembered-vocabulary-is-deleted-when-it-is-turned-off.md"
        assert (root / "adr" / name).exists()
        assert "0027" in (root / "adr" / "README.md").read_text(encoding="utf-8")
        assert "ADR-0027" in (root / "docs" / "architecture.md").read_text(encoding="utf-8")
