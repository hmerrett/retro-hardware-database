"""The audit (MANUAL §14, "Audit", "Moving boxes", "The report").

Scan a location, then scan what goes in it. Every scan is acted on the moment it
arrives, so putting things away, moving them and checking a shelf are one rule; a
round is kept on the server until it is finished, and the report says what was
found, what moved in, what was not scanned and what was not recognised.
"""

import re
from pathlib import Path

import pytest

from app import labels
from app.models import Computer, LogEntry, Move, Part
from conftest import content
from test_stylesheet_lint import COMPONENTS, declarations

JSON = {"Accept": "application/json"}
SCRIPT = Path(__file__).parents[1] / "app" / "static" / "storage.js"


@pytest.fixture
def location(client):
    def make(name, kind="box", parent=None):
        r = client.post("/api/locations", json={"name": name, "kind": kind, "parent": parent})
        assert r.status_code == 200, r.text
        return r.json()["asset_id"]

    return make


@pytest.fixture
def scan(client):
    """One scan, as the page's script sends it, answered as the script reads it."""

    def send(code, boxes=False):
        data = {"code": code} | ({"boxes": "1"} if boxes else {})
        r = client.post("/audit/scan", data=data, headers=JSON)
        assert r.status_code == 200, r.text
        return r.json()

    return send


def where(db, aid):
    db.expire_all()
    thing = db.get(Computer, aid) or db.get(Part, aid)
    return thing.location_id


class TestScanningALocation:
    def test_it_opens_and_says_what_is_expected_there(self, client, scan, location, computer):
        shelf = location("Shelf 2", "shelf")
        computer(location=shelf)
        computer(location=shelf)
        said = scan(shelf)
        assert said["tone"] == "ok" and said["open"] == shelf
        assert "Shelf 2" in said["words"]
        assert "2 things expected here" in said["words"]

    def test_an_empty_one_says_empty(self, client, scan, location):
        said = scan(location("Box 14"))
        assert "Empty" in said["words"]

    def test_a_tag_in_any_case_will_do(self, client, scan, location):
        shelf = location("Shelf 2", "shelf")
        assert scan(shelf.lower())["open"] == shelf

    def test_so_will_the_url_a_qr_code_holds(self, client, scan, location):
        shelf = location("Shelf 2", "shelf")
        assert scan(f"https://example.test/items/{shelf}/\n")["open"] == shelf


class TestScanningAThing:
    def test_one_already_here_is_found(self, client, db, scan, location, computer):
        shelf = location("Shelf 2", "shelf")
        aid = computer(location=shelf)["asset_id"]
        scan(shelf)
        said = scan(aid)
        assert (said["tone"], said["head"]) == ("ok", "Found")
        assert where(db, aid) == shelf

    def test_one_recorded_elsewhere_is_moved_in_there_and_then(
        self, client, db, scan, location, computer
    ):
        loft = location("Loft", "room")
        shelf = location("Shelf 2", "shelf")
        aid = computer(location=loft)["asset_id"]
        scan(shelf)
        said = scan(aid)
        assert (said["tone"], said["head"]) == ("moved", "Moved in")
        assert "from Loft" in said["words"]
        assert where(db, aid) == shelf

    def test_one_recorded_nowhere_is_moved_in_too(self, client, db, scan, location, computer):
        shelf = location("Shelf 2", "shelf")
        aid = computer()["asset_id"]
        scan(shelf)
        said = scan(aid)
        assert said["tone"] == "moved"
        assert "nowhere recorded" in said["words"]
        assert where(db, aid) == shelf

    def test_the_move_is_recorded_as_by_scan(self, client, db, scan, location, computer):
        shelf = location("Shelf 2", "shelf")
        aid = computer()["asset_id"]
        scan(shelf)
        scan(aid)
        db.expire_all()
        last = db.query(Move).filter(Move.asset_id == aid).order_by(Move.id.desc()).first()
        assert (last.to_id, last.how, last.who) == (shelf, "scan", "owner")

    def test_undo_puts_it_back_and_says_so_in_the_history(
        self, client, db, scan, location, computer
    ):
        loft = location("Loft", "room")
        shelf = location("Shelf 2", "shelf")
        aid = computer(location=loft)["asset_id"]
        scan(shelf)
        moved = scan(aid)
        r = client.post("/audit/undo", data={"scan": moved["scan"]}, headers=JSON)
        assert r.status_code == 200
        assert where(db, aid) == loft
        db.expire_all()
        last = db.query(Move).filter(Move.asset_id == aid).order_by(Move.id.desc()).first()
        assert (last.to_id, last.how) == (loft, "undo")

    def test_scanned_twice_it_changes_nothing(self, client, db, scan, location, computer):
        shelf = location("Shelf 2", "shelf")
        aid = computer()["asset_id"]
        scan(shelf)
        scan(aid)
        said = scan(aid)
        assert said["head"] == "Already scanned"
        db.expire_all()
        assert db.query(Move).filter(Move.asset_id == aid).count() == 1


