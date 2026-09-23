"""The catalogue of known machines, and filing a machine against it.

Three kinds of test here. The catalogue's own consistency, because it is data and a
typo in it is a wrong suggestion offered to every machine of that model. The
rows-to-string mapping, because computers.variant is a cache and a cache that
disagrees with what it caches is worse than no cache. And the two doors -- the form
and the API -- because everything in this register has to arrive by either and leave
the same record behind.
"""

import sys
import textwrap
from datetime import date
from pathlib import Path
from typing import ClassVar

import pytest

from conftest import served
from app import entry, machinedb, machines
from app.history import item_log
from app.models import AssetChip, AssetVariant, Computer, Part

ROOT = Path(__file__).resolve().parent.parent.parent


class TestCatalogueConsistency:
    def test_every_model_key_is_unique(self):
        keys = machines.keys()
        assert len(keys) == len(set(keys))

    def test_every_key_resolves(self):
        assert all(machines.model(k) is not None for k in machines.keys())  # noqa: SIM118

    def test_an_unknown_key_is_none_rather_than_an_error(self):
        assert machines.model("zx-spectrum-1024k") is None
        assert machines.model("") is None

    @pytest.mark.parametrize("key", machines.keys())
    def test_a_model_says_what_it_is(self, key):
        """The window runs from the Altair that started it to the last machine
        anybody here would call retro, and its job is not to police what belongs in
        the catalogue -- that is the documented-model rule, and it is a judgement
        rather than an arithmetic. Its job is to catch a year typed with a digit
        missing or a digit too many.

        It was a fixed year, and it moved twice in a day -- for Sony's console line,
        which is one family running from 1994 to 2006, and again for the DOS
        machines being made in Shenzhen now. So the far end is simply this year:
        nothing was made in the future, and a fixed ceiling was only ever standing
        in for that while sounding like a statement about what belongs here. What
        belongs is the documented-model rule, which is a judgement rather than an
        arithmetic, and this test was never the place it was made."""
        m = machines.model(key)
        assert m["model"] and m["manufacturer"] and m["family"]
        assert isinstance(m["year"], int) and 1969 < m["year"] <= date.today().year

    @pytest.mark.parametrize("key", machines.keys())
    def test_every_memory_size_is_a_figure_the_register_can_read(self, key):
        """The labels are offered on the memory box, which reads them with
        entry.to_kb -- so '48K' has to come back as the 48 KB the catalogue says it
        is, or picking a standard size would record the wrong machine."""
        for label, kb in machines.model(key)["ram"]:
            assert entry.to_kb(label) == kb, label

    @pytest.mark.parametrize("key", machines.keys())
    def test_each_socket_is_asked_once_and_has_something_to_offer(self, key):
        chips = machines.model(key)["chips"]
        roles = [c["role"] for c in chips]
        assert len(roles) == len(set(roles))
        for c in chips:
            assert c["label"] and c["variants"]
            assert len(set(c["variants"])) == len(c["variants"])

    @pytest.mark.parametrize("key", machines.keys())
    def test_nothing_offered_is_longer_than_the_column_that_holds_it(self, key):
        """A suggestion the database could not store would fail on save rather than
        at the keyboard."""
        m = machines.model(key)
        assert len(key) <= AssetVariant.model_key.type.length
        for issue in m["issues"]:
            assert len(issue) <= AssetVariant.issue.type.length, issue
        for style in m["styles"]:
            assert len(style) <= AssetVariant.style.type.length, style
        for region in m["regions"]:
            assert len(region) <= AssetVariant.region.type.length, region
        for chip in m["chips"]:
            assert len(chip["role"]) <= AssetChip.role.type.length
            for variant in chip["variants"]:
                assert len(variant) <= AssetChip.variant.type.length, variant

    def test_the_machines_asked_for_are_all_there(self):
        """The list this was built for, by the names they are known by -- which is
        the maker and the model together, since the catalogue holds them apart."""
        wanted = [
            "Commodore 64",
            "Sinclair ZX Spectrum+",
            "Commodore 16",
            "Atari 65XE",
            "Sega Mega Drive",
            "Amstrad CPC 464",
            "Amstrad CPC 6128",
            "Acorn BBC Micro Model B",
            "Commodore Amiga 500",
        ]
        have = {machines.full_name(k) for k in machines.keys()}  # noqa: SIM118
        assert not [w for w in wanted if w not in have]

    def test_no_model_repeats_its_maker(self):
        """The model field fills the machine's model box and the manufacturer fills
        its own, so a model named "Commodore 64" filed a C64 as "Commodore Commodore
        64". Whatever is added here later, the two fields say each thing once.

        The maker has to be there as a word of its own to be a repeat. A
        ColecoVision is one word that Coleco is inside of, not a maker written
        twice, and there is no split of it that is not a worse name -- so the rule
        is about the separator, and full_name says such a name once."""
        doubled = [
            (m["manufacturer"], m["model"])
            for m in machines.models()
            if m["manufacturer"] and m["model"].lower().startswith(m["manufacturer"].lower() + " ")
        ]
        assert doubled == []

    def test_a_name_its_maker_is_inside_of_is_said_once(self):
        assert machines.full_name("colecovision") == "ColecoVision"
        assert machines.full_name("c64") == "Commodore 64"

    def test_a_model_inherits_its_family_sockets(self):
        assert "ula" in machines.roles("zx-spectrum-48k")
        assert (
            machines.chip("zx-spectrum-48k", "ula")["variants"]
            == machines.chip("zx-spectrum-16k", "ula")["variants"]
        )

    def test_a_model_can_replace_one_of_them(self):
        """The +2A has Amstrad's gate array where the family has a Ferranti ULA."""
        assert machines.chip("zx-spectrum-plus2a", "ula")["variants"] == ["Amstrad 40056"]
        assert machines.chip("zx-spectrum-plus2a", "ula")["label"] == "ASIC"

    def test_a_model_can_say_it_has_no_such_socket(self):
        """A VIC-20 is a Commodore 8-bit but has no SID, and its sound is the VIC's.
        Answering the family's question would be recording a chip that is not in
        there."""
        assert "sid" in machines.roles("c64")
        assert "sid" not in machines.roles("vic-20")
        assert "ula" not in machines.roles("zx80")

    def test_sockets_are_asked_in_the_order_a_board_is_read_in(self):
        """A model's own additions follow the family's, rather than jumping the
        queue: a Spectrum +3 is asked for its CPU and ULA before its floppy
        controller."""
        assert machines.roles("zx-spectrum-plus3")[:2] == ["cpu", "ula"]
        assert "fdc" in machines.roles("zx-spectrum-plus3")[2:]

    def test_the_machines_a_person_asked_for_are_all_there(self):
        """The second round: the 8- and 16-bit machines of Europe, America and
        Japan, by the names they are known by."""
        wanted = [
            "Apple IIe",
            "Apple Macintosh Plus",
            "Tandy TRS-80 Model I",
            "Texas Instruments TI-99/4A",
            "ColecoVision",
            "Mattel Intellivision",
            "Commodore PET 2001",
            "Sinclair QL",
            "Oric Atmos",
            "Dragon 32",
            "MGT SAM Coupé",
            "Enterprise 128",
            "Thomson MO5",
            "Nintendo Entertainment System",
            "Nintendo Game Boy",
            "Nintendo Super NES",
            "NEC PC Engine",
            "Sharp X68000",
            "Fujitsu FM-7",
            "Toshiba HX-10",
            "Sega SG-1000",
            "Atari Lynx",
            "Acorn Atom",
            "Commodore CD32",
        ]
        have = {machines.full_name(k) for k in machines.keys()}  # noqa: SIM118
        assert not [w for w in wanted if w not in have]

    def test_the_picker_is_in_an_order_a_person_can_guess(self):
        """Seventy-odd makers and three hundred machines is only usable if you can
        guess where to look, so both lists are alphabetical -- worked out on load,
        so neither depends on the file staying tidy."""
        makers = [(f["manufacturer"] or f["name"]).casefold() for f in machines.FAMILIES]
        assert makers == sorted(makers)
        for family in machines.FAMILIES:
            names = [m["model"] for m in family["models"]]
            assert names == sorted(names, key=machines._by_name), family["name"]

    def test_a_number_in_a_name_sorts_as_a_number(self):
        """Alphabetical by characters would file the Amiga 1000 before the 500 and
        the 1040ST before the 520ST, which is not what anyone means by it."""
        family = next(f for f in machines.FAMILIES if f["key"] == "amiga")
        amiga = [m["model"] for m in family["models"]]
        assert amiga.index("Amiga 500") < amiga.index("Amiga 1000")
        assert amiga.index("Amiga 600") < amiga.index("Amiga 1200")

    def test_the_catalogue_for_the_form_covers_every_model(self):
        cat = machines.form_catalogue()
        assert set(cat) == set(machines.keys())
        spectrum = cat["zx-spectrum-plus"]
        assert spectrum["prefill"]["manufacturer"] == "Sinclair"
        assert spectrum["prefill"]["year"] == 1984
        assert "48K" in spectrum["ram"]
        assert "Issue 6A" in spectrum["issues"]
        assert [c["role"] for c in spectrum["chips"]] == ["cpu", "ula"]

    def test_prefill_only_offers_what_is_true_of_every_one_of_them(self):
        p = machines.prefill("c64")
        assert p["manufacturer"] == "Commodore" and p["model"] == "64"
        assert p["year"] == 1982 and p["chassis"] == "breadbin"
        # Not condition, source, or anything else about a particular machine.
        assert set(p) == {"manufacturer", "model", "year", "cpu", "chassis", "os"}

    def test_a_model_offers_the_sizes_it_was_sold_with_and_no_others(self):
        assert machines.ram_labels("zx-spectrum-48k") == ["48K", "16K"]
        assert machines.ram_labels("zx-spectrum-128") == ["128K"]


