"""The catalogue of known machines, and filing a machine against it.

Three kinds of test here. The catalogue's own consistency, because it is data and a
typo in it is a wrong suggestion offered to every machine of that model. The
rows-to-string mapping, because computers.variant is a cache and a cache that
disagrees with what it caches is worse than no cache. And the two doors -- the form
and the API -- because everything in this register has to arrive by either and leave
the same record behind.
"""
import pytest

from app import entry, machinedb, machines
from app.models import Computer, ComputerChip, ComputerVariant


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
        m = machines.model(key)
        assert m["model"] and m["manufacturer"] and m["family"]
        assert isinstance(m["year"], int) and 1975 < m["year"] < 1996

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
        assert len(key) <= ComputerVariant.model_key.type.length
        for issue in m["issues"]:
            assert len(issue) <= ComputerVariant.issue.type.length, issue
        for style in m["styles"]:
            assert len(style) <= ComputerVariant.style.type.length, style
        for region in m["regions"]:
            assert len(region) <= ComputerVariant.region.type.length, region
        for chip in m["chips"]:
            assert len(chip["role"]) <= ComputerChip.role.type.length
            for variant in chip["variants"]:
                assert len(variant) <= ComputerChip.variant.type.length, variant

    def test_the_machines_asked_for_are_all_there(self):
        """The list this was built for, by the names they are known by -- which is
        the maker and the model together, since the catalogue holds them apart."""
        wanted = ["Commodore 64", "Sinclair ZX Spectrum+", "Commodore 16",
                  "Atari 65XE", "Sega Mega Drive", "Amstrad CPC 464",
                  "Amstrad CPC 6128", "Acorn BBC Micro Model B",
                  "Commodore Amiga 500"]
        have = {machines.full_name(k) for k in machines.keys()}
        assert not [w for w in wanted if w not in have]

    def test_no_model_repeats_its_maker(self):
        """The model field fills the machine's model box and the manufacturer fills
        its own, so a model named "Commodore 64" filed a C64 as "Commodore Commodore
        64". Whatever is added here later, the two fields say each thing once."""
        doubled = [(m["manufacturer"], m["model"]) for m in machines.models()
                   if m["manufacturer"]
                   and m["model"].lower().startswith(m["manufacturer"].lower())]
        assert doubled == []

    def test_a_model_inherits_its_family_sockets(self):
        assert "ula" in machines.roles("zx-spectrum-48k")
        assert machines.chip("zx-spectrum-48k", "ula")["variants"] == \
            machines.chip("zx-spectrum-16k", "ula")["variants"]

    def test_a_model_can_replace_one_of_them(self):
        """The +2A has Amstrad's gate array where the family has a Ferranti ULA."""
        assert machines.chip("zx-spectrum-plus2a", "ula")["variants"] == \
            ["Amstrad 40056"]
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
            "zx-spectrum-plus", "Issue 6A", "moulded keys", "PAL (UK/Europe)",
            {"ula": "Ferranti 6C001E-7"}) == (
                "ZX Spectrum+ | Board: Issue 6A | Style: moulded keys | "
                "Region: PAL (UK/Europe) | ULA: Ferranti 6C001E-7")

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
        assert machines.render("c64", chips={"sidx": "Whatsit 9000"}) == \
            "64 | SIDX: Whatsit 9000"
        assert machines.render("c64", chips={"sound-chip": "Whatsit 9000"}) == \
            "64 | Sound chip: Whatsit 9000"

    def test_a_model_key_the_catalogue_lost_is_still_named(self):
        assert machines.render("zx-spectrum-2048k") == "zx-spectrum-2048k"


