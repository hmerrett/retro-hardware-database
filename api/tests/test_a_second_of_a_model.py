"""A second of a model you already have, as MANUAL.md section 5 promises it: on a new
machine, a maker and model already held -- typed, or filled in by the catalogue
picker -- offers to start from one of them; following it opens the form filled in
with what Duplicate copies, and nothing of the one machine's own; nothing is saved
until Save.
"""

import html
import json
import re

from app import main, machinedb
from app.models import Computer, ComputerDrive, ComputerRamModule

SOURCE = {
    "manufacturer": "IBM",
    "model": "5150",
    "name": "The first PC",
    "year": "1981",
    "chassis": "desktop",
    "cpu": "Intel 8088-4.77",
    "os": "PC DOS 1.0",
    "condition": "Working",
    "summary": "The one that started it.",
    "serial": "SN-0001",
    "source": "Club swap meet",
    "acquired_date": "2024-05-18",
    "notes": "Smells of the loft",
    "location": "Shelf 2",
    "rammod:30p1m": "4",
    "drive0_kind": "floppy",
    "drive0_form_factor": '5.25"',
    "drive0_size": "360KB",
    "drive0_count": "2",
}


def made(client, **fields):
    """A machine saved through its form, as the owner saves one."""
    r = client.post("/computers/new", data=SOURCE | fields, follow_redirects=False)
    assert r.status_code == 303, r.text
    return tag_of(r)


def tag_of(response) -> str:
    """The new machine's tag, from where its save sent the browser (`?build=1` and all)."""
    return response.headers["location"].split("?")[0].rsplit("/", 1)[1]


def offers(page: str) -> dict[str, dict[str, str]]:
    """What the new machine's form knows it could start from."""
    found = re.search(
        r'<script type="application/json" id="computer-form-data">(.*?)</script>', page, re.S
    )
    assert found, "the form carries no list of machines to start from"
    return json.loads(html.unescape(found.group(1)))["same"]


def value(page: str, name: str) -> str | None:
    found = re.search(rf'<input [^>]*name="{re.escape(name)}"[^>]*>', page)
    if not found:
        return None
    v = re.search(r'value="([^"]*)"', found.group(0))
    return html.unescape(v.group(1)) if v else ""


def textarea(page: str, name: str) -> str:
    return html.unescape(
        re.search(rf'<textarea [^>]*name="{name}"[^>]*>(.*?)</textarea>', page, re.S).group(1)
    )


class TestTheOffer:
    def test_the_new_form_knows_each_model_held_by_maker_and_model(self, client):
        aid = made(client)
        same = offers(client.get("/computers/new").text)
        assert same["named"] == {"ibm|5150": aid}

    def test_case_and_spacing_make_no_difference(self, client):
        aid = made(client, manufacturer="  ibm ", model="51 50")
        assert offers(client.get("/computers/new").text)["named"] == {"ibm|5150": aid}

    def test_a_catalogue_model_is_known_by_its_key(self, client):
        aid = made(
            client, manufacturer="Sinclair", model="ZX Spectrum", mach_model="zx-spectrum-48k"
        )
        assert offers(client.get("/computers/new").text)["catalogue"] == {"zx-spectrum-48k": aid}

    def test_one_still_in_the_collection_is_offered_before_one_that_has_gone(self, client, db):
        first, second = made(client), made(client)
        gone = db.get(Computer, min(first, second))
        gone.disposed = True
        db.commit()
        assert offers(client.get("/computers/new").text)["named"]["ibm|5150"] == max(first, second)

    def test_a_machine_with_no_maker_or_no_model_is_not_a_model_to_offer(self, client):
        made(client, manufacturer="", model="Mystery box")
        made(client, manufacturer="Custom build", model="")
        assert offers(client.get("/computers/new").text)["named"] == {}

    def test_the_line_is_under_the_identity_and_said_aloud_when_it_appears(self, client):
        page = client.get("/computers/new").text
        identity = re.search(
            r'<fieldset class="fieldset" id="s-identity">.*?</fieldset>', page, re.S
        )
        assert re.search(
            r'<div aria-live="polite"><p class="hint" id="samemake" hidden></p></div>',
            identity.group(0),
        )

    def test_an_existing_machines_form_makes_no_offer(self, client):
        aid = made(client)
        page = client.get(f"/computers/{aid}/edit").text
        assert 'id="computer-form-data"' not in page
        assert 'id="samemake"' not in page

    def test_the_script_follows_the_catalogue_picker_as_well_as_typing(self):
        """Picking a catalogue model fills the maker and model in by script, which
        fires no input event: the offer has to listen to the picker too."""
        script = (main.STATIC_DIR / "computer-form.js").read_text()
        assert "[data-machine-pick]" in script
        assert "'input'" in script
        assert "/computers/new?from=" in script