class TestPuttingOneThingAway:
    """Scan the thing, then the location."""

    def test_a_thing_scanned_with_nothing_open_is_held_and_shows_where_it_is(
        self, client, scan, location, computer
    ):
        loft = location("Loft", "room")
        aid = computer(location=loft)["asset_id"]
        said = scan(aid)
        assert said["open"] is None
        assert "Loft" in said["words"]
        assert "scan a location to move it there" in said["words"]

    def test_the_next_location_scanned_takes_it_and_opens(
        self, client, db, scan, location, computer
    ):
        loft = location("Loft", "room")
        shelf = location("Shelf 2", "shelf")
        aid = computer(location=loft)["asset_id"]
        scan(aid)
        said = scan(shelf)
        assert said["open"] == shelf
        assert where(db, aid) == shelf

    def test_scanning_another_thing_instead_leaves_the_first_where_it_was(
        self, client, db, scan, location, computer
    ):
        loft = location("Loft", "room")
        shelf = location("Shelf 2", "shelf")
        first = computer(location=loft)["asset_id"]
        second = computer(location=loft)["asset_id"]
        scan(first)
        scan(second)
        scan(shelf)
        assert where(db, first) == loft
        assert where(db, second) == shelf


class TestMovingBetweenLocations:
    def test_the_next_location_becomes_the_open_one(self, client, scan, location):
        a, b = location("Shelf 1", "shelf"), location("Shelf 2", "shelf")
        scan(a)
        assert scan(b)["open"] == b

    def test_a_location_recorded_elsewhere_is_opened_and_not_moved(
        self, client, db, scan, location
    ):
        from app.models import Location

        room = location("Workshop", "room")
        box = location("Box 14", "box", room)
        shelf = location("Shelf 2", "shelf")
        scan(shelf)
        assert scan(box)["open"] == box
        db.expire_all()
        assert db.get(Location, box).parent_id == room

    def test_a_location_inside_the_open_one_is_found_there_then_opened(
        self, client, scan, location
    ):
        shelf = location("Shelf 2", "shelf")
        box = location("Box 14", "box", shelf)
        scan(shelf)
        said = scan(box)
        assert said["open"] == box
        assert "Found on Shelf 2" in said["words"]

    def test_change_location_closes_the_open_one_without_opening_another(
        self, client, scan, location
    ):
        scan(location("Shelf 2", "shelf"))
        r = client.post("/audit/close", headers=JSON)
        assert r.status_code == 200, r.text
        assert r.json()["open"] is None
        assert "Scan a location" in content(client.get("/audit").text)

    def test_a_thing_scanned_after_it_is_held_not_moved_into_the_last_one(
        self, client, db, scan, location, computer
    ):
        loft = location("Loft", "room")
        aid = computer(location=loft)["asset_id"]
        scan(location("Shelf 2", "shelf"))
        client.post("/audit/close", headers=JSON)
        assert scan(aid)["head"] == "Where it is"
        assert where(db, aid) == loft

    def test_without_a_script_change_location_comes_back_to_the_page(self, client, scan, location):
        scan(location("Shelf 2", "shelf"))
        r = client.post("/audit/close", follow_redirects=False)
        assert (r.status_code, r.headers["location"]) == (303, "/audit")

    def test_a_location_closed_is_still_in_the_report(self, client, scan, location, computer):
        shelf = location("Shelf 2", "shelf")
        aid = computer(location=shelf)["asset_id"]
        scan(shelf)
        scan(aid)
        client.post("/audit/close", headers=JSON)
        report = client.post("/audit/finish", follow_redirects=True).text
        assert "Shelf 2" in report and aid in report


