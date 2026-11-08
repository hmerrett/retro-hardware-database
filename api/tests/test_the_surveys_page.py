"""The Surveys page, and who is shown what a survey found (MANUAL §23, ADR-0043).

Most surveys need nobody. The page is where the rest wait: a survey that is not
certain which machine it is about, and a thing found that nobody answered for at
the machine. It is also where every survey can be read back, with the report as
the program wrote it, and where the serial numbers and addresses surveys have
seen are listed, one to a row, under Seen.

What a survey records is the owner's working record, so it is for people signed
in. An Ethernet address is kept from visitors everywhere it could appear.
"""

import re

import pytest

from app import labels, specdb
from app.common import to_dict
from app.models import Part
from conftest import as_viewer, content, log_out
from survey_reports import (
    AGENTS,
    AWE64,
    BIOS_ROM,
    DISK,
    MAC,
    NIC,
    answer,
    edid,
    finding,
    get,
    read,
    survey,
)


@pytest.fixture(autouse=True)
def agents(monkeypatch):
    monkeypatch.setenv("RHDB_SURVEY_AGENTS", AGENTS)


def row(page: str, text: str) -> str:
    """The one row of a list that mentions `text`, so an assertion is about it."""
    rows = [r for r in re.split(r"<tr\b", page) if text in r]
    assert len(rows) == 1, f"{text!r} is on {len(rows)} rows"
    return rows[0]


def file_it(client, made: dict, tag: str, **extra):
    return client.post(
        f"/surveys/{made['id']}/file", data={"tag": tag} | extra, follow_redirects=False
    )


# --- who may read it, and in what order ---------------------------------------------


class TestReadingIt:
    def test_anybody_signed_in_can_read_the_surveys(self, client, computer):
        made = survey(client, TAG=computer()["asset_id"])
        as_viewer(client)
        for page in ("/surveys", f"/surveys/{made['id']}", "/surveys/seen"):
            assert client.get(page).status_code == 200, page
        assert client.get("/api/surveys").status_code == 200
        assert client.get(f"/api/surveys/{made['id']}").status_code == 200

    def test_a_visitor_is_shown_none_of_it(self, client, computer):
        made = survey(client, TAG=computer()["asset_id"])
        log_out(client)
        for page in ("/surveys", f"/surveys/{made['id']}", "/surveys/seen"):
            r = client.get(page, follow_redirects=False)
            assert r.status_code == 303 and r.headers["location"].startswith("/login"), page
        assert client.get("/api/surveys").status_code == 401
        assert client.get(f"/api/surveys/{made['id']}").status_code == 401

    def test_only_an_administrator_can_act_on_a_survey(self, client):
        made = survey(client, **DISK)
        as_viewer(client)
        assert file_it(client, made, "RH-0001").status_code == 403
        assert answer(client, made, "DISK1", "out").status_code == 403
        assert (
            client.post(f"/surveys/{made['id']}/delete", follow_redirects=False).status_code == 403
        )
        assert read(client, made["id"])["waiting"] == "machine"

    def test_waiting_comes_first_and_then_newest_first(self, client, computer):
        waiting = survey(client, taken="2026-11-01T09:00:00", **DISK)
        older = survey(client, taken="2026-11-02T09:00:00", TAG=computer()["asset_id"])
        newer = survey(client, taken="2026-11-03T09:00:00", TAG=computer()["asset_id"])
        listed = [s["id"] for s in client.get("/api/surveys").json()]
        assert listed == [waiting["id"], newer["id"], older["id"]]

    def test_the_page_shows_waiting_above_the_rest(self, client, computer):
        waiting = survey(client, taken="2026-11-01T09:00:00", **DISK)
        done = survey(client, taken="2026-11-02T09:00:00", TAG=computer()["asset_id"])
        page = content(client.get("/surveys").text)
        assert page.index(f"/surveys/{waiting['id']}") < page.index(f"/surveys/{done['id']}")

    def test_a_survey_with_a_failed_test_is_marked(self, client, computer):
        made = survey(client, TAG=computer()["asset_id"], RESULT="FAIL", TEST_CPU="FAIL")
        (listed,) = client.get("/api/surveys").json()
        assert listed["result"] == "FAIL"
        listed_row = row(content(client.get("/surveys").text), f"/surveys/{made['id']}")
        assert "failed" in listed_row.lower()


