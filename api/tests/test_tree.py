"""Where a thing is, is one tree (MANUAL §1 "Two tables", §4 "An item page", §5
"Where it is kept", §14 "Storage", §16 "Disposing, restoring and deleting";
ADR-0036).

Everything is inside at most one thing: a part is fitted in a machine, mounted on
another part or kept in a location, a machine is kept in a location, and a location
is inside a location. Moving anything moves what is inside it; what is inside a
machine or a part shares its fate, and what is inside a location does not.
"""

import pytest
from sqlalchemy.exc import IntegrityError

from app import ids
from app.db import SessionLocal
from app.models import Gone, LogEntry, Move, Part, Thing
from conftest import content, log_out


@pytest.fixture
def location(client):
    def make(name, kind="box", parent=None):
        r = client.post("/api/locations", json={"name": name, "kind": kind, "parent": parent})
        assert r.status_code == 200, r.text
        return r.json()["asset_id"]

    return make


@pytest.fixture
def rig(computer, part, location):
    """A drive on a controller card in a machine in a box on a shelf: the whole of
    the tree in one stack. {name: tag}."""
    shelf = location("Shelf 2", "shelf")
    box = location("Box 14", "box", shelf)
    machine = computer(location=box)["asset_id"]
    card = part(type="io", model="Controller", computer_id=machine)["asset_id"]
    drive = part(type="storage", model="ST-225", parent_id=card)["asset_id"]
    return {"shelf": shelf, "box": box, "machine": machine, "card": card, "drive": drive}


def inside(db, aid):
    db.expire_all()
    return db.get(Thing, aid).inside_id


def moves_of(db, aid):
    db.expire_all()
    return db.query(Move).filter(Move.asset_id == aid).order_by(Move.id).all()


def dispose(client, kind, aid, note="binned"):
    r = client.post(
        f"/{kind}/{aid}/dispose",
        data={"date": "2026-10-08", "note": note},
        follow_redirects=False,
    )
    assert r.status_code == 303


def save(client, **fields):
    data = {k: v for k, v in fields.items() if v is not None}
    r = client.post("/settings/server", data=data, follow_redirects=False)
    assert r.status_code == 303, r.text


class TestAThingIsInOnePlace:
    def test_fitting_a_part_takes_it_off_its_shelf(self, client, location, computer, part):
        shelf = location("Shelf", "shelf")
        machine = computer()["asset_id"]
        card = part(location=shelf)["asset_id"]
        client.post(f"/parts/{card}/link", data={"computer_id": machine})
        out = client.get(f"/api/parts/{card}").json()
        assert (out["computer_id"], out["parent_id"], out["location"]) == (machine, None, "")

    def test_putting_a_fitted_part_on_a_shelf_takes_it_out_of_its_machine(
        self, client, location, computer, part
    ):
        shelf = location("Shelf", "shelf")
        card = part(computer_id=computer()["asset_id"])["asset_id"]
        out = client.patch(f"/api/parts/{card}", json={"location": shelf}).json()
        assert (out["computer_id"], out["location"]) == (None, shelf)

    def test_a_request_naming_a_machine_and_a_location_fits_the_part(
        self, client, location, computer, part
    ):
        shelf = location("Shelf", "shelf")
        machine = computer()["asset_id"]
        out = part(computer_id=machine, location=shelf)
        assert (out["computer_id"], out["location"]) == (machine, "")

    def test_one_naming_a_machine_and_a_part_mounts_it_on_the_part(self, computer, part):
        machine = computer()["asset_id"]
        card = part(computer_id=machine)["asset_id"]
        out = part(computer_id=machine, parent_id=card)
        assert (out["computer_id"], out["parent_id"]) == (None, card)

    def test_a_blank_link_takes_it_out_and_leaves_it_nowhere(self, client, db, rig):
        out = client.patch(f"/api/parts/{rig['card']}", json={"computer_id": ""}).json()
        assert (out["computer_id"], out["location"]) == (None, "")
        assert inside(db, rig["card"]) is None

    def test_a_fitted_parts_form_has_no_location_box(self, client, rig):
        page = client.get(f"/parts/{rig['card']}/edit").text
        assert 'name="location"' not in page
        assert f'In <a href="/items/{rig["machine"]}">' in page

    def test_saving_that_form_leaves_it_in_its_machine(self, client, db, rig):
        client.post(
            f"/parts/{rig['card']}/edit",
            data={"type": "io", "model": "Controller"},
            follow_redirects=False,
        )
        assert inside(db, rig["card"]) == rig["machine"]