class TestStorage:
    def test_a_machine_with_nothing_recorded_reads_blank(self, computer, db):
        c = db.get(Computer, computer()["asset_id"])
        assert machinedb.read(db, c) == machinedb.BLANK

    def test_what_goes_in_comes_back(self, computer, db):
        c = db.get(Computer, computer()["asset_id"])
        machinedb.write(db, c, model_key="c64", issue="ASSY 250425",
                        style="rainbow label", region="PAL",
                        chips={"sid": "MOS 6581R4", "vic": "MOS 6569R3"})
        db.commit()
        assert machinedb.read(db, c) == {
            "model_key": "c64", "issue": "ASSY 250425", "style": "rainbow label",
            "region": "PAL", "chips": {"vic": "MOS 6569R3", "sid": "MOS 6581R4"},
            # Nothing was said about how they are held, and nothing is assumed.
            "sockets": {}}

    def test_how_a_chip_is_held_survives_the_chips_being_rewritten(self, computer,
                                                                   db):
        """write() replaces the chip rows wholesale, so a later call that names only
        the variants must not lose what was said about their sockets."""
        c = db.get(Computer, computer()["asset_id"])
        machinedb.write(db, c, model_key="c64", chips={"sid": "MOS 6581"},
                        sockets={"sid": True})
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
        machinedb.write(db, c, model_key="c64", issue="ASSY 250407",
                        chips={"sid": "MOS 6581"})
        machinedb.write(db, c, style="silver label")
        db.commit()
        v = machinedb.read(db, c)
        assert v["issue"] == "ASSY 250407" and v["chips"] == {"sid": "MOS 6581"}
        assert v["style"] == "silver label"

    def test_a_blank_chip_clears_that_socket_and_leaves_the_others(self, computer, db):
        c = db.get(Computer, computer()["asset_id"])
        machinedb.write(db, c, model_key="c64",
                        chips={"sid": "MOS 6581", "cpu": "MOS 6510"})
        machinedb.write(db, c, chips={"sid": "", "cpu": "MOS 6510"})
        db.commit()
        assert machinedb.read(db, c)["chips"] == {"cpu": "MOS 6510"}

    def test_filing_a_machine_out_of_the_catalogue_forgets_all_of_it(self, computer,
                                                                    db):
        c = db.get(Computer, computer()["asset_id"])
        machinedb.write(db, c, model_key="c64", issue="ASSY 250425",
                        chips={"sid": "MOS 6581"})
        machinedb.write(db, c, model_key="")
        db.commit()
        assert machinedb.read(db, c) == machinedb.BLANK
        assert c.variant == ""
        assert db.query(ComputerChip).count() == 0
        assert db.query(ComputerVariant).count() == 0

    def test_changing_model_keeps_the_chips_the_new_one_also_has(self, computer, db):
        c = db.get(Computer, computer()["asset_id"])
        machinedb.write(db, c, model_key="c64",
                        chips={"sid": "MOS 6581", "cpu": "MOS 6510"})
        machinedb.write(db, c, model_key="c64c")
        db.commit()
        assert machinedb.read(db, c)["chips"] == {"cpu": "MOS 6510",
                                                 "sid": "MOS 6581"}

    def test_changing_model_drops_the_chips_it_has_no_socket_for(self, computer, db):
        """A machine refiled as a Spectrum has no SID, and a record saying it has
        one describes a machine nobody owns."""
        c = db.get(Computer, computer()["asset_id"])
        machinedb.write(db, c, model_key="c64", chips={"sid": "MOS 6581"})
        machinedb.write(db, c, model_key="zx-spectrum-48k")
        db.commit()
        assert machinedb.read(db, c)["chips"] == {}
        assert c.variant == "ZX Spectrum 48K"

    def test_reading_many_takes_two_queries_and_gets_the_same_answers(self, computer,
                                                                     db):
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

    def test_deleting_a_machine_takes_its_catalogue_rows_with_it(self, client,
                                                                computer, db):
        c = db.get(Computer, computer()["asset_id"])
        machinedb.write(db, c, model_key="c64", chips={"sid": "MOS 6581"})
        db.commit()
        assert client.delete(f"/api/computers/{c.asset_id}").status_code == 200
        assert db.query(ComputerChip).count() == 0
        assert db.query(ComputerVariant).count() == 0


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
        assert "MOS 6581" in next(c["variants"] for c in c64["chips"]
                                  if c["role"] == "sid")

    def test_a_machine_can_be_created_as_one(self, client):
        r = client.post("/api/computers", json={
            "manufacturer": "Sinclair", "model": "ZX Spectrum+",
            "machine": {"model_key": "zx-spectrum-plus", "issue": "Issue 6A",
                        "style": "moulded keys",
                        "chips": {"ula": "Ferranti 6C001E-7"}}})
        assert r.status_code == 200, r.text
        body = r.json()
        assert body["machine"]["model"] == "ZX Spectrum+"
        assert body["machine"]["family"] == "Sinclair ZX"
        assert body["machine"]["chips"] == {"ula": "Ferranti 6C001E-7"}
        assert body["variant"] == ("ZX Spectrum+ | Board: Issue 6A | "
                                   "Style: moulded keys | ULA: Ferranti 6C001E-7")

    def test_sockets_ride_over_the_wire_beside_the_chips(self, client):
        r = client.post("/api/computers", json={
            "manufacturer": "Commodore", "model": "64",
            "machine": {"model_key": "c64", "chips": {"sid": "MOS 6581"},
                        "sockets": {"sid": True}}})
        assert r.status_code == 200, r.text
        assert r.json()["machine"]["sockets"] == {"sid": True}

    def test_a_socket_for_a_chip_the_model_has_not_got_is_refused(self, client):
        r = client.post("/api/computers", json={
            "manufacturer": "Commodore", "model": "64",
            "machine": {"model_key": "c64", "sockets": {"ula": True}}})
        assert r.status_code == 422 and "ula" in r.text

    def test_a_machine_that_is_not_one_says_so(self, computer):
        assert computer()["machine"] is None

    def test_it_comes_back_on_get_and_on_the_list(self, client, computer):
        c = computer(machine={"model_key": "c16"})
        assert client.get(f"/api/computers/{c['asset_id']}").json()["machine"][
            "model"] == "16"
        listed = {row["asset_id"]: row for row in client.get("/api/computers").json()}
        assert listed[c["asset_id"]]["machine"]["model_key"] == "c16"

    def test_a_patch_changes_only_what_it_names(self, client, computer):
        c = computer(machine={"model_key": "c64", "issue": "ASSY 250407",
                              "chips": {"sid": "MOS 6581"}})
        r = client.patch(f"/api/computers/{c['asset_id']}",
                         json={"machine": {"style": "silver label"}})
        assert r.status_code == 200, r.text
        m = r.json()["machine"]
        assert m["issue"] == "ASSY 250407" and m["chips"] == {"sid": "MOS 6581"}
        assert m["style"] == "silver label"

    def test_a_patch_that_says_nothing_about_it_leaves_it_alone(self, client,
                                                               computer):
        c = computer(machine={"model_key": "c64", "issue": "ASSY 250425"})
        r = client.patch(f"/api/computers/{c['asset_id']}", json={"notes": "cleaned"})
        assert r.json()["machine"]["issue"] == "ASSY 250425"

    def test_null_forgets_the_catalogue(self, client, computer):
        c = computer(machine={"model_key": "c64", "chips": {"sid": "MOS 6581"}})
        r = client.patch(f"/api/computers/{c['asset_id']}", json={"machine": None})
        assert r.status_code == 200, r.text
        assert r.json()["machine"] is None and r.json()["variant"] == ""

    def test_a_model_the_catalogue_does_not_have_is_refused(self, client):
        r = client.post("/api/computers",
                        json={"model": "X", "machine": {"model_key": "zx-spectrum"}})
        assert r.status_code == 422
        assert "zx-spectrum" in r.text

    def test_a_socket_the_model_does_not_have_is_refused(self, client):
        r = client.post("/api/computers", json={
            "model": "X", "machine": {"model_key": "c64",
                                      "chips": {"ula": "Ferranti 6C001E-7"}}})
        assert r.status_code == 422
        assert "ula" in r.text

    def test_a_chip_is_checked_against_the_model_already_on_file(self, client,
                                                                computer):
        c = computer(machine={"model_key": "c64"})
        r = client.patch(f"/api/computers/{c['asset_id']}",
                         json={"machine": {"chips": {"sid": "MOS 8580R5"}}})
        assert r.status_code == 200, r.text
        bad = client.patch(f"/api/computers/{c['asset_id']}",
                           json={"machine": {"chips": {"ted": "MOS 7360"}}})
        assert bad.status_code == 422

    def test_the_rendered_line_is_read_only(self, client, computer):
        """It is written from the rows, so sending one has no effect -- the rule
        installed_ram and drives already follow."""
        c = computer(machine={"model_key": "c64"})
        r = client.patch(f"/api/computers/{c['asset_id']}",
                         json={"variant": "an Amiga, honestly"})
        assert r.json()["variant"] == "64"

    def test_a_change_of_machine_is_in_the_history(self, client, computer):
        c = computer(machine={"model_key": "c64"})
        client.patch(f"/api/computers/{c['asset_id']}",
                     json={"machine": {"chips": {"sid": "MOS 6581R4"}}})
        page = client.get(f"/computers/{c['asset_id']}").text
        assert "MOS 6581R4" in page