class TestRendering:
    def test_a_machine_reads_as_the_machine_it_is(self):
        assert machines.render(
            "zx-spectrum-plus",
            "Issue 6A",
            "moulded keys",
            "PAL (UK/Europe)",
            {"ula": "Ferranti 6C001E-7"},
        ) == (
            "ZX Spectrum+ | Board: Issue 6A | Style: moulded keys | "
            "Region: PAL (UK/Europe) | ULA: Ferranti 6C001E-7"
        )

    def test_the_model_is_the_subject_rather_than_an_attribute(self):
        """It comes first and without a key, the way parse_specs keeps a keyless
        segment -- so a label can name it and nothing has to strip a prefix."""
        assert entry.parse_specs(machines.render("c64"))[0] == ("", "64")

    def test_what_is_not_known_is_not_said(self):
        assert machines.render("c64", "", "", "", {}) == "64"
        assert machines.render() == ""

    def test_chips_are_said_in_board_order_whatever_order_they_arrive_in(self):
        line = machines.render("c64", chips={"sid": "MOS 6581", "cpu": "MOS 6510"})
        assert line == "64 | CPU: MOS 6510 | SID: MOS 6581"

    def test_a_chip_from_a_socket_the_catalogue_dropped_still_says_what_it_is(self):
        """What was seen on the board is not wrong for having gone out of the
        catalogue, so the role slug names itself: short ones read as the acronyms
        they are, longer ones as words."""
        assert machines.render("c64", chips={"sidx": "Whatsit 9000"}) == "64 | SIDX: Whatsit 9000"
        assert (
            machines.render("c64", chips={"sound-chip": "Whatsit 9000"})
            == "64 | Sound chip: Whatsit 9000"
        )

    def test_a_model_key_the_catalogue_lost_is_still_named(self):
        assert machines.render("zx-spectrum-2048k") == "zx-spectrum-2048k"


class TestStorage:
    def test_a_machine_with_nothing_recorded_reads_blank(self, computer, db):
        c = db.get(Computer, computer()["asset_id"])
        assert machinedb.read(db, c) == machinedb.BLANK

    def test_what_goes_in_comes_back(self, computer, db):
        c = db.get(Computer, computer()["asset_id"])
        machinedb.write(
            db,
            c,
            model_key="c64",
            issue="ASSY 250425",
            style="rainbow label",
            region="PAL",
            chips={"sid": "MOS 6581R4", "vic": "MOS 6569R3"},
        )
        db.commit()
        assert machinedb.read(db, c) == {
            "model_key": "c64",
            "issue": "ASSY 250425",
            "style": "rainbow label",
            "region": "PAL",
            "chips": {"vic": "MOS 6569R3", "sid": "MOS 6581R4"},
            # Nothing was said about how they are held, and nothing is assumed.
            "sockets": {},
        }

    def test_how_a_chip_is_held_survives_the_chips_being_rewritten(self, computer, db):
        """write() replaces the chip rows wholesale, so a later call that names only
        the variants must not lose what was said about their sockets."""
        c = db.get(Computer, computer()["asset_id"])
        machinedb.write(db, c, model_key="c64", chips={"sid": "MOS 6581"}, sockets={"sid": True})
        machinedb.write(db, c, chips={"sid": "MOS 6581R4", "cpu": "MOS 6510"})
        db.commit()
        v = machinedb.read(db, c)
        assert v["chips"] == {"cpu": "MOS 6510", "sid": "MOS 6581R4"}
        assert v["sockets"] == {"sid": True}

    def test_the_sockets_can_be_answered_on_their_own(self, computer, db):
        c = db.get(Computer, computer()["asset_id"])
        machinedb.write(db, c, model_key="c64", chips={"sid": "MOS 6581"})
        machinedb.write(db, c, sockets={"sid": False})
        db.commit()
        v = machinedb.read(db, c)
        assert v["chips"] == {"sid": "MOS 6581"} and v["sockets"] == {"sid": False}

    def test_the_cache_is_written_from_the_rows(self, computer, db):
        c = db.get(Computer, computer()["asset_id"])
        machinedb.write(db, c, model_key="c64", chips={"sid": "MOS 8580R5"})
        db.commit()
        assert c.variant == "64 | SID: MOS 8580R5"

    def test_a_field_not_named_is_left_as_it_was(self, computer, db):
        """The convention ramdb and drivedb already follow: a caller that knows one
        thing must not wipe the others."""
        c = db.get(Computer, computer()["asset_id"])
        machinedb.write(db, c, model_key="c64", issue="ASSY 250407", chips={"sid": "MOS 6581"})
        machinedb.write(db, c, style="silver label")
        db.commit()
        v = machinedb.read(db, c)
        assert v["issue"] == "ASSY 250407" and v["chips"] == {"sid": "MOS 6581"}
        assert v["style"] == "silver label"

    def test_a_blank_chip_clears_that_socket_and_leaves_the_others(self, computer, db):
        c = db.get(Computer, computer()["asset_id"])
        machinedb.write(db, c, model_key="c64", chips={"sid": "MOS 6581", "cpu": "MOS 6510"})
        machinedb.write(db, c, chips={"sid": "", "cpu": "MOS 6510"})
        db.commit()
        assert machinedb.read(db, c)["chips"] == {"cpu": "MOS 6510"}

    def test_filing_a_machine_out_of_the_catalogue_forgets_all_of_it(self, computer, db):
        c = db.get(Computer, computer()["asset_id"])
        machinedb.write(db, c, model_key="c64", issue="ASSY 250425", chips={"sid": "MOS 6581"})
        machinedb.write(db, c, model_key="")
        db.commit()
        assert machinedb.read(db, c) == machinedb.BLANK
        assert c.variant == ""
        assert db.query(AssetChip).count() == 0
        assert db.query(AssetVariant).count() == 0

    def test_changing_model_keeps_the_chips_the_new_one_also_has(self, computer, db):
        c = db.get(Computer, computer()["asset_id"])
        machinedb.write(db, c, model_key="c64", chips={"sid": "MOS 6581", "cpu": "MOS 6510"})
        machinedb.write(db, c, model_key="c64c")
        db.commit()
        assert machinedb.read(db, c)["chips"] == {"cpu": "MOS 6510", "sid": "MOS 6581"}

    def test_changing_model_drops_the_chips_it_has_no_socket_for(self, computer, db):
        """A machine refiled as a Spectrum has no SID, and a record saying it has
        one describes a machine nobody owns."""
        c = db.get(Computer, computer()["asset_id"])
        machinedb.write(db, c, model_key="c64", chips={"sid": "MOS 6581"})
        machinedb.write(db, c, model_key="zx-spectrum-48k")
        db.commit()
        assert machinedb.read(db, c)["chips"] == {}
        assert c.variant == "ZX Spectrum 48K"

    def test_reading_many_takes_two_queries_and_gets_the_same_answers(self, computer, db):
        first = db.get(Computer, computer()["asset_id"])
        second = db.get(Computer, computer()["asset_id"])
        plain = db.get(Computer, computer()["asset_id"])
        machinedb.write(db, first, model_key="c64", chips={"sid": "MOS 6581"})
        machinedb.write(db, second, model_key="zx-spectrum-48k", issue="Issue 3B")
        db.commit()
        many = machinedb.read_many(db, [first, second, plain])
        assert many[first.asset_id] == machinedb.read(db, first)
        assert many[second.asset_id] == machinedb.read(db, second)
        assert plain.asset_id not in many

    def test_deleting_a_machine_takes_its_catalogue_rows_with_it(self, client, computer, db):
        c = db.get(Computer, computer()["asset_id"])
        machinedb.write(db, c, model_key="c64", chips={"sid": "MOS 6581"})
        db.commit()
        assert client.delete(f"/api/computers/{c.asset_id}").status_code == 200
        assert db.query(AssetChip).count() == 0
        assert db.query(AssetVariant).count() == 0


class TestApi:
    def test_the_catalogue_is_readable_over_the_wire(self, client):
        r = client.get("/api/machines")
        assert r.status_code == 200
        families = r.json()["families"]
        models = [m for f in families for m in f["models"]]
        assert len(models) == len(machines.keys())
        c64 = next(m for m in models if m["key"] == "c64")
        assert c64["model"] == "64" and c64["year"] == 1982
        assert "ASSY 250425" in c64["issues"]
        assert "MOS 6581" in next(c["variants"] for c in c64["chips"] if c["role"] == "sid")

    def test_a_machine_can_be_created_as_one(self, client):
        r = client.post(
            "/api/computers",
            json={
                "manufacturer": "Sinclair",
                "model": "ZX Spectrum+",
                "machine": {
                    "model_key": "zx-spectrum-plus",
                    "issue": "Issue 6A",
                    "style": "moulded keys",
                    "chips": {"ula": "Ferranti 6C001E-7"},
                },
            },
        )
        assert r.status_code == 200, r.text
        body = r.json()
        assert body["machine"]["model"] == "ZX Spectrum+"
        assert body["machine"]["family"] == "Sinclair ZX"
        assert body["machine"]["chips"] == {"ula": "Ferranti 6C001E-7"}
        assert body["variant"] == (
            "ZX Spectrum+ | Board: Issue 6A | Style: moulded keys | ULA: Ferranti 6C001E-7"
        )

    def test_sockets_ride_over_the_wire_beside_the_chips(self, client):
        r = client.post(
            "/api/computers",
            json={
                "manufacturer": "Commodore",
                "model": "64",
                "machine": {
                    "model_key": "c64",
                    "chips": {"sid": "MOS 6581"},
                    "sockets": {"sid": True},
                },
            },
        )
        assert r.status_code == 200, r.text
        assert r.json()["machine"]["sockets"] == {"sid": True}

    def test_a_mounting_can_be_changed_without_saying_the_chips_again(self, client):
        """The web form always sends the two together, so nothing had tried this:
        sockets alone, on a machine that already has a chip recorded. A loop over
        the chip rows reused the name the variant row was held under, and the next
        line asked a chip for its model."""
        made = client.post(
            "/api/computers",
            json={
                "manufacturer": "Commodore",
                "model": "64",
                "machine": {
                    "model_key": "c64",
                    "chips": {"sid": "MOS 6581"},
                    "sockets": {"sid": True},
                },
            },
        ).json()
        r = client.patch(
            f"/api/computers/{made['asset_id']}",
            json={"machine": {"model_key": "c64", "sockets": {"sid": False}}},
        )
        assert r.status_code == 200, r.text
        assert r.json()["machine"]["sockets"] == {"sid": False}
        assert r.json()["machine"]["chips"] == {"sid": "MOS 6581"}

    def test_a_socket_for_a_chip_the_model_has_not_got_is_refused(self, client):
        r = client.post(
            "/api/computers",
            json={
                "manufacturer": "Commodore",
                "model": "64",
                "machine": {"model_key": "c64", "sockets": {"ula": True}},
            },
        )
        assert r.status_code == 422 and "ula" in r.text

    def test_a_machine_that_is_not_one_says_so(self, computer):
        assert computer()["machine"] is None

    def test_it_comes_back_on_get_and_on_the_list(self, client, computer):
        c = computer(machine={"model_key": "c16"})
        assert client.get(f"/api/computers/{c['asset_id']}").json()["machine"]["model"] == "16"
        listed = {row["asset_id"]: row for row in client.get("/api/computers").json()}
        assert listed[c["asset_id"]]["machine"]["model_key"] == "c16"

    def test_a_patch_changes_only_what_it_names(self, client, computer):
        c = computer(
            machine={"model_key": "c64", "issue": "ASSY 250407", "chips": {"sid": "MOS 6581"}}
        )
        r = client.patch(
            f"/api/computers/{c['asset_id']}", json={"machine": {"style": "silver label"}}
        )
        assert r.status_code == 200, r.text
        m = r.json()["machine"]
        assert m["issue"] == "ASSY 250407" and m["chips"] == {"sid": "MOS 6581"}
        assert m["style"] == "silver label"

    def test_a_patch_that_says_nothing_about_it_leaves_it_alone(self, client, computer):
        c = computer(machine={"model_key": "c64", "issue": "ASSY 250425"})
        r = client.patch(f"/api/computers/{c['asset_id']}", json={"notes": "cleaned"})
        assert r.json()["machine"]["issue"] == "ASSY 250425"

    def test_null_forgets_the_catalogue(self, client, computer):
        c = computer(machine={"model_key": "c64", "chips": {"sid": "MOS 6581"}})
        r = client.patch(f"/api/computers/{c['asset_id']}", json={"machine": None})
        assert r.status_code == 200, r.text
        assert r.json()["machine"] is None and r.json()["variant"] == ""

    def test_a_model_the_catalogue_does_not_have_is_refused(self, client):
        r = client.post(
            "/api/computers", json={"model": "X", "machine": {"model_key": "zx-spectrum"}}
        )
        assert r.status_code == 422
        assert "zx-spectrum" in r.text

    def test_a_socket_the_model_does_not_have_is_refused(self, client):
        r = client.post(
            "/api/computers",
            json={
                "model": "X",
                "machine": {"model_key": "c64", "chips": {"ula": "Ferranti 6C001E-7"}},
            },
        )
        assert r.status_code == 422
        assert "ula" in r.text

    def test_a_chip_is_checked_against_the_model_already_on_file(self, client, computer):
        c = computer(machine={"model_key": "c64"})
        r = client.patch(
            f"/api/computers/{c['asset_id']}", json={"machine": {"chips": {"sid": "MOS 8580R5"}}}
        )
        assert r.status_code == 200, r.text
        bad = client.patch(
            f"/api/computers/{c['asset_id']}", json={"machine": {"chips": {"ted": "MOS 7360"}}}
        )
        assert bad.status_code == 422

    def test_the_rendered_line_is_read_only(self, client, computer):
        """It is written from the rows, so sending one has no effect -- the rule
        installed_ram and drives already follow."""
        c = computer(machine={"model_key": "c64"})
        r = client.patch(f"/api/computers/{c['asset_id']}", json={"variant": "an Amiga, honestly"})
        assert r.json()["variant"] == "64"

    def test_a_change_of_machine_is_in_the_history(self, client, computer):
        c = computer(machine={"model_key": "c64"})
        client.patch(
            f"/api/computers/{c['asset_id']}", json={"machine": {"chips": {"sid": "MOS 6581R4"}}}
        )
        page = client.get(f"/computers/{c['asset_id']}").text
        assert "MOS 6581R4" in page


