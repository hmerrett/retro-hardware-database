"""A machine that reports itself (MANUAL §23, ADR-0043).

Started with a survey program, a machine tests itself and writes a report of what
it is made of. An agent beside it sends the report, and the register files it.
Everything a survey finds gets one of three answers: it is left out, it is part
of the machine, or it is a part of its own. The machine itself is one the register
has, or a new one. Every serial number and Ethernet address is recorded whatever
its answer, so nothing is new twice.

These are the manual's promises, one to a test and in the manual's order. Reports
are sent the way the agent sends them, through its own door with its own key, and
what became of them is read back through the API, as anything else is.
"""

from pathlib import Path

import pytest

from app import settings
from conftest import log_out
from survey_reports import (
    ADAPTEC_ROM,
    AGENTS,
    ANONYMOUS_ROM,
    AWE64,
    BIOS_ROM,
    BOOT_ROM,
    CHATTY_ROM,
    CIRRUS_ROM,
    CLONE_BIOS,
    COMPAQ_BIOS,
    COMPAQ_VGA_ROM,
    DELL_BIOS,
    DISK,
    HP_BIOS,
    MAC,
    NETBOOT_ROM,
    NIC,
    PRINTERS,
    QEMU_EDID,
    VGA_ROM,
    XTIDE_ROM,
    answer,
    ask,
    edid,
    finding,
    get,
    location,
    parts_in,
    read,
    report,
    send,
    survey,
)


@pytest.fixture(autouse=True)
def agents(monkeypatch):
    """Two agents, as the environment names them. The second prints the labels of
    the tags its surveys make on the workshop's printer."""
    monkeypatch.setenv("RHDB_SURVEY_AGENTS", AGENTS)


@pytest.fixture
def with_disk(computer, part):
    """A machine with an IDE disk fitted in it, the disk's serial number on file."""

    def make(serial="QX123", **fields):
        machine = computer(**fields)
        disk = part(
            type="storage",
            manufacturer="Quantum",
            model="Fireball 1080AT",
            serial=serial,
            computer_id=machine["asset_id"],
            specs="Kind: Hard disk | Interface: IDE",
        )
        return machine, disk

    return make


@pytest.fixture
def bench_card(client, computer, part):
    """A network card kept on the bench, its address recorded the way it is the
    first time: its tag typed at the machine it was started from."""

    def make(name="Bench 1"):
        bench = location(client, name, "bench")
        card = part(
            type="network", manufacturer="UMC", model="UM9003AF", location=bench["asset_id"]
        )
        first = computer()
        survey(client, TAG=first["asset_id"], NIC_ANSWER=card["asset_id"], **NIC)
        return card, bench

    return make


def computers(client) -> list[dict]:
    r = client.get("/api/computers")
    assert r.status_code == 200, r.text
    return r.json()


def all_parts(client) -> list[dict]:
    r = client.get("/api/parts")
    assert r.status_code == 200, r.text
    return r.json()


# --- what it takes ---------------------------------------------------------------


class TestWhatItTakes:
    def test_with_no_agent_named_the_register_takes_no_surveys(self, client, computer, monkeypatch):
        """Not an empty list: the feature does not exist until a key has been written
        down in the environment, as with the print agent."""
        monkeypatch.delenv("RHDB_SURVEY_AGENTS")
        machine = computer()
        r = send(client, report(TAG=machine["asset_id"], CPU="80286", CPUKHZ="12000"))
        assert r.status_code == 401, r.text
        assert not get(client, "computers", machine["asset_id"])["cpu"]

    def test_a_wrong_key_is_refused(self, client):
        assert send(client, report(), key="not-a-key").status_code == 401

    def test_the_agents_key_opens_its_own_door_and_nothing_else(self, client, computer):
        """Asked by somebody holding only the key: the suite's client is otherwise
        signed in as an administrator, and everything would answer."""
        machine = computer()
        log_out(client)
        head = {"Authorization": "Bearer key-one"}
        assert send(client, report()).status_code == 200
        assert client.get("/api/computers", headers=head).status_code == 401
        assert client.get(f"/api/computers/{machine['asset_id']}", headers=head).status_code == 401
        assert client.post("/api/computers", json={"model": "X"}, headers=head).status_code == 401
        assert client.get("/api/surveys", headers=head).status_code == 401
        # Not followed: the login page a visitor is sent to answers 200 itself.
        page = client.get("/surveys", headers=head, follow_redirects=False)
        assert page.status_code == 303 and page.headers["location"].startswith("/login")

    def test_a_tag_a_survey_makes_has_its_label_printed_on_the_agents_printer(
        self, client, monkeypatch
    ):
        """So a new machine's label is waiting by the time it is switched off."""
        monkeypatch.setenv("RHDB_PRINT_AGENTS", PRINTERS)
        made = survey(client, key="key-two", TAG="NEW")
        jobs = client.get("/api/print/jobs").json()
        assert [(j["agent"], j["asset_id"]) for j in jobs] == [("workshop-pi", made["machine"])]

    def test_an_agent_named_without_a_printer_prints_nothing(self, client, monkeypatch):
        monkeypatch.setenv("RHDB_PRINT_AGENTS", PRINTERS)
        survey(client, key="key-one", TAG="NEW")
        assert client.get("/api/print/jobs").json() == []


# --- at the machine: the question before the tests ----------------------------------


class TestAQuestionBeforeTheTests:
    def test_a_machine_the_register_recognises_is_named(self, client, with_disk):
        machine, _ = with_disk()
        assert ask(client, DISK1_SERIAL="QX123")["TAG"] == machine["asset_id"]

    def test_each_thing_found_is_given_the_answer_already_held(self, client, with_disk):
        _, disk = with_disk()
        assert ask(client, DISK1_SERIAL="QX123")["DISK1_ANSWER"] == disk["asset_id"]

    def test_a_card_kept_on_a_bench_is_answered_as_the_benchs(self, client, bench_card):
        card, _ = bench_card()
        assert ask(client, **NIC)["NIC_ANSWER"] == f"{card['asset_id']} BENCH"

    def test_something_left_out_is_answered_out(self, client, computer):
        machine = computer()
        survey(client, TAG=machine["asset_id"], DISK1_ANSWER="OUT", **DISK)
        assert ask(client, DISK1_SERIAL="QX123")["DISK1_ANSWER"] == "OUT"

    def test_a_question_carrying_the_tag_is_answered_for_that_machine(self, client, computer):
        """A thing with no serial number is known only in the machine it was answered
        in, so the answer for it needs the machine, which the person may have just
        typed."""
        machine = computer()
        survey(client, TAG=machine["asset_id"], VIDEO="VGA", VIDEO_ANSWER="OUT")
        assert ask(client, TAG=machine["asset_id"], VIDEO="VGA")["VIDEO_ANSWER"] == "OUT"
        assert "VIDEO_ANSWER" not in ask(client, VIDEO="VGA")

    def test_something_never_seen_has_no_answer(self, client):
        answered = ask(client, DISK1_SERIAL="NEVER-SEEN")
        assert "DISK1_ANSWER" not in answered and "TAG" not in answered

    def test_the_answer_names_each_thing_the_register_can_name(self, client):
        """So the machine shows each thing by that name, and asks its make and model
        only of what nobody can name: a card by its ROM, which comes with the
        question, a card on the PCI bus by its chip, a disk by its own model."""
        answered = ask(
            client,
            roms=[("VIDEO.C00", VGA_ROM)],
            VIDEO="VGA",
            ROM1="C000 32768 VIDEO.C00",
            PCI1="8086:1229 0200",
            **DISK,
        )
        assert answered["VIDEO_NAME"] == "Tseng Labs ET4000"
        assert answered["PCI1_NAME"] == "Intel 82557 EtherExpress PRO/100"
        assert answered["DISK1_NAME"] == "QUANTUM FIREBALL1080A"

    def test_what_the_register_can_only_describe_has_no_name(self, client):
        """A ROM that names nobody, a chip the PCI table does not know, the ports, and a
        disk the BIOS knows by its size alone."""
        answered = ask(
            client,
            roms=[("SCSI.C80", ANONYMOUS_ROM)],
            ROM1="C800 16384 SCSI.C80",
            PCI1="1234:5678 0401",
            COM1="03F8",
            DISK1_KB="21360",
            DISK1_CHS="615/4/17",
            DISK1_TYPE="BIOS",
        )
        assert [k for k in answered if k.endswith("_NAME")] == []

    def test_a_message_a_rom_prints_is_not_the_cards_name(self, client):
        """QEMU's VGA BIOS prints "cirrus mode switch regular", which names a maker and
        says nothing about the card."""
        answered = ask(
            client, roms=[("VIDEO.C00", CHATTY_ROM)], VIDEO="VGA", ROM1="C000 32768 VIDEO.C00"
        )
        assert "VIDEO_NAME" not in answered

    def test_a_machine_is_named_by_what_its_bios_says(self, client):
        answered = ask(
            client, SYSTEM_MAKER="Dell Computer Corporation", SYSTEM_MODEL="OptiPlex GX1"
        )
        assert answered["SYSTEM_NAME"] == "Dell Computer Corporation OptiPlex GX1"

    def test_a_bios_that_says_nothing_names_nothing(self, client):
        answered = ask(
            client, SYSTEM_MAKER="System manufacturer", SYSTEM_MODEL="System Product Name"
        )
        assert "SYSTEM_NAME" not in answered

    def test_a_question_without_its_roms_is_still_answered(self, client):
        """As an agent from before ROMs went with the question sends one: what a ROM
        would have named is unnamed, and the rest is answered as ever."""
        answered = ask(client, VIDEO="VGA", ROM1="C000 32768 VIDEO.C00", PCI1="8086:1229 0200")
        assert answered["PCI1_NAME"] == "Intel 82557 EtherExpress PRO/100"
        assert "VIDEO_NAME" not in answered

    def test_a_network_boot_rom_the_survey_could_not_place_is_the_cards(self, client):
        """netboot's ROM says neither that it is a network card's nor whose. Its text
        says it starts a machine from the network, so the register says which ROM it
        is, and the machine asks about it nowhere."""
        answered = ask(
            client, roms=[("NETBOOT.C80", NETBOOT_ROM)], ROM1="C800 16384 NETBOOT.C80", **NIC
        )
        assert answered["NIC_ROM"] == "C800"

    def test_two_roms_that_boot_from_the_network_are_left_to_be_answered(self, client):
        answered = ask(
            client,
            roms=[("A.C80", NETBOOT_ROM), ("B.D00", NETBOOT_ROM)],
            ROM1="C800 16384 A.C80",
            ROM2="D000 16384 B.D00",
            **NIC,
        )
        assert "NIC_ROM" not in answered

    def test_no_rom_is_given_to_a_card_no_packet_driver_ran(self, client):
        answered = ask(client, roms=[("A.C80", NETBOOT_ROM)], ROM1="C800 16384 A.C80")
        assert "NIC_ROM" not in answered

    def test_asking_with_roms_keeps_nothing(self, client):
        """The ROMs are read for what they say, and kept with the survey that sends
        them, not with the question."""
        ask(client, roms=[("BIOS.E80", BIOS_ROM)], ROM1="E800 98304 BIOS.E80")
        assert files(client) == []

    def test_asking_records_nothing(self, client):
        """A question is not a survey. Its serial numbers are recorded when the
        survey that carries them arrives."""
        ask(client, DISK1_SERIAL="QX999")
        seen = client.get("/surveys/seen")
        assert seen.status_code == 200, seen.text
        assert "QX999" not in seen.text

    def test_the_answer_to_a_survey_names_the_machine_and_what_is_waiting(self, client, computer):
        """It comes back to the machine's screen, so whoever is there knows it went
        and whether anything needs them."""
        machine = computer()
        r = send(client, report(TAG=machine["asset_id"], **DISK))
        assert r.status_code == 200, r.text
        receipt = r.json()["receipt"]
        assert machine["asset_id"] in receipt
        assert "1 thing" in receipt and "waiting" in receipt

    def test_the_answer_names_a_machine_with_no_name_by_its_tag_once(self, client):
        """A machine made at the machine has nothing to be called yet but its tag, and
        a screen reading "RH-9Q0D RH-9Q0D" looks like a fault."""
        r = send(client, report(TAG="NEW"))
        assert r.status_code == 200, r.text
        (made,) = r.json()["surveys"]
        assert r.json()["receipt"].splitlines()[0] == made["machine"]

    def test_the_answer_says_how_the_tests_went_in_the_historys_words(self, client, computer):
        """The tests' own names keep their capitals: RAM, not ram."""
        r = send(
            client,
            report(
                TAG=computer()["asset_id"],
                RESULT="FAIL",
                TESTS="17",
                FAILED="2",
                TEST_RAM="FAIL",
                TEST_FDC="FAIL",
            ),
        )
        assert r.status_code == 200, r.text
        assert "2 of 17 tests failed (RAM, floppy)." in r.json()["receipt"]


# --- at the machine: labels for what is new -----------------------------------------


def small_label_goes_to(client, destination: str) -> None:
    """The small label's Goes to, set as the settings page sets it."""
    rows = [d for d in settings.DEFINITIONS if d.section == settings.LABELS]
    posted = {
        d.key: settings.value(d.key)
        for d in rows
        if d.kind != settings.SWITCH or settings.on(d.key)
    }
    r = client.post("/settings/labels", data=posted | {"label_small_destination": destination})
    assert r.status_code in (200, 303), r.text[:300]
    settings.forget()


class TestLabelsForWhatIsNew:
    """Where the small label goes to a print agent's queue, a survey offers to print
    the small label of everything it makes, once, at the machine (MANUAL §23, "At the
    machine"; ADR-0049)."""

    @pytest.fixture(autouse=True)
    def printers(self, monkeypatch):
        monkeypatch.setenv("RHDB_PRINT_AGENTS", PRINTERS)

    def test_the_answer_offers_the_printer_the_small_label_goes_to(self, client):
        small_label_goes_to(client, "agent:workshop-pi")
        assert ask(client, **DISK)["LABELS"] == "workshop-pi"

    def test_nothing_is_offered_where_the_small_label_is_a_pdf(self, client):
        assert "LABELS" not in ask(client, **DISK)

    def test_an_agent_with_a_printer_of_its_own_is_not_asked(self, client):
        small_label_goes_to(client, "agent:workshop-pi")
        assert "LABELS" not in ask(client, key="key-two", **DISK)

    def test_yes_queues_the_small_label_of_everything_the_survey_makes(self, client):
        small_label_goes_to(client, "agent:workshop-pi")
        made = survey(client, TAG="NEW", DISK1_ANSWER="NEW", LABELS="YES", **DISK)
        jobs = client.get("/api/print/jobs").json()
        disk = finding(made, "DISK1")["part"]
        assert sorted((j["agent"], j["asset_id"], j["label"]) for j in jobs) == sorted(
            [("workshop-pi", made["machine"], "small"), ("workshop-pi", disk, "small")]
        )

    def test_without_yes_nothing_is_printed(self, client):
        small_label_goes_to(client, "agent:workshop-pi")
        survey(client, TAG="NEW", DISK1_ANSWER="NEW", **DISK)
        assert client.get("/api/print/jobs").json() == []

    def test_the_receipt_says_the_labels_were_sent(self, client):
        small_label_goes_to(client, "agent:workshop-pi")
        r = send(client, report(TAG="NEW", DISK1_ANSWER="NEW", LABELS="YES", **DISK))
        assert r.status_code == 200, r.text
        assert "2 small labels sent to workshop-pi." in r.json()["receipt"]

    def test_yes_queues_the_label_of_a_new_board(self, client):
        small_label_goes_to(client, "agent:workshop-pi")
        made = survey(client, TAG="NEW BOARD", LABELS="YES", **BOARDISH)
        jobs = client.get("/api/print/jobs").json()
        assert [(j["agent"], j["asset_id"], j["label"]) for j in jobs] == [
            ("workshop-pi", made["machine"], "small")
        ]