class TestAFittedPart:
    def test_scanned_into_a_location_it_is_taken_out_of_its_machine(
        self, client, db, scan, location, computer, part
    ):
        loft = location("Loft", "room")
        drawer = location("Spares drawer", "other")
        cid = computer(location=loft)["asset_id"]
        pid = part(computer_id=cid)["asset_id"]
        scan(drawer)
        said = scan(pid)
        assert f"taken out of {cid}" in said["words"]
        db.expire_all()
        got = db.get(Part, pid)
        assert (got.computer_id, got.location_id) == (None, drawer)
        for aid in (pid, cid):
            lines = [e.message for e in db.query(LogEntry).filter(LogEntry.asset_id == aid)]
            assert any("taken out" in (m or "") for m in lines), aid

    def test_undo_puts_it_back_in_its_machine_as_well(
        self, client, db, scan, location, computer, part
    ):
        loft = location("Loft", "room")
        drawer = location("Spares drawer", "other")
        cid = computer(location=loft)["asset_id"]
        pid = part(computer_id=cid)["asset_id"]
        scan(drawer)
        moved = scan(pid)
        client.post("/audit/undo", data={"scan": moved["scan"]}, headers=JSON)
        db.expire_all()
        got = db.get(Part, pid)
        assert (got.computer_id, got.location_id) == (cid, None)

    def test_scanned_where_its_machine_is_it_is_found_and_stays_fitted(
        self, client, db, scan, location, computer, part
    ):
        shelf = location("Shelf 2", "shelf")
        cid = computer(location=shelf)["asset_id"]
        pid = part(computer_id=cid)["asset_id"]
        scan(shelf)
        assert scan(pid)["head"] == "Found"
        db.expire_all()
        assert db.get(Part, pid).computer_id == cid


class TestWhatIsRefused:
    """These move nothing, sound the error, and are listed as not recognised."""

    def test_a_code_that_is_not_a_tag_here(self, client, scan, location):
        scan(location("Shelf 2", "shelf"))
        said = scan("5012345678900")
        assert said["tone"] == "refused"
        assert "5012345678900" in said["words"]

    def test_a_tag_nothing_has(self, client, scan):
        assert scan("RH-ZZZZ")["tone"] == "refused"

    def test_a_project(self, client, scan, location):
        tag = client.post("/api/projects", json={"name": "Recap the +2A"}).json()["asset_id"]
        scan(location("Shelf 2", "shelf"))
        said = scan(tag)
        assert said["tone"] == "refused"
        assert "not kept anywhere" in said["words"]

    def test_something_disposed_of(self, client, db, scan, location, computer):
        shelf = location("Shelf 2", "shelf")
        aid = computer()["asset_id"]
        client.patch(f"/api/computers/{aid}", json={"disposed": True, "disposed_at": "2026-09-01"})
        scan(shelf)
        said = scan(aid)
        assert said["tone"] == "refused"
        assert "2026-09-01" in said["words"]
        assert where(db, aid) is None


class TestMovingBoxes:
    def test_with_it_on_a_location_scanned_goes_inside_the_open_one(
        self, client, db, scan, location, computer
    ):
        from app.models import Location

        shelf = location("Shelf 2", "shelf")
        box = location("Box 14")
        computer(location=box)
        computer(location=box)
        scan(shelf, boxes=True)
        said = scan(box, boxes=True)
        assert (said["tone"], said["head"]) == ("moved", "Moved in")
        assert "2 things came with it" in said["words"]
        assert said["open"] == shelf, "the shelf stays open"
        db.expire_all()
        assert db.get(Location, box).parent_id == shelf

    def test_undo_puts_the_box_back(self, client, db, scan, location):
        from app.models import Location

        loft = location("Loft", "room")
        shelf = location("Shelf 2", "shelf")
        box = location("Box 14", "box", loft)
        scan(shelf, boxes=True)
        moved = scan(box, boxes=True)
        client.post("/audit/undo", data={"scan": moved["scan"]}, headers=JSON)
        db.expire_all()
        assert db.get(Location, box).parent_id == loft

    def test_a_box_into_its_own_contents_is_refused(self, client, db, scan, location):
        from app.models import Location

        box = location("Box 14")
        bag = location("Bag 6", "bag", box)
        scan(bag, boxes=True)
        said = scan(box, boxes=True)
        assert said["tone"] == "refused"
        db.expire_all()
        assert db.get(Location, box).parent_id is None