class TestForm:
    def _new(self, client, **fields):
        r = client.post(
            "/computers/new",
            data={"manufacturer": "Sinclair", "model": "Spectrum", **fields},
            follow_redirects=False,
        )
        assert r.status_code == 303, r.text
        return r.headers["location"].split("/computers/")[1].split("?")[0]

    def test_the_form_offers_every_model(self, client):
        page = client.get("/computers/new").text
        assert 'value="zx-spectrum-plus"' in page
        assert 'value="megadrive"' in page
        # The catalogue itself is shipped for the script to build the rest from.
        assert "Ferranti 6C001E-7" in page

    def test_a_machine_can_be_filed_from_the_form(self, client, db):
        aid = self._new(
            client,
            mach_model="zx-spectrum-48k",
            mach_fields="1",
            mach_issue="Issue 3B",
            mach_style="rubber keys",
            mach_region="PAL (UK/Europe)",
            **{"chip:ula": "Ferranti 6C001E-7", "chip:cpu": "NEC D780C-1"},
        )
        c = db.get(Computer, aid)
        v = machinedb.read(db, c)
        assert v["model_key"] == "zx-spectrum-48k" and v["issue"] == "Issue 3B"
        assert v["chips"] == {"cpu": "NEC D780C-1", "ula": "Ferranti 6C001E-7"}
        assert "ULA: Ferranti 6C001E-7" in c.variant

    def test_the_edit_form_comes_back_with_what_was_picked(self, client, db):
        aid = self._new(
            client,
            mach_model="c64",
            mach_fields="1",
            mach_issue="ASSY 250425",
            **{"chip:sid": "MOS 6581R4"},
        )
        page = client.get(f"/computers/{aid}/edit").text
        assert 'value="c64" selected' in page
        # The saved answers go to the script, which builds the boxes from them.
        assert "ASSY 250425" in page and "MOS 6581R4" in page

    def test_a_socket_the_model_does_not_have_is_ignored(self, client, db):
        """Fields left over from another model in the same tab cannot put a ULA in a
        Commodore 64."""
        aid = self._new(
            client,
            mach_model="c64",
            mach_fields="1",
            **{"chip:ula": "Ferranti 6C001E-7", "chip:sid": "MOS 6581"},
        )
        c = db.get(Computer, aid)
        assert machinedb.read(db, c)["chips"] == {"sid": "MOS 6581"}

    def test_the_tickbox_says_which_chips_are_in_a_socket(self, client, db):
        """A socketed chip can be swapped to test a fault; a soldered one is forty
        pins and a desoldering station. The box beside each chip records which."""
        aid = self._new(
            client,
            mach_model="c64",
            mach_fields="1",
            **{"chip:sid": "MOS 6581", "chip:sid:socketed": "on", "chip:vic": "MOS 6569R3"},
        )
        v = machinedb.read(db, db.get(Computer, aid))
        assert v["sockets"] == {"sid": True, "vic": False}

    def test_a_socket_nobody_named_a_chip_for_is_not_answered_either(self, client, db):
        """The box is off for every socket on the form, including the ones left at
        "not recorded". Saving must not turn that into a claim that a chip nobody
        has looked at is soldered down -- there is no chip there to hold."""
        aid = self._new(
            client,
            mach_model="c64",
            mach_fields="1",
            **{"chip:sid": "MOS 6581", "chip:sid:socketed": "on"},
        )
        v = machinedb.read(db, db.get(Computer, aid))
        assert v["chips"] == {"sid": "MOS 6581"} and v["sockets"] == {"sid": True}

    def test_unticking_it_says_soldered_rather_than_forgetting(self, client, db):
        aid = self._new(
            client,
            mach_model="c64",
            mach_fields="1",
            **{"chip:sid": "MOS 6581", "chip:sid:socketed": "on"},
        )
        r = client.post(
            f"/computers/{aid}/edit",
            data={
                "manufacturer": "Commodore",
                "model": "64",
                "mach_model": "c64",
                "mach_fields": "1",
                "chip:sid": "MOS 6581",
            },
            follow_redirects=False,
        )
        assert r.status_code == 303
        assert machinedb.read(db, db.get(Computer, aid))["sockets"] == {"sid": False}

    def test_a_save_that_could_not_draw_the_fields_does_not_erase_them(self, client, db):
        """Without the marker the script sets, only the model choice is read: a
        browser that ran no JavaScript submits no variation fields, and a blank
        field it never drew must not read as an answer of "nothing"."""
        aid = self._new(
            client,
            mach_model="c64",
            mach_fields="1",
            mach_issue="ASSY 250425",
            **{"chip:sid": "MOS 6581"},
        )
        r = client.post(
            f"/computers/{aid}/edit",
            data={"manufacturer": "Commodore", "model": "64", "mach_model": "c64"},
            follow_redirects=False,
        )
        assert r.status_code == 303
        c = db.get(Computer, aid)
        v = machinedb.read(db, c)
        assert v["issue"] == "ASSY 250425" and v["chips"] == {"sid": "MOS 6581"}

    def test_choosing_not_a_catalogue_model_files_it_out(self, client, db):
        aid = self._new(client, mach_model="c64", mach_fields="1", mach_issue="ASSY 250425")
        r = client.post(
            f"/computers/{aid}/edit",
            data={"manufacturer": "Commodore", "model": "64", "mach_model": ""},
            follow_redirects=False,
        )
        assert r.status_code == 303
        c = db.get(Computer, aid)
        assert machinedb.read(db, c) == machinedb.BLANK and c.variant == ""

    def test_a_form_that_never_asked_leaves_a_machine_alone(self, client, computer, db):
        """Another form posting to the same handler -- one with no machine picker on
        it at all -- must not clear what this one recorded."""
        c = db.get(Computer, computer()["asset_id"])
        machinedb.write(db, c, model_key="c64", issue="ASSY 250425")
        db.commit()
        r = client.post(
            f"/computers/{c.asset_id}/edit",
            data={"manufacturer": "Commodore", "model": "64"},
            follow_redirects=False,
        )
        assert r.status_code == 303
        db.expire_all()
        assert machinedb.read(db, c)["issue"] == "ASSY 250425"

    def test_the_machine_page_says_what_it_is(self, client, db):
        aid = self._new(
            client,
            mach_model="zx-spectrum-plus",
            mach_fields="1",
            mach_issue="Issue 6A",
            mach_style="moulded keys",
            **{"chip:ula": "Ferranti 6C001E-7"},
        )
        page = client.get(f"/computers/{aid}").text
        assert "ZX Spectrum+" in page and "Issue 6A" in page
        assert "ULA" in page and "Ferranti 6C001E-7" in page

    def test_a_machine_outside_the_catalogue_has_no_such_section(self, client, computer):
        page = client.get(f"/computers/{computer()['asset_id']}").text
        assert "Catalogue model" not in page

    def test_the_label_carries_the_board_and_the_chips(self, client, db):
        """On a sealed machine nothing inside has a tag of its own, so the label is
        the only place the board issue and the ULA can be printed.

        The chips share one line, named by their sockets: a machine has a CPU field
        and a CPU socket saying different true things, and two label lines both
        headed CPU would read as a contradiction."""
        aid = self._new(
            client,
            mach_model="zx-spectrum-48k",
            mach_fields="1",
            mach_issue="Issue 3B",
            cpu="Zilog Z80A-3.5",
            **{"chip:ula": "Ferranti 6C001E-7", "chip:cpu": "NEC D780C-1"},
        )
        from app import labels
        from app.common import to_dict

        lines = labels.computer_lines(to_dict(db.get(Computer, aid)), [])
        assert "Machine: ZX Spectrum 48K" in lines
        assert "Board: Issue 3B" in lines
        assert "Chips: CPU NEC D780C-1, ULA Ferranti 6C001E-7" in lines
        assert len([x for x in lines if x.startswith("CPU:")]) == 1

    def test_a_label_for_a_machine_outside_the_catalogue_is_unchanged(self, computer, db):
        from app import labels
        from app.common import to_dict

        c = db.get(Computer, computer(cpu="Intel 486DX2-66")["asset_id"])
        lines = labels.computer_lines(to_dict(c), [])
        assert not [x for x in lines if x.startswith(("Machine:", "Chips:"))]

    def test_a_duplicate_is_the_same_model_and_not_the_same_board(self, client, db):
        """Another one of these is another one of these; which board issue and which
        ULA are in it are found by opening it."""
        aid = self._new(
            client,
            mach_model="c64",
            mach_fields="1",
            mach_issue="ASSY 250425",
            **{"chip:sid": "MOS 6581"},
        )
        r = client.post(f"/computers/{aid}/duplicate", follow_redirects=False)
        copy = r.headers["location"].split("/computers/")[1]
        v = machinedb.read(db, db.get(Computer, copy))
        assert v["model_key"] == "c64"
        assert v["issue"] == "" and v["chips"] == {}

    def test_a_machine_is_searchable_by_the_chip_in_it(self, client, db):
        """What the rendered cache is for: the register is searched over every text
        column, so a part number recorded in a socket is a way back to the
        machine."""
        aid = self._new(client, mach_model="c64", mach_fields="1", **{"chip:sid": "MOS 8580R5"})
        hits = client.get("/?q=8580R5").text
        assert aid in hits