# --- which machine it is ---------------------------------------------------------


class TestWhichMachineItIs:
    def test_the_tag_typed_at_the_machine_files_the_survey_there(self, client, computer):
        machine = computer()
        made = survey(client, TAG=machine["asset_id"])
        assert made["machine"] == machine["asset_id"]
        assert made["how"] == "typed"

    def test_a_motherboards_tag_files_the_survey_against_the_board(self, client, part):
        """A bare board on the bench, tested before it goes back in a case."""
        board = part(type="motherboard")
        assert survey(client, TAG=board["asset_id"])["machine"] == board["asset_id"]

    def test_a_motherboard_fitted_in_a_machine_stands_for_the_machine(self, client, computer, part):
        machine = computer()
        board = part(type="motherboard", computer_id=machine["asset_id"])
        assert survey(client, TAG=board["asset_id"])["machine"] == machine["asset_id"]

    def test_n_at_the_machine_makes_a_new_computer(self, client):
        before = len(computers(client))
        made = survey(client, TAG="NEW", CPU="80286", CPUKHZ="12000")
        assert made["how"] == "new"
        assert len(computers(client)) == before + 1
        assert get(client, "computers", made["machine"])["cpu"] == "80286-12"

    def test_a_new_machine_is_named_by_the_make_and_model_typed_for_it(self, client):
        made = survey(client, TAG="NEW", SYSTEM_MAKER="IBM", SYSTEM_MODEL="5160")
        machine = get(client, "computers", made["machine"])
        assert (machine["manufacturer"], machine["model"]) == ("IBM", "5160")

    def test_what_was_typed_chooses_no_catalogue_model(self, client):
        """The catalogue names models its own way, and adopting one is a choice a
        person confirms."""
        made = survey(client, TAG="NEW", SYSTEM_MAKER="IBM", SYSTEM_MODEL="PC XT")
        assert get(client, "computers", made["machine"])["machine"] is None

    def test_a_new_computer_has_no_name_until_somebody_gives_it_one(self, client):
        """So it is called by its tag, as any machine with nothing filled in is."""
        made = get(client, "computers", survey(client, TAG="NEW")["machine"])
        assert (made["name"], made["manufacturer"], made["model"]) == ("", "", "")

    def test_a_machine_is_recognised_by_a_hard_disk_fitted_in_it(self, client, with_disk):
        machine, disk = with_disk()
        made = survey(client, **DISK)
        assert made["machine"] == machine["asset_id"]
        assert (made["how"], made["by"]) == ("recognised", disk["asset_id"])

    def test_a_machine_is_recognised_by_its_network_card(self, client, computer):
        machine = computer()
        survey(client, TAG=machine["asset_id"], NIC_ANSWER="NEW", **NIC)
        assert survey(client, **NIC)["machine"] == machine["asset_id"]

    def test_a_machine_is_recognised_by_a_network_chip_recorded_as_part_of_it(
        self, client, computer
    ):
        machine = computer()
        survey(client, TAG=machine["asset_id"], NIC_ANSWER="MACHINE", **NIC)
        assert survey(client, **NIC)["machine"] == machine["asset_id"]

    def test_a_machine_is_recognised_by_the_serial_number_its_bios_keeps(self, client, computer):
        machine = computer(serial="7XK2Q11")
        assert survey(client, SYSTEM_SERIAL="7XK2Q11")["machine"] == machine["asset_id"]

    def test_a_board_serial_number_recognises_the_machine_the_board_is_fitted_in(
        self, client, computer, part
    ):
        machine = computer()
        part(type="motherboard", serial="BRD-7", computer_id=machine["asset_id"])
        assert survey(client, BOARD_SERIAL="BRD-7")["machine"] == machine["asset_id"]

    def test_with_nothing_to_go_on_a_survey_waits_for_a_machine(self, client):
        made = survey(client, CPU="80286", CPUKHZ="12000", **DISK)
        assert made["machine"] is None
        assert made["waiting"] == "machine"

    def test_a_tag_that_disagrees_with_what_is_inside_waits_and_does_nothing(
        self, client, computer, with_disk
    ):
        typed = computer()
        with_disk()
        made = survey(client, TAG=typed["asset_id"], CPU="80286", CPUKHZ="12000", **DISK)
        assert made["waiting"] == "machine"
        assert not get(client, "computers", typed["asset_id"])["cpu"]

    def test_n_that_disagrees_with_what_is_inside_waits_and_makes_nothing(self, client, with_disk):
        with_disk()
        before = len(computers(client))
        assert survey(client, TAG="NEW", **DISK)["waiting"] == "machine"
        assert len(computers(client)) == before

    def test_b_at_the_machine_makes_a_new_motherboard_and_no_computer(self, client):
        """A bare board on the bench that the register does not have yet (ADR-0052)."""
        before = len(computers(client))
        made = survey(client, TAG="NEW BOARD", **BOARDISH)
        assert made["how"] == "new"
        assert len(computers(client)) == before
        assert get(client, "parts", made["machine"])["type"] == "motherboard"

    def test_b_that_disagrees_with_what_is_inside_waits_and_makes_nothing(self, client, with_disk):
        _machine, disk = with_disk()
        before = len(all_parts(client))
        made = survey(client, TAG="NEW BOARD", **DISK)
        assert made["waiting"] == "machine"
        assert disk["asset_id"] in made["reason"]
        assert len(all_parts(client)) == before

    def test_b_for_a_board_the_register_has_waits_rather_than_add_it_twice(self, client, part):
        """With N, a board known by its serial number is going into the new case; with
        B it is the board itself."""
        board = part(type="motherboard", model="P5A", serial="MB-13")
        before = len(all_parts(client))
        made = survey(client, TAG="NEW BOARD", BOARD_SERIAL="MB-13", **BOARDISH)
        assert made["waiting"] == "machine"
        assert board["asset_id"] in made["reason"]
        assert len(all_parts(client)) == before

    def test_insides_that_point_at_two_machines_wait(self, client, computer, with_disk):
        with_disk()
        computer(serial="7XK2Q11")
        assert survey(client, SYSTEM_SERIAL="7XK2Q11", **DISK)["waiting"] == "machine"

    @pytest.mark.parametrize("what", ["part", "location", "project", "disposed"])
    def test_a_tag_that_is_not_a_machine_or_a_motherboard_waits(self, client, computer, part, what):
        if what == "part":
            tag = part(type="video")["asset_id"]
        elif what == "location":
            tag = location(client, "Shelf 2", "shelf")["asset_id"]
        elif what == "project":
            tag = client.post("/api/projects", json={"name": "Recap"}).json()["asset_id"]
        else:
            tag = computer()["asset_id"]
            r = client.patch(f"/api/computers/{tag}", json={"disposed": True})
            assert r.status_code == 200, r.text
        assert survey(client, TAG=tag)["waiting"] == "machine"

    def test_a_tag_the_register_never_issued_makes_nothing(self, client):
        """The register issues every tag, so a tag it never issued is a typing
        mistake, never a new record."""
        before = len(computers(client))
        assert survey(client, TAG="RH-ZZZZ")["waiting"] == "machine"
        assert len(computers(client)) == before
        assert client.get("/api/computers/RH-ZZZZ").status_code == 404

    def test_a_card_kept_on_a_bench_never_says_which_machine_this_is(self, client, bench_card):
        bench_card()
        assert survey(client, **NIC)["waiting"] == "machine"


# --- what it does with what it finds -----------------------------------------------


class TestWhatItDoesWithWhatItFinds:
    def test_what_is_always_part_of_the_machine_is_never_asked_about(self, client, computer):
        machine = computer()
        made = survey(
            client,
            TAG=machine["asset_id"],
            CPU="80286",
            CPUKHZ="12000",
            RAMKB="640",
            OS="MS-DOS 6.22",
        )
        assert made["waiting"] is None
        for thing in ("CPU", "MEMORY", "OS"):
            assert finding(made, thing)["answer"] == "machine"

    def test_a_hard_disk_cannot_be_part_of_the_machine(self, client, computer):
        """The register keeps a hard disk as a part of its own, so a disk answered as
        part of the machine has not been answered."""
        machine = computer()
        made = survey(client, TAG=machine["asset_id"], DISK1_ANSWER="MACHINE", **DISK)
        assert finding(made, "DISK1")["answer"] is None
        assert made["waiting"] == "answer"
        assert answer(client, made, "DISK1", "machine").status_code == 400

    def test_a_card_may_be_part_of_the_machine(self, client, computer, part):
        machine = computer()
        board = part(type="motherboard", computer_id=machine["asset_id"])
        made = survey(client, TAG=machine["asset_id"], VIDEO="VGA", VIDEO_ANSWER="MACHINE")
        assert finding(made, "VIDEO")["answer"] == "machine"
        assert "Onboard video" in get(client, "parts", board["asset_id"])["specs"]

    def test_an_answer_is_remembered_for_the_same_thing_in_the_same_machine(self, client, computer):
        machine = computer()
        survey(client, TAG=machine["asset_id"], VIDEO="VGA", VIDEO_ANSWER="OUT")
        again = survey(client, TAG=machine["asset_id"], VIDEO="VGA")
        assert finding(again, "VIDEO")["answer"] == "out"
        assert again["waiting"] is None

    def test_a_thing_with_a_serial_number_is_known_wherever_it_turns_up(self, client, computer):
        first, second = computer(), computer()
        survey(client, TAG=first["asset_id"], DISK1_ANSWER="OUT", **DISK)
        elsewhere = survey(client, TAG=second["asset_id"], **DISK)
        assert finding(elsewhere, "DISK1")["answer"] == "out"
        assert elsewhere["waiting"] is None

    def test_a_thing_with_no_serial_number_is_known_only_in_the_machine_it_was_answered_in(
        self, client, computer
    ):
        """A VGA card in one machine says nothing about the VGA card in another."""
        first, second = computer(), computer()
        survey(client, TAG=first["asset_id"], VIDEO="VGA", VIDEO_ANSWER="OUT")
        elsewhere = survey(client, TAG=second["asset_id"], VIDEO="VGA")
        assert finding(elsewhere, "VIDEO")["answer"] is None
        assert elsewhere["waiting"] == "answer"

    def test_two_of_the_same_in_one_machine_are_counted(self, client, computer):
        """The survey cannot tell which is which, so the second is the new one."""
        machine = computer()
        nic = "10EC:8029 0200"
        survey(client, TAG=machine["asset_id"], PCI1=nic, PCI1_ANSWER="NEW")
        again = survey(client, TAG=machine["asset_id"], PCI1=nic, PCI2=nic)
        answers = sorted(str(finding(again, t)["answer"]) for t in ("PCI1", "PCI2"))
        assert answers == ["None", "part"]
        assert again["waiting"] == "answer"

    def test_the_network_card_is_one_thing_however_the_survey_sees_it(self, client, computer):
        """By its address, and on the PCI bus: the card the survey ran through is asked
        about once, and a new one is named by its chip where the register knows it."""
        made = survey(
            client, TAG=computer()["asset_id"], PCI1="8086:1229 0200", NIC_ANSWER="NEW", **NIC
        )
        assert [f["thing"] for f in made["findings"] if f["kind"] != "machine"] == ["NIC"]
        assert made["waiting"] is None
        card = get(client, "parts", finding(made, "NIC")["part"])
        assert (card["manufacturer"], card["model"]) == ("Intel", "82557 EtherExpress PRO/100")

    def test_a_second_network_card_on_the_pci_bus_is_a_card_of_its_own(self, client, computer):
        made = survey(
            client,
            TAG=computer()["asset_id"],
            PCI1="8086:1229 0200",
            PCI2="10EC:8029 0200",
            **NIC,
        )
        assert all(f["thing"] != "PCI1" for f in made["findings"])
        assert finding(made, "PCI2")["answer"] is None

    def test_an_answer_that_no_longer_holds_is_asked_again(self, client, computer, part):
        machine = computer()
        card = part(type="video", model="ET4000", computer_id=machine["asset_id"])
        survey(client, TAG=machine["asset_id"], VIDEO="VGA", VIDEO_ANSWER=card["asset_id"])
        r = client.patch(f"/api/parts/{card['asset_id']}", json={"computer_id": None})
        assert r.status_code == 200, r.text
        again = survey(client, TAG=machine["asset_id"], VIDEO="VGA")
        assert finding(again, "VIDEO")["answer"] is None

    def test_what_the_register_expected_and_did_not_find_is_listed_and_left(
        self, client, with_disk
    ):
        """A disk recorded in the machine that did not answer when the others did. It
        is there to be looked at: nothing is moved, and nothing is deleted."""
        machine, disk = with_disk()
        made = survey(
            client,
            TAG=machine["asset_id"],
            DISK1_MODEL="CONNER CP30254",
            DISK1_SERIAL="CN-OTHER",
            DISK1_TYPE="ATA",
        )
        assert disk["asset_id"] in made["missing"]
        assert get(client, "parts", disk["asset_id"])["computer_id"] == machine["asset_id"]


# --- drives -------------------------------------------------------------------------

# A floppy drive as the BIOS has it, and a CD-ROM drive and a CompactFlash card as
# they describe themselves through IDENTIFY.
FLOPPY = {"FLOPPY1": "1.44M"}
CDROM = {"DISK2_MODEL": "MITSUMI CRMC-FX001D", "DISK2_SERIAL": "CD-77", "DISK2_TYPE": "ATAPI"}
CFCARD = {
    "DISK1_MODEL": "SanDisk SDCFB-128",
    "DISK1_SERIAL": "CF-123",
    "DISK1_TYPE": "CFA",
    "DISK1_KB": "125184",
    "DISK1_CHS": "978/8/32",
}
FLOPPY_SPECS = 'Kind: Floppy/Gotek | Interface: 34-pin floppy | Media: 3.5" | Size: 1.44MB'