# --- a survey that waits for a machine -------------------------------------------------


class TestFilingASurveyThatWaits:
    def test_file_does_what_the_tag_typed_at_the_machine_would_have_done(self, client, computer):
        made = survey(client, CPU="80286", CPUKHZ="12000", **DISK)
        machine = computer()
        assert file_it(client, made, machine["asset_id"]).status_code == 303
        assert read(client, made["id"])["machine"] == machine["asset_id"]
        assert get(client, "computers", machine["asset_id"])["cpu"] == "80286-12"

    def test_filing_that_would_take_a_part_out_of_another_machine_says_so_first(
        self, client, computer, part
    ):
        other = computer()
        disk = part(
            type="storage",
            serial="QX123",
            computer_id=other["asset_id"],
            specs="Kind: Hard disk | Interface: IDE",
        )
        machine = computer()
        made = survey(client, TAG=machine["asset_id"], **DISK)
        asking = file_it(client, made, machine["asset_id"])
        assert asking.status_code == 200
        assert disk["asset_id"] in asking.text and other["asset_id"] in asking.text
        assert get(client, "parts", disk["asset_id"])["computer_id"] == other["asset_id"]
        assert file_it(client, made, machine["asset_id"], confirm="1").status_code == 303
        assert get(client, "parts", disk["asset_id"])["computer_id"] == machine["asset_id"]

    def test_new_computer_opens_the_form_with_what_the_survey_found(self, client):
        made = survey(
            client, CPU="486DX2", CPUVENDOR="GenuineIntel", CPUKHZ="66000", OS="MS-DOS 6.22"
        )
        form = client.get(f"/computers/new?survey={made['id']}")
        assert form.status_code == 200, form.text
        assert 'value="Intel 486DX2-66"' in form.text
        assert 'value="MS-DOS 6.22"' in form.text

    def test_saving_the_new_computer_files_the_survey_against_it(self, client):
        made = survey(client, CPU="80286", CPUKHZ="12000")
        r = client.post(
            "/computers/new",
            data={
                "manufacturer": "Amstrad",
                "model": "PC2286",
                "cpu": "80286-12",
                "survey": str(made["id"]),
            },
            follow_redirects=False,
        )
        assert r.status_code == 303, r.text
        aid = r.headers["location"].split("/")[2].split("?")[0]
        assert read(client, made["id"])["machine"] == aid


# --- a thing that waits for an answer ---------------------------------------------------


class TestAnsweringOnThePage:
    def test_a_survey_waiting_on_an_answer_has_done_everything_else(self, client, computer):
        machine = computer()
        made = survey(client, TAG=machine["asset_id"], CPU="80286", CPUKHZ="12000", **DISK)
        assert made["waiting"] == "answer"
        assert get(client, "computers", machine["asset_id"])["cpu"] == "80286-12"

    def test_new_part_makes_it_as_n_at_the_machine_would(self, client, computer):
        machine = computer()
        made = survey(client, TAG=machine["asset_id"], **DISK)
        assert answer(client, made, "DISK1", "new").status_code == 303
        after = read(client, made["id"])
        disk = get(client, "parts", finding(after, "DISK1")["part"])
        assert (disk["computer_id"], disk["serial"]) == (machine["asset_id"], "QX123")
        assert after["waiting"] is None

    def test_link_joins_a_part_the_register_has(self, client, computer, part):
        machine = computer()
        disk = part(
            type="storage", model="Fireball 1080AT", specs="Kind: Hard disk | Interface: IDE"
        )
        made = survey(client, TAG=machine["asset_id"], **DISK)
        assert answer(client, made, "DISK1", "link", tag=disk["asset_id"]).status_code == 303
        got = get(client, "parts", disk["asset_id"])
        assert (got["serial"], got["computer_id"]) == ("QX123", machine["asset_id"])

    def test_leave_out_leaves_it_out(self, client, computer):
        machine = computer()
        made = survey(client, TAG=machine["asset_id"], **DISK)
        assert answer(client, made, "DISK1", "out").status_code == 303
        after = read(client, made["id"])
        assert finding(after, "DISK1")["answer"] == "out"
        assert after["waiting"] is None
        assert client.get(f"/api/parts?computer_id={machine['asset_id']}").json() == []

    def test_part_of_the_machine_is_an_answer_a_card_may_be_given(self, client, computer):
        machine = computer()
        made = survey(client, TAG=machine["asset_id"], VIDEO="VGA")
        assert answer(client, made, "VIDEO", "machine").status_code == 303
        assert finding(read(client, made["id"]), "VIDEO")["answer"] == "machine"

    def test_an_answer_can_be_changed_afterwards(self, client, computer):
        machine = computer()
        made = survey(client, TAG=machine["asset_id"], DISK1_ANSWER="OUT", **DISK)
        assert answer(client, made, "DISK1", "new").status_code == 303
        assert finding(read(client, made["id"]), "DISK1")["answer"] == "part"