class TestForm:
    def _new(self, client, **fields):
        r = client.post("/computers/new",
                        data={"manufacturer": "Sinclair", "model": "Spectrum",
                              **fields}, follow_redirects=False)
        assert r.status_code == 303, r.text
        return r.headers["location"].split("/computers/")[1].split("?")[0]

    def test_the_form_offers_every_model(self, client):
        page = client.get("/computers/new").text
        assert 'value="zx-spectrum-plus"' in page
        assert 'value="megadrive"' in page
        # The catalogue itself is shipped for the script to build the rest from.
        assert "Ferranti 6C001E-7" in page

    def test_a_machine_can_be_filed_from_the_form(self, client, db):
        aid = self._new(client, mach_model="zx-spectrum-48k", mach_fields="1",
                        mach_issue="Issue 3B", mach_style="rubber keys",
                        mach_region="PAL (UK/Europe)",
                        **{"chip:ula": "Ferranti 6C001E-7",
                           "chip:cpu": "NEC D780C-1"})
        c = db.get(Computer, aid)
        v = machinedb.read(db, c)
        assert v["model_key"] == "zx-spectrum-48k" and v["issue"] == "Issue 3B"
        assert v["chips"] == {"cpu": "NEC D780C-1", "ula": "Ferranti 6C001E-7"}
        assert "ULA: Ferranti 6C001E-7" in c.variant

    def test_the_edit_form_comes_back_with_what_was_picked(self, client, db):
        aid = self._new(client, mach_model="c64", mach_fields="1",
                        mach_issue="ASSY 250425", **{"chip:sid": "MOS 6581R4"})
        page = client.get(f"/computers/{aid}/edit").text
        assert 'value="c64" selected' in page
        # The saved answers go to the script, which builds the boxes from them.
        assert "ASSY 250425" in page and "MOS 6581R4" in page

    def test_a_socket_the_model_does_not_have_is_ignored(self, client, db):
        """Fields left over from another model in the same tab cannot put a ULA in a
        Commodore 64."""
        aid = self._new(client, mach_model="c64", mach_fields="1",
                        **{"chip:ula": "Ferranti 6C001E-7",
                           "chip:sid": "MOS 6581"})
        c = db.get(Computer, aid)
        assert machinedb.read(db, c)["chips"] == {"sid": "MOS 6581"}

    def test_the_tickbox_says_which_chips_are_in_a_socket(self, client, db):
        """A socketed chip can be swapped to test a fault; a soldered one is forty
        pins and a desoldering station. The box beside each chip records which."""
        aid = self._new(client, mach_model="c64", mach_fields="1",
                        **{"chip:sid": "MOS 6581", "chip:sid:socketed": "on",
                           "chip:vic": "MOS 6569R3"})
        v = machinedb.read(db, db.get(Computer, aid))
        assert v["sockets"] == {"sid": True, "vic": False}

    def test_a_socket_nobody_named_a_chip_for_is_not_answered_either(self, client,
                                                                     db):
        """The box is off for every socket on the form, including the ones left at
        "not recorded". Saving must not turn that into a claim that a chip nobody
        has looked at is soldered down -- there is no chip there to hold."""
        aid = self._new(client, mach_model="c64", mach_fields="1",
                        **{"chip:sid": "MOS 6581", "chip:sid:socketed": "on"})
        v = machinedb.read(db, db.get(Computer, aid))
        assert v["chips"] == {"sid": "MOS 6581"} and v["sockets"] == {"sid": True}

    def test_unticking_it_says_soldered_rather_than_forgetting(self, client, db):
        aid = self._new(client, mach_model="c64", mach_fields="1",
                        **{"chip:sid": "MOS 6581", "chip:sid:socketed": "on"})
        r = client.post(f"/computers/{aid}/edit",
                        data={"manufacturer": "Commodore", "model": "64",
                              "mach_model": "c64", "mach_fields": "1",
                              "chip:sid": "MOS 6581"}, follow_redirects=False)
        assert r.status_code == 303
        assert machinedb.read(db, db.get(Computer, aid))["sockets"] == {"sid": False}

    def test_a_save_that_could_not_draw_the_fields_does_not_erase_them(self, client,
                                                                      db):
        """Without the marker the script sets, only the model choice is read: a
        browser that ran no JavaScript submits no variation fields, and a blank
        field it never drew must not read as an answer of "nothing"."""
        aid = self._new(client, mach_model="c64", mach_fields="1",
                        mach_issue="ASSY 250425", **{"chip:sid": "MOS 6581"})
        r = client.post(f"/computers/{aid}/edit",
                        data={"manufacturer": "Commodore", "model": "64",
                              "mach_model": "c64"}, follow_redirects=False)
        assert r.status_code == 303
        c = db.get(Computer, aid)
        v = machinedb.read(db, c)
        assert v["issue"] == "ASSY 250425" and v["chips"] == {"sid": "MOS 6581"}

    def test_choosing_not_a_catalogue_model_files_it_out(self, client, db):
        aid = self._new(client, mach_model="c64", mach_fields="1",
                        mach_issue="ASSY 250425")
        r = client.post(f"/computers/{aid}/edit",
                        data={"manufacturer": "Commodore", "model": "64",
                              "mach_model": ""}, follow_redirects=False)
        assert r.status_code == 303
        c = db.get(Computer, aid)
        assert machinedb.read(db, c) == machinedb.BLANK and c.variant == ""

    def test_a_form_that_never_asked_leaves_a_machine_alone(self, client, computer,
                                                           db):
        """Another form posting to the same handler -- one with no machine picker on
        it at all -- must not clear what this one recorded."""
        c = db.get(Computer, computer()["asset_id"])
        machinedb.write(db, c, model_key="c64", issue="ASSY 250425")
        db.commit()
        r = client.post(f"/computers/{c.asset_id}/edit",
                        data={"manufacturer": "Commodore", "model": "64"},
                        follow_redirects=False)
        assert r.status_code == 303
        db.expire_all()
        assert machinedb.read(db, c)["issue"] == "ASSY 250425"

    def test_the_machine_page_says_what_it_is(self, client, db):
        aid = self._new(client, mach_model="zx-spectrum-plus", mach_fields="1",
                        mach_issue="Issue 6A", mach_style="moulded keys",
                        **{"chip:ula": "Ferranti 6C001E-7"})
        page = client.get(f"/computers/{aid}").text
        assert "ZX Spectrum+" in page and "Issue 6A" in page
        assert "ULA" in page and "Ferranti 6C001E-7" in page

    def test_a_machine_outside_the_catalogue_has_no_such_section(self, client,
                                                                computer):
        page = client.get(f"/computers/{computer()['asset_id']}").text
        assert "Catalogue model" not in page

    def test_the_label_carries_the_board_and_the_chips(self, client, db):
        """On a sealed machine nothing inside has a tag of its own, so the label is
        the only place the board issue and the ULA can be printed.

        The chips share one line, named by their sockets: a machine has a CPU field
        and a CPU socket saying different true things, and two label lines both
        headed CPU would read as a contradiction."""
        aid = self._new(client, mach_model="zx-spectrum-48k", mach_fields="1",
                        mach_issue="Issue 3B", cpu="Zilog Z80A-3.5",
                        **{"chip:ula": "Ferranti 6C001E-7",
                           "chip:cpu": "NEC D780C-1"})
        from app import labels
        from app.main import to_dict
        lines = labels.computer_lines(to_dict(db.get(Computer, aid)), [])
        assert "Machine: ZX Spectrum 48K" in lines
        assert "Board: Issue 3B" in lines
        assert "Chips: CPU NEC D780C-1, ULA Ferranti 6C001E-7" in lines
        assert len([x for x in lines if x.startswith("CPU:")]) == 1

    def test_a_label_for_a_machine_outside_the_catalogue_is_unchanged(self, computer,
                                                                     db):
        from app import labels
        from app.main import to_dict
        c = db.get(Computer, computer(cpu="Intel 486DX2-66")["asset_id"])
        lines = labels.computer_lines(to_dict(c), [])
        assert not [x for x in lines if x.startswith(("Machine:", "Chips:"))]

    def test_a_duplicate_is_the_same_model_and_not_the_same_board(self, client, db):
        """Another one of these is another one of these; which board issue and which
        ULA are in it are found by opening it."""
        aid = self._new(client, mach_model="c64", mach_fields="1",
                        mach_issue="ASSY 250425", **{"chip:sid": "MOS 6581"})
        r = client.post(f"/computers/{aid}/duplicate", follow_redirects=False)
        copy = r.headers["location"].split("/computers/")[1]
        v = machinedb.read(db, db.get(Computer, copy))
        assert v["model_key"] == "c64"
        assert v["issue"] == "" and v["chips"] == {}

    def test_a_machine_is_searchable_by_the_chip_in_it(self, client, db):
        """What the rendered cache is for: the register is searched over every text
        column, so a part number recorded in a socket is a way back to the
        machine."""
        aid = self._new(client, mach_model="c64", mach_fields="1",
                        **{"chip:sid": "MOS 8580R5"})
        hits = client.get("/?q=8580R5").text
        assert aid in hits