class TestDrives:
    """A floppy drive, a CD-ROM drive and a CompactFlash card are asked about like any
    other thing, and what the register already has of them is not asked (MANUAL §23,
    "What it does with what it finds"; ADR-0048)."""

    def test_each_drive_is_asked_about_with_all_three_answers(self, client, computer):
        made = survey(client, TAG=computer()["asset_id"], **FLOPPY, **CDROM, **CFCARD)
        for thing in ("FLOPPY1", "DISK2", "DISK1"):
            assert finding(made, thing)["fits"] == ["part", "machine", "out"]
            assert finding(made, thing)["answer"] is None
        assert made["waiting"] == "answer"

    def test_n_makes_a_floppy_drive_named_by_what_was_typed(self, client, computer):
        machine = computer()
        made = survey(
            client,
            TAG=machine["asset_id"],
            FLOPPY1_ANSWER="NEW",
            FLOPPY1_MAKER="TEAC",
            FLOPPY1_MODEL="FD-235HF",
            **FLOPPY,
        )
        drive = get(client, "parts", finding(made, "FLOPPY1")["part"])
        assert (drive["type"], drive["manufacturer"], drive["model"]) == (
            "storage",
            "TEAC",
            "FD-235HF",
        )
        assert "Kind: Floppy/Gotek" in drive["specs"] and "Size: 1.44MB" in drive["specs"]
        assert drive["computer_id"] == machine["asset_id"]

    def test_n_makes_a_cd_rom_drive_or_a_card_named_by_itself(self, client, computer):
        made = survey(
            client,
            TAG=computer()["asset_id"],
            DISK2_ANSWER="NEW",
            DISK1_ANSWER="NEW",
            **CDROM,
            **CFCARD,
        )
        cd = get(client, "parts", finding(made, "DISK2")["part"])
        assert (cd["model"], cd["serial"]) == ("MITSUMI CRMC-FX001D", "CD-77")
        assert "Kind: Optical" in cd["specs"]
        card = get(client, "parts", finding(made, "DISK1")["part"])
        assert (card["model"], card["serial"]) == ("SanDisk SDCFB-128", "CF-123")
        assert "Kind: SD/CF card" in card["specs"] and "978/8/32" in card["specs"]

    def test_m_writes_a_row_in_the_machines_drives(self, client, computer):
        machine = computer()
        survey(
            client,
            TAG=machine["asset_id"],
            FLOPPY1="1.44M",
            FLOPPY2="1.2M",
            DISK3_MODEL="MITSUMI CRMC-FX001D",
            DISK3_TYPE="ATAPI",
            FLOPPY1_ANSWER="MACHINE",
            FLOPPY2_ANSWER="MACHINE",
            DISK3_ANSWER="MACHINE",
        )
        drives = get(client, "computers", machine["asset_id"])["drives"]
        assert "1.44MB" in drives and "1.2MB" in drives and "CRMC-FX001D" in drives

    def test_a_drive_its_rows_already_record_is_part_of_the_machine(self, client, computer):
        machine = computer(drives='3.5" 1.44MB floppy')
        before = get(client, "computers", machine["asset_id"])["drives"]
        assert ask(client, TAG=machine["asset_id"], **FLOPPY)["FLOPPY1_ANSWER"] == "MACHINE"
        made = survey(client, TAG=machine["asset_id"], **FLOPPY)
        assert finding(made, "FLOPPY1")["answer"] == "machine"
        assert made["waiting"] is None
        assert get(client, "computers", machine["asset_id"])["drives"] == before

    def test_a_row_stands_for_as_many_drives_as_it_counts(self, client, computer):
        machine = computer(drives='2 x 3.5" 1.44MB floppy')
        made = survey(client, TAG=machine["asset_id"], FLOPPY1="1.44M", FLOPPY2="1.44M")
        assert [finding(made, t)["answer"] for t in ("FLOPPY1", "FLOPPY2")] == [
            "machine",
            "machine",
        ]

    def test_a_gotek_row_stands_for_a_floppy_drive(self, client, computer):
        machine = computer(drives="Gotek")
        made = survey(client, TAG=machine["asset_id"], **FLOPPY)
        assert finding(made, "FLOPPY1")["answer"] == "machine"

    def test_rows_for_cd_rom_drives_and_cards_stand_for_them(self, client, computer):
        machine = computer(drives="CD-ROM; CF card")
        made = survey(client, TAG=machine["asset_id"], **CDROM, **CFCARD)
        assert [finding(made, t)["answer"] for t in ("DISK2", "DISK1")] == [
            "machine",
            "machine",
        ]

    def test_a_drive_its_rows_do_not_record_is_asked(self, client, computer):
        """The BIOS has a 1.44MB drive where the record has a 1.2MB one."""
        machine = computer(drives='5.25" 1.2MB floppy')
        before = get(client, "computers", machine["asset_id"])["drives"]
        made = survey(client, TAG=machine["asset_id"], **FLOPPY)
        assert finding(made, "FLOPPY1")["answer"] is None
        assert get(client, "computers", machine["asset_id"])["drives"] == before

    def test_a_drive_fitted_in_it_as_a_part_is_that_part(self, client, computer, part):
        machine = computer()
        drive = part(
            type="storage",
            manufacturer="NEC",
            model="FD1231T",
            specs=FLOPPY_SPECS,
            computer_id=machine["asset_id"],
        )
        assert ask(client, TAG=machine["asset_id"], **FLOPPY)["FLOPPY1_ANSWER"] == drive["asset_id"]
        made = survey(client, TAG=machine["asset_id"], **FLOPPY)
        assert finding(made, "FLOPPY1")["part"] == drive["asset_id"]
        assert get(client, "computers", machine["asset_id"])["drives"] == ""

    def test_a_fitted_drive_with_another_serial_is_another_drive(self, client, computer, part):
        machine = computer()
        part(
            type="storage",
            model="MITSUMI CRMC-FX001D",
            serial="CD-OTHER",
            specs="Kind: Optical | Interface: IDE",
            computer_id=machine["asset_id"],
        )
        made = survey(client, TAG=machine["asset_id"], **CDROM)
        assert finding(made, "DISK2")["answer"] is None

    def test_an_answer_for_a_floppy_drive_is_remembered(self, client, computer):
        machine = computer()
        survey(client, TAG=machine["asset_id"], FLOPPY1_ANSWER="OUT", **FLOPPY)
        again = survey(client, TAG=machine["asset_id"], **FLOPPY)
        assert finding(again, "FLOPPY1")["answer"] == "out"

    def test_a_cd_rom_drive_is_known_by_its_serial_and_says_which_machine(self, client, computer):
        machine = computer()
        first = survey(client, TAG=machine["asset_id"], DISK2_ANSWER="NEW", **CDROM)
        again = survey(client, **CDROM)
        assert again["machine"] == machine["asset_id"]
        assert finding(again, "DISK2")["part"] == finding(first, "DISK2")["part"]


# --- what it could not see ---------------------------------------------------------


class TestWhatItCouldNotSee:
    """After the things it found, a survey asks about what it could not see: the parts
    on record it did not find, and anything else fitted. It looks for a sound card and
    expanded memory itself (MANUAL §23, "At the machine" and "What it does with what it
    finds"; ADR-0050)."""

    def test_the_answer_names_each_part_on_record_it_did_not_find(self, client, computer, part):
        machine = computer()
        sound = part(
            type="sound",
            manufacturer="Creative",
            model="Sound Blaster Pro",
            computer_id=machine["asset_id"],
        )
        answered = ask(client, TAG=machine["asset_id"])
        assert answered["KEPT1"] == f"{sound['asset_id']} Creative Sound Blaster Pro"

    def test_a_part_the_survey_found_is_not_named_again(self, client, with_disk):
        machine, _disk = with_disk()
        answered = ask(client, TAG=machine["asset_id"], **DISK)
        assert not [k for k in answered if k.startswith("KEPT")]

    def test_a_part_said_to_be_taken_out_leaves_the_machine(self, client, computer, part):
        machine = computer()
        sound = part(type="sound", model="Sound Blaster Pro", computer_id=machine["asset_id"])
        survey(client, TAG=machine["asset_id"], GONE1=sound["asset_id"])
        got = get(client, "parts", sound["asset_id"])
        assert not got["computer_id"] and not got["location"]

    def test_only_a_part_in_this_machine_is_taken_out(self, client, computer, part):
        other = computer()
        sound = part(type="sound", model="Sound Blaster Pro", computer_id=other["asset_id"])
        survey(client, TAG=computer()["asset_id"], GONE1=sound["asset_id"])
        assert get(client, "parts", sound["asset_id"])["computer_id"] == other["asset_id"]

    def test_a_tag_given_for_anything_else_fits_that_part(self, client, computer, part):
        shelf = location(client, "Shelf 3", "shelf")
        card = part(type="ram", model="RAM 3000", location=shelf["asset_id"])
        machine = computer()
        survey(client, TAG=machine["asset_id"], EXTRA1_ANSWER=card["asset_id"])
        assert get(client, "parts", card["asset_id"])["computer_id"] == machine["asset_id"]

    def test_n_for_anything_else_makes_a_part_named_by_what_was_typed(self, client, computer):
        machine = computer()
        made = survey(
            client,
            TAG=machine["asset_id"],
            EXTRA1_ANSWER="NEW",
            EXTRA1_MAKER="Everex",
            EXTRA1_MODEL="RAM 3000",
        )
        card = get(client, "parts", finding(made, "EXTRA1")["part"])
        assert (card["manufacturer"], card["model"], card["computer_id"]) == (
            "Everex",
            "RAM 3000",
            machine["asset_id"],
        )

    def test_a_sound_blaster_is_found_and_asked_its_make(self, client, computer):
        """A clone answers as a Sound Blaster does, so the card is not named by it."""
        made = survey(client, TAG=computer()["asset_id"], SOUND="220 3.02")
        found = finding(made, "SOUND")
        assert found["fits"] == ["part", "machine", "out"]
        assert "Sound Blaster Pro" in found["name"]
        assert "SOUND_NAME" not in ask(client, SOUND="220 3.02")

    def test_n_makes_a_sound_card(self, client, computer):
        made = survey(
            client,
            TAG=computer()["asset_id"],
            SOUND="220 3.02",
            SOUND_ANSWER="NEW",
            SOUND_MAKER="Creative",
            SOUND_MODEL="Sound Blaster Pro",
        )
        card = get(client, "parts", finding(made, "SOUND")["part"])
        assert (card["type"], card["manufacturer"], card["model"]) == (
            "sound",
            "Creative",
            "Sound Blaster Pro",
        )

    def test_an_adlib_alone_is_a_sound_card(self, client, computer):
        made = survey(client, TAG=computer()["asset_id"], ADLIB="388")
        assert finding(made, "ADLIB")["fits"] == ["part", "machine", "out"]

    def test_an_adlib_beside_a_sound_blaster_is_the_sound_blasters(self, client, computer):
        made = survey(client, TAG=computer()["asset_id"], SOUND="220 3.02", ADLIB="388")
        assert [f["thing"] for f in made["findings"] if f["thing"] in ("SOUND", "ADLIB")] == [
            "SOUND"
        ]

    def test_expanded_memory_on_an_at_is_a_memory_card(self, client, computer):
        made = survey(
            client,
            TAG=computer()["asset_id"],
            CPU="80286",
            EMS_KB="2048",
            EMS_ANSWER="NEW",
            EMS_MAKER="Everex",
            EMS_MODEL="RAM 3000",
        )
        card = get(client, "parts", finding(made, "EMS")["part"])
        assert (card["type"], card["manufacturer"], card["model"]) == ("ram", "Everex", "RAM 3000")

    def test_expanded_memory_on_a_386_is_not_a_card(self, client, computer):
        made = survey(client, TAG=computer()["asset_id"], CPU="80386", EMS_KB="2048")
        assert not [f for f in made["findings"] if f["thing"] == "EMS"]

    def test_an_answer_for_a_sound_card_is_remembered(self, client, computer):
        machine = computer()
        survey(client, TAG=machine["asset_id"], SOUND="220 3.02", SOUND_ANSWER="OUT")
        again = survey(client, TAG=machine["asset_id"], SOUND="220 3.02")
        assert finding(again, "SOUND")["answer"] == "out"

    def test_the_page_says_a_built_in_card_is_on_the_motherboard(self, client, computer):
        made = survey(client, TAG=computer()["asset_id"], VIDEO="VGA", VIDEO_ANSWER="MACHINE")
        page = client.get(f"/surveys/{made['id']}")
        assert page.status_code == 200, page.text
        assert "built into the motherboard." in page.text


# --- serial numbers and addresses --------------------------------------------------