class TestWhereTheBoardAndPartsAreAskedFor:
    """A PC is described by what is fitted in it, so its page carries the motherboard
    and the parts list. A catalogue machine is not that sort of object -- a C64 has
    no board to link and nothing on a shelf goes in one -- so while it has neither,
    the page it is read on says nothing about them and the edit form carries them
    instead, which is where a drive that does turn up gets added from."""

    def _c64(self, client):
        r = client.post(
            "/computers/new",
            data={
                "manufacturer": "Commodore",
                "model": "64",
                "mach_model": "c64",
                "mach_fields": "1",
            },
            follow_redirects=False,
        )
        assert r.status_code == 303, r.text
        return r.headers["location"].split("/computers/")[1].split("?")[0]

    def test_a_bare_catalogue_machine_is_not_asked_about_either(self, client):
        page = client.get(f"/computers/{self._c64(client)}").text
        assert "add motherboard" not in page
        assert ">Motherboard<" not in page and "Parts <span" not in page

    def test_its_edit_form_carries_them_instead(self, client):
        page = client.get(f"/computers/{self._c64(client)}/edit").text
        assert "add motherboard" in page
        assert "/parts/new?computer_id=" in page

    def test_fitting_something_brings_them_back_to_the_page(self, client, part):
        aid = self._c64(client)
        part(type="storage", model="1541", computer_id=aid)
        page = client.get(f"/computers/{aid}").text
        assert "add motherboard" in page and "1541" in page
        # ...and the form stops offering what the page now has.
        assert "add motherboard" not in client.get(f"/computers/{aid}/edit").text

    def test_a_pc_keeps_them_on_its_page_and_off_its_form(self, client, computer):
        aid = computer()["asset_id"]
        assert "add motherboard" in client.get(f"/computers/{aid}").text
        assert "add motherboard" not in client.get(f"/computers/{aid}/edit").text

    def test_parts_are_added_from_one_button(self, client, computer):
        """ "add part -- one button for every kind; the form it opens asks the type
        first." A row of them was the same menu said twice."""
        aid = computer()["asset_id"]
        page = client.get(f"/computers/{aid}").text
        assert f'href="/parts/new?computer_id={aid}">add part</a>' in page
        assert "type=video&computer_id=" not in page

    def test_the_form_it_opens_claims_no_type_yet(self, client, computer):
        aid = computer()["asset_id"]
        page = client.get(f"/parts/new?computer_id={aid}").text
        assert "<h2>New part</h2>" in page
        assert "<h2>New Video</h2>" in client.get("/parts/new?type=video").text

    def test_how_a_chip_is_held_rides_on_the_socket(self, client, db):
        """Six sockets each ending in "— soldered to the board" is a paragraph; a
        tick and a cross are read at a glance. Each socket is a card of its own, and
        the mark sits on its strip beside the socket's name -- it answers how this
        one is held, which is a fact about the socket rather than about the number
        marked on the chip."""
        aid = self._c64(client)
        c = db.get(Computer, aid)
        machinedb.write(
            db, c, chips={"sid": "MOS 6581", "cpu": "MOS 6510"}, sockets={"sid": True, "cpu": False}
        )
        db.commit()
        page = client.get(f"/computers/{aid}").text
        assert '<div class="cardgrid">' in page
        assert 'aria-label="in a socket" title="in a socket">✓' in page
        assert 'aria-label="soldered to the board" title="soldered to the board">✗' in page

    def test_a_socket_nobody_has_looked_in_says_nothing(self, client, db):
        """Neither answer is not the same as soldered."""
        aid = self._c64(client)
        c = db.get(Computer, aid)
        machinedb.write(db, c, chips={"sid": "MOS 6581"}, sockets={})
        db.commit()
        page = client.get(f"/computers/{aid}").text
        assert "MOS 6581" in page and "soldered to the board" not in page


class TestACatalogueThatGrows:
    """The catalogue names what is commonly seen, and the register keeps meeting
    what is not. A variation typed into the custom box once is offered as a button
    ever after, so discovering a ULA nobody had written up is a thing you do once.
    """

    def cat(self, recorded):
        return machines.with_recorded(machines.form_catalogue(), recorded)

    def ula(self, catalogue, key="zx-spectrum-48k"):
        return next(c["variants"] for c in catalogue[key]["chips"] if c["role"] == "ula")

    def test_a_chip_the_catalogue_never_heard_of_is_offered(self):
        out = self.ula(self.cat({"zx-spectrum-48k": {"chips": {"ula": ["Ferranti 6C001W-8"]}}}))
        assert "Ferranti 6C001W-8" in out

    def test_the_curated_order_is_kept_and_discoveries_follow(self):
        """What was written down deliberately is what a person reads down first."""
        known = self.ula(self.cat({}))
        out = self.ula(self.cat({"zx-spectrum-48k": {"chips": {"ula": ["AAA first"]}}}))
        assert out[: len(known)] == known
        assert out[-1] == "AAA first"

    def test_one_already_offered_is_not_offered_twice(self):
        out = self.ula(self.cat({"zx-spectrum-48k": {"chips": {"ula": ["Ferranti 6C001E-7"]}}}))
        assert out.count("Ferranti 6C001E-7") == 1

    def test_a_difference_of_case_or_spacing_is_not_a_different_chip(self):
        out = self.ula(self.cat({"zx-spectrum-48k": {"chips": {"ula": ["ferranti  6C001E-7"]}}}))
        assert len([v for v in out if v.lower().replace("  ", " ") == "ferranti 6c001e-7"]) == 1

    def test_what_one_model_teaches_is_not_told_about_another(self):
        """A ULA found in a Spectrum says nothing about a Commodore 64."""
        cat = self.cat({"zx-spectrum-48k": {"chips": {"ula": ["Ferranti 9Z9"]}}})
        for chip in cat["c64"]["chips"]:
            assert "Ferranti 9Z9" not in chip["variants"]

    def test_a_socket_the_catalogue_dropped_is_not_brought_back(self):
        cat = self.cat({"c64": {"chips": {"ula": ["Ferranti 6C001E-7"]}}})
        assert "ula" not in [c["role"] for c in cat["c64"]["chips"]]

    def test_the_other_variations_grow_the_same_way(self):
        cat = self.cat(
            {
                "c64": {
                    "issues": ["ASSY 250466 rev B"],
                    "styles": ["Aldi C64 (short board)"],
                    "regions": ["PAL"],
                }
            }
        )
        assert "ASSY 250466 rev B" in cat["c64"]["issues"]
        # ...and the ones it already knew are still there once each.
        assert cat["c64"]["styles"].count("Aldi C64 (short board)") == 1
        assert cat["c64"]["regions"].count("PAL") == 1

    def test_what_machines_say_is_read_back_by_model(self, computer, db):
        c = db.get(Computer, computer()["asset_id"])
        machinedb.write(
            db, c, model_key="zx-spectrum-48k", issue="Issue 3B", chips={"ula": "Ferranti 6C001W-8"}
        )
        db.commit()
        seen = machinedb.recorded(db)
        assert seen["zx-spectrum-48k"]["chips"]["ula"] == ["Ferranti 6C001W-8"]
        assert seen["zx-spectrum-48k"]["issues"] == ["Issue 3B"]

    def test_a_machine_outside_the_catalogue_teaches_nothing(self, computer, db):
        c = db.get(Computer, computer()["asset_id"])
        machinedb.write(db, c, model_key="")
        db.commit()
        assert machinedb.recorded(db) == {}

    def test_a_chip_typed_once_is_offered_on_the_next_machine(self, client):
        """The whole point, end to end: the custom box on one machine puts the chip
        into the list the next machine's form is built from."""
        r = client.post(
            "/computers/new",
            data={
                "manufacturer": "Sinclair",
                "model": "Spectrum",
                "mach_model": "zx-spectrum-48k",
                "mach_fields": "1",
                "chip:ula": "custom",
                "chip:ula_custom": "Ferranti 6C001W-8",
            },
            follow_redirects=False,
        )
        assert r.status_code == 303, r.text
        # A blank form: the only place this can appear is the catalogue the script
        # builds its buttons from.
        assert "Ferranti 6C001W-8" in client.get("/computers/new").text

    def test_the_custom_box_is_what_gets_stored(self, client, db):
        r = client.post(
            "/computers/new",
            data={
                "manufacturer": "Commodore",
                "model": "64",
                "mach_model": "c64",
                "mach_fields": "1",
                "mach_issue": "custom",
                "mach_issue_custom": "  ASSY 250425  rev C ",
                "chip:sid": "MOS 6582",
            },
            follow_redirects=False,
        )
        aid = r.headers["location"].split("/computers/")[1].split("?")[0]
        row = db.get(AssetVariant, aid)
        # Squeezed, like every other typed answer the form takes.
        assert row.issue == "ASSY 250425 rev C"
        assert db.query(AssetChip).filter(AssetChip.asset_id == aid).one().variant == "MOS 6582"

    def test_custom_with_nothing_typed_records_nothing(self, client, db):
        r = client.post(
            "/computers/new",
            data={
                "manufacturer": "Commodore",
                "model": "64",
                "mach_model": "c64",
                "mach_fields": "1",
                "chip:sid": "custom",
                "chip:sid_custom": "   ",
            },
            follow_redirects=False,
        )
        aid = r.headers["location"].split("/computers/")[1].split("?")[0]
        assert db.query(AssetChip).filter(AssetChip.asset_id == aid).count() == 0