class TestARoundIsKept:
    def test_storage_mode_opened_again_carries_on_where_it_was(
        self, client, scan, location, computer
    ):
        shelf = location("Shelf 2", "shelf")
        aid = computer()["asset_id"]
        scan(shelf)
        scan(aid)
        page = content(client.get("/audit").text)
        assert "Shelf 2" in page and aid in page

    def test_without_a_script_a_scan_comes_back_to_the_page(self, client, location):
        shelf = location("Shelf 2", "shelf")
        r = client.post("/audit/scan", data={"code": shelf}, follow_redirects=False)
        assert (r.status_code, r.headers["location"]) == (303, "/audit")
        assert "Shelf 2" in content(client.get("/audit").text)


class TestTheReport:
    @pytest.fixture
    def round_(self, client, scan, location, computer):
        """A shelf the register says holds three things, one of which is scanned, one
        moved in from the loft, one left unscanned, and a code nobody issued."""
        loft = location("Loft", "room")
        shelf = location("Shelf 2", "shelf")
        found = computer(location=shelf, model="Found")["asset_id"]
        missing = computer(location=shelf, model="Missing")["asset_id"]
        incoming = computer(location=loft, model="Incoming")["asset_id"]
        scan(shelf)
        scan(found)
        scan(incoming)
        scan("NOT-A-TAG")
        r = client.post("/audit/finish", follow_redirects=False)
        assert r.status_code == 303
        return {
            "report": r.headers["location"],
            "found": found,
            "missing": missing,
            "incoming": incoming,
            "shelf": shelf,
            "loft": loft,
        }

    def section(self, page, heading):
        return page.split(f">{heading}<", 1)[1].split("</section>", 1)[0]

    def test_it_says_what_was_found(self, client, round_):
        page = content(client.get(round_["report"]).text)
        assert round_["found"] in self.section(page, "Found")

    def test_and_what_moved_in_from_where(self, client, round_):
        page = content(client.get(round_["report"]).text)
        moved = self.section(page, "Moved in")
        assert round_["incoming"] in moved and "Loft" in moved

    def test_and_what_was_not_scanned(self, client, round_):
        page = content(client.get(round_["report"]).text)
        assert round_["missing"] in self.section(page, "Not scanned")

    def test_and_what_was_not_recognised(self, client, round_):
        page = content(client.get(round_["report"]).text)
        assert "NOT-A-TAG" in self.section(page, "Not recognised")

    def test_what_was_not_scanned_stays_where_the_register_has_it(self, client, db, round_):
        assert where(db, round_["missing"]) == round_["shelf"]

    def test_record_as_missing_writes_it_on_each_things_history(self, client, db, round_):
        r = client.post(f"{round_['report']}/missing", follow_redirects=False)
        assert r.status_code == 303
        db.expire_all()
        line = (
            db.query(LogEntry)
            .filter(LogEntry.asset_id == round_["missing"], LogEntry.kind == "check")
            .one()
        )
        assert "not found at the check of Shelf 2" in line.message
        assert (
            not db.query(LogEntry)
            .filter(LogEntry.asset_id == round_["found"], LogEntry.kind == "check")
            .count()
        )

    def test_recording_twice_writes_each_line_once(self, client, db, round_):
        client.post(f"{round_['report']}/missing")
        client.post(f"{round_['report']}/missing")
        db.expire_all()
        assert (
            db.query(LogEntry)
            .filter(LogEntry.asset_id == round_["missing"], LogEntry.kind == "check")
            .count()
            == 1
        )

    def test_finishing_closes_the_round(self, client, round_):
        page = content(client.get("/audit").text)
        assert round_["incoming"] not in page