class TestWhatTheHardwareSays:
    """What a survey finds by asking the hardware itself: Plug and Play cards, a
    monitor, the video card's chip, a Gravis UltraSound and an MPU-401, and what the
    ports are (MANUAL §23, "What it does with what it finds"; ADR-0051)."""

    # Plug and Play cards

    def test_a_plug_and_play_card_is_named_by_its_maker_and_its_own_name(self, client, computer):
        made = survey(client, TAG=computer()["asset_id"], **AWE64)
        assert finding(made, "PNP1")["fits"] == ["part", "machine", "out"]
        assert ask(client, **AWE64)["PNP1_NAME"] == "Creative Labs SB AWE64 PnP"

    def test_n_makes_a_part_of_its_maker_and_model(self, client, computer):
        made = survey(client, TAG=computer()["asset_id"], PNP1_ANSWER="NEW", **AWE64)
        card = get(client, "parts", finding(made, "PNP1")["part"])
        assert (card["type"], card["manufacturer"], card["model"]) == (
            "sound",
            "Creative Labs",
            "SB AWE64 PnP",
        )

    def test_its_serial_number_is_not_written_as_the_parts(self, client, computer):
        """It is printed on no label, so it is not what the field holds."""
        made = survey(client, TAG=computer()["asset_id"], PNP1_ANSWER="NEW", **AWE64)
        assert not get(client, "parts", finding(made, "PNP1")["part"])["serial"]

    def test_it_is_known_by_its_serial_number_wherever_it_turns_up(self, client, computer):
        survey(client, TAG=computer()["asset_id"], PNP1_ANSWER="OUT", **AWE64)
        again = survey(client, TAG=computer()["asset_id"], **AWE64)
        assert finding(again, "PNP1")["answer"] == "out"

    def test_one_whose_serial_number_says_nothing_is_known_per_machine(self, client, computer):
        card = AWE64 | {"PNP1": "CTL0045 FFFFFFFF"}
        machine = computer()
        survey(client, TAG=machine["asset_id"], PNP1_ANSWER="OUT", **card)
        assert finding(survey(client, TAG=machine["asset_id"], **card), "PNP1")["answer"] == "out"
        assert finding(survey(client, TAG=computer()["asset_id"], **card), "PNP1")["answer"] is None

    def test_a_plug_and_play_card_says_which_machine_it_is(self, client, computer):
        machine = computer()
        survey(client, TAG=machine["asset_id"], PNP1_ANSWER="NEW", **AWE64)
        assert ask(client, **AWE64)["TAG"] == machine["asset_id"]

    def test_a_sound_blaster_at_its_ports_is_that_card(self, client, computer):
        made = survey(
            client,
            TAG=computer()["asset_id"],
            SOUND="220 4.13",
            MPU="330",
            GUS="240 1024",
            **AWE64 | {"PNP1_IO": "220 240 330 388"},
        )
        assert [f["thing"] for f in made["findings"] if f["kind"] == "card"] == ["PNP1"]

    def test_the_machine_is_told_so_it_asks_about_the_card_once(self, client):
        answered = ask(client, SOUND="220 4.13", MPU="330", **AWE64)
        assert (answered["SOUND_ANSWER"], answered["MPU_ANSWER"]) == ("PNP1", "PNP1")

    def test_a_sound_blaster_16s_mpu_401_is_asked_about_once(self, client):
        assert ask(client, SOUND="220 4.13", MPU="330")["MPU_ANSWER"] == "SOUND"

    def test_a_plug_and_play_network_card_is_the_network_card(self, client, computer):
        card = {
            "PNP1": "TCM5090 0012AB34",
            "PNP1_ANSI": "3Com 3C509B EtherLink III",
            "PNP1_IO": "300",
        }
        made = survey(client, TAG=computer()["asset_id"], **NIC, **card)
        assert not [f for f in made["findings"] if f["thing"] == "PNP1"]
        answered = ask(client, **NIC, **card)
        assert answered["NIC_NAME"] == "3Com 3C509B EtherLink III"
        assert answered["PNP1_ANSWER"] == "NIC"

    # A monitor

    def test_a_monitor_is_named_by_its_maker_and_model(self, client, computer):
        made = survey(client, TAG=computer()["asset_id"], **edid())
        assert finding(made, "MONITOR")["fits"] == ["part", "out"]
        assert ask(client, **edid())["MONITOR_NAME"] == "Dell P1110"

    def test_qemus_monitor_is_named_from_what_it_gave(self, client, computer):
        made = survey(client, TAG=computer()["asset_id"], **QEMU_EDID)
        assert finding(made, "MONITOR")["name"] == "Red Hat QEMU Monitor"
        assert ask(client, **QEMU_EDID)["MONITOR_NAME"] == "Red Hat QEMU Monitor"

    def test_n_makes_a_display_with_its_serial_number(self, client, computer):
        machine = computer()
        made = survey(client, TAG=machine["asset_id"], **edid(), MONITOR_ANSWER="NEW")
        screen = get(client, "parts", finding(made, "MONITOR")["part"])
        assert (screen["type"], screen["manufacturer"], screen["model"], screen["serial"]) == (
            "display",
            "Dell",
            "P1110",
            "9J0123A1B2C3",
        )
        assert screen["computer_id"] == machine["asset_id"]

    def test_a_monitor_is_known_by_its_serial_number_wherever_it_turns_up(self, client, computer):
        survey(client, TAG=computer()["asset_id"], **edid(), MONITOR_ANSWER="OUT")
        again = survey(client, TAG=computer()["asset_id"], **edid())
        assert finding(again, "MONITOR")["answer"] == "out"

    def test_its_number_serves_where_it_writes_none_out(self, client, computer, part):
        screen = part(type="display", manufacturer="Dell", model="P1110", serial="19088743")
        made = survey(client, TAG=computer()["asset_id"], **edid(number=0x01234567, serial=""))
        assert finding(made, "MONITOR")["part"] == screen["asset_id"]

    def test_one_that_gives_no_serial_number_is_known_per_machine(self, client, computer):
        blank = edid(number=0x01010101, serial="")
        machine = computer()
        survey(client, TAG=machine["asset_id"], **blank, MONITOR_ANSWER="OUT")
        assert (
            finding(survey(client, TAG=machine["asset_id"], **blank), "MONITOR")["answer"] == "out"
        )
        assert (
            finding(survey(client, TAG=computer()["asset_id"], **blank), "MONITOR")["answer"]
            is None
        )

    def test_a_monitor_does_not_say_which_machine_it_is(self, client, computer):
        machine = computer()
        survey(client, TAG=machine["asset_id"], **edid(), MONITOR_ANSWER="NEW")
        assert "TAG" not in ask(client, **edid())

    def test_the_benchs_monitor_is_left_on_the_bench(self, client, computer, part):
        bench = location(client, "Bench 1", "bench")
        screen = part(
            type="display", model="P1110", serial="9J0123A1B2C3", location=bench["asset_id"]
        )
        survey(client, TAG=computer()["asset_id"], **edid())
        assert get(client, "parts", screen["asset_id"])["location"] == bench["asset_id"]

    def test_the_page_offers_to_add_a_monitor_to_the_bench(self, client, computer):
        location(client, "Bench 1", "bench")
        made = survey(client, TAG=computer()["asset_id"], **edid())
        page = client.get(f"/surveys/{made['id']}")
        assert page.status_code == 200, page.text
        assert 'value="bench"' in page.text

    # The video card's chip

    def test_a_vga_card_is_named_by_its_chip_where_nothing_else_names_it(self, client, computer):
        assert ask(client, VIDEO="VGA", VIDEO_CHIP="TSENG 40")["VIDEO_NAME"] == "Tseng Labs ET4000"

    def test_qemus_isa_cirrus_card_is_named_by_its_chip(self, client, computer):
        assert ask(client, VIDEO="VGA", VIDEO_CHIP="CIRRUS A0")["VIDEO_NAME"] == (
            "Cirrus Logic CL-GD5430"
        )

    def test_a_later_s3_is_named_by_its_second_id(self, client, computer):
        assert ask(client, VIDEO="VGA", VIDEO_CHIP="S3 E1 11")["VIDEO_NAME"] == "S3 Trio64"

    def test_a_wd_chip_is_named_by_the_digits_in_its_registers(self, client, computer):
        name = ask(client, VIDEO="VGA", VIDEO_CHIP="WD 33 31")["VIDEO_NAME"]
        assert name == "Western Digital WD90C31"

    def test_a_chip_on_the_pci_bus_is_named_by_the_bus(self, client, computer):
        answered = ask(client, VIDEO="VGA", VIDEO_CHIP="TSENG 40", PCI1="5333:8811 0300")
        assert "Tseng" not in answered.get("VIDEO_NAME", "")

    def test_n_makes_a_video_card_of_its_chip(self, client, computer):
        made = survey(
            client,
            TAG=computer()["asset_id"],
            VIDEO="VGA",
            VIDEO_CHIP="TSENG 40",
            VIDEO_ANSWER="NEW",
        )
        card = get(client, "parts", finding(made, "VIDEO")["part"])
        assert (card["type"], card["manufacturer"], card["model"]) == (
            "video",
            "Tseng Labs",
            "ET4000",
        )

    def test_its_rom_names_it_before_its_chip(self, client, computer):
        answered = ask(
            client,
            roms=[("RH0001.C00", CIRRUS_ROM)],
            VIDEO="VGA",
            VIDEO_CHIP="TSENG 40",
            ROM1="C000 32768 RH0001.C00",
        )
        assert answered["VIDEO_NAME"] == "Cirrus Logic CL-GD5428"

    def test_an_answer_given_before_its_chip_was_read_still_holds(self, client, computer):
        machine = computer()
        survey(client, TAG=machine["asset_id"], VIDEO="VGA", VIDEO_ANSWER="OUT")
        again = survey(client, TAG=machine["asset_id"], VIDEO="VGA", VIDEO_CHIP="TSENG 40")
        assert finding(again, "VIDEO")["answer"] == "out"

    # A Gravis UltraSound and an MPU-401

    def test_a_gravis_ultrasound_is_named_as_itself(self, client, computer):
        made = survey(client, TAG=computer()["asset_id"], GUS="240 1024", GUS_ANSWER="NEW")
        card = get(client, "parts", finding(made, "GUS")["part"])
        assert (card["type"], card["manufacturer"], card["model"]) == (
            "sound",
            "Advanced Gravis",
            "UltraSound",
        )

    def test_an_mpu_401_is_asked_its_make(self, client, computer):
        made = survey(client, TAG=computer()["asset_id"], MPU="330")
        assert finding(made, "MPU")["fits"] == ["part", "machine", "out"]
        assert "MPU_NAME" not in ask(client, MPU="330")

    def test_a_sound_blaster_16s_mpu_401_is_that_cards(self, client, computer):
        made = survey(client, TAG=computer()["asset_id"], SOUND="220 4.13", MPU="330")
        assert not [f for f in made["findings"] if f["thing"] == "MPU"]

    # The ports

    def test_the_ports_say_each_serial_ports_chip_and_each_parallel_ports_mode(
        self, client, computer
    ):
        made = survey(
            client,
            TAG=computer()["asset_id"],
            COM1="03F8 16550A IRQ4 PLUG:NONE",
            COM2="02F8 8250 IRQ3 PLUG:NONE",
            LPT1="0378 ECP PLUG:NONE",
            PORTS_ANSWER="NEW",
        )
        card = get(client, "parts", finding(made, "PORTS")["part"])
        assert card["specs"] == "Ports: Serial (16550A), Serial (8250), Parallel (ECP)"

    def test_ports_answered_before_are_not_asked_again(self, client, computer):
        machine = computer()
        survey(client, TAG=machine["asset_id"], COM1="03F8", PORTS_ANSWER="OUT")
        again = survey(client, TAG=machine["asset_id"], COM1="03F8 16550A IRQ4 PLUG:NONE")
        assert finding(again, "PORTS")["answer"] == "out"


class TestSerialNumbersAndAddresses:
    def test_every_serial_number_and_address_is_recorded_whatever_its_answer(
        self, client, computer
    ):
        survey(client, TAG=computer()["asset_id"], **DISK, **NIC)
        seen = client.get("/surveys/seen")
        assert seen.status_code == 200, seen.text
        assert "QX123" in seen.text and MAC in seen.text

    def test_a_disk_left_out_stays_left_out_until_its_answer_is_changed(self, client, computer):
        machine = computer()
        first = survey(client, TAG=machine["asset_id"], DISK1_ANSWER="OUT", **DISK)
        assert answer(client, first, "DISK1", "new").status_code == 303
        again = survey(client, TAG=machine["asset_id"], **DISK)
        assert finding(again, "DISK1")["answer"] == "part"

    def test_a_part_of_its_own_carries_its_serial_number(self, client, computer):
        made = survey(client, TAG=computer()["asset_id"], DISK1_ANSWER="NEW", **DISK)
        assert get(client, "parts", finding(made, "DISK1")["part"])["serial"] == "QX123"

    def test_a_network_card_carries_its_address(self, client, computer):
        made = survey(client, TAG=computer()["asset_id"], NIC_ANSWER="NEW", **NIC)
        assert get(client, "parts", finding(made, "NIC")["part"])["ethernet_address"] == MAC

    def test_an_address_that_is_part_of_the_machine_makes_no_part(self, client, computer):
        machine = computer()
        survey(client, TAG=machine["asset_id"], NIC_ANSWER="MACHINE", **NIC)
        assert parts_in(client, machine["asset_id"]) == []


# --- part of the machine -----------------------------------------------------------