class TestMovingSomethingMovesWhatIsInIt:
    def test_a_drive_on_a_card_in_a_machine_is_where_the_machine_is(self, client, rig):
        page = content(client.get(f"/parts/{rig['drive']}").text)
        assert "Box 14" in page and "Shelf 2" in page

    def test_moving_the_box_moves_everything_in_it(self, client, location, rig):
        loft = location("Loft", "room")
        client.patch(f"/api/locations/{rig['box']}", json={"parent": loft})
        page = content(client.get(f"/parts/{rig['drive']}").text)
        # The row, not the history: a move line says the path as it read at the time.
        row = page.split("<dt>Location</dt>", 1)[1].split("</dd>", 1)[0]
        assert "Loft" in row and "Shelf 2" not in row

    def test_and_writes_one_move_on_the_box_only(self, client, db, location, rig):
        loft = location("Loft", "room")
        before = {
            aid: len(moves_of(db, aid)) for aid in (rig["machine"], rig["card"], rig["drive"])
        }
        client.patch(f"/api/locations/{rig['box']}", json={"parent": loft})
        assert moves_of(db, rig["box"])[-1].to_id == loft
        assert {aid: len(moves_of(db, aid)) for aid in before} == before


class TestFittingIsAMove:
    def test_fitting_a_card_writes_a_move_from_its_shelf_to_the_machine(
        self, client, db, location, computer, part
    ):
        shelf = location("Shelf", "shelf")
        machine = computer()["asset_id"]
        card = part(location=shelf)["asset_id"]
        client.post(f"/parts/{card}/link", data={"computer_id": machine})
        last = moves_of(db, card)[-1]
        assert (last.from_id, last.to_id, last.how) == (shelf, machine, "edit")

    def test_taking_it_out_writes_one_and_leaves_it_nowhere(self, client, db, rig):
        client.post(f"/parts/{rig['card']}/unlink", data={})
        last = moves_of(db, rig["card"])[-1]
        assert (last.from_id, last.to_id) == (rig["machine"], None)
        assert inside(db, rig["card"]) is None

    def test_the_machine_says_what_went_in_and_what_came_out(self, client, db, computer, part):
        machine = computer()["asset_id"]
        card = part()["asset_id"]
        client.post(f"/computers/{machine}/link-part", data={"part_id": card})
        client.post(f"/parts/{card}/unlink", data={})
        db.expire_all()
        said = [e.message for e in db.query(LogEntry).filter(LogEntry.asset_id == machine)]
        assert f"fitted {card}" in said and f"{card} taken out" in said

    def test_a_cards_moves_say_which_machines_it_has_been_in(self, client, computer, part):
        first, second = computer()["asset_id"], computer()["asset_id"]
        card = part(computer_id=first)["asset_id"]
        client.patch(f"/api/parts/{card}", json={"computer_id": second})
        been = {(m["from"], m["to"]) for m in client.get(f"/api/items/{card}/moves").json()}
        assert (first, second) in been


class TestNothingGoesInsideItself:
    def test_a_part_cannot_be_mounted_on_itself(self, client, part):
        card = part()["asset_id"]
        r = client.patch(f"/api/parts/{card}", json={"parent_id": card})
        assert r.status_code == 422

    def test_or_on_anything_mounted_on_it_however_far_down(self, client, rig):
        r = client.patch(f"/api/parts/{rig['card']}", json={"parent_id": rig["drive"]})
        assert r.status_code == 422
        assert "mounted on itself" in r.text

    def test_a_location_cannot_go_inside_one_inside_it(self, client, rig):
        r = client.patch(f"/api/locations/{rig['shelf']}", json={"parent": rig["box"]})
        assert r.status_code == 422

    def test_the_mount_button_refuses_and_the_page_says_why(self, client, db, rig):
        r = client.post(
            f"/parts/{rig['drive']}/attach", data={"part_id": rig["card"]}, follow_redirects=False
        )
        assert r.status_code == 303 and "mounterr=1" in r.headers["location"]
        assert inside(db, rig["card"]) == rig["machine"]
        assert "Not mounted." in client.get(r.headers["location"]).text


class TestNothingGoesInsideSomethingDisposedOf:
    def test_the_api_refuses_to_fit_a_part_in_a_disposed_machine(self, client, computer, part):
        machine = computer()["asset_id"]
        dispose(client, "computers", machine)
        card = part()["asset_id"]
        r = client.patch(f"/api/parts/{card}", json={"computer_id": machine})
        assert r.status_code == 422
        assert "disposed of" in r.text

    def test_and_so_does_the_page(self, client, db, computer, part):
        machine = computer()["asset_id"]
        dispose(client, "computers", machine)
        card = part()["asset_id"]
        r = client.post(
            f"/parts/{card}/link", data={"computer_id": machine}, follow_redirects=False
        )
        assert "fiterr=1" in r.headers["location"]
        assert inside(db, card) is None