class TestStartingFromIt:
    def test_the_form_is_filled_in_with_what_duplicate_copies(self, client):
        aid = made(client)
        page = client.get(f"/computers/new?from={aid}").text
        for name in ("name", "year", "chassis", "cpu", "os", "manufacturer", "model"):
            assert value(page, name) == SOURCE[name], name
        assert textarea(page, "summary") == SOURCE["summary"]
        assert re.search(r'<option value="Working" selected', page)
        assert value(page, "rammod:30p1m") == "4"
        assert value(page, "drive0_size") == "360KB"
        assert value(page, "drive0_count") == "2"

    def test_nothing_of_the_one_machine_comes_with_it(self, client):
        aid = made(client)
        page = client.get(f"/computers/new?from={aid}").text
        for name in ("serial", "source", "acquired_date", "location"):
            assert not value(page, name), name
        assert textarea(page, "notes") == ""

    def test_the_catalogue_model_comes_and_the_board_issue_and_chips_do_not(self, client, db):
        aid = made(client, manufacturer="Commodore", model="64", mach_model="c64")
        machinedb.write(db, db.get(Computer, aid), chips={"sid": "MOS 6581"}, sockets={"sid": True})
        db.commit()
        page = client.get(f"/computers/new?from={aid}").text
        saved = json.loads(
            html.unescape(
                re.search(
                    r'<script type="application/json" id="machine-data">(.*?)</script>', page, re.S
                ).group(1)
            )
        )["saved"]
        assert saved["model_key"] == "c64"
        assert saved["chips"] == {}
        assert saved["sockets"] == {}
        assert saved["issue"] == ""

    def test_it_is_a_new_machines_form_and_says_where_it_was_copied_from(self, client):
        aid = made(client)
        page = client.get(f"/computers/new?from={aid}").text
        assert 'action="/computers/new"' in page
        assert '<h1 class="heading">New computer</h1>' in page
        assert f'Copied from <a href="/computers/{aid}">{aid}</a>.' in page
        # It is still a new machine's form, so it can start from another one too.
        assert 'id="samemake"' in page

    def test_nothing_is_saved_until_save(self, client, db):
        aid = made(client)
        before = db.query(Computer).count()
        client.get(f"/computers/new?from={aid}")
        assert db.query(Computer).count() == before

    def test_saving_it_makes_a_second_machine_and_leaves_the_first_alone(self, client, db):
        aid = made(client)
        page = client.get(f"/computers/new?from={aid}").text
        posted = {
            "manufacturer": value(page, "manufacturer"),
            "model": value(page, "model"),
            "name": "The second PC",
            "rammod:30p1m": value(page, "rammod:30p1m"),
            "drive0_kind": "floppy",
            "drive0_size": value(page, "drive0_size"),
            "drive0_count": value(page, "drive0_count"),
        }
        r = client.post("/computers/new", data=posted, follow_redirects=False)
        new = tag_of(r)
        assert new != aid
        db.expire_all()
        assert db.get(Computer, aid).name == "The first PC"
        assert db.query(ComputerRamModule).filter_by(computer_id=new).count() == 1
        assert db.query(ComputerDrive).filter_by(computer_id=new).count() == 1

    def test_a_tag_that_is_not_a_machine_opens_the_plain_form(self, client):
        page = client.get("/computers/new?from=RH-ZZZZ").text
        assert "Copied from" not in page
        assert value(page, "manufacturer") == ""