class TestABoardIsFiledLikeTheMachineItCameOutOf:
    """The board is the object the catalogue's questions were always about. A bare
    Amiga 500 board on a shelf is a real thing with an asset tag, and it is a Rev 6A
    with this Agnus and this Gary in it -- so it files against the same catalogue,
    from the same pickers, into the same two tables, and teaches them the same
    lessons. What it is not asked is the case style and the region: those are facts
    about a whole machine in a box, and a board out of a PAL Spectrum is not a PAL
    board.
    """

    def _board(self, client, **fields):
        r = client.post(
            "/parts/new", data={"type": "motherboard", **fields}, follow_redirects=False
        )
        assert r.status_code == 303, r.text
        return r.headers["location"].rsplit("/", 1)[1].split("?")[0]

    def test_what_goes_in_comes_back(self, part, db):
        p = db.get(Part, part(type="motherboard")["asset_id"])
        machinedb.write(
            db,
            p,
            model_key="amiga-500",
            issue="Rev 6A",
            chips={"agnus": "8372A (ECS, 1MB)", "gary": "5719"},
            sockets={"agnus": True},
        )
        db.commit()
        v = machinedb.read(db, p)
        assert v["model_key"] == "amiga-500" and v["issue"] == "Rev 6A"
        assert v["chips"] == {"agnus": "8372A (ECS, 1MB)", "gary": "5719"}
        assert v["sockets"] == {"agnus": True}

    def test_the_rendered_line_lands_on_the_part(self, part, db):
        """parts.variant is the same cache computers.variant is, over the same rows
        -- which is why refresh() does not have to know which it has been handed."""
        p = db.get(Part, part(type="motherboard")["asset_id"])
        machinedb.write(db, p, model_key="amiga-500", issue="Rev 6A", chips={"gary": "5719"})
        db.commit()
        assert p.variant == "Amiga 500 | Board: Rev 6A | Gary: 5719"

    def test_a_bare_board_is_created_from_the_pickers(self, client, db):
        """The point of the whole thing: a shelf spare is filed as "Amiga 500 board,
        Rev 6A, these chips" from a menu, not as a sentence in the notes."""
        aid = self._board(
            client,
            model="Amiga 500",
            mach_model="amiga-500",
            mach_fields="1",
            mach_issue="Rev 6A",
            **{"chip:agnus": "8372A (ECS, 1MB)", "chip:agnus:socketed": "on"},
        )
        p = db.get(Part, aid)
        v = machinedb.read(db, p)
        assert v["model_key"] == "amiga-500" and v["issue"] == "Rev 6A"
        assert v["chips"] == {"agnus": "8372A (ECS, 1MB)"}
        assert v["sockets"] == {"agnus": True}
        assert p.computer_id is None

    def test_the_form_offers_the_catalogue_to_a_board_and_to_nothing_else(self, client):
        board = client.get("/parts/new?type=motherboard").text
        assert 'value="amiga-500"' in board and "Rev 6A" in board
        # A SIMM is not a model of machine, and the catalogue is a quarter of a
        # megabyte that a form which cannot use it does not need to carry.
        ram = client.get("/parts/new?type=ram").text
        assert 'value="amiga-500"' not in ram and "mach_model" not in ram

    def test_only_a_board_is_filed_however_the_form_arrives(self, client, db):
        """The pickers are on no other type's form, so this can only be a hand-made
        post -- and it is refused there too rather than in the markup alone."""
        aid = self._board(
            client, type="ram", mach_model="c64", mach_fields="1", **{"chip:sid": "MOS 6581"}
        )
        p = db.get(Part, aid)
        assert machinedb.read(db, p) == machinedb.BLANK and p.variant == ""

    def test_a_board_is_not_asked_the_two_questions_a_case_answers(self, client, db):
        """The script that draws the variation fields is the machine form's own, told
        which form it is on, and it draws neither of them for a board. The save reads
        the form the same way round, so a stray field left over from a machine's form
        in the same browser tab is not read either."""
        page = served(client, client.get("/parts/new?type=motherboard").text)
        assert '"board": true' in page
        aid = self._board(
            client, mach_model="amiga-500", mach_fields="1", mach_style="A500", mach_region="PAL"
        )
        v = machinedb.read(db, db.get(Part, aid))
        assert v["style"] == "" and v["region"] == ""

    def test_the_edit_form_comes_back_with_what_was_picked(self, client):
        aid = self._board(
            client,
            mach_model="amiga-500",
            mach_fields="1",
            mach_issue="Rev 6A",
            **{"chip:gary": "5719"},
        )
        page = client.get(f"/parts/{aid}/edit").text
        assert 'value="amiga-500" selected' in page
        assert "Rev 6A" in page and "5719" in page

    def test_the_part_page_says_which_machine_it_is_out_of(self, client):
        aid = self._board(
            client,
            mach_model="amiga-500",
            mach_fields="1",
            mach_issue="Rev 6A",
            **{"chip:gary": "5719"},
        )
        page = client.get(f"/parts/{aid}").text
        assert "Catalogue model" in page and "Amiga 500" in page
        assert "Rev 6A" in page and "Gary" in page and "5719" in page

    def test_an_ordinary_part_has_no_such_section(self, client, part):
        page = client.get(f"/parts/{part()['asset_id']}").text
        assert "Catalogue model" not in page

    def test_the_label_carries_the_board_and_its_chips(self, client, db):
        """A bare board in a box says nothing about itself; the label is the only
        place its revision is written where a person can read it."""
        from app import labels
        from app.common import to_dict

        aid = self._board(
            client,
            mach_model="amiga-500",
            mach_fields="1",
            mach_issue="Rev 6A",
            **{"chip:gary": "5719"},
        )
        lines = labels.part_lines(to_dict(db.get(Part, aid)))
        assert "Machine: Amiga 500" in lines
        assert "Board: Rev 6A" in lines
        assert "Chips: Gary 5719" in lines

    def test_retyping_it_out_of_being_a_board_forgets_the_catalogue(self, client, db):
        """A record saying this RAM stick is an Amiga 500 board describes nothing
        anybody owns -- the same rule as filing a machine out of the catalogue."""
        aid = self._board(client, mach_model="amiga-500", mach_fields="1", mach_issue="Rev 6A")
        r = client.post(f"/parts/{aid}/edit", data={"type": "ram"}, follow_redirects=False)
        assert r.status_code == 303
        p = db.get(Part, aid)
        db.refresh(p)
        assert machinedb.read(db, p) == machinedb.BLANK and p.variant == ""

    def test_a_duplicate_is_the_same_model_and_not_the_same_board(self, client, db):
        """Another one of these is another one of these; which revision it is and
        what is in its sockets are read off the board in your hand."""
        aid = self._board(
            client,
            mach_model="amiga-500",
            mach_fields="1",
            mach_issue="Rev 6A",
            **{"chip:gary": "5719"},
        )
        r = client.post(f"/parts/{aid}/duplicate", follow_redirects=False)
        copy = r.headers["location"].rsplit("/", 1)[1]
        v = machinedb.read(db, db.get(Part, copy))
        assert v["model_key"] == "amiga-500"
        assert v["issue"] == "" and v["chips"] == {}

    def test_deleting_a_board_takes_its_catalogue_rows_with_it(self, client, db):
        """There is no foreign key to cascade any more -- an asset id is the whole
        register's, not one table's -- so the delete path clears them by hand."""
        aid = self._board(client, mach_model="amiga-500", mach_fields="1", **{"chip:gary": "5719"})
        p = db.get(Part, aid)
        p.disposed = True
        db.commit()
        assert client.delete(f"/api/parts/{aid}").status_code == 200
        assert db.query(AssetChip).count() == 0
        assert db.query(AssetVariant).count() == 0

    def test_a_board_teaches_the_catalogue_what_a_machine_would(self, client):
        """A Rev nobody had written up is the same evidence about Amiga 500 boards
        wherever it was read off: it is the same board either way, and which object
        it was found on is exactly what does not matter about it."""
        self._board(
            client,
            mach_model="amiga-500",
            mach_fields="1",
            mach_issue="custom",
            mach_issue_custom="Rev 9Z",
            **{"chip:gary": "custom", "chip:gary_custom": "5719 (rev B)"},
        )
        # A blank machine's form: the only place these can appear is the catalogue
        # its buttons are built from.
        page = client.get("/computers/new").text
        assert "Rev 9Z" in page and "5719 (rev B)" in page

    def test_a_machine_and_its_board_share_one_pair_of_tables(self, client, computer, db):
        """Which is the whole of what keying them by asset id buys: one row each, in
        the same two tables, read and written by the same code."""
        aid = self._board(client, mach_model="amiga-500", mach_fields="1", mach_issue="Rev 6A")
        c = db.get(Computer, computer()["asset_id"])
        machinedb.write(db, c, model_key="amiga-500", issue="Rev 8A")
        db.commit()
        assert {r.asset_id for r in db.query(AssetVariant).all()} == {aid, c.asset_id}

    def test_the_line_is_searchable_the_way_a_machine_s_is(self, client):
        aid = self._board(
            client, mach_model="amiga-500", mach_fields="1", **{"chip:agnus": "8372A (ECS, 1MB)"}
        )
        assert aid in client.get("/?q=8372A").text