class TestPartOfTheMachine:
    def test_the_processor_is_written_the_way_the_form_asks_for_it(self, client, computer):
        """From what a survey program sends: the family it says (80486), the CPUID
        signature that says which 486 it is, and the speed it measured."""
        machine = computer()
        survey(
            client,
            TAG=machine["asset_id"],
            CPU="80486",
            CPUVENDOR="GenuineIntel",
            CPUSIG="0435",
            CPUKHZ="66667",
        )
        assert get(client, "computers", machine["asset_id"])["cpu"] == "Intel 486DX2-66"

    @pytest.mark.parametrize(
        ("cpu", "vendor", "signature", "khz", "written"),
        [
            ("80486", "GenuineIntel", "0480", "100000", "Intel 486DX4-100"),
            ("80486", "AuthenticAMD", "04F4", "133333", "AMD 5x86-133"),
            ("PENTIUM", "GenuineIntel", "052C", "133000", "Intel Pentium-133"),
            ("PENTIUM", "GenuineIntel", "0543", "233000", "Intel Pentium MMX-233"),
            ("PENTIUM", "AuthenticAMD", "058C", "300000", "AMD K6-2-300"),
            ("PENTIUM", "CyrixInstead", "0520", "120000", "Cyrix 6x86-120"),
            ("P6", "GenuineIntel", "0652", "350000", "Intel Pentium II-350"),
            ("P6", "GenuineIntel", "0683", "733000", "Intel Pentium III-733"),
            # A model nobody has told the register about is called by its family.
            ("PENTIUM", "GenuineIntel", "05F0", "100000", "Intel Pentium-100"),
        ],
    )
    def test_a_chip_that_answers_cpuid_is_named_by_what_it_answers(
        self, client, computer, cpu, vendor, signature, khz, written
    ):
        """An AMD K6-2 says it is of the Pentium's family, and is written as itself."""
        made = survey(
            client,
            TAG=computer()["asset_id"],
            CPU=cpu,
            CPUVENDOR=vendor,
            CPUSIG=signature,
            CPUKHZ=khz,
        )
        assert finding(made, "CPU")["name"] == written

    def test_a_chip_too_old_to_say_who_made_it_is_written_without_a_maker(self, client, computer):
        machine = computer()
        survey(client, TAG=machine["asset_id"], CPU="80286", CPUKHZ="12000")
        assert get(client, "computers", machine["asset_id"])["cpu"] == "80286-12"

    def test_a_486_too_early_for_cpuid_is_written_as_the_survey_says_it(self, client, computer):
        made = survey(client, TAG=computer()["asset_id"], CPU="80486", CPUKHZ="33000")
        assert finding(made, "CPU")["name"] == "80486-33"

    def test_the_speed_written_is_the_speed_measured(self, client, computer):
        """So a machine surveyed with its turbo switched off is written at its slower
        speed."""
        machine = computer()
        survey(
            client,
            TAG=machine["asset_id"],
            CPU="80486",
            CPUVENDOR="GenuineIntel",
            CPUSIG="0435",
            CPUKHZ="8000",
        )
        assert get(client, "computers", machine["asset_id"])["cpu"] == "Intel 486DX2-8"

    def test_the_coprocessor_goes_in_the_catalogues_fpu_socket(self, client, computer):
        machine = computer(machine={"model_key": "ibm-5150"})
        survey(client, TAG=machine["asset_id"], FPU="8087")
        chips = get(client, "computers", machine["asset_id"])["machine"]["chips"]
        assert chips["fpu"] == "Intel 8087"

    def test_without_a_socket_the_coprocessor_goes_on_the_motherboard(self, client, computer, part):
        machine = computer()
        board = part(type="motherboard", computer_id=machine["asset_id"])
        survey(client, TAG=machine["asset_id"], FPU="80387")
        assert "80387" in get(client, "parts", board["asset_id"])["specs"]

    def test_memory_is_written_as_a_plain_total_when_nothing_is_recorded(self, client, computer):
        machine = computer()
        survey(client, TAG=machine["asset_id"], RAMKB="640", EXTKB="0")
        assert get(client, "computers", machine["asset_id"])["installed_ram"] == "640 KiB"

    @pytest.mark.parametrize(("ext", "total"), [("384", "1 MiB"), ("3072", "4 MiB")])
    def test_above_a_mebibyte_memory_is_rounded_up_to_whole_mebibytes(
        self, client, computer, ext, total
    ):
        """Because an AT's BIOS leaves out the 384 KiB under its ROMs."""
        machine = computer()
        survey(client, TAG=machine["asset_id"], RAMKB="640", EXTKB=ext)
        assert get(client, "computers", machine["asset_id"])["installed_ram"] == total

    def test_memory_already_recorded_is_left_alone_and_the_difference_shown(self, client, computer):
        machine = computer(installed_ram="640KiB")
        made = survey(client, TAG=machine["asset_id"], RAMKB="512", EXTKB="0")
        assert get(client, "computers", machine["asset_id"])["installed_ram"] == "640 KiB"
        assert {"field": "installed_ram", "recorded": "640 KiB", "found": "512 KiB"} in made[
            "differs"
        ]

    def test_the_operating_system_on_the_first_hard_disk_is_written(self, client, computer):
        machine = computer()
        survey(client, TAG=machine["asset_id"], OS="MS-DOS 6.22")
        assert get(client, "computers", machine["asset_id"])["os"] == "MS-DOS 6.22"

    def test_what_a_later_pcs_bios_says_fills_its_maker_model_and_serial_number(
        self, client, computer
    ):
        machine = computer(manufacturer="", model="")
        survey(
            client,
            TAG=machine["asset_id"],
            SYSTEM_MAKER="Dell Computer Corporation",
            SYSTEM_MODEL="OptiPlex GXi",
            SYSTEM_SERIAL="7XK2Q11",
        )
        got = get(client, "computers", machine["asset_id"])
        assert got["model"] == "OptiPlex GXi"
        assert got["serial"] == "7XK2Q11"
        assert "Dell" in got["manufacturer"]

    def test_a_placeholder_from_the_bios_says_nothing(self, client, computer):
        machine = computer(manufacturer="", model="")
        survey(
            client,
            TAG=machine["asset_id"],
            SYSTEM_MODEL="System Product Name",
            SYSTEM_SERIAL="To be filled by O.E.M.",
        )
        got = get(client, "computers", machine["asset_id"])
        assert (got["model"], got["serial"]) == ("", "")

    def test_the_bios_goes_in_the_catalogues_bios_socket(self, client, computer):
        machine = computer(machine={"model_key": "ibm-5150"})
        survey(client, TAG=machine["asset_id"], BIOSVENDOR="IBM", BIOSDATE="10/27/82")
        chips = get(client, "computers", machine["asset_id"])["machine"]["chips"]
        assert chips["bios"] == "BIOS 10/27/82"

    def test_otherwise_the_bios_goes_on_the_motherboard(self, client, computer, part):
        machine = computer()
        board = part(type="motherboard", computer_id=machine["asset_id"])
        survey(client, TAG=machine["asset_id"], BIOSVENDOR="Award", BIOSDATE="08/22/96")
        specs = get(client, "parts", board["asset_id"])["specs"]
        assert "BIOS: Award" in specs and "08/22/96" in specs

    def test_the_chipset_a_later_pc_names_goes_on_the_motherboard(self, client, computer, part):
        machine = computer()
        board = part(type="motherboard", computer_id=machine["asset_id"])
        survey(client, TAG=machine["asset_id"], PCI1="8086:122D 0600")
        assert "430FX" in get(client, "parts", board["asset_id"])["specs"]

    def test_ports_answered_as_part_of_the_machine_go_on_the_motherboard(
        self, client, computer, part
    ):
        machine = computer()
        board = part(type="motherboard", computer_id=machine["asset_id"])
        survey(
            client,
            TAG=machine["asset_id"],
            COM1="03F8 16550A IRQ4",
            COM2="02F8 16550A IRQ3",
            LPT1="0378 IRQ7",
            PORTS_ANSWER="MACHINE",
        )
        specs = get(client, "parts", board["asset_id"])["specs"]
        assert "Ports: 2× Serial (16550A), Parallel" in specs

    def test_anything_else_built_in_gets_a_line_of_its_own(self, client, computer, part):
        machine = computer()
        board = part(type="motherboard", computer_id=machine["asset_id"])
        survey(client, TAG=machine["asset_id"], PCI1="1274:1371 0401", PCI1_ANSWER="MACHINE")
        assert "Onboard sound" in get(client, "parts", board["asset_id"])["specs"]

    def test_with_no_motherboard_on_record_the_answer_is_kept_and_nothing_written(
        self, client, computer
    ):
        machine = computer()
        survey(client, TAG=machine["asset_id"], VIDEO="VGA", VIDEO_ANSWER="MACHINE")
        assert parts_in(client, machine["asset_id"]) == []
        again = survey(client, TAG=machine["asset_id"], VIDEO="VGA")
        assert finding(again, "VIDEO")["answer"] == "machine"

    def test_a_bare_motherboard_gets_what_belongs_to_a_board(self, client, part):
        board = part(type="motherboard")
        survey(
            client,
            TAG=board["asset_id"],
            BIOSVENDOR="AMI",
            BIOSDATE="04/04/93",
            BOARD_SERIAL="BRD-9",
            PCI1="8086:122D 0600",
        )
        got = get(client, "parts", board["asset_id"])
        assert "AMI" in got["specs"] and "04/04/93" in got["specs"] and "430FX" in got["specs"]
        assert got["serial"] == "BRD-9"
        assert got["condition"] == "Working"


# --- the motherboard ----------------------------------------------------------------

# What a PC's BIOS says of its board: its date, a ROM copy, and on a later PC the
# chipset the bus names.
BOARDISH = {"BIOSDATE": "08/22/96", "PCI1": "8086:7030 0600"}


class TestTheMotherboard:
    """A machine with no motherboard on record is asked about one, so its BIOS, its
    chipset and its serial number have somewhere to go (MANUAL §23, "Part of the
    machine"; ADR-0045)."""

    def test_a_machine_with_no_board_on_record_is_asked_about_one(self, client, computer):
        made = survey(client, TAG=computer()["asset_id"], **BOARDISH)
        assert finding(made, "BOARD")["answer"] is None
        assert finding(made, "BOARD")["fits"] == ["part", "out"]
        assert made["waiting"] == "answer"

    def test_n_makes_one_fitted_in_the_machine_and_its_bios_goes_on_it(self, client, computer):
        machine = computer()
        made = survey(
            client,
            roms=[("BIOS.BIN", BIOS_ROM)],
            TAG=machine["asset_id"],
            ROM1="F000 65536 BIOS.BIN",
            BOARD_ANSWER="NEW",
            BOARD_MAKER="ASUSTeK",
            BOARD_MODEL="P/I-P55TVP4",
            BOARD_SERIAL="MB-123",
            **BOARDISH,
        )
        assert made["waiting"] is None
        board = get(client, "parts", finding(made, "BOARD")["part"])
        assert board["type"] == "motherboard"
        assert board["computer_id"] == machine["asset_id"]
        assert (board["manufacturer"], board["model"]) == ("ASUSTeK", "P/I-P55TVP4")
        assert board["serial"] == "MB-123"
        assert "Award" in board["specs"] and "08/22/96" in board["specs"]
        assert "430VX" in board["specs"]
        assert files(client)[0]["assets"] == [board["asset_id"]]

    def test_a_new_machine_gets_its_board_the_same_way(self, client):
        made = survey(client, TAG="NEW", BOARD_ANSWER="NEW", **BOARDISH)
        board = get(client, "parts", finding(made, "BOARD")["part"])
        assert board["computer_id"] == made["machine"]
        assert "08/22/96" in board["specs"]

    def test_a_board_its_bios_names_takes_that_name(self, client, computer):
        made = survey(
            client,
            TAG=computer()["asset_id"],
            BOARD_ANSWER="NEW",
            BOARD_MAKER="ASUSTeK Computer INC.",
            BOARD_MODEL="P5A",
            **BOARDISH,
        )
        board = get(client, "parts", finding(made, "BOARD")["part"])
        assert (board["manufacturer"], board["model"]) == ("ASUSTeK Computer INC.", "P5A")

    def test_a_placeholder_never_names_a_board(self, client, computer):
        made = survey(
            client,
            TAG=computer()["asset_id"],
            BOARD_ANSWER="NEW",
            BOARD_MAKER="To be filled by O.E.M.",
            BOARD_MODEL="To be filled by O.E.M.",
            **BOARDISH,
        )
        board = get(client, "parts", finding(made, "BOARD")["part"])
        assert (board["manufacturer"], board["model"]) == ("", "")

    def test_x_is_remembered(self, client, computer):
        machine = computer()
        survey(client, TAG=machine["asset_id"], BOARD_ANSWER="OUT", **BOARDISH)
        again = survey(client, TAG=machine["asset_id"], **BOARDISH)
        assert finding(again, "BOARD")["answer"] == "out"
        assert again["waiting"] is None
        assert ask(client, TAG=machine["asset_id"], **BOARDISH)["BOARD_ANSWER"] == "OUT"

    def test_a_board_cannot_be_part_of_the_machine(self, client, computer):
        """Part of the machine is what the catalogue's sockets are for."""
        made = survey(client, TAG=computer()["asset_id"], BOARD_ANSWER="MACHINE", **BOARDISH)
        assert finding(made, "BOARD")["answer"] is None
        assert answer(client, made, "BOARD", "machine").status_code == 400

    def test_a_machine_with_a_board_on_record_is_not_asked(self, client, computer, part):
        machine = computer()
        board = part(type="motherboard", computer_id=machine["asset_id"])
        assert ask(client, TAG=machine["asset_id"], **BOARDISH)["BOARD_ANSWER"] == board["asset_id"]
        made = survey(client, TAG=machine["asset_id"], **BOARDISH)
        assert finding(made, "BOARD")["part"] == board["asset_id"]
        assert made["waiting"] is None

    def test_a_catalogue_machine_that_keeps_its_own_bios_is_not_asked(self, client, computer):
        """An IBM 5150's BIOS goes in its BIOS ROM socket."""
        machine = computer(machine={"model_key": "ibm-5150"})
        assert ask(client, TAG=machine["asset_id"], **BOARDISH)["BOARD_ANSWER"] == "MACHINE"
        made = survey(client, TAG=machine["asset_id"], **BOARDISH)
        assert finding(made, "BOARD")["answer"] == "machine"
        assert made["waiting"] is None

    def test_a_board_the_register_has_is_joined_by_its_tag(self, client, computer, part):
        shelf = location(client, "Shelf 4", "shelf")
        board = part(type="motherboard", model="P5A", location=shelf["asset_id"])
        machine = computer()
        survey(client, TAG=machine["asset_id"], BOARD_ANSWER=board["asset_id"], **BOARDISH)
        got = get(client, "parts", board["asset_id"])
        assert got["computer_id"] == machine["asset_id"]
        assert "08/22/96" in got["specs"]

    def test_a_board_the_register_has_is_known_by_its_serial(self, client, computer, part):
        board = part(type="motherboard", model="P5A", serial="MB-9")
        machine = computer()
        made = survey(client, TAG=machine["asset_id"], BOARD_SERIAL="MB-9", **BOARDISH)
        assert finding(made, "BOARD")["part"] == board["asset_id"]
        assert get(client, "parts", board["asset_id"])["computer_id"] == machine["asset_id"]

    def test_a_loose_board_known_by_its_serial_goes_into_a_new_machine(self, client, part):
        """With N typed, a board on a shelf is a board being put in a case."""
        board = part(type="motherboard", model="P5A", serial="MB-11")
        made = survey(client, TAG="NEW", BOARD_SERIAL="MB-11", **BOARDISH)
        assert made["how"] == "new"
        assert get(client, "parts", board["asset_id"])["computer_id"] == made["machine"]

    def test_with_nothing_typed_a_loose_board_is_the_board_being_surveyed(self, client, part):
        """A bare board on the bench, known by its serial number."""
        board = part(type="motherboard", model="P5A", serial="MB-12")
        made = survey(client, BOARD_SERIAL="MB-12", **BOARDISH)
        assert made["machine"] == board["asset_id"]
        assert finding(made, "BOARD")["part"] == board["asset_id"]

    def test_a_board_made_by_b_is_named_as_a_new_board_in_a_machine_is(self, client):
        made = survey(
            client,
            TAG="NEW BOARD",
            BOARD_MAKER="ASUSTeK Computer INC.",
            BOARD_MODEL="P5A",
            **BOARDISH,
        )
        board = get(client, "parts", made["machine"])
        assert (board["manufacturer"], board["model"]) == ("ASUSTeK Computer INC.", "P5A")

    def test_a_board_made_by_b_takes_the_name_of_the_computer_maker_whose_bios_it_is(self, client):
        made = survey(client, TAG="NEW BOARD", BIOSVENDOR="Compaq", **BOARDISH)
        board = get(client, "parts", made["machine"])
        assert (board["manufacturer"], board["model"]) == ("Compaq", "")

    def test_a_board_made_by_b_gets_what_belongs_to_a_board(self, client):
        made = survey(
            client,
            roms=[("BIOS.BIN", BIOS_ROM)],
            TAG="NEW BOARD",
            ROM1="F000 65536 BIOS.BIN",
            BOARD_SERIAL="BRD-10",
            **BOARDISH,
        )
        board = get(client, "parts", made["machine"])
        assert "Award" in board["specs"] and "08/22/96" in board["specs"]
        assert "430VX" in board["specs"]
        assert board["serial"] == "BRD-10"
        assert board["condition"] == "Working"
        assert files(client)[0]["assets"] == [board["asset_id"]]

    def test_a_board_made_by_b_is_its_own_motherboard_and_is_not_asked_about_one(self, client):
        made = survey(client, TAG="NEW BOARD", **BOARDISH)
        assert finding(made, "BOARD")["part"] == made["machine"]
        assert made["waiting"] is None

    def test_a_board_made_by_b_has_no_location_until_it_is_put_away(self, client):
        board = get(client, "parts", survey(client, TAG="NEW BOARD", **BOARDISH)["machine"])
        assert not board["location"] and not board["computer_id"] and not board["parent_id"]

    def test_b_makes_a_board_from_a_report_that_says_nothing_of_one(self, client):
        """B said there is one, which is enough."""
        made = survey(client, TAG="NEW BOARD")
        assert made["how"] == "new"
        assert get(client, "parts", made["machine"])["type"] == "motherboard"

    def test_a_board_made_on_the_surveys_page_gets_the_bios_too(self, client, computer):
        machine = computer()
        made = survey(
            client,
            roms=[("BIOS.BIN", BIOS_ROM)],
            TAG=machine["asset_id"],
            ROM1="F000 65536 BIOS.BIN",
            **BOARDISH,
        )
        r = answer(client, made, "BOARD", "new")
        assert r.status_code in (200, 303), r.text
        board = get(client, "parts", finding(read(client, made["id"]), "BOARD")["part"])
        assert "Award" in board["specs"] and "08/22/96" in board["specs"]
        assert board["asset_id"] in files(client)[0]["assets"]

    def test_the_answer_names_a_board_its_bios_names(self, client):
        assert (
            ask(client, BOARD_MAKER="ASUSTeK Computer INC.", BOARD_MODEL="P5A", **BOARDISH)[
                "BOARD_NAME"
            ]
            == "ASUSTeK Computer INC. P5A"
        )
        assert "BOARD_NAME" not in ask(
            client, BOARD_MAKER="System manufacturer", BOARD_MODEL="P5A", **BOARDISH
        )