class TestWhatIsInsideShareItsFate:
    def test_disposing_of_a_card_disposes_of_the_drive_on_it(self, client, db, rig):
        dispose(client, "parts", rig["card"])
        db.expire_all()
        drive = db.get(Part, rig["drive"])
        assert drive.disposed and drive.disposed_note == "binned"

    def test_restoring_the_card_brings_the_drive_back(self, client, db, rig):
        dispose(client, "parts", rig["card"])
        client.post(f"/parts/{rig['card']}/restore")
        db.expire_all()
        assert not db.get(Part, rig["drive"]).disposed

    def test_a_part_restored_on_its_own_comes_out_of_a_disposed_machine(self, client, db, rig):
        dispose(client, "computers", rig["machine"])
        client.post(f"/parts/{rig['card']}/restore")
        db.expire_all()
        assert not db.get(Part, rig["card"]).disposed
        assert inside(db, rig["card"]) is None

    def test_the_delete_page_lists_everything_inside_all_the_way_down(self, client, rig):
        dispose(client, "computers", rig["machine"])
        page = client.get(f"/computers/{rig['machine']}/delete").text
        assert rig["card"] in page and rig["drive"] in page
        assert 'name="with_parts"' not in page

    def test_deleting_a_machine_deletes_everything_in_it(self, client, db, rig):
        dispose(client, "computers", rig["machine"])
        url = f"http://testserver/computers/{rig['machine']}"
        r = client.post(
            f"/computers/{rig['machine']}/delete", data={"confirm": url}, follow_redirects=False
        )
        assert r.status_code == 303
        db.expire_all()
        assert db.get(Part, rig["card"]) is None
        assert db.get(Part, rig["drive"]) is None

    def test_the_api_refuses_to_delete_a_machine_still_in_the_collection(self, client, db, rig):
        r = client.delete(f"/api/computers/{rig['machine']}")
        assert r.status_code == 409
        db.expire_all()
        assert db.get(Part, rig["drive"]) is not None

    def test_or_a_part(self, client, rig):
        assert client.delete(f"/api/parts/{rig['card']}").status_code == 409

    def test_once_disposed_the_api_deletes_it_and_everything_in_it(self, client, db, rig):
        client.patch(f"/api/computers/{rig['machine']}", json={"disposed": True})
        assert client.delete(f"/api/computers/{rig['machine']}").status_code == 200
        db.expire_all()
        assert db.get(Part, rig["card"]) is None and db.get(Part, rig["drive"]) is None


class TestDeletingALocationDeletesNothingInIt:
    def test_what_was_in_it_is_left_nowhere(self, client, db, rig):
        r = client.post(f"/locations/{rig['box']}/delete", follow_redirects=False)
        assert r.status_code == 303
        assert inside(db, rig["machine"]) is None
        assert inside(db, rig["card"]) == rig["machine"], "what is in the machine stays in it"

    def test_each_says_so_with_a_move(self, client, db, rig):
        client.post(f"/locations/{rig['box']}/delete")
        last = moves_of(db, rig["machine"])[-1]
        assert (last.from_id, last.to_id) == (rig["box"], None)

    def test_a_location_inside_it_keeps_what_is_in_it(self, client, db, location, part):
        room = location("Room", "room")
        crate = location("Crate", "box", room)
        card = part(location=crate)["asset_id"]
        client.post(f"/locations/{room}/delete")
        assert inside(db, crate) is None
        assert inside(db, card) == crate

    def test_the_api_does_the_same(self, client, db, rig):
        assert client.delete(f"/api/locations/{rig['box']}").status_code == 200
        assert inside(db, rig["machine"]) is None
        assert moves_of(db, rig["machine"])[-1].how == "api"