class TestTheBoardsDoorOnTheApi:
    def test_a_board_can_be_created_as_one(self, client):
        r = client.post(
            "/api/parts",
            json={
                "type": "motherboard",
                "model": "Amiga 500",
                "machine": {"model_key": "amiga-500", "issue": "Rev 6A", "chips": {"gary": "5719"}},
            },
        )
        assert r.status_code == 200, r.text
        body = r.json()
        assert body["machine"]["model"] == "Amiga 500"
        assert body["machine"]["family"] == "Commodore Amiga"
        assert body["variant"] == "Amiga 500 | Board: Rev 6A | Gary: 5719"

    def test_a_part_that_is_not_one_says_so(self, part):
        p = part()
        assert p["machine"] is None and p["variant"] == ""

    def test_it_comes_back_on_get_and_on_the_list(self, client):
        r = client.post(
            "/api/parts",
            json={"type": "motherboard", "machine": {"model_key": "amiga-500", "issue": "Rev 6A"}},
        )
        aid = r.json()["asset_id"]
        assert client.get(f"/api/parts/{aid}").json()["machine"]["issue"] == "Rev 6A"
        listed = {row["asset_id"]: row for row in client.get("/api/parts").json()}
        assert listed[aid]["machine"]["model_key"] == "amiga-500"

    def test_only_a_motherboard_may_have_one(self, client):
        """A card or a SIMM filed as a Commodore 64 is a mistake worth hearing
        about, and one the register would have nowhere to show."""
        r = client.post("/api/parts", json={"type": "ram", "machine": {"model_key": "c64"}})
        assert r.status_code == 422 and "motherboard" in r.text

    def test_a_board_is_not_asked_about_a_case(self, client):
        """The two a machine answers are not in the shape at all, so sending one is
        the same mistake as sending any other field the register has not got."""
        r = client.post(
            "/api/parts",
            json={"type": "motherboard", "machine": {"model_key": "amiga-500", "style": "A500"}},
        )
        assert r.status_code == 422 and "style" in r.text

    def test_a_socket_the_model_does_not_have_is_refused(self, client):
        r = client.post(
            "/api/parts",
            json={
                "type": "motherboard",
                "machine": {"model_key": "amiga-500", "chips": {"sid": "MOS 6581"}},
            },
        )
        assert r.status_code == 422 and "sid" in r.text

    def test_a_patch_changes_only_what_it_names(self, client):
        aid = client.post(
            "/api/parts",
            json={
                "type": "motherboard",
                "machine": {"model_key": "amiga-500", "issue": "Rev 6A", "chips": {"gary": "5719"}},
            },
        ).json()["asset_id"]
        r = client.patch(f"/api/parts/{aid}", json={"notes": "recapped"})
        assert r.json()["machine"]["issue"] == "Rev 6A"
        r = client.patch(f"/api/parts/{aid}", json={"machine": {"issue": "Rev 8A"}})
        m = r.json()["machine"]
        assert m["issue"] == "Rev 8A" and m["chips"] == {"gary": "5719"}

    def test_null_forgets_the_catalogue(self, client):
        aid = client.post(
            "/api/parts", json={"type": "motherboard", "machine": {"model_key": "amiga-500"}}
        ).json()["asset_id"]
        r = client.patch(f"/api/parts/{aid}", json={"machine": None})
        assert r.json()["machine"] is None and r.json()["variant"] == ""

    def test_anything_may_be_asked_to_forget_one_it_has_not_got(self, client, part):
        """Null asks for nothing to be there, which is a request a SIMM can answer
        as well as a board can."""
        r = client.patch(f"/api/parts/{part()['asset_id']}", json={"machine": None})
        assert r.status_code == 200 and r.json()["machine"] is None

    def test_retyping_it_out_of_being_a_board_forgets_the_catalogue(self, client):
        aid = client.post(
            "/api/parts", json={"type": "motherboard", "machine": {"model_key": "amiga-500"}}
        ).json()["asset_id"]
        r = client.patch(f"/api/parts/{aid}", json={"type": "ram"})
        assert r.status_code == 200, r.text
        assert r.json()["machine"] is None and r.json()["variant"] == ""

    def test_the_rendered_line_is_read_only(self, client):
        """Written from the rows, so sending one has no effect -- the rule
        installed_ram and drives already follow."""
        aid = client.post(
            "/api/parts", json={"type": "motherboard", "machine": {"model_key": "amiga-500"}}
        ).json()["asset_id"]
        r = client.patch(f"/api/parts/{aid}", json={"variant": "a Spectrum, really"})
        assert r.json()["variant"] == "Amiga 500"


class TestDetachingTheBoard:
    """The verb that turns a piece of a description into an object.

    A sealed Spectrum is one object and its board issue is one of the answers the
    machine gives about itself. Lift the board out onto a shelf and that stops being
    true: it is now a thing that can be photographed, tagged, swapped and sold
    separately, which is the register's whole test for an asset id. So the board
    issue and the chips move onto the new object, because they were always facts
    about the board; the model is copied, because the machine is still a Spectrum;
    and the case style and the region stay, because the case did not move.

    One press, one object, one way. There is no re-absorb: refitting a board is
    setting computer_id like any other part, and folding an object back into a
    description would mean deleting a tagged, photographed thing.
    """

    @staticmethod
    def image(name="board.jpg"):
        import io

        from PIL import Image

        buf = io.BytesIO()
        Image.new("RGB", (400, 300), (40, 90, 60)).save(buf, "JPEG", quality=90)
        buf.seek(0)
        return (name, buf, "image/jpeg")

    def machine(self, client, db, **fields):
        """A Spectrum with a board issue, a ULA, a case style and a region -- one of
        each of the four answers, so a test can tell which of them moved."""
        c = db.get(
            Computer,
            client.post(
                "/api/computers", json={"manufacturer": "Sinclair", "model": "ZX Spectrum 48K"}
            ).json()["asset_id"],
        )
        machinedb.write(
            db,
            c,
            model_key="zx-spectrum-48k",
            issue="Issue 4B",
            style="rubber keys",
            region="PAL (UK/Europe)",
            chips={"ula": "6C001E-7"},
            sockets={"ula": True},
        )
        db.commit()
        return c

    def detach(self, client, aid, files=None):
        r = client.post(f"/computers/{aid}/detach-board", files=files, follow_redirects=False)
        assert r.status_code == 303, r.text
        return r.headers["location"].rsplit("/", 1)[1]

    def test_the_board_becomes_an_object_holding_the_board_s_own_answers(self, client, db):
        c = self.machine(client, db)
        board = db.get(Part, self.detach(client, c.asset_id))
        assert board.type == "motherboard"
        v = machinedb.read(db, board)
        assert v["model_key"] == "zx-spectrum-48k"
        assert v["issue"] == "Issue 4B"
        assert v["chips"] == {"ula": "6C001E-7"} and v["sockets"] == {"ula": True}
        # The two a case answers were never asked of the board and are not invented
        # for it: a board out of a rubber-key Spectrum is not a rubber-key board.
        assert v["style"] == "" and v["region"] == ""

    def test_the_machine_keeps_being_the_machine_on_the_shelf(self, client, db):
        """Its id, its model, its case and its market are untouched -- what it has
        stopped being able to answer is which board is in it, because the board is
        answering for itself now."""
        c = self.machine(client, db)
        was = c.asset_id
        self.detach(client, was)
        db.refresh(c)
        v = machinedb.read(db, c)
        assert c.asset_id == was
        assert v["model_key"] == "zx-spectrum-48k"
        assert v["style"] == "rubber keys" and v["region"] == "PAL (UK/Europe)"
        assert v["issue"] == "" and v["chips"] == {}

    def test_the_rendered_lines_follow_the_rows_on_both(self, client, db):
        """Two caches over one pair of tables, so the machine's line loses the board
        issue in the same write that puts it on the board's."""
        c = self.machine(client, db)
        board = db.get(Part, self.detach(client, c.asset_id))
        db.refresh(c)
        assert "Issue 4B" in board.variant and "6C001E-7" in board.variant
        assert "Issue 4B" not in c.variant and "6C001E-7" not in c.variant
        assert "rubber keys" in c.variant

    def test_the_board_is_linked_back_into_the_machine_it_came_out_of(self, client, db):
        """Detaching is about the object, not about where it is: the board is out of
        the case and still fitted to that machine."""
        c = self.machine(client, db)
        board = db.get(Part, self.detach(client, c.asset_id))
        assert board.computer_id == c.asset_id
        assert f"/parts/{board.asset_id}" in client.get(f"/computers/{c.asset_id}").text

    def test_both_histories_name_the_other(self, client, db):
        """One event, written down on both sides of it -- the register's answer to
        "where did this board come from" and "what happened to that machine"."""
        c = self.machine(client, db)
        aid = self.detach(client, c.asset_id)
        theirs = [e.message for e in item_log(db, c.asset_id)]
        mine = [e.message for e in item_log(db, aid)]
        assert any(aid in m for m in theirs)
        assert any(c.asset_id in m for m in mine)

    def test_the_board_s_history_opens_with_where_it_came_from(self, client, db):
        """A detached board was not created out of nothing, and its first line says
        so rather than saying "created" -- the birth and the separation are one
        event."""
        c = self.machine(client, db)
        first = item_log(db, self.detach(client, c.asset_id))[-1]
        assert first.kind == "created"
        assert first.message == f"detached from computer {c.asset_id}"

    def test_the_maker_and_the_model_come_across_and_nothing_else_does(self, client, db):
        """Enough that the board has a name in a list; not so much that the register
        claims to know the condition of a board nobody has looked at."""
        c = self.machine(client, db)
        c.condition = "working"
        c.source = "eBay"
        db.commit()
        board = db.get(Part, self.detach(client, c.asset_id))
        assert board.manufacturer == "Sinclair" and board.model == "ZX Spectrum 48K"
        assert not board.condition and not board.source
        assert board.year is None and board.acquired_date is None

    def test_the_photograph_taken_while_it_is_out_becomes_its_portrait(self, client, db):
        """The point of the form. A board is photographable at the moment it is out
        of the case and before it goes back in, and that moment does not come round
        again -- so the file picker is on the page that records the separation."""
        from app import main

        c = self.machine(client, db)
        aid = self.detach(client, c.asset_id, files={"photos": self.image()})
        assert (main.IMAGES_DIR / "parts" / f"{aid}.jpg").exists()
        assert db.get(Part, aid).image == f"parts/{aid}.jpg"

    def test_it_goes_through_without_one(self, client, db):
        """A separation that really happened is recorded even with no camera to hand:
        an object with no portrait is a gap to be chased later, not a reason to write
        down the wrong thing now."""
        c = self.machine(client, db)
        board = db.get(Part, self.detach(client, c.asset_id))
        assert board.image in ("", None)
        assert machinedb.read(db, board)["issue"] == "Issue 4B"

    def test_a_machine_the_catalogue_does_not_name_has_nothing_to_move(self, client, computer):
        """A PC's board is already an object described by its chipset and its slots,
        and is entered as a part in the ordinary way."""
        aid = computer()["asset_id"]
        assert client.get(f"/computers/{aid}/detach-board").status_code == 400
        assert client.post(f"/computers/{aid}/detach-board").status_code == 400

    def test_a_machine_has_one_board(self, client, db):
        """The scope guard: one object per real separation event. Without it the
        button is one object per press, which is inventing hardware rather than
        recording what happened."""
        c = self.machine(client, db)
        first = self.detach(client, c.asset_id)
        r = client.post(f"/computers/{c.asset_id}/detach-board")
        assert r.status_code == 400 and first in r.text
        assert db.query(Part).filter(Part.type == "motherboard").count() == 1

    def test_the_action_is_offered_where_the_answers_it_moves_are_read(self, client, db):
        c = self.machine(client, db)
        assert "detach-board" in client.get(f"/computers/{c.asset_id}").text
        self.detach(client, c.asset_id)
        assert "detach-board" not in client.get(f"/computers/{c.asset_id}").text

    def test_the_page_says_what_will_move_before_it_moves(self, client, db):
        c = self.machine(client, db)
        page = client.get(f"/computers/{c.asset_id}/detach-board").text
        assert "Issue 4B" in page and "6C001E-7" in page
        # And what will not, said out loud: "detach" reads like the machine is being
        # taken to pieces, and the case is not going anywhere.
        assert "rubber keys" in page and "PAL (UK/Europe)" in page
        assert "keeps its asset tag" in page

    def test_a_board_lifted_out_and_unlinked_can_be_refitted_like_any_part(self, client, db):
        """One way only. Refitting is not a re-absorb -- there is no undo that would
        fold a tagged, photographed object back into a description -- it is setting
        computer_id, and the board keeps its own answers through both."""
        c = self.machine(client, db)
        aid = self.detach(client, c.asset_id)
        client.post(f"/parts/{aid}/unlink", follow_redirects=False)
        # An unlinked board is offered for linking wherever the free-board queries
        # run: the machine's own page once something else is fitted, and the edit
        # form for the catalogue machine with nothing in it.
        assert aid in client.get(f"/computers/{c.asset_id}/edit").text
        r = client.post(
            f"/computers/{c.asset_id}/link-motherboard",
            data={"part_id": aid},
            follow_redirects=False,
        )
        assert r.status_code == 303
        board = db.get(Part, aid)
        db.refresh(board)
        assert board.computer_id == c.asset_id
        assert machinedb.read(db, board)["issue"] == "Issue 4B"
        # And the machine did not get the board issue back by having the board put
        # back in it. The board is where that is written down now.
        db.refresh(c)
        assert machinedb.read(db, c)["issue"] == ""

    def test_a_detached_board_is_asked_the_catalogue_s_questions_on_its_own_form(self, client, db):
        """It arrives filed, so its edit form comes back with what moved -- and it is
        the board's form, which does not ask the two a case answers."""
        c = self.machine(client, db)
        page = served(client, client.get(f"/parts/{self.detach(client, c.asset_id)}/edit").text)
        assert 'value="zx-spectrum-48k" selected' in page
        assert "Issue 4B" in page and "6C001E-7" in page
        assert '"board": true' in page

    def test_the_memory_rows_stay_on_the_machine(self, client, db):
        """Left where they are on purpose, and noted as an open question rather than
        guessed at: those rows count chips rather than identify them, and they are
        half of how a machine's installed RAM is rendered."""
        from app import ramdb

        c = self.machine(client, db)
        ramdb.write(db, c, [], [("4116", 16)], "", None)
        db.commit()
        self.detach(client, c.asset_id)
        db.refresh(c)
        assert ramdb.read(db, c) == ([], [("4116", 16)])
        assert c.installed_ram == "16× 4116 (32 KiB)" and c.installed_ram_kb == 32