class TestThePage:
    """What the audit puts on the screen: the question a round starts with, a
    prompt saying what to do next, the panel, the round's list, and the site's own
    buttons -- with no box to type into while a script is running."""

    def test_a_round_starts_by_asking_how_you_are_scanning(self, client):
        page = content(client.get("/audit").text)
        start = page.split('id="storage-start"', 1)[1].split('id="storage-prompt"', 1)[0]
        assert 'data-scan-with="scanner"' in start
        camera = re.search(r'<button[^>]*data-scan-with="camera"[^>]*>', start)
        assert camera and "scan-open" in camera[0], "offered only where there is a camera"

    def test_a_round_already_going_is_not_asked_again(self, client, scan, location):
        assert 'data-started=""' in client.get("/audit").text
        scan(location("Shelf 2", "shelf"))
        assert 'data-started="1"' in client.get("/audit").text

    def test_with_nothing_open_it_says_scan_a_location(self, client):
        assert "Scan a location" in content(client.get("/audit").text)

    def test_with_a_location_open_it_says_what_to_scan_into_and_where_that_is(
        self, client, scan, location
    ):
        rack = location("Rack 3", "rack", location("Workshop", "room"))
        scan(location("Shelf 2", "shelf", rack))
        page = content(client.get("/audit").text)
        prompt = page.split('id="storage-prompt"', 1)[1].split("</div>", 1)[0]
        assert "Scan things into" in prompt and "Shelf 2" in prompt
        assert "Workshop / Rack 3" in prompt

    def test_each_answer_carries_what_the_prompt_says(self, scan, location):
        """The script redraws the prompt from the answer, as a reload would draw it."""
        said = scan(location("Shelf 2", "shelf", location("Rack 3", "rack")))
        assert (said["open_name"], said["open_path"]) == ("Shelf 2", "Rack 3")

    def test_change_location_is_offered_only_while_one_is_open(self, client, scan, location):
        def change():
            return client.get("/audit").text.split('id="storage-change"', 1)[1].split(">", 1)[0]

        assert "hidden" in change()
        scan(location("Shelf 2", "shelf"))
        assert "hidden" not in change()

    def test_the_scan_box_listens_without_an_on_screen_keyboard(self, client):
        page = client.get("/audit").text
        box = page.split('id="scan-code"', 1)[1].split(">", 1)[0]
        assert "autofocus" in box and 'inputmode="none"' in box

    def test_without_a_script_it_is_a_box_and_scan_it(self, client):
        """The box is put away by the script, so with none running it is there."""
        page = content(client.get("/audit").text)
        form = page.split('id="storage-form"', 1)[1].split("</form>", 1)[0]
        opening = form.split(">", 1)[0]
        assert "hidden" not in opening and "quiet" not in opening
        assert 'id="scan-code"' in form and 'type="submit"' in form

    def test_it_says_whether_it_is_ready_for_a_scan(self, client):
        assert 'id="storage-ready"' in content(client.get("/audit").text)

    def test_a_whole_code_is_taken_without_waiting_for_enter(self):
        """The script's own pattern, asked what the manual promises: the seven
        characters a barcode holds, or the whole address a QR code holds -- the one
        the labels print, slash and all, so a scanner slow between characters has
        not finished until it has typed the slash. Nothing shorter or longer: a code
        still arriving is not a scan yet."""
        found = re.search(r"const WHOLE = /(.+)/i;", SCRIPT.read_text(encoding="utf-8"))
        assert found, "storage.js names its pattern WHOLE"
        whole = re.compile(found[1], re.IGNORECASE)
        url = labels.item_url("RH-K7Q2")
        assert url.endswith("/items/RH-K7Q2/")
        for code in ("RH-K7Q2", "rh-k7q2", " RH-K7Q2 ", url, url.upper()):
            assert whole.search(code), code
        for code in ("RH-K7Q", "RH-K7Q2X", url[:-1], url[:-2], "X-RH-K7Q2", url + "X", ""):
            assert not whole.search(code), code

    @pytest.mark.parametrize(
        "control",
        [
            'id="storage-finish"',
            'id="storage-boxes"',
            'id="storage-type"',
            'id="storage-sound"',
            'id="storage-change"',
        ],
    )
    def test_its_controls_are_there(self, client, control):
        assert control in client.get("/audit").text

    def test_its_buttons_are_the_sites_own_size(self):
        """A size of its own made the audit look like another site, for thumbs
        that a scanner's trigger had already taken the work from."""
        own = [
            (selector, prop)
            for selector, prop, _ in declarations(COMPONENTS)
            if any(s in selector for s in (".storage .btn", ".bigswitch", ".scanform .scanbox"))
            and prop in ("min-height", "height", "width", "font-size", "padding")
        ]
        assert own == []

    def test_the_camera_scan_is_offered(self, client):
        assert re.search(r'class="[^"]*\bscan-open\b', content(client.get("/audit").text))

    def test_moving_boxes_is_off_whenever_it_opens(self, client):
        page = client.get("/audit").text
        switch = page.split('id="storage-boxes"', 1)[1].split(">", 1)[0]
        assert "checked" not in switch