class TestWhereTheBoardAndPartsAreAskedFor:
    """A PC is described by what is fitted in it, so its page carries the motherboard
    and the parts list. A catalogue machine is not that sort of object -- a C64 has
    no board to link and nothing on a shelf goes in one -- so while it has neither,
    the page it is read on says nothing about them and the edit form carries them
    instead, which is where a drive that does turn up gets added from."""

    def _c64(self, client):
        r = client.post("/computers/new",
                        data={"manufacturer": "Commodore", "model": "64",
                              "mach_model": "c64", "mach_fields": "1"},
                        follow_redirects=False)
        assert r.status_code == 303, r.text
        return r.headers["location"].split("/computers/")[1].split("?")[0]

    def test_a_bare_catalogue_machine_is_not_asked_about_either(self, client):
        page = client.get(f"/computers/{self._c64(client)}").text
        assert "Create motherboard" not in page
        assert ">Motherboard<" not in page and "Parts <span" not in page

    def test_its_edit_form_carries_them_instead(self, client):
        page = client.get(f"/computers/{self._c64(client)}/edit").text
        assert "Create motherboard" in page
        assert "type=storage&computer_id=" in page

    def test_fitting_something_brings_them_back_to_the_page(self, client, part):
        aid = self._c64(client)
        part(type="storage", model="1541", computer_id=aid)
        page = client.get(f"/computers/{aid}").text
        assert "Create motherboard" in page and "1541" in page
        # ...and the form stops offering what the page now has.
        assert "Create motherboard" not in client.get(f"/computers/{aid}/edit").text

    def test_a_pc_keeps_them_on_its_page_and_off_its_form(self, client, computer):
        aid = computer()["asset_id"]
        assert "Create motherboard" in client.get(f"/computers/{aid}").text
        assert "Create motherboard" not in client.get(f"/computers/{aid}/edit").text