class TestResync:
    def test_a_board_that_has_drifted_is_reported_and_rewritten(self, part, db):
        """A board goes stale for the reason a machine does, and against the same
        catalogue: renaming a model has to reach both."""
        from app import resync

        p = db.get(Part, part(type="motherboard")["asset_id"])
        machinedb.write(db, p, model_key="amiga-500", chips={"gary": "5719"})
        p.variant = "Amiga 500 | Gary: something else"
        db.commit()
        assert [x[0].asset_id for x in resync.plan_variant(db)] == [p.asset_id]
        machinedb.refresh(db, p)
        db.commit()
        assert p.variant == "Amiga 500 | Gary: 5719"
        assert resync.plan_variant(db) == []

    def test_a_line_that_has_drifted_is_reported_and_rewritten(self, computer, db):
        """The catalogue's words are not stored, so correcting one leaves every
        machine filed under it rendering the old wording until it is edited. This is
        what brings them back into line."""
        from app import resync

        c = db.get(Computer, computer()["asset_id"])
        machinedb.write(db, c, model_key="c64", chips={"sid": "MOS 6581"})
        c.variant = "64 | SID: something else"
        db.commit()
        assert [x[0].asset_id for x in resync.plan_variant(db)] == [c.asset_id]
        machinedb.refresh(db, c)
        db.commit()
        assert c.variant == "64 | SID: MOS 6581"
        assert resync.plan_variant(db) == []


class TestReadingATypedRecordAgainstTheCatalogue:
    """Most of this register was typed before the catalogue existed: a maker and a
    model in two free-text boxes, which is how a person writes down what is on the
    badge. machines.suggest is how the two are introduced -- it proposes, a person
    decides, and nothing here writes anything.

    The cases are all real ones out of the live register, because a matcher tuned
    against invented names is tuned against nothing.
    """

    @staticmethod
    def best(maker, model):
        found = machines.suggest(maker, model)
        return found[0][0] if found else None

    def test_the_same_name_written_the_same_way_is_the_top_match(self):
        assert self.best("Amstrad", "PC1640") == "amstrad-pc1640"
        assert self.best("Commodore", "Amiga 500") == "amiga-500"
        assert self.best("IBM", "PS/2 Model 80") == "ps2-8580"

    def test_a_trailing_space_is_not_a_different_manufacturer(self):
        """Two records in the live register carry one -- "IBM " and "Amstrad " --
        and a space is not a maker. _fold absorbs it, as it does for everything
        else that asks whether two answers are the same answer."""
        assert self.best("Amstrad ", "PC2286") == "amstrad-pc2286"
        assert machines.suggest("IBM ", "5170") == machines.suggest("IBM", "5170")

    def test_a_number_is_not_a_near_miss(self):
        """The one that made this need a scorer of its own. Letter by letter "IBM
        5170" is slightly closer to "IBM PC 5150" than to "IBM PC/AT 5170", because
        the wrong one is shorter -- and a 5170 is not almost a 5150."""
        found = {k: s for k, s, _e in machines.suggest("IBM", "5170")}
        assert self.best("IBM", "5170") == "ibm-5170"
        assert "ibm-5150" not in found
        assert self.best("Amstrad", "PC1512") == "amstrad-pc1512"

    def test_a_model_that_says_more_than_the_catalogue_does_still_matches(self):
        """ "Olivetti Personal Computer M21" is what is on the badge, in full. The
        catalogue calls it the M21, and difflib's ratio halves for the extra
        words."""
        assert self.best("Olivetti", "Personal Computer M21") == "olivetti-m21"

    def test_an_aside_in_the_model_box_does_not_hide_the_match(self):
        """ "GRiDCASE 2 (Philips PC200)" is somebody recording a second opinion
        beside the name rather than naming the machine that."""
        key, score, exact = machines.suggest("Grid", "GRiDCASE 2 (Philips PC200)")[0]
        assert (key, exact) == ("grid-gridcase-2", True)
        assert score == 1.0

    def test_the_same_name_beats_a_name_it_is_inside_of(self):
        """A machine typed as "BBC Micro Model B" is as wholly inside "BBC Micro
        Model B+" as it is inside itself, and only one of those is what somebody
        wrote down."""
        assert self.best("Acorn", "BBC Micro Model B") == "bbc-model-b"
        assert self.best("Compaq", "Deskpro 386") == "compaq-deskpro-386"

    def test_a_fuller_model_beats_the_line_it_belongs_to(self):
        """ "Compaq Portable" is a real machine and a real prefix of the one on the
        record, so both are offered -- but the record carries a number and the
        model that shares it is the better reading."""
        found = [k for k, _s, _e in machines.suggest("Compaq", "Portable 486/66")]
        assert found[0] == "compaq-portable-486"
        assert "compaq-portable" in found  # still offered, just not first

    def test_a_machine_is_found_under_its_other_name(self):
        """Half the styles in the catalogue are second names: an Olivetti M24 is an
        AT&T 6300 in America, a Victor 9000 is a Sirius 1 here, a VTech Laser 3000
        is a Dick Smith Cat in Australia, and a Tandon PCX has TM 6001A on the
        plate. Somebody typing what is in front of them types one of those as often
        as the name the catalogue happens to file it under."""
        assert self.best("Tandon", "TM6001A") == "tandon-pcx"
        assert self.best("AT&T", "6300") == "olivetti-m24"
        assert self.best("Sony", "Sirius 1") == "victor-9000"
        assert self.best("Dick Smith", "Cat") == "laser-3000"

    def test_a_style_is_only_read_against_the_whole_name(self):
        """The other half of the styles are configurations, not names -- "386SX-20",
        "two drives", "mono". Tested against a bare model box those find anything:
        a Pocket 386 typed as model "386sx-40" matched the PS/1 Model 2121, whose
        styles list its two clock speeds."""
        assert self.best("Pocket DOS", "386sx-40") == "pocket-386"
        assert "ps1-2121" not in [k for k, _s, _e in machines.suggest("Pocket DOS", "386sx-40")]

    def test_a_name_beats_the_same_score_reached_through_a_style(self):
        """A style is the second answer to what a machine is called, so where a
        model's own name is as good a match it wins. Nothing in the catalogue is
        filed under a style."""
        assert machines._BY_STYLE < 1

    def test_a_machine_the_catalogue_does_not_know_gets_no_answer(self):
        """The point of the floor. A whitebox clone, an office PC from after the
        era and a modern reproduction have nothing to be filed as, and saying so is
        the correct outcome rather than a failure to match."""
        assert machines.suggest("Mitac", "MiStation 4052F/M") == []
        assert machines.suggest("IBM ", "ThinkCentre 8183-21G") == []
        assert machines.suggest("Intel", "Xpress System Deskside LX Base 8TE16F") == []

    def test_nothing_typed_suggests_nothing(self):
        assert machines.suggest("", "") == []
        assert machines.suggest("   ", None) == []

    def test_every_score_is_a_fraction(self):
        for maker, model in (
            ("IBM", "5170"),
            ("Acorn", "BBC Micro Model B"),
            ("Compaq", "Portable 486/66"),
            ("Opus", "PCV Turbo"),
        ):
            for _key, score, _exact in machines.suggest(maker, model):
                assert machines.MATCH_FLOOR <= score <= 1.0

    def test_where_the_record_and_the_catalogue_disagree_is_reported(self):
        """Shown so a person can see it, and never acted on. Two IBM 5170s in this
        register are dated 1985 and 1988; the AT came out in 1984, and all three of
        those are true of something."""
        differs = {
            field: (mine, theirs)
            for field, mine, theirs in machines.disagreements(
                "ibm-5170", {"manufacturer": "IBM", "year": 1988, "model": "5170"}
            )
        }
        assert differs["year"] == ("1988", "1984")
        assert differs["model"] == ("5170", "PC/AT 5170")
        assert "manufacturer" not in differs  # those two agree

    def test_a_blank_field_is_not_a_disagreement(self):
        """A record that says nothing about its CPU is not contradicting the
        catalogue about it."""
        assert machines.disagreements("ibm-5170", {"cpu": "", "year": None}) == []

    def test_an_unknown_model_has_nothing_to_disagree_about(self):
        assert machines.disagreements("no-such-model", {"year": 1990}) == []