# --- a survey's own page ------------------------------------------------------------------


class TestASurveysPage:
    def test_it_shows_the_report_as_the_program_wrote_it(self, client, computer):
        made = survey(client, TAG=computer()["asset_id"])
        assert "DIAG 1.0  hardware report" in client.get(f"/surveys/{made['id']}").text

    def test_it_shows_the_machines_own_clock_beside_the_real_one(self, client, computer):
        made = survey(
            client,
            TAG=computer()["asset_id"],
            taken="2026-11-06T10:00:00",
            DATE="01/01/1980",
            TIME="00:01:12",
        )
        page = content(client.get(f"/surveys/{made['id']}").text)
        assert "01/01/1980" in page and "06/11/2026" in page

    def test_it_shows_the_text_in_each_rom(self, client, computer):
        made = survey(
            client,
            roms=[("BIOS.BIN", BIOS_ROM)],
            TAG=computer()["asset_id"],
            ROM1="F000 65536 BIOS.BIN",
        )
        assert "Award Modular BIOS v4.51PG" in client.get(f"/surveys/{made['id']}").text

    def test_it_shows_what_was_read_that_differs_from_the_record(self, client, computer):
        machine = computer(installed_ram="640KiB")
        made = survey(client, TAG=machine["asset_id"], RAMKB="512", EXTKB="0")
        page = content(client.get(f"/surveys/{made['id']}").text)
        assert "640 KiB" in page and "512 KiB" in page

    def test_it_shows_what_was_expected_and_not_found(self, client, computer, part):
        machine = computer()
        disk = part(
            type="storage",
            serial="QX123",
            computer_id=machine["asset_id"],
            specs="Kind: Hard disk | Interface: IDE",
        )
        made = survey(
            client,
            TAG=machine["asset_id"],
            DISK1_MODEL="CONNER CP30254",
            DISK1_SERIAL="CN-OTHER",
            DISK1_TYPE="ATA",
        )
        assert disk["asset_id"] in content(client.get(f"/surveys/{made['id']}").text)

    def test_delete_removes_a_survey_and_keeps_what_it_filled_in(self, client, computer):
        machine = computer()
        made = survey(
            client,
            roms=[("BIOS.BIN", BIOS_ROM)],
            TAG=machine["asset_id"],
            CPU="80286",
            CPUKHZ="12000",
            ROM1="F000 65536 BIOS.BIN",
            DISK1_ANSWER="OUT",
            **DISK,
        )
        assert (
            client.post(f"/surveys/{made['id']}/delete", follow_redirects=False).status_code == 303
        )
        assert client.get(f"/api/surveys/{made['id']}").status_code == 404
        assert get(client, "computers", machine["asset_id"])["cpu"] == "80286-12"
        assert len(client.get("/api/files").json()) == 1
        assert "QX123" in client.get("/surveys/seen").text


# --- Seen ------------------------------------------------------------------------------------


