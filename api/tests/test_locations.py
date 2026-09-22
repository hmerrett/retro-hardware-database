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

    def test_a_parts_own_answer_stands_beside_where_it_is_installed(self, client, computer, part):
        """The card-in-a-drawer case. Two rows, because a part can be fitted in a
        machine and still be kept somewhere else -- a board out on the bench is
        still the board out of that machine."""
        cid = computer(location="Loft")["asset_id"]
        pid = part(computer_id=cid, location="Spares drawer")["asset_id"]
        page = client.get(f"/parts/{pid}").text
        assert "<dt>Location</dt>" in page
        assert "Spares drawer" in page
        assert "Loft" not in page, "its own answer wins over the one it is offered"
        assert "Fitted in" in page and cid in page


class TestARowOlderThanTheFeature:
    """The case the suite could not see, and the one that took the live preview
    down: a row that was in the register before the column existed.

    Every other test here makes its rows through the app, where the model's
    `default=""` fills the column in whatever the schema would otherwise have done
    -- and SQLAlchemy applies that default to a Core insert as well, so even going
    round the ORM does not reproduce it. Only the schema itself can, which is the
    point: a column left nullable reads as "" throughout a suite like this one and
    as NULL on any installation that had a collection in it when the migration ran.
    That is how 0028 left `serial`, why 0034 had to go back for it, and what made
    `GET /api/computers` a 500 for every caller in between.

    So these write the row the way a database holds one -- naming the columns a
    row older than the feature would have had, and letting the schema answer for
    the rest. The column is now NOT NULL with a server default of "", so what the
    schema answers is the same "" the app would have written.
    """

    def older_row(self, db, table, aid, **columns):
        """A row as a version of the app that predates `location` left one.

        Every column that version knew about is written the way it wrote them --
        "" for the text ones, which is what its models said, and NULL for a link,
        because a link to nothing is nothing and not the empty string. `location`
        alone is left out, because it did not exist to be written: what the row
        gets for it is the schema's answer and nothing else, which is the whole of
        what these tests are about.

        Raw SQL rather than a Core insert, and this is the reason the bug hid for
        so long: SQLAlchemy applies a column's Python-side default to a Core insert
        too, so even going round the ORM writes the "" the schema was supposed to
        be asked for. Parameterised throughout (database-standards); the column
        names are the table's own and never come from data.
        """
        from sqlalchemy import String, text

        values: dict[str, object] = {}
        for column in table.columns:
            if column.name == "location":
                continue
            if column.foreign_keys:
                values[column.name] = None
            elif isinstance(column.type, String):
                values[column.name] = ""
        values |= {"asset_id": aid, **columns}
        # Backticked, because `condition` is reserved in MariaDB -- the same rock
        # Setting.name is named to steer round. The names come from the table's own
        # metadata and never from data.
        fields = ", ".join(f"`{name}`" for name in values)
        binds = ", ".join(f":{name}" for name in values)
        db.execute(text(f"INSERT INTO {table.name} ({fields}) VALUES ({binds})"), values)
        db.commit()
        return aid

    def test_a_machine_older_than_the_column_reads_as_blank(self, client, db):
        self.older_row(db, Computer.__table__, "RH-0001", model="Older")
        got = client.get("/api/computers/RH-0001")
        assert got.status_code == 200, got.text
        assert got.json()["location"] == ""

    def test_a_part_older_than_the_column_reads_as_blank(self, client, db):
        self.older_row(db, Part.__table__, "RH-0002", type="other", model="Older")
        got = client.get("/api/parts/RH-0002")
        assert got.status_code == 200, got.text
        assert got.json()["location"] == ""

    def test_the_lists_survive_one(self, client, db):
        """The half that made it a 500 rather than an untidiness: the response is
        validated as a whole list, so one row older than the feature took every
        caller's `GET /api/computers` with it -- and the MCP tools with that."""
        self.older_row(db, Computer.__table__, "RH-0001", model="Older")
        self.older_row(db, Part.__table__, "RH-0002", type="other", model="Older")
        assert client.get("/api/computers").status_code == 200
        assert client.get("/api/parts").status_code == 200

    def test_the_pages_survive_one_as_well(self, client, db):
        """The gallery and the item pages read the column too, and a search reads
        it off every row at once."""
        self.older_row(db, Computer.__table__, "RH-0001", model="Older")
        self.older_row(db, Part.__table__, "RH-0002", type="other", computer_id="RH-0001")
        assert client.get("/").status_code == 200
        assert client.get("/?q=older").status_code == 200
        assert client.get("/computers/RH-0001").status_code == 200
        assert client.get("/parts/RH-0002").status_code == 200

    def test_such_a_row_is_still_placed_by_what_it_is_fitted_in(self, client, db):
        """And the derived answer works over it, which it could not if blank had
        two spellings -- `inherited` reads the column and strips it."""
        self.older_row(db, Computer.__table__, "RH-0001", model="Older")
        self.older_row(db, Part.__table__, "RH-0002", type="other", computer_id="RH-0001")
        client.patch("/api/computers/RH-0001", json={"location": CRATE})
        assert CRATE in client.get("/parts/RH-0002").text

    def test_the_migrated_schema_leaves_no_nulls_to_find(self, client, db, computer, part):
        """Read off the database the migrations built (conftest runs the real ones),
        rather than off the models that describe it."""
        from sqlalchemy import text

        computer()
        part()
        self.older_row(db, Computer.__table__, "RH-0001", model="Older")
        for table in ("computers", "parts"):
            nulls = db.execute(
                text(f"SELECT COUNT(*) FROM {table} WHERE location IS NULL")
            ).scalar()
            assert nulls == 0, f"{table} holds a second spelling of nowhere recorded"

    def test_the_column_cannot_hold_one(self, client, db):
        """The belt to the server default's braces. Asked of the migrated schema
        itself, so it is a fact about what an installation gets rather than about
        what the server's strictness happens to be set to today."""
        from sqlalchemy import inspect

        from app.db import engine

        for table in ("computers", "parts"):
            column = next(c for c in inspect(engine).get_columns(table) if c["name"] == "location")
            assert column["nullable"] is False, f"{table}.location can still be NULL"


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
        """Otherwise it reads as something somebody typed on this part, and the
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
        page = client.get(f"/parts/{chip}").text
        assert "On the bench" in page
        assert "Loft" not in page

    def test_a_part_that_says_for_itself_is_not_given_an_answer(self, client, computer, part):
        cid = computer(location=CRATE)["asset_id"]
        pid = part(computer_id=cid, location="Spares drawer")["asset_id"]
        page = client.get(f"/parts/{pid}").text
        assert "Spares drawer" in page
        assert "blue crate 3" not in page

    def test_clearing_the_box_hands_the_part_back_to_its_machine(self, client, computer, part):
        """The way round the manual promises: type an answer and it wins, take it
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
        from app.models import Part

        a = part(type="other")["asset_id"]
        b = part(type="other", parent_id=a)["asset_id"]
        db.get(Part, a).parent_id = b
        db.commit()
        assert client.get(f"/parts/{a}").status_code == 200
        assert client.get(f"/parts/{b}").status_code == 200
        assert client.get("/?q=anything").status_code == 200