# --- a part of its own --------------------------------------------------------------


class TestAPartOfItsOwn:
    def test_a_new_part_that_names_nothing_is_named_by_what_was_typed(self, client, computer):
        made = survey(
            client,
            roms=[("SCSI.C80", ANONYMOUS_ROM)],
            TAG=computer()["asset_id"],
            ROM1="C800 16384 SCSI.C80",
            ROM1_ANSWER="NEW",
            ROM1_MAKER="Adaptec",
            ROM1_MODEL="AHA-1542CF",
        )
        card = get(client, "parts", finding(made, "ROM1")["part"])
        assert (card["manufacturer"], card["model"]) == ("Adaptec", "AHA-1542CF")

    def test_a_disk_the_bios_knows_only_by_its_size_is_named_by_what_was_typed(
        self, client, computer
    ):
        made = survey(
            client,
            TAG=computer()["asset_id"],
            DISK1_KB="21360",
            DISK1_CHS="615/4/17",
            DISK1_TYPE="BIOS",
            DISK1_ANSWER="NEW",
            DISK1_MAKER="Seagate",
            DISK1_MODEL="ST-225",
        )
        disk = get(client, "parts", finding(made, "DISK1")["part"])
        assert (disk["manufacturer"], disk["model"]) == ("Seagate", "ST-225")
        assert "Capacity" in disk["specs"]

    def test_only_what_was_typed_is_written(self, client, computer):
        """Enter at the model leaves the name the register would have given it."""
        made = survey(
            client,
            TAG=computer()["asset_id"],
            COM1="03F8",
            PORTS_ANSWER="NEW",
            PORTS_MAKER="Everex",
        )
        card = get(client, "parts", finding(made, "PORTS")["part"])
        assert (card["manufacturer"], card["model"]) == ("Everex", "I/O card")

    def test_a_typed_name_is_never_how_the_thing_is_known_again(self, client, computer):
        """The next survey of the machine finds the same card by what the card says
        about itself, and nobody types anything that time."""
        machine = computer()
        first = survey(
            client,
            TAG=machine["asset_id"],
            COM1="03F8",
            PORTS_ANSWER="NEW",
            PORTS_MAKER="Everex",
            PORTS_MODEL="EV-170",
        )
        again = survey(client, TAG=machine["asset_id"], COM1="03F8")
        assert finding(again, "PORTS")["part"] == finding(first, "PORTS")["part"]

    def test_a_tag_answered_at_the_machine_joins_the_part_to_its_serial_number(
        self, client, computer, part
    ):
        """How a disk catalogued by hand, before anything had read its serial number,
        is joined to its own record rather than added twice."""
        machine = computer()
        shelf = location(client, "Shelf 2", "shelf")
        disk = part(
            type="storage",
            model="Fireball 1080AT",
            location=shelf["asset_id"],
            specs="Kind: Hard disk | Interface: IDE",
        )
        survey(client, TAG=machine["asset_id"], DISK1_ANSWER=disk["asset_id"], **DISK)
        got = get(client, "parts", disk["asset_id"])
        assert got["serial"] == "QX123"
        assert got["computer_id"] == machine["asset_id"]
        assert len(all_parts(client)) == 1

    def test_n_makes_a_new_hard_disk_named_as_it_names_itself(self, client, computer):
        machine = computer()
        made = survey(client, TAG=machine["asset_id"], DISK1_ANSWER="NEW", **DISK)
        disk = get(client, "parts", finding(made, "DISK1")["part"])
        assert disk["computer_id"] == machine["asset_id"]
        assert disk["type"] == "storage"
        assert "FIREBALL1080A" in f"{disk['name']} {disk['model']}".upper()
        assert "Hard disk" in disk["specs"] and "IDE" in disk["specs"]
        assert "2097" in disk["specs"]

    def test_n_makes_a_new_card_named_by_its_rom(self, client, computer):
        machine = computer()
        made = survey(
            client,
            roms=[("VIDEO.BIN", VGA_ROM)],
            TAG=machine["asset_id"],
            VIDEO="VGA",
            ROM1="C000 32768 VIDEO.BIN",
            VIDEO_ANSWER="NEW",
        )
        card = get(client, "parts", finding(made, "VIDEO")["part"])
        assert card["type"] == "video"
        assert "ET4000" in f"{card['name']} {card['model']}"

    def test_n_makes_a_new_card_named_by_its_chip_on_the_pci_bus(self, client, computer):
        machine = computer()
        made = survey(client, TAG=machine["asset_id"], PCI1="1013:00B8 0300", PCI1_ANSWER="NEW")
        card = get(client, "parts", finding(made, "PCI1")["part"])
        assert card["type"] == "video"
        assert "5446" in f"{card['name']} {card['model']}"

    def test_n_makes_a_network_card_named_by_its_driver_with_its_address(self, client, computer):
        machine = computer()
        made = survey(client, TAG=machine["asset_id"], NIC_ANSWER="NEW", **NIC)
        card = get(client, "parts", finding(made, "NIC")["part"])
        assert card["type"] == "network"
        assert "NE2000" in f"{card['name']} {card['model']}"
        assert card["ethernet_address"] == MAC

    def test_n_makes_the_ports_an_io_card_with_them_on_it(self, client, computer):
        machine = computer()
        made = survey(
            client,
            TAG=machine["asset_id"],
            COM1="03F8 16550A IRQ4",
            LPT1="0378 IRQ7",
            PORTS_ANSWER="NEW",
        )
        card = get(client, "parts", finding(made, "PORTS")["part"])
        assert card["type"] == "io"
        assert card["computer_id"] == machine["asset_id"]

    def test_a_part_fitted_in_this_machine_is_confirmed_and_filled_in(self, client, with_disk):
        machine, disk = with_disk()
        made = survey(client, TAG=machine["asset_id"], **DISK)
        assert finding(made, "DISK1")["part"] == disk["asset_id"]
        assert "2097" in get(client, "parts", disk["asset_id"])["specs"]

    def test_a_part_kept_on_a_shelf_is_moved_into_the_machine_by_survey(
        self, client, computer, part
    ):
        machine = computer()
        shelf = location(client, "Shelf 2", "shelf")
        disk = part(
            type="storage",
            serial="QX123",
            location=shelf["asset_id"],
            specs="Kind: Hard disk | Interface: IDE",
        )
        survey(client, TAG=machine["asset_id"], **DISK)
        assert get(client, "parts", disk["asset_id"])["computer_id"] == machine["asset_id"]
        moves = client.get(f"/api/items/{disk['asset_id']}/moves").json()
        assert moves[0]["how"] == "survey"

    def test_a_part_kept_nowhere_is_moved_into_the_machine(self, client, computer, part):
        machine = computer()
        disk = part(type="storage", serial="QX123", specs="Kind: Hard disk | Interface: IDE")
        survey(client, TAG=machine["asset_id"], **DISK)
        assert get(client, "parts", disk["asset_id"])["computer_id"] == machine["asset_id"]

    def test_a_part_in_another_machine_is_never_taken_out(self, client, computer, with_disk):
        other, disk = with_disk()
        machine = computer()
        assert survey(client, TAG=machine["asset_id"], **DISK)["waiting"] == "machine"
        assert get(client, "parts", disk["asset_id"])["computer_id"] == other["asset_id"]

    def test_a_disk_that_cannot_say_which_one_it_is_is_known_by_its_size_in_the_same_machine(
        self, client, computer
    ):
        """An MFM disk seen only through the BIOS, answered like a card."""
        machine = computer()
        mfm = {"DISK1_TYPE": "BIOS", "DISK1_CHS": "615/4/17", "DISK1_KB": "20910"}
        first = survey(client, TAG=machine["asset_id"], DISK1_ANSWER="NEW", **mfm)
        again = survey(client, TAG=machine["asset_id"], **mfm)
        assert finding(again, "DISK1")["part"] == finding(first, "DISK1")["part"]
        assert len(parts_in(client, machine["asset_id"])) == 1


# --- who made it, from its BIOS ------------------------------------------------------


def with_bios(rom: bytes) -> dict:
    """A report's copy of its system BIOS, as the survey program sends it."""
    return {"roms": [("BIOS.BIN", rom)], "ROM1": "F000 65536 BIOS.BIN"}


def new_board(client, made: dict) -> dict:
    return get(client, "parts", finding(made, "BOARD")["part"])


class TestWhoMadeItFromItsBios:
    """A BIOS a computer maker wrote, or put its name in, says who made the board it
    is on, and nearly always the machine (MANUAL §23, "Who made it, from its BIOS";
    ADR-0047)."""

    @pytest.mark.parametrize(
        "vendor, maker",
        [
            ("Compaq", "Compaq"),
            ("IBM", "IBM"),
            ("Amstrad", "Amstrad"),
            ("Olivetti", "Olivetti"),
            ("Tandy", "Tandy"),
            ("Zenith", "Zenith Data Systems"),
            ("Toshiba", "Toshiba"),
            ("Commodore", "Commodore"),
        ],
    )
    def test_a_new_board_is_named_by_the_maker_that_wrote_its_bios(
        self, client, computer, vendor, maker
    ):
        made = survey(
            client, TAG=computer()["asset_id"], BOARD_ANSWER="NEW", BIOSVENDOR=vendor, **BOARDISH
        )
        board = new_board(client, made)
        assert (board["manufacturer"], board["model"]) == (maker, "")

    @pytest.mark.parametrize(
        "rom, maker", [(HP_BIOS, "HP"), (DELL_BIOS, "Dell")], ids=["HP", "Dell"]
    )
    def test_hp_and_dell_are_known_by_their_name_in_a_bios_phoenix_wrote(
        self, client, computer, rom, maker
    ):
        made = survey(
            client,
            TAG=computer()["asset_id"],
            BOARD_ANSWER="NEW",
            BIOSVENDOR="Phoenix",
            **with_bios(rom),
            **BOARDISH,
        )
        assert new_board(client, made)["manufacturer"] == maker

    @pytest.mark.parametrize("vendor", ["AMI", "Award", "Phoenix", "Quadtel"])
    def test_a_bios_house_names_nobody(self, client, computer, vendor):
        made = survey(
            client, TAG=computer()["asset_id"], BOARD_ANSWER="NEW", BIOSVENDOR=vendor, **BOARDISH
        )
        assert new_board(client, made)["manufacturer"] == ""
        answered = ask(client, BIOSVENDOR=vendor, **BOARDISH)
        assert "BOARD_NAME" not in answered and "SYSTEM_MAKER" not in answered

    def test_the_copy_of_the_bios_is_read_for_its_maker(self, client, computer):
        """With no word from the survey program about who wrote it."""
        made = survey(
            client, TAG=computer()["asset_id"], BOARD_ANSWER="NEW", **with_bios(COMPAQ_BIOS)
        )
        assert new_board(client, made)["manufacturer"] == "Compaq"

    def test_a_clone_bios_that_says_compaq_names_nobody(self, client, computer):
        """The copy says Phoenix wrote it, and is believed over the survey program,
        which found COMPAQ first."""
        made = survey(
            client,
            TAG=computer()["asset_id"],
            BOARD_ANSWER="NEW",
            BIOSVENDOR="Compaq",
            **with_bios(CLONE_BIOS),
            **BOARDISH,
        )
        assert new_board(client, made)["manufacturer"] == ""

    def test_the_answer_names_the_board_so_it_is_not_asked(self, client):
        assert ask(client, BIOSVENDOR="Compaq", **BOARDISH)["BOARD_NAME"] == "Compaq"

    def test_smbios_names_the_board_before_its_bios_maker(self, client):
        answered = ask(
            client,
            BOARD_MAKER="Dell Computer Corporation",
            BOARD_MODEL="0X1234",
            **with_bios(DELL_BIOS),
            **BOARDISH,
        )
        assert answered["BOARD_NAME"] == "Dell Computer Corporation 0X1234"

    def test_a_board_on_record_with_no_maker_has_it_filled_in(self, client, computer, part):
        machine = computer()
        board = part(type="motherboard", model="", computer_id=machine["asset_id"])
        survey(client, TAG=machine["asset_id"], BIOSVENDOR="Compaq", **BOARDISH)
        assert get(client, "parts", board["asset_id"])["manufacturer"] == "Compaq"

    def test_a_new_machine_is_offered_its_bios_maker(self, client):
        assert ask(client, BIOSVENDOR="Compaq", **BOARDISH)["SYSTEM_MAKER"] == "Compaq"

    def test_the_maker_offered_is_the_one_smbios_gives_where_it_gives_one(self, client):
        answered = ask(client, SYSTEM_MAKER="Dell Computer Corporation", **with_bios(DELL_BIOS))
        assert answered["SYSTEM_MAKER"] == "Dell Computer Corporation"

    def test_a_new_machine_takes_its_bios_maker_when_nothing_was_typed(self, client):
        made = survey(client, TAG="NEW", BIOSVENDOR="Compaq", **BOARDISH)
        assert get(client, "computers", made["machine"])["manufacturer"] == "Compaq"

    def test_the_badge_typed_at_the_machine_wins(self, client):
        """An AT&T 6300 is an Olivetti inside."""
        made = survey(
            client,
            TAG="NEW",
            BIOSVENDOR="Olivetti",
            SYSTEM_MAKER="AT&T",
            SYSTEM_MODEL="6300",
            **BOARDISH,
        )
        got = get(client, "computers", made["machine"])
        assert (got["manufacturer"], got["model"]) == ("AT&T", "6300")

    def test_a_machine_with_no_maker_recorded_has_it_filled_in(self, client, computer):
        machine = computer(manufacturer="", model="")
        survey(client, TAG=machine["asset_id"], BIOSVENDOR="Compaq", **BOARDISH)
        assert get(client, "computers", machine["asset_id"])["manufacturer"] == "Compaq"

    def test_the_new_computer_form_starts_with_its_bios_maker(self, client):
        made = survey(client, BIOSVENDOR="Compaq", **BOARDISH)
        assert made["waiting"] == "machine"
        form = client.get(f"/computers/new?survey={made['id']}")
        assert form.status_code == 200, form.text
        assert 'value="Compaq"' in form.text

    def test_a_recorded_maker_is_never_changed_or_called_a_difference(self, client, computer, part):
        machine = computer(manufacturer="AT&T", model="6300")
        board = part(type="motherboard", manufacturer="AT&T", computer_id=machine["asset_id"])
        made = survey(client, TAG=machine["asset_id"], BIOSVENDOR="Olivetti", **BOARDISH)
        assert get(client, "computers", machine["asset_id"])["manufacturer"] == "AT&T"
        assert get(client, "parts", board["asset_id"])["manufacturer"] == "AT&T"
        assert not [d for d in made["differs"] if d["field"] == "manufacturer"]

    @pytest.mark.parametrize(
        "rom, made_by",
        [
            (VGA_ROM, ("Tseng Labs", "ET4000")),
            (ADAPTEC_ROM, ("Adaptec", "AHA-1540B/1542B")),
            (CIRRUS_ROM, ("Cirrus Logic", "CL-GD5428")),
        ],
        ids=["on its banner", "on its banner too", "on a line of its own"],
    )
    def test_a_new_card_is_made_by_the_company_its_rom_names(self, client, computer, rom, made_by):
        made = survey(
            client,
            roms=[("CARD.C80", rom)],
            TAG=computer()["asset_id"],
            ROM1="C800 16384 CARD.C80",
            ROM1_ANSWER="NEW",
        )
        card = get(client, "parts", finding(made, "ROM1")["part"])
        assert (card["manufacturer"], card["model"]) == made_by

    def test_a_branded_machines_own_card_carries_its_maker(self, client, computer):
        """The Compaq 286's video BIOS says only whose it is."""
        rom = {"roms": [("VIDEO.C00", COMPAQ_VGA_ROM)], "VIDEO": "UNKNOWN"}
        rom["ROM1"] = "C000 24576 VIDEO.C00"
        assert ask(client, **rom)["VIDEO_NAME"] == "Compaq"
        made = survey(client, TAG=computer()["asset_id"], VIDEO_ANSWER="NEW", **rom)
        card = get(client, "parts", finding(made, "VIDEO")["part"])
        assert (card["manufacturer"], card["model"]) == ("Compaq", "")

    def test_the_answer_names_a_card_by_its_maker_and_its_model(self, client):
        answered = ask(client, roms=[("CARD.C80", CIRRUS_ROM)], ROM1="C800 16384 CARD.C80")
        assert answered["ROM1_NAME"] == "Cirrus Logic CL-GD5428"

    def test_a_rom_that_names_a_program_gives_a_model_and_no_maker(self, client, computer):
        made = survey(
            client,
            roms=[("XTIDE.C80", XTIDE_ROM)],
            TAG=computer()["asset_id"],
            ROM1="C800 8192 XTIDE.C80",
            ROM1_ANSWER="NEW",
        )
        card = get(client, "parts", finding(made, "ROM1")["part"])
        assert (card["manufacturer"], card["model"]) == ("", "XTIDE Universal")