class TestACatalogueThatGrows:
    """The catalogue names what is commonly seen, and the register keeps meeting
    what is not. A variation typed into the custom box once is offered as a button
    ever after, so discovering a ULA nobody had written up is a thing you do once.
    """

    def cat(self, recorded):
        return machines.with_recorded(machines.form_catalogue(), recorded)

    def ula(self, catalogue, key="zx-spectrum-48k"):
        return next(c["variants"] for c in catalogue[key]["chips"]
                    if c["role"] == "ula")

    def test_a_chip_the_catalogue_never_heard_of_is_offered(self):
        out = self.ula(self.cat({"zx-spectrum-48k": {"chips": {"ula": ["Ferranti 6C001W-8"]}}}))
        assert "Ferranti 6C001W-8" in out

    def test_the_curated_order_is_kept_and_discoveries_follow(self):
        """What was written down deliberately is what a person reads down first."""
        known = self.ula(self.cat({}))
        out = self.ula(self.cat({"zx-spectrum-48k": {"chips": {"ula": ["AAA first"]}}}))
        assert out[:len(known)] == known
        assert out[-1] == "AAA first"

    def test_one_already_offered_is_not_offered_twice(self):
        out = self.ula(self.cat(
            {"zx-spectrum-48k": {"chips": {"ula": ["Ferranti 6C001E-7"]}}}))
        assert out.count("Ferranti 6C001E-7") == 1

    def test_a_difference_of_case_or_spacing_is_not_a_different_chip(self):
        out = self.ula(self.cat(
            {"zx-spectrum-48k": {"chips": {"ula": ["ferranti  6C001E-7"]}}}))
        assert len([v for v in out if v.lower().replace("  ", " ")
                    == "ferranti 6c001e-7"]) == 1

    def test_what_one_model_teaches_is_not_told_about_another(self):
        """A ULA found in a Spectrum says nothing about a Commodore 64."""
        cat = self.cat({"zx-spectrum-48k": {"chips": {"ula": ["Ferranti 9Z9"]}}})
        for chip in cat["c64"]["chips"]:
            assert "Ferranti 9Z9" not in chip["variants"]

    def test_a_socket_the_catalogue_dropped_is_not_brought_back(self):
        cat = self.cat({"c64": {"chips": {"ula": ["Ferranti 6C001E-7"]}}})
        assert "ula" not in [c["role"] for c in cat["c64"]["chips"]]

    def test_the_other_variations_grow_the_same_way(self):
        cat = self.cat({"c64": {"issues": ["ASSY 250466 rev B"],
                                "styles": ["Aldi C64 (short board)"],
                                "regions": ["PAL"]}})
        assert "ASSY 250466 rev B" in cat["c64"]["issues"]
        # ...and the ones it already knew are still there once each.
        assert cat["c64"]["styles"].count("Aldi C64 (short board)") == 1
        assert cat["c64"]["regions"].count("PAL") == 1

    def test_what_machines_say_is_read_back_by_model(self, computer, db):
        c = db.get(Computer, computer()["asset_id"])
        machinedb.write(db, c, model_key="zx-spectrum-48k", issue="Issue 3B",
                        chips={"ula": "Ferranti 6C001W-8"})
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
        r = client.post("/computers/new",
                        data={"manufacturer": "Sinclair", "model": "Spectrum",
                              "mach_model": "zx-spectrum-48k", "mach_fields": "1",
                              "chip:ula": "custom",
                              "chip:ula_custom": "Ferranti 6C001W-8"},
                        follow_redirects=False)
        assert r.status_code == 303, r.text
        # A blank form: the only place this can appear is the catalogue the script
        # builds its buttons from.
        assert "Ferranti 6C001W-8" in client.get("/computers/new").text

    def test_the_custom_box_is_what_gets_stored(self, client, db):
        r = client.post("/computers/new",
                        data={"manufacturer": "Commodore", "model": "64",
                              "mach_model": "c64", "mach_fields": "1",
                              "mach_issue": "custom",
                              "mach_issue_custom": "  ASSY 250425  rev C ",
                              "chip:sid": "MOS 6582"}, follow_redirects=False)
        aid = r.headers["location"].split("/computers/")[1].split("?")[0]
        row = db.get(ComputerVariant, aid)
        # Squeezed, like every other typed answer the form takes.
        assert row.issue == "ASSY 250425 rev C"
        assert db.query(ComputerChip).filter(
            ComputerChip.computer_id == aid).one().variant == "MOS 6582"

    def test_custom_with_nothing_typed_records_nothing(self, client, db):
        r = client.post("/computers/new",
                        data={"manufacturer": "Commodore", "model": "64",
                              "mach_model": "c64", "mach_fields": "1",
                              "chip:sid": "custom", "chip:sid_custom": "   "},
                        follow_redirects=False)
        aid = r.headers["location"].split("/computers/")[1].split("?")[0]
        assert db.query(ComputerChip).filter(
            ComputerChip.computer_id == aid).count() == 0


class TestResync:
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