class TestATagIsNeverIssuedTwice:
    def test_a_deleted_things_tag_is_kept(self, client, db, part):
        aid = part()["asset_id"]
        client.patch(f"/api/parts/{aid}", json={"disposed": True})
        client.delete(f"/api/parts/{aid}")
        db.expire_all()
        assert isinstance(db.get(Thing, aid), Gone)

    def test_and_is_never_handed_out_again(self, client, db, part, monkeypatch):
        aid = part()["asset_id"]
        client.patch(f"/api/parts/{aid}", json={"disposed": True})
        client.delete(f"/api/parts/{aid}")
        offered = iter([aid, "RH-ZZZZ"])
        monkeypatch.setattr(ids, "_random_id", lambda: next(offered))
        assert ids.next_asset_id(db) == "RH-ZZZZ"

    def test_its_label_finds_nothing(self, client, part):
        aid = part()["asset_id"]
        client.patch(f"/api/parts/{aid}", json={"disposed": True})
        client.delete(f"/api/parts/{aid}")
        assert client.get(f"/items/{aid}", follow_redirects=False).status_code == 404

    def test_the_database_refuses_a_second_thing_with_a_tag_taken(self, computer):
        aid = computer()["asset_id"]
        with SessionLocal() as db, pytest.raises(IntegrityError):
            db.add(Part(asset_id=aid, type="other"))
            db.commit()


class TestInAMachineMeansAnywhereInIt:
    def test_its_page_lists_the_drive_under_its_card(self, client, rig):
        page = client.get(f"/computers/{rig['machine']}").text
        assert rig["drive"] in page
        assert 'class="mounted"' in page

    def test_browsing_what_is_in_it_includes_the_drive(self, client, rig):
        page = client.get(f"/browse?f=in&v={rig['machine']}").text
        assert rig["drive"] in page

    def test_its_label_says_which_machine_the_drive_is_in(self, db, rig):
        from app import printing

        source = printing.source_of(db, db.get(Part, rig["drive"]))
        assert source.row["computer_id"] == rig["machine"]


class TestWhoIsToldWhereAThingIsKept:
    def test_a_new_item_starts_unticked_out_of_the_box(self, computer):
        assert computer()["location_public"] is False

    def test_with_show_locations_on_a_new_item_starts_ticked(self, client, computer):
        save(client, public_locations="1")
        assert computer()["location_public"] is True

    def test_turning_the_switch_changes_no_item_already_there(self, client, computer):
        aid = computer()["asset_id"]
        save(client, public_locations="1")
        assert client.get(f"/api/computers/{aid}").json()["location_public"] is False

    def test_a_visitor_sees_the_row_only_when_the_tick_is_on(self, client, location, computer):
        box = location("Box 14")
        hidden = computer(location=box)["asset_id"]
        shown = computer(location=box, location_public=True)["asset_id"]
        log_out(client)
        assert "<dt>Location</dt>" not in client.get(f"/computers/{hidden}").text
        assert "<dt>Location</dt>" in client.get(f"/computers/{shown}").text

    def test_a_fitted_part_follows_its_machines_tick(self, client, rig):
        log_out(client)
        assert "<dt>Location</dt>" not in client.get(f"/parts/{rig['drive']}").text

    def test_and_is_told_when_the_machine_is(self, client, rig):
        client.patch(f"/api/computers/{rig['machine']}", json={"location_public": True})
        log_out(client)
        assert "<dt>Location</dt>" in client.get(f"/parts/{rig['drive']}").text

    def test_while_location_pages_are_private_the_path_is_names(self, client, location, computer):
        box = location("Box 14")
        aid = computer(location=box, location_public=True)["asset_id"]
        log_out(client)
        page = client.get(f"/computers/{aid}").text
        assert "Box 14" in page and f'href="/locations/{box}"' not in page

    def test_a_visitors_search_finds_a_ticked_thing_by_where_it_is(
        self, client, location, computer
    ):
        loft = location("Loft", "room")
        told = computer(location=loft, location_public=True)["asset_id"]
        kept = computer(location=loft)["asset_id"]
        log_out(client)
        found = client.get("/?q=loft").text
        assert told in found and kept not in found

    def test_a_public_location_page_shows_a_visitor_only_ticked_things(
        self, client, location, computer
    ):
        save(client, public_locations="1")
        box = location("Box 14")
        told = computer(location=box)["asset_id"]
        kept = computer(location=box, location_public=False)["asset_id"]
        log_out(client)
        page = client.get(f"/locations/{box}").text
        assert told in page and kept not in page

    def test_the_form_saves_the_tick(self, client, db, computer):
        aid = computer()["asset_id"]
        fields = {"manufacturer": "Acme", "model": "Test", "location": ""}
        client.post(f"/computers/{aid}/edit", data=fields | {"location_public": "1"})
        assert client.get(f"/api/computers/{aid}").json()["location_public"] is True
        client.post(f"/computers/{aid}/edit", data=fields)
        assert client.get(f"/api/computers/{aid}").json()["location_public"] is False

    def test_the_tick_is_not_something_a_search_matches(self, client, computer):
        computer(location_public=True)
        assert "RH-" not in content(client.get("/?q=true").text)