# --- bench cards ---------------------------------------------------------------------


class TestBenchCards:
    def test_a_location_can_be_a_bench(self, client):
        assert location(client, "Bench 1", "bench")["kind"] == "bench"

    def test_a_card_kept_on_a_bench_is_never_fitted_in_the_machine(
        self, client, computer, bench_card
    ):
        card, bench = bench_card()
        machine = computer()
        survey(client, TAG=machine["asset_id"], **NIC)
        got = get(client, "parts", card["asset_id"])
        assert not got["computer_id"]
        assert got["location"] == bench["asset_id"]
        assert parts_in(client, machine["asset_id"]) == []

    def test_a_part_mounted_on_a_bench_card_is_the_benchs_too(self, client, computer, part):
        """A boot ROM on the bench's network card goes where the card goes."""
        bench = location(client, "Bench 1", "bench")
        card = part(type="network", model="UM9003AF", location=bench["asset_id"])
        rom = part(type="other", model="Boot ROM", parent_id=card["asset_id"])
        machine = computer()
        survey(
            client, TAG=machine["asset_id"], ROM1="C800 16384 X.C80", ROM1_ANSWER=rom["asset_id"]
        )
        assert get(client, "parts", rom["asset_id"])["parent_id"] == card["asset_id"]
        assert parts_in(client, machine["asset_id"]) == []

    def test_a_card_in_a_box_on_a_bench_is_fitted_like_a_card_on_a_shelf(
        self, client, computer, part
    ):
        """A tray of spare cards beside the machines is stock, not the bench's kit."""
        bench = location(client, "Bench 1", "bench")
        tray = location(client, "Network cards", "box", parent=bench["asset_id"])
        card = part(type="network", model="UM9003AF", location=tray["asset_id"])
        machine = computer()
        survey(client, TAG=machine["asset_id"], NIC_ANSWER=card["asset_id"], **NIC)
        assert get(client, "parts", card["asset_id"])["computer_id"] == machine["asset_id"]

    def test_a_bench_cards_address_is_recorded_where_it_stands(self, client, bench_card):
        card, bench = bench_card()
        got = get(client, "parts", card["asset_id"])
        assert got["ethernet_address"] == MAC
        assert got["location"] == bench["asset_id"]

    def test_the_survey_names_the_card_it_came_through(self, client, computer, bench_card):
        card, _ = bench_card()
        assert survey(client, TAG=computer()["asset_id"], **NIC)["bench_card"] == card["asset_id"]

    def test_add_to_bench_makes_a_new_card_on_a_bench(self, client, computer):
        bench = location(client, "Bench 1", "bench")
        made = survey(client, TAG=computer()["asset_id"], **NIC)
        r = answer(client, made, "NIC", "bench", bench=bench["asset_id"])
        assert r.status_code == 303, r.text
        card = get(client, "parts", finding(read(client, made["id"]), "NIC")["part"])
        assert card["location"] == bench["asset_id"]
        assert card["ethernet_address"] == MAC

    def test_a_card_made_in_a_machine_and_moved_to_a_bench_is_a_bench_card_from_then_on(
        self, client, computer
    ):
        """The first time its address is read, N fits it in the machine being tested;
        moved to the bench afterwards, it is left alone in every machine after."""
        first, second = computer(), computer()
        bench = location(client, "Bench 1", "bench")
        made = survey(client, TAG=first["asset_id"], NIC_ANSWER="NEW", **NIC)
        card = finding(made, "NIC")["part"]
        r = client.patch(f"/api/parts/{card}", json={"location": bench["asset_id"]})
        assert r.status_code == 200, r.text
        survey(client, TAG=second["asset_id"], **NIC)
        assert get(client, "parts", card)["location"] == bench["asset_id"]
        assert parts_in(client, second["asset_id"]) == []

    def test_a_bench_card_is_left_alone_whichever_machine_it_is_in(
        self, client, computer, bench_card
    ):
        card, bench = bench_card()
        for _ in range(2):
            machine = computer()
            made = survey(client, TAG=machine["asset_id"], **NIC)
            assert made["waiting"] is None
            assert parts_in(client, machine["asset_id"]) == []
        assert get(client, "parts", card["asset_id"])["location"] == bench["asset_id"]

    def test_a_machine_standing_on_a_bench_keeps_its_own_cards(self, client, computer):
        """What is fitted in a machine is the machine's, wherever the machine is."""
        bench = location(client, "Bench 1", "bench")
        machine = computer(location=bench["asset_id"])
        survey(client, TAG=machine["asset_id"], NIC_ANSWER="NEW", **NIC)
        assert survey(client, **NIC)["machine"] == machine["asset_id"]


# --- working, from the tests ---------------------------------------------------------

PASSED = {"RESULT": "PASS", "TESTS": "3", "TEST_CPU": "PASS", "TEST_RAM": "PASS"}


class TestWorkingFromTheTests:
    @pytest.mark.parametrize("condition", ["", "Untested"])
    def test_a_survey_whose_every_test_passed_marks_the_machine_working(
        self, client, computer, condition
    ):
        machine = computer(condition=condition)
        survey(client, TAG=machine["asset_id"], **PASSED)
        assert get(client, "computers", machine["asset_id"])["condition"] == "Working"

    def test_a_test_that_does_not_apply_does_not_count_against_it(self, client, computer):
        """A clock on an XT, a second interrupt controller on a PC."""
        machine = computer()
        survey(client, TAG=machine["asset_id"], TEST_RTC="NA", **PASSED)
        assert get(client, "computers", machine["asset_id"])["condition"] == "Working"

    def test_a_skipped_test_does_because_it_has_not_been_run(self, client, computer):
        machine = computer()
        survey(client, TAG=machine["asset_id"], TEST_FDC="SKIP", **PASSED)
        assert get(client, "computers", machine["asset_id"])["condition"] == ""

    def test_a_soak_counts_the_same(self, client, computer):
        machine = computer()
        survey(
            client,
            TAG=machine["asset_id"],
            MODE="SOAK",
            PASSES="48",
            ELAPSED="12:00:00",
            STOPPED="ESC",
            **PASSED,
        )
        assert get(client, "computers", machine["asset_id"])["condition"] == "Working"

    @pytest.mark.parametrize("condition", ["", "Untested"])
    def test_a_failed_test_never_writes_faulty(self, client, computer, condition):
        """A failure says where to look rather than what the machine is."""
        machine = computer(condition=condition)
        survey(client, TAG=machine["asset_id"], **PASSED | {"RESULT": "FAIL", "TEST_RAM": "FAIL"})
        assert get(client, "computers", machine["asset_id"])["condition"] == condition

    def test_a_run_that_was_stopped_part_way_marks_nothing(self, client, computer):
        machine = computer()
        survey(client, TAG=machine["asset_id"], **PASSED | {"RESULT": "ABORTED"})
        assert get(client, "computers", machine["asset_id"])["condition"] == ""

    @pytest.mark.parametrize(
        "condition", ["Partially working", "Faulty", "For parts/repair", "Restored"]
    )
    def test_a_condition_somebody_chose_is_never_changed(self, client, computer, condition):
        machine = computer(condition=condition)
        survey(client, TAG=machine["asset_id"], **PASSED)
        assert get(client, "computers", machine["asset_id"])["condition"] == condition

    def test_a_failure_never_takes_working_away(self, client, computer):
        machine = computer(condition="Working")
        survey(client, TAG=machine["asset_id"], **PASSED | {"RESULT": "FAIL", "TEST_RAM": "FAIL"})
        assert get(client, "computers", machine["asset_id"])["condition"] == "Working"

    def test_a_faulty_machine_that_passes_every_test_is_pointed_out(self, client, computer):
        machine = computer(condition="Faulty")
        made = survey(client, TAG=machine["asset_id"], **PASSED)
        assert [d for d in made["differs"] if d["field"] == "condition"]

    def test_the_parts_in_the_machine_keep_their_condition(self, client, computer, part):
        """The tests are of the machine, and do not say which card each result
        belongs to."""
        machine = computer()
        card = part(type="video", computer_id=machine["asset_id"])
        survey(client, TAG=machine["asset_id"], **PASSED)
        assert get(client, "parts", card["asset_id"])["condition"] == ""


# --- ROMs ------------------------------------------------------------------------------


def files(client) -> list[dict]:
    r = client.get("/api/files")
    assert r.status_code == 200, r.text
    return r.json()


class TestROMs:
    def test_a_rom_is_kept_as_a_private_file_with_a_note_saying_what_it_is(self, client, computer):
        machine = computer()
        survey(
            client,
            roms=[("BIOS.BIN", BIOS_ROM)],
            TAG=machine["asset_id"],
            BIOSVENDOR="Award",
            BIOSDATE="08/22/96",
            ROM1="F000 65536 BIOS.BIN",
        )
        (kept,) = files(client)
        assert kept["public"] is False
        assert "BIOS" in kept["note"] and "Award" in kept["note"]

    def test_the_bios_is_linked_to_the_machine(self, client, computer):
        machine = computer()
        survey(
            client,
            roms=[("BIOS.BIN", BIOS_ROM)],
            TAG=machine["asset_id"],
            ROM1="F000 65536 BIOS.BIN",
        )
        assert files(client)[0]["assets"] == [machine["asset_id"]]

    def test_the_bios_is_linked_to_the_motherboard_when_there_is_one(self, client, computer, part):
        machine = computer()
        board = part(type="motherboard", computer_id=machine["asset_id"])
        survey(
            client,
            roms=[("BIOS.BIN", BIOS_ROM)],
            TAG=machine["asset_id"],
            ROM1="F000 65536 BIOS.BIN",
        )
        assert files(client)[0]["assets"] == [board["asset_id"]]

    def test_a_cards_rom_is_linked_to_the_card(self, client, computer, part):
        machine = computer()
        card = part(type="video", model="ET4000", computer_id=machine["asset_id"])
        survey(
            client,
            roms=[("VIDEO.BIN", VGA_ROM)],
            TAG=machine["asset_id"],
            VIDEO="VGA",
            ROM1="C000 32768 VIDEO.BIN",
            VIDEO_ANSWER=card["asset_id"],
        )
        assert files(client)[0]["assets"] == [card["asset_id"]]

    def test_a_cards_rom_is_linked_to_the_machine_when_the_card_is_part_of_it(
        self, client, computer
    ):
        machine = computer()
        survey(
            client,
            roms=[("VIDEO.BIN", VGA_ROM)],
            TAG=machine["asset_id"],
            VIDEO="VGA",
            ROM1="C000 32768 VIDEO.BIN",
            VIDEO_ANSWER="MACHINE",
        )
        assert files(client)[0]["assets"] == [machine["asset_id"]]

    def test_the_rom_of_something_left_out_is_not_kept(self, client, computer):
        machine = computer()
        survey(
            client,
            roms=[("VIDEO.BIN", VGA_ROM)],
            TAG=machine["asset_id"],
            VIDEO="VGA",
            ROM1="C000 32768 VIDEO.BIN",
            VIDEO_ANSWER="OUT",
        )
        assert files(client) == []

    def test_the_same_rom_is_one_file_linked_to_one_more_thing(self, client, computer):
        first, second = computer(), computer()
        for machine in (first, second):
            survey(
                client,
                roms=[("BIOS.BIN", BIOS_ROM)],
                TAG=machine["asset_id"],
                ROM1="F000 65536 BIOS.BIN",
            )
        (kept,) = files(client)
        assert sorted(kept["assets"]) == sorted([first["asset_id"], second["asset_id"]])

    def test_roms_start_private_whatever_new_files_are_public_says(self, client, computer):
        """A BIOS is somebody's copyright, and publishing one should be a decision."""
        r = client.post("/settings/server", data={"files_public": "1"}, follow_redirects=False)
        assert r.status_code == 303, r.text
        machine = computer()
        survey(
            client,
            roms=[("BIOS.BIN", BIOS_ROM)],
            TAG=machine["asset_id"],
            ROM1="F000 65536 BIOS.BIN",
        )
        assert files(client)[0]["public"] is False

    def test_a_network_cards_boot_rom_goes_with_the_card(self, client, computer, bench_card):
        """So a bench card's boot ROM is the bench card's in every machine, and is
        never asked about."""
        card, _ = bench_card()
        made = survey(
            client,
            roms=[("NETBOOT.BIN", BOOT_ROM)],
            TAG=computer()["asset_id"],
            NIC_ROM="D000",
            ROM1="D000 16384 NETBOOT.BIN",
            **NIC,
        )
        assert made["waiting"] is None
        assert files(client)[0]["assets"] == [card["asset_id"]]

    def test_a_later_boards_bios_is_the_bios_wherever_it_starts(self, client, computer):
        """It runs to the top of the first megabyte. One that starts at E800 is the
        BIOS, and never a card to be asked about. What waits is the board it is on,
        which this machine has none of on record."""
        machine = computer()
        made = survey(
            client,
            roms=[("BIOS.BIN", BIOS_ROM)],
            TAG=machine["asset_id"],
            ROM1="E800 98304 BIOS.BIN",
        )
        assert all(f["thing"] != "ROM1" for f in made["findings"])
        assert [f["thing"] for f in made["findings"] if f["answer"] is None] == ["BOARD"]
        (kept,) = files(client)
        assert kept["note"].startswith("BIOS")
        assert kept["assets"] == [machine["asset_id"]]

    def test_its_maker_and_version_are_read_wherever_it_starts(self, client, computer, part):
        machine = computer()
        board = part(type="motherboard", computer_id=machine["asset_id"])
        survey(
            client,
            roms=[("BIOS.BIN", BIOS_ROM)],
            TAG=machine["asset_id"],
            BIOSDATE="08/22/96",
            ROM1="E800 98304 BIOS.BIN",
        )
        specs = get(client, "parts", board["asset_id"])["specs"]
        assert "Award" in specs and "4.51PG" in specs

    def test_an_option_rom_below_the_bios_is_still_a_card(self, client, computer):
        made = survey(
            client,
            roms=[("SCSI.BIN", BOOT_ROM)],
            TAG=computer()["asset_id"],
            ROM1="E000 16384 SCSI.BIN",
        )
        assert finding(made, "ROM1")["kind"] == "card"

    def test_a_network_boot_rom_is_the_cards_in_the_report_too(self, client, computer, bench_card):
        """Where the machine did not hear which ROM it is (the register was not
        reached, or an agent from before ROMs went with the question), the report's
        ROMs say it."""
        card, _ = bench_card()
        made = survey(
            client,
            roms=[("NETBOOT.C80", NETBOOT_ROM)],
            TAG=computer()["asset_id"],
            ROM1="C800 16384 NETBOOT.C80",
            **NIC,
        )
        assert all(f["thing"] != "ROM1" for f in made["findings"])
        assert made["waiting"] is None
        assert files(client)[0]["assets"] == [card["asset_id"]]

    def test_the_text_in_each_rom_is_kept_with_the_survey(self, client, computer):
        made = survey(
            client,
            roms=[("BIOS.BIN", BIOS_ROM)],
            TAG=computer()["asset_id"],
            ROM1="F000 65536 BIOS.BIN",
        )
        (rom,) = made["roms"]
        assert "Award Modular BIOS v4.51PG, An Energy Star Ally" in rom["text"]

    def test_the_bioss_maker_version_and_date_are_read_from_its_text(self, client, computer, part):
        machine = computer()
        board = part(type="motherboard", computer_id=machine["asset_id"])
        survey(
            client,
            roms=[("BIOS.BIN", BIOS_ROM)],
            TAG=machine["asset_id"],
            BIOSDATE="08/22/96",
            ROM1="F000 65536 BIOS.BIN",
        )
        specs = get(client, "parts", board["asset_id"])["specs"]
        assert "Award" in specs and "4.51PG" in specs and "08/22/96" in specs

    def test_a_bios_date_is_written_month_first(self, client, computer, part):
        """As the BIOS writes it, because that is how it is known and looked up."""
        machine = computer()
        board = part(type="motherboard", computer_id=machine["asset_id"])
        survey(client, TAG=machine["asset_id"], BIOSVENDOR="IBM", BIOSDATE="10/27/82")
        specs = get(client, "parts", board["asset_id"])["specs"]
        assert "10/27/82" in specs and "27/10/82" not in specs