class TestTheBrandedPcsAreInTheCatalogue:
    """The machines the register holds that were filed as free text before, and the
    rule they were let in under: a documented branded model belongs in the
    catalogue, a whitebox clone does not. Both halves of that are worth pinning --
    what was added, and what was deliberately not.
    """

    HELD: ClassVar = [
        "ibm-5170",
        "ps2-8530",
        "ps2-8555-sx",
        "ps2-8580",
        "ps1-2121",
        "amstrad-pc1640",
        "amstrad-pc2286",
        "compaq-portable-486",
        "olivetti-m21",
        "opus-pc-v-turbo",
        "grid-gridcase-2",
        "victor-9000",
    ]

    @pytest.mark.parametrize("key", HELD)
    def test_a_machine_this_collection_holds_can_be_filed(self, key):
        assert machines.model(key) is not None

    def test_ibms_keys_are_its_own_machine_types(self):
        """Keys are forever, so they are built from the maker's own stable
        designation rather than from a marketing name that moved: IBM's four-digit
        machine type is on the plate and was never reused."""
        for key, number in (
            ("ibm-5150", "5150"),
            ("ibm-5160", "5160"),
            ("ibm-5170", "5170"),
            ("ps2-8530", "8530"),
            ("ps2-8555-sx", "8555"),
            ("ps2-8580", "8580"),
        ):
            assert number in machines.model(key)["model"], key

    def test_the_line_is_the_model_and_not_the_era(self):
        """A PC in the catalogue is not a contradiction of what the catalogue is
        for. It is there because it was sold as a model somebody documented, which
        is the only test any of these pass."""
        pcs = [
            m
            for m in machines.models()
            if m["year"] >= 1981 and m["family"] in ("IBM PC", "IBM PS/2", "Compaq", "Amstrad PC")
        ]
        assert len(pcs) > 20
        for m in pcs:
            assert m["manufacturer"] and m["cpu"]


class TestTheListOfWhatIsInIt:
    """catalogue.txt is the catalogue in plain text -- makers and machines, no
    detail -- for the question that gets asked far more often than any question
    about a board issue. It is generated, so the only way it stays true is if
    something notices when it stops being."""

    def test_it_is_in_step_with_the_catalogue(self):
        sys.path.insert(0, str(ROOT / "tools"))
        import catalogue_list

        wanted = catalogue_list.render(machines.FAMILIES)
        have = (ROOT / "catalogue.txt").read_text(encoding="utf-8")
        assert have == wanted, (
            "catalogue.txt is out of step with"
            " api/app/machines.yaml -- run"
            " `python tools/catalogue_list.py`"
        )


class TestTheToolThatAdoptsAMachine:
    """tools/adopt_machines.py, which is the one thing here that writes to a real
    register from the command line. What it picks up and what it leaves alone is
    therefore worth pinning down away from the confirming, which a person does.

    The matching itself is machines.suggest, tested above; this is the sieve in
    front of it.
    """

    @staticmethod
    def tool():
        sys.path.insert(0, str(ROOT / "tools"))
        import adopt_machines

        return adopt_machines

    def rows(self, **over):
        base = {
            "asset_id": "RH-0001",
            "manufacturer": "IBM",
            "model": "5170",
            "year": 1985,
            "disposed": False,
            "machine": None,
        }
        return [base | over]

    def test_a_machine_with_no_model_is_what_it_is_for(self):
        assert len(self.tool().unfiled(self.rows())) == 1

    def test_a_machine_already_filed_is_left_alone(self):
        """Not "proposed again and skipped" -- not shown at all. The catalogue
        model on it is somebody's answer, and re-asking a settled question is how a
        settled question gets un-settled by a tired thumb."""
        filed = self.rows(machine={"model_key": "ibm-5170"})
        assert self.tool().unfiled(filed) == []

    def test_what_has_gone_is_not_worth_cataloguing(self):
        assert self.tool().unfiled(self.rows(disposed=True)) == []

    def test_one_machine_can_be_asked_about_on_its_own(self):
        both = [*self.rows(), dict(self.rows()[0], asset_id="RH-0002")]
        got = self.tool().unfiled(both, only="rh-0002")
        assert [c["asset_id"] for c in got] == ["RH-0002"]

    def test_the_report_carries_the_disagreements_with_it(self):
        """What the person deciding needs in front of them: the proposal, and every
        way the record already contradicts it."""
        [first, *_] = self.tool().report(self.rows()[0])
        assert first["key"] == "ibm-5170"
        assert first["name"] == "IBM PC/AT 5170"
        assert ("year", "1985", "1984") in first["differs"]

    def test_a_machine_the_catalogue_cannot_place_reports_nothing(self):
        assert (
            self.tool().report(self.rows(manufacturer="Mitac", model="MiStation 4052F/M")[0]) == []
        )


class TestTheFileTheCatalogueIsWrittenIn:
    """machines.yaml is meant to be edited by anyone with a text editor, so what a
    mistake in it does matters as much as what a correct one does. Every one of
    these is a wrong edit, and each has to fail at load with the family, the model
    and the field named -- a catalogue that half-loaded would quietly offer a
    Spectrum no ULA, and nobody would know until they went to record one.
    """

    GOOD = """
    lists:
      z80: [Zilog Z80A, NEC D780C-1]
    families:
      - key: sinclair
        name: Sinclair ZX
        manufacturer: Sinclair
        regions: [PAL (UK/Europe)]
        chips:
          - socket: cpu
            label: CPU
            variants: z80
        models:
          - key: zx-spectrum-48k
            model: ZX Spectrum 48K
            year: 1982
            ram: [48K, 16K]
            styles: [rubber keys]
    """

    def written(self, tmp_path, text):
        path = tmp_path / "machines.yaml"
        path.write_text(textwrap.dedent(text), encoding="utf-8")
        return path

    def load(self, tmp_path, text):
        return machines.load(self.written(tmp_path, text))

    def refused(self, tmp_path, text):
        with pytest.raises(machines.CatalogueError) as caught:
            self.load(tmp_path, text)
        return str(caught.value)

    def test_a_good_file_reads(self, tmp_path):
        families = self.load(tmp_path, self.GOOD)
        model = families[0]["models"][0]
        assert model["ram"] == [("48K", 48), ("16K", 16)]
        assert families[0]["chips"][0]["variants"] == ["Zilog Z80A", "NEC D780C-1"]

    def test_a_shared_list_can_be_named_wherever_a_list_is_expected(self, tmp_path):
        families = self.load(tmp_path, self.GOOD.replace("styles: [rubber keys]", "styles: z80"))
        assert families[0]["models"][0]["styles"] == ["Zilog Z80A", "NEC D780C-1"]

    def test_a_misspelled_field_says_what_was_meant(self, tmp_path):
        message = self.refused(tmp_path, self.GOOD.replace("styles:", "styel:"))
        assert "styel" in message and "styles" in message
        assert "zx-spectrum-48k" in message

    def test_a_field_that_is_no_kind_of_typo_lists_the_ones_there_are(self, tmp_path):
        message = self.refused(tmp_path, self.GOOD.replace("styles:", "colour:"))
        assert "colour" in message and "chassis" in message

    def test_a_memory_size_nothing_can_read_is_refused(self, tmp_path):
        """The labels are offered on the memory box and read back with
        entry.to_kb, so one it cannot read would file the machine with no memory
        at all."""
        message = self.refused(tmp_path, self.GOOD.replace("[48K, 16K]", "[a lot]"))
        assert "a lot" in message and "ram" in message

    def test_two_models_cannot_share_a_key(self, tmp_path):
        message = self.refused(
            tmp_path,
            self.GOOD
            + textwrap.dedent("""
              - key: zx-spectrum-48k
                model: ZX Spectrum 48K (again)
                year: 1982
        """),
        )
        assert "zx-spectrum-48k" in message

    def test_a_year_that_is_not_a_year_is_refused(self, tmp_path):
        assert "year" in self.refused(tmp_path, self.GOOD.replace("year: 1982", "year: '82"))

    def test_a_model_with_no_name_is_refused(self, tmp_path):
        message = self.refused(tmp_path, self.GOOD.replace("model: ZX Spectrum 48K", "cpu: Z80"))
        assert "model" in message

    def test_a_shared_list_that_is_not_there_is_refused(self, tmp_path):
        message = self.refused(tmp_path, self.GOOD.replace("variants: z80", "variants: z80a"))
        assert "z80a" in message and "z80" in message

    def test_one_socket_cannot_be_asked_twice(self, tmp_path):
        message = self.refused(
            tmp_path,
            self.GOOD.replace(
                "            variants: z80",
                "            variants: z80\n          - socket: cpu\n"
                "            variants: [MOS 6502]",
            ),
        )
        assert "cpu" in message

    def test_an_answer_too_long_for_its_column_is_refused_at_the_file(self, tmp_path):
        """Rather than on save, in front of whoever was recording the machine."""
        message = self.refused(tmp_path, self.GOOD.replace("[rubber keys]", "[" + "x" * 80 + "]"))
        assert "styles" in message and "64" in message

    def test_a_file_that_is_not_yaml_at_all_says_so(self, tmp_path):
        assert "YAML" in self.refused(tmp_path, "families: [\n")

    def test_a_missing_file_says_where_it_looked(self, tmp_path):
        with pytest.raises(machines.CatalogueError) as caught:
            machines.load(tmp_path / "nothing.yaml")
        assert "nothing.yaml" in str(caught.value)

    def test_the_file_the_register_ships_is_the_one_it_loads(self):
        assert machines.CATALOGUE_FILE.exists()
        assert [f["key"] for f in machines.load()] == [f["key"] for f in machines.FAMILIES]