class TestAnInheritedAnswerIsNotRemembered:
    """It is worked out rather than typed, and the vocabulary is of places somebody
    has actually named."""

    def test_it_does_not_join_the_table(self, client, db, computer, part):
        cid = computer(location=CRATE)["asset_id"]
        part(computer_id=cid)
        assert [row.name for row in db.query(Location).all()] == [CRATE]

    def test_it_is_offered_once_and_not_twice(self, client, computer, part):
        """The machine's own answer is on the list because the machine is kept
        there; the four cards in it do not put it there four more times."""
        cid = computer(location=CRATE)["asset_id"]
        for _ in range(3):
            part(computer_id=cid)
        assert machine_offers(client) == [CRATE]

    def test_emptying_the_machine_does_not_leave_the_place_in_use(self, client, computer, part):
        """What is in use is what somebody has written down. A part that was only
        ever shown the crate was never in it as far as the register is concerned,
        so clearing the machine leaves the crate to the remembered half."""
        cid = computer(location=CRATE)["asset_id"]
        part(computer_id=cid)
        client.patch(f"/api/computers/{cid}", json={"location": ""})
        save(client, remember_locations=None)
        assert machine_offers(client) == []


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
        assert 'id="location" name="location" value=""' in page
        assert 'autocomplete="off" list="dl_location"' in page
        assert (
            'id="location" name="location" value="" autocomplete="off" list="dl_locations"'
        ) in client.get("/parts/new").text


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
        assert "<dt>Location</dt>" not in page

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

    @pytest.mark.parametrize("who", ["owner", "visitor"])
    def test_the_gallery_carries_it_to_nobody(self, client, computer, monkeypatch, who):
        """The cards used to hold a condensed blob the browser filtered on, and the
        question was who it was written for. Paging and searching moved to the
        server (spec 15), the blob went with the filter, and a card says where
        nothing is kept -- so the answer is now nobody, owner included."""
        computer(location=CRATE)
        if who == "visitor":
            visitor(monkeypatch)
        assert "blue crate 3" not in client.get("/").text

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

    def test_a_visitor_is_shown_no_inherited_location_either(
        self, client, computer, part, monkeypatch
    ):
        """The gate is on the answer and not on the column, or a part would publish
        what its machine keeps back."""
        cid = computer(location=CRATE)["asset_id"]
        pid = part(computer_id=cid)["asset_id"]
        assert CRATE in client.get(f"/parts/{pid}").text, "the owner sees it"
        visitor(monkeypatch)
        page = client.get(f"/parts/{pid}").text
        assert CRATE not in page
        assert "<dt>Location</dt>" not in page

    def test_a_visitors_search_does_not_match_on_an_inherited_one(
        self, client, computer, part, monkeypatch
    ):
        cid = computer(location=CRATE)["asset_id"]
        pid = part(computer_id=cid)["asset_id"]
        visitor(monkeypatch)
        assert pid not in client.get("/?q=loft").text
        assert pid not in client.get("/suggest?q=loft").text

    def test_turning_it_on_shows_and_finds_an_inherited_one(
        self, client, computer, part, monkeypatch
    ):
        cid = computer(location=CRATE)["asset_id"]
        pid = part(computer_id=cid)["asset_id"]
        save(client, public_locations="1")
        visitor(monkeypatch)
        assert CRATE in client.get(f"/parts/{pid}").text
        assert pid in client.get("/?q=loft").text

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
        assert pid not in client.get("/?q=loft").text

    @pytest.mark.parametrize("who", ["owner", "visitor"])
    def test_no_card_carries_the_inherited_answer_either(
        self, client, computer, part, monkeypatch, who
    ):
        """The inherited answer is findable by searching for it, which the tests
        above hold; what it is not is written into the gallery's markup."""
        cid = computer(location=CRATE)["asset_id"]
        part(computer_id=cid)
        if who == "visitor":
            visitor(monkeypatch)
        assert "blue crate 3" not in client.get("/").text


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