class TestSeen:
    def test_seen_lists_each_serial_number_and_address_with_what_it_belongs_to(
        self, client, computer
    ):
        machine = computer()
        made = survey(
            client, TAG=machine["asset_id"], DISK1_ANSWER="NEW", NIC_ANSWER="OUT", **DISK, **NIC
        )
        page = content(client.get("/surveys/seen").text)
        assert finding(made, "DISK1")["part"] in row(page, "QX123")
        assert "left out" in row(page, MAC).lower()

    def test_seen_says_a_plug_and_play_card_or_a_monitor_is_one(self, client, computer):
        survey(client, TAG=computer()["asset_id"], **AWE64, **edid())
        page = content(client.get("/surveys/seen").text)
        assert "Plug and Play card" in row(page, "CTL0045:1A2B3C4D")
        assert "Monitor" in row(page, "DELA0A3:9J0123A1B2C3")

    def test_seen_says_where_and_when_each_was_last_seen(self, client, computer):
        first, second = computer(), computer()
        survey(
            client, taken="2026-11-01T10:00:00", TAG=first["asset_id"], DISK1_ANSWER="OUT", **DISK
        )
        survey(client, taken="2026-11-05T10:00:00", TAG=second["asset_id"], **DISK)
        found = row(content(client.get("/surveys/seen").text), "QX123")
        assert second["asset_id"] in found and first["asset_id"] not in found
        assert "05/11/2026" in found

    def test_each_opens_the_last_survey_that_read_it(self, client, computer):
        first = survey(client, TAG=computer()["asset_id"], DISK1_ANSWER="OUT", **DISK)
        last = survey(client, TAG=computer()["asset_id"], **DISK)
        found = row(content(client.get("/surveys/seen").text), "QX123")
        assert f"/surveys/{last['id']}" in found and f"/surveys/{first['id']}" not in found

    def test_signed_in_a_search_finds_a_serial_number_a_survey_has_seen(self, client, computer):
        """So the number on a drive's label says where that drive has been, even if
        it was never made a part."""
        made = survey(client, TAG=computer()["asset_id"], DISK1_ANSWER="OUT", **DISK)
        found = content(client.get("/", params={"q": "QX123"}).text)
        assert f"/surveys/{made['id']}" in found


# --- who sees what ------------------------------------------------------------------------


class TestWhoSeesWhat:
    def test_a_visitor_is_never_shown_an_ethernet_address(self, client, computer):
        made = survey(client, TAG=computer()["asset_id"], NIC_ANSWER="NEW", **NIC)
        card = finding(made, "NIC")["part"]
        assert MAC in client.get(f"/parts/{card}").text
        log_out(client)
        page = client.get(f"/parts/{card}")
        assert page.status_code == 200
        assert MAC not in page.text

    def test_a_visitors_search_never_finds_an_ethernet_address(self, client, computer):
        made = survey(client, TAG=computer()["asset_id"], NIC_ANSWER="NEW", **NIC)
        card = finding(made, "NIC")["part"]
        assert card in content(client.get("/", params={"q": MAC}).text)
        log_out(client)
        assert card not in content(client.get("/", params={"q": MAC}).text)
        assert card not in client.get("/suggest", params={"q": MAC}).text

    def test_an_ethernet_address_is_never_printed_on_a_label(self, client, computer, db):
        made = survey(client, TAG=computer()["asset_id"], NIC_ANSWER="NEW", **NIC)
        card = db.get(Part, finding(made, "NIC")["part"])
        printed = labels.part_lines(to_dict(card), specdb.pairs(db, card))
        assert all(MAC not in line for line in printed)

    def test_a_hard_disks_serial_number_is_public_once_it_is_a_part(self, client, computer):
        made = survey(client, TAG=computer()["asset_id"], DISK1_ANSWER="NEW", **DISK)
        disk = finding(made, "DISK1")["part"]
        log_out(client)
        assert "QX123" in client.get(f"/parts/{disk}").text
        assert disk in content(client.get("/", params={"q": "QX123"}).text)

    def test_a_serial_number_that_belongs_to_nothing_is_kept_from_a_visitors_search(
        self, client, computer
    ):
        made = survey(client, TAG=computer()["asset_id"], DISK1_ANSWER="OUT", **DISK)
        log_out(client)
        assert f"/surveys/{made['id']}" not in client.get("/", params={"q": "QX123"}).text

    def test_a_visitor_sees_the_survey_line_and_not_the_link_to_it(self, client, computer):
        machine = computer()
        made = survey(client, TAG=machine["asset_id"])
        signed_in = content(client.get(f"/computers/{machine['asset_id']}").text)
        assert f"/surveys/{made['id']}" in signed_in
        log_out(client)
        visitor = content(client.get(f"/computers/{machine['asset_id']}").text)
        assert "Surveyed" in visitor
        assert f"/surveys/{made['id']}" not in visitor

    def test_the_survey_pages_are_walked_with_every_other_page(self, a_page_of_everything):
        """So they are held to the content policy and the accessibility rules like
        the rest (ADR-0021, ADR-0014): those tests walk this list."""
        walked = set(a_page_of_everything)
        assert {"/surveys", "/surveys/seen"} <= walked
        assert any(re.fullmatch(r"/surveys/\d+", page) for page in walked)
