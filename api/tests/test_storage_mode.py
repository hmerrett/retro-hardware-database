"""The audit (MANUAL §14, "Audit", "The report"; ADR-0036).

Scan a location or a machine, then everything in it, and **next** before the next
place. Every scan is acted on the moment it arrives, so putting things away, moving
boxes, fitting parts and checking a shelf are one rule; a round is kept on the
server until it is finished, and the report says what was found, what moved in,
what was not scanned and what was not recognised.
"""

import re
from pathlib import Path

import pytest

from app import labels
from app.models import LogEntry, Move, Thing
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

    def send(code):
        r = client.post("/audit/scan", data={"code": code}, headers=JSON)
        assert r.status_code == 200, r.text
        return r.json()

    return send


def where(db, aid):
    """What a thing or a location is directly inside: a location, a machine, a card."""
    db.expire_all()
    return db.get(Thing, aid).inside_id


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


class TestAPartScannedWithNothingOpen:
    def test_says_where_it_is_and_moves_nothing(self, client, db, scan, location, part):
        loft = location("Loft", "room")
        aid = part(location=loft)["asset_id"]
        said = scan(aid)
        assert (said["open"], said["head"]) == (None, "Where it is")
        assert "Loft" in said["words"]
        assert where(db, aid) == loft

    def test_and_a_location_scanned_after_it_takes_nothing_with_it(
        self, client, db, scan, location, part
    ):
        loft = location("Loft", "room")
        shelf = location("Shelf 2", "shelf")
        aid = part(location=loft)["asset_id"]
        scan(aid)
        assert scan(shelf)["open"] == shelf
        assert where(db, aid) == loft


class TestNext:
    """Until next is pressed, everything scanned goes into what is open -- a location
    included, which is how a box goes onto a shelf."""

    def test_until_then_a_location_scanned_goes_inside_the_open_one(
        self, client, db, scan, location, computer
    ):
        shelf = location("Shelf 2", "shelf")
        box = location("Box 14")
        computer(location=box)
        computer(location=box)
        scan(shelf)
        said = scan(box)
        assert (said["tone"], said["head"]) == ("moved", "Moved in")
        assert "2 things came with it" in said["words"]
        assert said["open"] == shelf, "the shelf stays open"
        assert where(db, box) == shelf

    def test_a_location_already_inside_the_open_one_is_found(self, client, scan, location):
        shelf = location("Shelf 2", "shelf")
        box = location("Box 14", "box", shelf)
        scan(shelf)
        said = scan(box)
        assert (said["head"], said["open"]) == ("Found", shelf)

    def test_undo_puts_the_box_back(self, client, db, scan, location):
        loft = location("Loft", "room")
        shelf = location("Shelf 2", "shelf")
        box = location("Box 14", "box", loft)
        scan(shelf)
        moved = scan(box)
        client.post("/audit/undo", data={"scan": moved["scan"]}, headers=JSON)
        assert where(db, box) == loft

    def test_a_box_into_its_own_contents_is_refused(self, client, db, scan, location):
        box = location("Box 14")
        bag = location("Bag 6", "bag", box)
        scan(bag)
        said = scan(box)
        assert said["tone"] == "refused"
        assert where(db, box) is None

    def test_next_closes_what_is_open_so_the_next_scan_opens(self, client, scan, location):
        a, b = location("Shelf 1", "shelf"), location("Shelf 2", "shelf")
        scan(a)
        r = client.post("/audit/close", headers=JSON)
        assert r.status_code == 200, r.text
        assert r.json()["open"] is None
        assert "Scan a location or a machine" in content(client.get("/audit").text)
        assert scan(b)["open"] == b

    def test_without_a_script_next_comes_back_to_the_page(self, client, scan, location):
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