# --- in the history ------------------------------------------------------------------


def lines(client, aid: str, kind: str | None = None) -> list[dict]:
    r = client.get(f"/api/items/{aid}/log")
    assert r.status_code == 200, r.text
    return [e for e in r.json() if kind is None or e["kind"] == kind]


class TestInTheHistory:
    def test_each_survey_writes_one_line_marked_survey(self, client, computer):
        machine = computer()
        survey(client, TAG=machine["asset_id"], CPU="80286", CPUKHZ="12000", OS="MS-DOS 5.00")
        assert len(lines(client, machine["asset_id"], "survey")) == 1

    def test_the_line_is_dated_when_the_survey_was_taken(self, client, computer):
        """By the agent's clock, since a machine's own is often wrong."""
        machine = computer()
        survey(client, TAG=machine["asset_id"], taken="2026-11-01T09:30:00", DATE="01/01/1980")
        (line,) = lines(client, machine["asset_id"], "survey")
        assert line["created_at"].startswith("2026-11-01T09:30")

    def test_a_machine_a_survey_made_was_made_before_it_was_surveyed(self, client):
        """Its history reads in the order it happened: made, then surveyed. The survey
        line is dated when the survey was taken, so the line that made it is too."""
        made = survey(client, TAG="NEW", taken="2026-11-01T09:30:00")
        log = lines(client, made["machine"])
        kinds = [e["kind"] for e in log]
        assert kinds.index("survey") < kinds.index("created"), kinds
        created = next(e for e in log if e["kind"] == "created")
        assert created["created_at"].startswith("2026-11-01T09:30")

    def test_a_board_a_survey_made_was_made_before_it_was_surveyed(self, client):
        made = survey(client, TAG="NEW BOARD", taken="2026-11-01T09:30:00", **BOARDISH)
        log = lines(client, made["machine"])
        kinds = [e["kind"] for e in log]
        assert kinds.index("survey") < kinds.index("created"), kinds
        created = next(e for e in log if e["kind"] == "created")
        assert created["created_at"].startswith("2026-11-01T09:30")

    def test_the_line_says_every_test_passed_and_what_was_filled_in(self, client, computer):
        machine = computer()
        survey(client, TAG=machine["asset_id"], CPU="80286", CPUKHZ="12000", **PASSED)
        (line,) = lines(client, machine["asset_id"], "survey")
        assert "every test passed" in line["message"]
        assert "CPU" in line["message"]

    def test_the_line_says_how_many_tests_failed_and_which(self, client, computer):
        machine = computer()
        survey(
            client,
            TAG=machine["asset_id"],
            RESULT="FAIL",
            TESTS="17",
            FAILED="2",
            TEST_RAM="FAIL",
            TEST_FDC="FAIL",
        )
        (line,) = lines(client, machine["asset_id"], "survey")
        assert "2 of 17 tests failed" in line["message"]
        assert "RAM" in line["message"]

    def test_the_line_says_how_many_tests_were_skipped(self, client, computer):
        """A skipped test has not been run, so the line never says every test
        passed."""
        machine = computer()
        survey(client, TAG=machine["asset_id"], **PASSED | {"TESTS": "3", "TEST_FDC": "SKIP"})
        (line,) = lines(client, machine["asset_id"], "survey")
        assert "2 of 3 tests passed, 1 skipped" in line["message"]
        assert "every test passed" not in line["message"]

    def test_the_counts_are_of_the_tests_that_apply(self, client, computer):
        """A clock test on an XT is no test at all, so it is not one of the total."""
        machine = computer()
        survey(
            client,
            TAG=machine["asset_id"],
            **PASSED | {"TESTS": "4", "NA": "1", "TEST_RTC": "NA", "TEST_FDC": "SKIP"},
        )
        (line,) = lines(client, machine["asset_id"], "survey")
        assert "2 of 3 tests passed, 1 skipped" in line["message"]

    def test_so_are_the_failures(self, client, computer):
        machine = computer()
        survey(
            client,
            TAG=machine["asset_id"],
            RESULT="FAIL",
            TESTS="17",
            NA="2",
            FAILED="2",
            TEST_RAM="FAIL",
            TEST_FDC="FAIL",
        )
        (line,) = lines(client, machine["asset_id"], "survey")
        assert "2 of 15 tests failed" in line["message"]

    def test_a_test_that_does_not_apply_still_lets_it_say_every_test_passed(self, client, computer):
        machine = computer()
        survey(client, TAG=machine["asset_id"], **PASSED | {"TEST_RTC": "NA"})
        (line,) = lines(client, machine["asset_id"], "survey")
        assert "every test passed" in line["message"]

    def test_a_soaks_line_says_how_long_it_ran(self, client, computer):
        machine = computer()
        survey(
            client,
            TAG=machine["asset_id"],
            MODE="SOAK",
            PASSES="48",
            ELAPSED="12:00:00",
            STOPPED="ESC",
            **PASSED,
        )
        (line,) = lines(client, machine["asset_id"], "survey")
        assert "48 passes over 12 hours" in line["message"]

    def test_the_line_says_nothing_a_visitor_is_not_shown(self, client, computer):
        """No serial number, no address, nowhere anything is kept: the history is
        public."""
        shelf = location(client, "Loft crate 3", "box")
        machine = computer(location=shelf["asset_id"])
        survey(client, TAG=machine["asset_id"], DISK1_ANSWER="NEW", NIC_ANSWER="NEW", **DISK, **NIC)
        (line,) = lines(client, machine["asset_id"], "survey")
        for private in ("QX123", MAC, "Loft crate 3"):
            assert private not in line["message"]

    def test_an_ethernet_address_is_never_written_into_a_parts_history(self, client, computer):
        made = survey(client, TAG=computer()["asset_id"], NIC_ANSWER="NEW", **NIC)
        card = finding(made, "NIC")["part"]
        assert all(MAC not in entry["message"] for entry in lines(client, card))


# --- what a survey never does ----------------------------------------------------------


class TestWhatASurveyNeverDoes:
    def test_it_never_changes_something_already_recorded(self, client, computer):
        machine = computer(cpu="Intel 80386DX-33", os="PC DOS 3.30", serial="ABC")
        survey(
            client,
            TAG=machine["asset_id"],
            CPU="80486",
            CPUVENDOR="GenuineIntel",
            CPUSIG="0435",
            CPUKHZ="66000",
            OS="MS-DOS 6.22",
            SYSTEM_SERIAL="XYZ",
        )
        got = get(client, "computers", machine["asset_id"])
        assert (got["cpu"], got["os"], got["serial"]) == ("Intel 80386DX-33", "PC DOS 3.30", "ABC")

    def test_it_never_makes_anything_nobody_asked_for(self, client, computer):
        machine = computer()
        before = (len(computers(client)), len(all_parts(client)))
        survey(client, TAG=machine["asset_id"], VIDEO="VGA", **DISK, **NIC)
        assert (len(computers(client)), len(all_parts(client))) == before

    def test_it_never_moves_the_machine_it_is_surveying(self, client, computer):
        shelf = location(client, "Shelf 2", "shelf")
        machine = computer(location=shelf["asset_id"])
        survey(client, TAG=machine["asset_id"])
        assert get(client, "computers", machine["asset_id"])["location"] == shelf["asset_id"]


# --- what a report says --------------------------------------------------------------


class TestWhatAReportSays:
    def test_a_report_without_an_rhdb_section_is_refused(self, client):
        assert send(client, "Every test passed.\r\n").status_code == 422

    def test_an_rhdb_section_with_nothing_in_it_is_refused(self, client):
        assert send(client, "DIAG 1.0\r\n\r\n[RHDB]\r\n").status_code == 422

    def test_a_file_with_several_reports_in_it_is_several_surveys(self, client, computer):
        first, second = computer(), computer()
        both = report(TAG=first["asset_id"]) + report(TAG=second["asset_id"])
        r = send(client, both)
        assert r.status_code == 200, r.text
        filed = [made["machine"] for made in r.json()["surveys"]]
        assert filed == [first["asset_id"], second["asset_id"]]

    def test_a_key_the_register_does_not_know_is_ignored(self, client, computer):
        machine = computer()
        made = survey(client, TAG=machine["asset_id"], SOMETHING_NEW="42")
        assert made["machine"] == machine["asset_id"]

    def test_the_report_is_kept_as_the_program_wrote_it(self, client, computer):
        made = survey(client, TAG=computer()["asset_id"])
        assert made["report"].startswith("DIAG 1.0  hardware report")

    def test_the_machines_own_clock_is_kept_beside_the_real_one(self, client, computer):
        """A machine whose clock thinks it is 1980 has a flat battery."""
        made = survey(
            client,
            TAG=computer()["asset_id"],
            taken="2026-11-06T10:00:00",
            DATE="01/01/1980",
            TIME="00:01:12",
        )
        assert made["clock"] == "01/01/1980 00:01:12"
        assert made["taken"].startswith("2026-11-06T10:00")


# --- a report as tinydiag writes it ----------------------------------------------------

TINYDIAG = Path(__file__).parent / "data" / "tinydiag-0.8.0-qemu.txt"


def tinydiag_report(**answers: str) -> str:
    """The report tinydiag 0.8.0 wrote in QEMU, with the answers given at the machine
    where the program puts them: the tag in its own line, the rest before [END]."""
    text = TINYDIAG.read_bytes().decode("cp437")
    if tag := answers.pop("TAG", ""):
        text = text.replace("\r\nTAG=\r\n", f"\r\nTAG={tag}\r\n", 1)
    added = "".join(f"{k}={v}\r\n" for k, v in answers.items())
    return text.replace("[END]\r\n", added + "[END]\r\n")


class TestAReportAsTinydiagWritesIt:
    """A survey program's own report rather than the register's idea of one: what
    tinydiag 0.8.0 wrote on QEMU's PC, with an IDE disk, a CD-ROM, a BIOS that starts at
    E800, and three tests skipped."""

    def test_n_at_the_machine_makes_a_computer_of_what_it_found(self, client):
        r = send(
            client,
            tinydiag_report(
                TAG="NEW",
                BOARD_ANSWER="NEW",
                DISK1_ANSWER="NEW",
                DISK2_ANSWER="MACHINE",
                FLOPPY1_ANSWER="NEW",
                VIDEO_ANSWER="NEW",
                PORTS_ANSWER="MACHINE",
            ),
        )
        assert r.status_code == 200, r.text
        (sent,) = r.json()["surveys"]
        made = read(client, sent["id"])
        assert made["waiting"] is None
        floppy = get(client, "parts", finding(made, "FLOPPY1")["part"])
        assert "Size: 1.44MB" in floppy["specs"]
        board = get(client, "parts", finding(made, "BOARD")["part"])
        assert board["computer_id"] == made["machine"]
        assert "06/23/99" in board["specs"]
        machine = get(client, "computers", made["machine"])
        # QEMU's clock, measured faithfully.
        assert machine["cpu"] == "Intel 486DX4-3857"
        assert machine["installed_ram"] == "4 MiB"
        assert machine["os"] == "MS-DOS with Windows"
        assert "DVD-ROM" in machine["drives"]
        disk = get(client, "parts", finding(made, "DISK1")["part"])
        assert (disk["model"], disk["serial"]) == ("QEMU HARDDISK", "QM00001")

    def test_its_receipt_says_three_tests_were_skipped(self, client):
        r = send(client, tinydiag_report(TAG="NEW"))
        assert r.status_code == 200, r.text
        assert "14 of 17 tests passed, 3 skipped." in r.json()["receipt"]

    def test_left_alone_it_waits_to_be_told_which_machine_it_is(self, client):
        r = send(client, tinydiag_report())
        assert r.status_code == 200, r.text
        (sent,) = r.json()["surveys"]
        assert sent["waiting"] == "machine"