class TestFittingPartsInAMachine:
    """Scan the machine, then each card, drive and board going into it."""

    def test_a_machine_scanned_with_nothing_open_opens(self, client, scan, location, computer):
        machine = computer(model="Amiga 500", location=location("Shelf 2", "shelf"))["asset_id"]
        said = scan(machine)
        assert said["open"] == machine
        assert "Shelf 2" in said["open_path"]

    def test_a_part_scanned_into_it_is_fitted_and_taken_off_its_shelf(
        self, client, db, scan, location, computer, part
    ):
        drawer = location("Spares drawer", "other")
        machine = computer()["asset_id"]
        card = part(location=drawer)["asset_id"]
        scan(machine)
        said = scan(card)
        assert said["tone"] == "moved"
        assert where(db, card) == machine
        last = db.query(Move).filter(Move.asset_id == card).order_by(Move.id.desc()).first()
        assert (last.from_id, last.to_id, last.how) == (drawer, machine, "scan")

    def test_one_already_in_it_however_far_down_is_found(self, client, db, scan, computer, part):
        machine = computer()["asset_id"]
        card = part(computer_id=machine)["asset_id"]
        drive = part(type="storage", parent_id=card)["asset_id"]
        scan(machine)
        assert scan(drive)["head"] == "Found"
        assert where(db, drive) == card

    @pytest.mark.parametrize("what", ["machine", "location"])
    def test_a_machine_or_a_location_scanned_into_it_is_refused(
        self, client, db, scan, location, computer, what
    ):
        machine = computer()["asset_id"]
        other = computer()["asset_id"] if what == "machine" else location("Box 14")
        scan(machine)
        said = scan(other)
        assert said["tone"] == "refused"
        assert where(db, other) is None

    def test_a_machine_scanned_onto_a_shelf_is_put_there_with_what_is_in_it(
        self, client, db, scan, location, computer, part
    ):
        shelf = location("Shelf 2", "shelf")
        machine = computer()["asset_id"]
        card = part(computer_id=machine)["asset_id"]
        scan(shelf)
        said = scan(machine)
        assert "1 thing came with it" in said["words"]
        assert where(db, machine) == shelf
        assert where(db, card) == machine

    def test_the_report_says_what_was_fitted(self, client, scan, computer, part):
        machine = computer(model="Amiga 500")["asset_id"]
        card = part()["asset_id"]
        scan(machine)
        scan(card)
        report = client.post("/audit/finish", follow_redirects=True).text
        assert "Amiga 500" in report and card in report


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
        assert where(db, pid) == drawer
        lines = [e.message for e in db.query(LogEntry).filter(LogEntry.asset_id == cid)]
        assert f"{pid} taken out" in lines

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
        assert where(db, pid) == cid

    def test_undo_is_refused_when_its_machine_has_since_been_deleted(
        self, client, db, scan, location, computer, part
    ):
        """There is nothing to put it back in, and saying so beats a server error
        (ADR-0036): the part stays where the scan put it."""
        drawer = location("Spares drawer", "other")
        cid = computer()["asset_id"]
        pid = part(computer_id=cid)["asset_id"]
        scan(drawer)
        moved = scan(pid)
        client.patch(f"/api/computers/{cid}", json={"disposed": True})
        assert client.delete(f"/api/computers/{cid}").status_code == 200
        r = client.post("/audit/undo", data={"scan": moved["scan"]}, headers=JSON)
        assert r.json()["tone"] == "refused"
        assert where(db, pid) == drawer

    def test_undo_is_refused_where_it_would_mount_a_part_on_its_own_host(
        self, client, db, scan, location, part
    ):
        """Taken off its card by a scan, and the card mounted on it since: putting it
        back would mount each on the other (MANUAL §1, "Two tables"), so nothing
        moves and the panel says why."""
        drawer = location("Spares drawer", "other")
        card = part(type="io")["asset_id"]
        drive = part(type="storage", parent_id=card)["asset_id"]
        scan(drawer)
        moved = scan(drive)
        assert client.patch(f"/api/parts/{card}", json={"parent_id": drive}).status_code == 200
        said = client.post("/audit/undo", data={"scan": moved["scan"]}, headers=JSON).json()
        assert said["tone"] == "refused"
        assert card in said["words"]
        assert where(db, drive) == drawer
        assert where(db, card) == drive

    def test_scanned_where_its_machine_is_it_is_found_and_stays_fitted(
        self, client, db, scan, location, computer, part
    ):
        shelf = location("Shelf 2", "shelf")
        cid = computer(location=shelf)["asset_id"]
        pid = part(computer_id=cid)["asset_id"]
        scan(shelf)
        assert scan(pid)["head"] == "Found"
        assert where(db, pid) == cid


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

    def test_with_nothing_open_it_says_scan_a_location_or_a_machine(self, client):
        assert "Scan a location or a machine" in content(client.get("/audit").text)

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

    def test_next_is_offered_only_while_something_is_open(self, client, scan, location):
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

    def test_there_is_no_switch_for_moving_boxes(self, client):
        """A box scanned while a shelf is open goes onto it, so moving one needs no
        switch -- and a switch was a special case nobody could predict mid-loft."""
        assert "storage-boxes" not in client.get("/audit").text
