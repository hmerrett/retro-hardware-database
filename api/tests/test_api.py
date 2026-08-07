"""End-to-end behaviour through the REST API and the GUI forms.

Weighted towards the things that have actually broken: typed columns rejecting or
silently eating form input, a select with no option for the value it holds, links
left pointing at deleted rows, and derived strings being written to directly.
"""
import re
from datetime import date, datetime
from pathlib import Path

import pytest


class TestTypedColumns:
    def test_year_and_date_come_back_typed(self, computer):
        c = computer(year=1991, acquired_date="2026-05-16")
        assert c["year"] == 1991 and c["acquired_date"] == "2026-05-16"

    def test_a_year_that_is_not_a_number_is_refused(self, client):
        r = client.post("/api/computers", json={"model": "X", "year": "notayear"})
        assert r.status_code == 422

    def test_a_date_that_is_not_a_date_is_refused(self, client):
        r = client.post("/api/computers", json={"model": "X", "acquired_date": "soon"})
        assert r.status_code == 422

    def test_not_recorded_is_null_not_zero(self, computer):
        c = computer()
        assert c["year"] is None and c["acquired_date"] is None

    def test_creating_from_the_form_with_both_blank(self, client):
        """These were String columns; when they became SMALLINT and DATE the create
        path still passed "" straight through, and the form 500'd."""
        r = client.post("/computers/new",
                        data={"manufacturer": "Acme", "model": "Blank",
                              "year": "", "acquired_date": ""},
                        follow_redirects=False)
        assert r.status_code == 303
        aid = r.headers["location"].split("/")[2].split("?")[0]
        c = client.get(f"/api/computers/{aid}").json()
        assert c["year"] is None and c["acquired_date"] is None

    def test_the_form_accepts_a_day_first_date(self, client, computer):
        aid = computer()["asset_id"]
        client.post(f"/computers/{aid}/edit", data={"acquired_date": "17/06/2026"},
                    follow_redirects=False)
        assert client.get(f"/api/computers/{aid}").json()["acquired_date"] == "2026-06-17"

    def test_clearing_a_typed_field_from_the_form(self, client, computer):
        aid = computer(year=1991)["asset_id"]
        client.post(f"/computers/{aid}/edit", data={"year": ""}, follow_redirects=False)
        assert client.get(f"/api/computers/{aid}").json()["year"] is None


class TestCondition:
    def test_a_value_outside_the_vocabulary_survives_an_edit(self, client, computer):
        """The select had no option for such a value, so saving the form posted an
        empty string and the value was lost without a word."""
        aid = computer(condition="RAM fault")["asset_id"]
        page = client.get(f"/computers/{aid}/edit").text
        assert '<option value="RAM fault" selected>' in page

    def test_the_current_value_is_offered_once(self, client, computer):
        aid = computer(condition="Working")["asset_id"]
        page = client.get(f"/computers/{aid}/edit").text
        assert page.count('value="Working"') == 1

    @pytest.mark.parametrize("path", ["/computers/new", "/parts/new"])
    def test_a_new_thing_claims_nothing_about_its_condition(self, client, path):
        """It used to open on "Working", so anything added and not thought about
        was recorded as working when nobody had checked."""
        page = client.get(path).text
        assert '<option value="Working" selected>' not in page
        assert '<option value="">not recorded</option>' in page

    def test_a_condition_can_be_taken_back_off(self, client, computer):
        aid = computer(condition="Working")["asset_id"]
        client.post(f"/computers/{aid}/edit", data={"condition": ""},
                    follow_redirects=False)
        assert client.get(f"/api/computers/{aid}").json()["condition"] == ""


class TestDisposal:
    def test_disposing_records_a_flag_a_date_and_a_note(self, client, part):
        aid = part()["asset_id"]
        client.post(f"/parts/{aid}/dispose",
                    data={"note": "sold at the rally", "date": "2026-07-20"},
                    follow_redirects=False)
        p = client.get(f"/api/parts/{aid}").json()
        assert p["disposed"] is True
        assert p["disposed_at"] == "2026-07-20"
        assert p["disposed_note"] == "sold at the rally"

    def test_disposing_with_nothing_typed_still_records_the_day(self, client, part):
        aid = part()["asset_id"]
        client.post(f"/parts/{aid}/dispose", data={"note": "", "date": ""},
                    follow_redirects=False)
        p = client.get(f"/api/parts/{aid}").json()
        assert p["disposed"] is True
        assert p["disposed_at"] == date.today().isoformat()

    def test_restoring_clears_all_three(self, client, part):
        aid = part()["asset_id"]
        client.post(f"/parts/{aid}/dispose", data={"note": "binned"},
                    follow_redirects=False)
        client.post(f"/parts/{aid}/restore", follow_redirects=False)
        p = client.get(f"/api/parts/{aid}").json()
        assert p["disposed"] is False
        assert p["disposed_at"] is None and p["disposed_note"] == ""

    def test_a_disposal_without_a_date_still_reads_as_disposed(self, client, part):
        """Every disposal in the collection predates the date field, which is why
        the flag is its own column rather than being inferred from the date."""
        aid = part()["asset_id"]
        client.patch(f"/api/parts/{aid}",
                     json={"disposed": True, "disposed_note": "recycled"})
        p = client.get(f"/api/parts/{aid}").json()
        assert p["disposed"] is True and p["disposed_at"] is None


class TestDisposingAMachineTakesItsPartsWithIt:
    """A machine leaves the collection as an assembled thing. If its contents kept
    reading as held, the register would claim we still have parts that are in the
    same skip as the machine they were bolted into."""

    def test_the_parts_installed_in_it_are_disposed_too(self, client, computer, part):
        cid = computer()["asset_id"]
        pid = part(computer_id=cid)["asset_id"]
        client.post(f"/computers/{cid}/dispose",
                    data={"note": "sold as a lot", "date": "2026-07-20"},
                    follow_redirects=False)
        p = client.get(f"/api/parts/{pid}").json()
        assert p["disposed"] is True
        assert p["disposed_at"] == "2026-07-20"
        assert p["disposed_note"] == "sold as a lot"

    def test_a_part_mounted_on_a_card_in_it_goes_too(self, client, computer, part):
        """A disk on a controller carries the controller's id, not the machine's,
        so the walk has to follow the whole tree rather than one column."""
        cid = computer()["asset_id"]
        card = part(type="io", computer_id=cid)["asset_id"]
        disk = part(type="storage", parent_id=card)["asset_id"]
        client.post(f"/computers/{cid}/dispose", data={"note": "binned"},
                    follow_redirects=False)
        assert client.get(f"/api/parts/{disk}").json()["disposed"] is True

    def test_a_part_outside_the_machine_is_left_alone(self, client, computer, part):
        cid = computer()["asset_id"]
        spare = part()["asset_id"]
        client.post(f"/computers/{cid}/dispose", data={"note": "binned"},
                    follow_redirects=False)
        assert client.get(f"/api/parts/{spare}").json()["disposed"] is False

    def test_a_part_already_disposed_keeps_its_own_record(self, client, computer,
                                                          part):
        cid = computer()["asset_id"]
        pid = part(computer_id=cid)["asset_id"]
        client.post(f"/parts/{pid}/dispose",
                    data={"note": "died on the bench", "date": "2026-01-05"},
                    follow_redirects=False)
        client.post(f"/computers/{cid}/dispose",
                    data={"note": "sold as a lot", "date": "2026-07-20"},
                    follow_redirects=False)
        p = client.get(f"/api/parts/{pid}").json()
        assert p["disposed_at"] == "2026-01-05"
        assert p["disposed_note"] == "died on the bench"

    def test_restoring_the_machine_brings_those_parts_back(self, client, computer,
                                                           part):
        cid = computer()["asset_id"]
        pid = part(computer_id=cid)["asset_id"]
        client.post(f"/computers/{cid}/dispose", data={"note": "binned"},
                    follow_redirects=False)
        client.post(f"/computers/{cid}/restore", follow_redirects=False)
        p = client.get(f"/api/parts/{pid}").json()
        assert p["disposed"] is False
        assert p["disposed_at"] is None and p["disposed_note"] == ""

    def test_restoring_leaves_a_part_that_went_separately(self, client, computer,
                                                          part):
        """Only what went out with the machine comes back with it."""
        cid = computer()["asset_id"]
        pid = part(computer_id=cid)["asset_id"]
        client.post(f"/parts/{pid}/dispose",
                    data={"note": "died on the bench", "date": "2026-01-05"},
                    follow_redirects=False)
        client.post(f"/computers/{cid}/dispose", data={"note": "binned"},
                    follow_redirects=False)
        client.post(f"/computers/{cid}/restore", follow_redirects=False)
        assert client.get(f"/api/parts/{pid}").json()["disposed"] is True

    def test_the_json_api_cascades_the_same_way(self, client, computer, part):
        """The rule belongs to the data, not to the GUI: the MCP server and the
        command-line tools go through PATCH and must not leave a machine disposed
        with its parts still reading as held."""
        cid = computer()["asset_id"]
        pid = part(computer_id=cid)["asset_id"]
        client.patch(f"/api/computers/{cid}",
                     json={"disposed": True, "disposed_at": "2026-07-20",
                           "disposed_note": "sold as a lot"})
        p = client.get(f"/api/parts/{pid}").json()
        assert p["disposed"] is True and p["disposed_at"] == "2026-07-20"
        client.patch(f"/api/computers/{cid}", json={"disposed": False})
        assert client.get(f"/api/parts/{pid}").json()["disposed"] is False

    def test_editing_a_disposed_machine_does_not_re_dispose(self, client, computer,
                                                            part):
        """The cascade fires on the change, not on the state, so a later edit
        cannot overwrite a part that was restored on its own."""
        cid = computer()["asset_id"]
        pid = part(computer_id=cid)["asset_id"]
        client.patch(f"/api/computers/{cid}", json={"disposed": True})
        client.post(f"/parts/{pid}/restore", follow_redirects=False)
        client.patch(f"/api/computers/{cid}", json={"notes": "in the garage"})
        assert client.get(f"/api/parts/{pid}").json()["disposed"] is False

    def test_both_histories_say_what_happened(self, client, computer, part):
        cid = computer()["asset_id"]
        pid = part(computer_id=cid)["asset_id"]
        client.post(f"/computers/{cid}/dispose", data={"note": "binned"},
                    follow_redirects=False)
        assert "1 part in it went with it" in client.get(f"/computers/{cid}").text
        assert f"marked disposed with {cid}" in client.get(f"/parts/{pid}").text


class TestLinks:
    def test_a_new_part_stands_alone(self, part):
        p = part()
        assert p["computer_id"] is None and p["parent_id"] is None

    def test_blank_means_standalone_on_the_wire(self, client, part, computer):
        aid = part(computer_id=computer()["asset_id"])["asset_id"]
        p = client.patch(f"/api/parts/{aid}", json={"computer_id": ""}).json()
        assert p["computer_id"] is None

    def test_the_standalone_filter_finds_unlinked_parts(self, client, part, computer):
        loose = part()["asset_id"]
        fitted = part(computer_id=computer()["asset_id"])["asset_id"]
        found = [p["asset_id"] for p in
                 client.get("/api/parts", params={"computer_id": ""}).json()]
        assert loose in found and fitted not in found

    def test_a_link_to_something_that_does_not_exist_is_refused(self, client, part):
        aid = part()["asset_id"]
        assert client.patch(f"/api/parts/{aid}",
                            json={"computer_id": "RH-NOPE"}).status_code == 404
        assert client.patch(f"/api/parts/{aid}",
                            json={"parent_id": "RH-NOPE"}).status_code == 404

    def test_deleting_a_computer_unlinks_its_parts(self, client, part, computer):
        cid = computer()["asset_id"]
        aid = part(computer_id=cid)["asset_id"]
        client.delete(f"/api/computers/{cid}")
        assert client.get(f"/api/parts/{aid}").json()["computer_id"] is None

    def test_deleting_a_host_part_unlinks_what_was_mounted_on_it(self, client, part):
        host = part(type="io")["asset_id"]
        child = part(type="storage", parent_id=host)["asset_id"]
        client.delete(f"/api/parts/{host}")
        assert client.get(f"/api/parts/{child}").json()["parent_id"] is None

    def test_deleting_a_computer_does_not_delete_its_parts(self, client, part, computer):
        cid = computer()["asset_id"]
        aid = part(computer_id=cid)["asset_id"]
        client.delete(f"/api/computers/{cid}")
        assert client.get(f"/api/parts/{aid}").status_code == 200


class TestInstalledRam:
    def test_the_module_grid_becomes_a_total_and_a_string(self, client, computer):
        aid = computer()["asset_id"]
        client.post(f"/computers/{aid}/edit",
                    data={"rammod:30p1m": "8", "installed_ram": ""},
                    follow_redirects=False)
        c = client.get(f"/api/computers/{aid}").json()
        assert c["installed_ram"] == "8× 1MB 30-pin (8 MB)"
        assert c["installed_ram_kb"] == 8192

    def test_a_plain_amount_over_the_wire_becomes_a_number(self, client, computer):
        aid = computer()["asset_id"]
        c = client.patch(f"/api/computers/{aid}",
                         json={"installed_ram": "640KB"}).json()
        assert c["installed_ram"] == "640 KB" and c["installed_ram_kb"] == 640

    def test_setting_a_total_does_not_wipe_a_breakdown(self, client, computer):
        aid = computer()["asset_id"]
        client.post(f"/computers/{aid}/edit",
                    data={"rammod:30p1m": "8", "installed_ram": ""},
                    follow_redirects=False)
        c = client.patch(f"/api/computers/{aid}",
                         json={"installed_ram": "32MB"}).json()
        assert c["installed_ram"] == "8× 1MB 30-pin (8 MB)"

    def test_replacing_a_total_with_a_note_does_not_leave_the_old_figure(
            self, client, computer):
        """Passing None once meant "leave the total alone", so the stale number
        stayed and the string read '16 MB; 16MB (2 banks)'."""
        aid = computer()["asset_id"]
        client.patch(f"/api/computers/{aid}", json={"installed_ram": "16MB"})
        c = client.patch(f"/api/computers/{aid}",
                         json={"installed_ram": "16MB (2 banks)"}).json()
        assert c["installed_ram_kb"] is None
        assert c["installed_ram"] == "16MB (2 banks)"

    def test_clearing_the_grid_clears_the_memory(self, client, computer):
        aid = computer()["asset_id"]
        client.post(f"/computers/{aid}/edit", data={"rammod:30p1m": "8"},
                    follow_redirects=False)
        client.post(f"/computers/{aid}/edit", data={"rammod:30p1m": ""},
                    follow_redirects=False)
        c = client.get(f"/api/computers/{aid}").json()
        assert c["installed_ram"] == "" and c["installed_ram_kb"] is None

    def test_parity_reaches_the_stored_total(self, client, computer):
        aid = computer()["asset_id"]
        client.post(f"/computers/{aid}/edit", data={"ramchip:41256": "18"},
                    follow_redirects=False)
        assert client.get(f"/api/computers/{aid}").json()["installed_ram_kb"] == 512


class TestDrives:
    def test_a_typed_field_becomes_rows_and_renders_back(self, client, computer):
        c = computer(drives='2x 5.25" 360K; 1x Gotek 1.44MB')
        assert c["drives"] == '2× 5.25" 360K floppy; 1.44MB Gotek'

    def test_the_row_editor_replaces_the_drives(self, client, computer):
        aid = computer(drives="1GB CF")["asset_id"]
        client.post(f"/computers/{aid}/edit",
                    data={"drive0_count": "2", "drive0_kind": "floppy",
                          "drive0_form_factor": '5.25"', "drive0_size": "360K",
                          "drive0_model": ""},
                    follow_redirects=False)
        assert client.get(f"/api/computers/{aid}").json()["drives"] == \
            '2× 5.25" 360K floppy'

    def test_an_emptied_row_removes_that_drive(self, client, computer):
        aid = computer(drives="1GB CF")["asset_id"]
        client.post(f"/computers/{aid}/edit", data={"drive0_kind": "",
                    "drive0_size": "", "drive0_model": ""}, follow_redirects=False)
        assert client.get(f"/api/computers/{aid}").json()["drives"] == ""

    def test_routing_a_floppy_to_a_machine_survives_the_next_save(
            self, client, computer):
        """The routing path used to append text to the rendered string, which the
        next save re-rendered away."""
        aid = computer()["asset_id"]
        client.post("/parts/new",
                    data={"type": "storage", "computer_id": aid,
                          "kind": "Floppy/Gotek", "drive_desc": '1x 5.25" 1.2MB'},
                    follow_redirects=False)
        assert client.get(f"/api/computers/{aid}").json()["drives"] == \
            '5.25" 1.2MB floppy'
        page = client.get(f"/computers/{aid}/edit").text
        assert 'value="1.2MB"' in page

    def test_the_form_records_both_halves_of_a_bezel(self, client, computer):
        aid = computer()["asset_id"]
        client.post(f"/computers/{aid}/edit",
                    data={"drive0_count": "1", "drive0_kind": "floppy",
                          "drive0_form_factor": '3.5"', "drive0_size": "1.44MB",
                          "drive0_model": "", "drive0_colour": "Beige",
                          "drive0_yellowing": "Heavily yellowed"},
                    follow_redirects=False)
        assert client.get(f"/api/computers/{aid}").json()["drives"] == \
            '3.5" 1.44MB floppy (beige, heavily yellowed)'

    def test_a_shade_with_no_yellowing_is_a_clean_drive(self, client, computer):
        aid = computer()["asset_id"]
        client.post(f"/computers/{aid}/edit",
                    data={"drive0_count": "1", "drive0_kind": "floppy",
                          "drive0_colour": "Off-white", "drive0_yellowing": ""},
                    follow_redirects=False)
        assert client.get(f"/api/computers/{aid}").json()["drives"] == \
            "floppy (off-white)"

    def test_both_come_back_into_the_form(self, client, computer):
        """Each menu has to hold what was saved, or the next save would quietly drop
        it -- the same trap a select with no option for its value always is."""
        aid = computer(
            drives='3.5" 1.44MB floppy (grey-beige, unevenly yellowed)')["asset_id"]
        page = client.get(f"/computers/{aid}/edit").text
        assert '<option value="Grey-beige" selected>' in page
        assert '<option value="Unevenly yellowed" selected>' in page
        client.post(f"/computers/{aid}/edit",
                    data={"drive0_count": "1", "drive0_kind": "floppy",
                          "drive0_form_factor": '3.5"', "drive0_size": "1.44MB",
                          "drive0_model": "", "drive0_colour": "Grey-beige",
                          "drive0_yellowing": "Unevenly yellowed"},
                    follow_redirects=False)
        assert client.get(f"/api/computers/{aid}").json()["drives"] == \
            '3.5" 1.44MB floppy (grey-beige, unevenly yellowed)'

    def test_a_row_with_only_a_bezel_is_still_a_drive(self, client, computer):
        """Nothing else known about it yet, but the bezel was looked at."""
        aid = computer()["asset_id"]
        client.post(f"/computers/{aid}/edit",
                    data={"drive0_yellowing": "Browned"}, follow_redirects=False)
        assert client.get(f"/api/computers/{aid}").json()["drives"] == "(browned)"

    def test_the_edit_form_carries_the_chart(self, client, computer):
        """The chart is next to the menus because that is where the choice is made:
        a bezel is held up to the screen and the nearest one taken."""
        page = client.get(f"/computers/{computer()['asset_id']}/edit").text
        assert "colour chart" in page
        for label in ("Black", "Grey", "White", "Beige", "Lightly yellowed"):
            assert f'<option value="{label}">' in page
        # The chart draws each level on three shades, from the same function the
        # menus' live swatch reads.
        assert page.count("linear-gradient(115deg") >= 3
        # The drive rows do not fit a phone; squeezed to fit, the row showed two
        # characters of a model and none of the bezel.
        assert re.search(r'<div class="hscroll">\s*<table class="drives">', page)

    def test_a_bezel_is_searchable(self, client, computer):
        """It rides on the drives string, which the search index reads, so "which
        machines have a yellowed floppy" is a question the box can answer."""
        aid = computer(drives='3.5" 1.44MB floppy (beige, yellowed)')["asset_id"]
        computer(drives='3.5" 1.44MB floppy (beige)')
        found = re.findall(r'/computers/(RH-[A-Z0-9]+)"',
                           client.get("/?q=yellowed").text)
        assert set(found) == {aid}

    def test_routing_a_drive_reads_its_bezel(self, client, computer):
        aid = computer()["asset_id"]
        client.post("/parts/new",
                    data={"type": "storage", "computer_id": aid,
                          "kind": "Floppy/Gotek",
                          "drive_desc": '1x 5.25" 1.2MB beige, lightly yellowed'},
                    follow_redirects=False)
        assert client.get(f"/api/computers/{aid}").json()["drives"] == \
            '5.25" 1.2MB floppy (beige, lightly yellowed)'

    def test_routing_a_drive_takes_the_bezel_from_its_menus(self, client, computer):
        """Adding a drive from the part form is where most of them get added, so the
        menus are there too rather than only in the machine's own form."""
        aid = computer()["asset_id"]
        client.post("/parts/new",
                    data={"type": "storage", "computer_id": aid,
                          "kind": "Floppy/Gotek", "drive_desc": '1x 5.25" 1.2MB',
                          "drive_colour": "Grey", "drive_yellowing": "Browned"},
                    follow_redirects=False)
        assert client.get(f"/api/computers/{aid}").json()["drives"] == \
            '5.25" 1.2MB floppy (grey, browned)'

    def test_the_menu_wins_over_the_same_thing_typed(self, client, computer):
        aid = computer()["asset_id"]
        client.post("/parts/new",
                    data={"type": "storage", "computer_id": aid,
                          "kind": "Floppy/Gotek",
                          "drive_desc": '1x 5.25" 1.2MB beige',
                          "drive_colour": "Warm beige"},
                    follow_redirects=False)
        assert client.get(f"/api/computers/{aid}").json()["drives"] == \
            '5.25" 1.2MB floppy (warm beige)'

    def test_a_blank_menu_leaves_what_was_typed(self, client, computer):
        aid = computer()["asset_id"]
        client.post("/parts/new",
                    data={"type": "storage", "computer_id": aid,
                          "kind": "Floppy/Gotek",
                          "drive_desc": '1x 5.25" 1.2MB beige',
                          "drive_colour": "", "drive_yellowing": ""},
                    follow_redirects=False)
        assert client.get(f"/api/computers/{aid}").json()["drives"] == \
            '5.25" 1.2MB floppy (beige)'

    def test_the_history_names_the_bezel_that_was_picked(self, client, computer):
        aid = computer()["asset_id"]
        client.post("/parts/new",
                    data={"type": "storage", "computer_id": aid,
                          "kind": "Floppy/Gotek", "drive_desc": "1x 3.5in 1.44MB",
                          "drive_colour": "Beige", "drive_yellowing": "Yellowed"},
                    follow_redirects=False)
        messages = [e["message"] for e in client.get(f"/api/items/{aid}/log").json()]
        assert 'added drive: 3.5" 1.44MB floppy (beige, yellowed)' in messages

    def test_the_routed_form_offers_the_menus_and_the_chart(self, client, computer):
        page = client.get(f"/parts/new?type=storage&computer_id="
                          f"{computer()['asset_id']}").text
        assert 'name="drive_colour"' in page and 'name="drive_yellowing"' in page
        assert "colour chart" in page

    def test_a_routed_drive_with_no_machine_keeps_its_bezel(self, client):
        """No machine to route to, so it becomes a storage part after all -- and the
        bezel picked on the way in comes with it."""
        r = client.post("/parts/new",
                        data={"type": "storage", "kind": "Floppy/Gotek",
                              "drive_desc": '5.25" 1.2MB',
                              "drive_colour": "Beige",
                              "drive_yellowing": "Lightly yellowed"},
                        follow_redirects=False)
        aid = r.headers["location"].rsplit("/", 1)[-1]
        specs = client.get(f"/api/parts/{aid}").json()["specs"]
        assert "Colour: Beige" in specs and "Yellowing: Lightly yellowed" in specs

    def test_routing_a_floppy_creates_no_part(self, client, computer):
        aid = computer()["asset_id"]
        client.post("/parts/new",
                    data={"type": "storage", "computer_id": aid,
                          "kind": "Floppy/Gotek", "drive_desc": "1x 3.5in 1.44MB"},
                    follow_redirects=False)
        assert client.get("/api/parts", params={"computer_id": aid}).json() == []


class TestADriveKeptAsAPart:
    """A routed kind with no machine to route to becomes a part after all, and its
    description is the only thing that says what the drive is. It used to be read
    for the machine's drive row and thrown away on the path that made a part, so
    the part arrived saying nothing but 'Kind: Floppy/Gotek'."""

    DESC = '3.5" 1.44MB floppy, Sony CDU55'

    def make(self, client, **extra):
        r = client.post("/parts/new",
                        data={"type": "storage", "kind": "Floppy/Gotek",
                              "drive_desc": self.DESC, **extra},
                        follow_redirects=False)
        return r.headers["location"].rsplit("/", 1)[-1]

    def test_the_description_is_kept(self, client):
        aid = self.make(client)
        assert f"Description: {self.DESC}" in \
            client.get(f"/api/parts/{aid}").json()["specs"]

    def test_the_form_opens_on_it_again(self, client):
        from markupsafe import escape
        aid = self.make(client)
        assert f'value="{escape(self.DESC)}"' in client.get(f"/parts/{aid}/edit").text

    def test_a_no_op_save_does_not_drop_it(self, client):
        aid = self.make(client)
        client.post(f"/parts/{aid}/edit",
                    data={"type": "storage", "kind": "Floppy/Gotek",
                          "drive_desc": self.DESC}, follow_redirects=False)
        assert self.DESC in client.get(f"/api/parts/{aid}").json()["specs"]

    def test_editing_it_is_not_ignored(self, client):
        aid = self.make(client)
        client.post(f"/parts/{aid}/edit",
                    data={"type": "storage", "kind": "Floppy/Gotek",
                          "drive_desc": "5.25in 360K floppy"}, follow_redirects=False)
        specs = client.get(f"/api/parts/{aid}").json()["specs"]
        assert "Description: 5.25in 360K floppy" in specs and self.DESC not in specs

    def test_duplicating_carries_it_across(self, client):
        aid = self.make(client)
        r = client.post(f"/parts/{aid}/duplicate", follow_redirects=False)
        copy = r.headers["location"].rsplit("/", 1)[-1]
        assert self.DESC in client.get(f"/api/parts/{copy}").json()["specs"]

    def test_a_second_one_started_from_it_opens_on_it(self, client):
        """The duplicate-then-edit route: /parts/new?from= fills the form in from
        an existing part, and the description is part of what it describes."""
        aid = self.make(client)
        page = client.get(f"/parts/new?from={aid}").text
        assert "1.44MB floppy, Sony CDU55" in page

    def test_a_machine_to_route_to_still_wins(self, client, computer):
        cid = computer()["asset_id"]
        self.make(client, computer_id=cid)
        assert client.get("/api/parts", params={"computer_id": cid}).json() == []
        assert "1.44MB" in client.get(f"/api/computers/{cid}").json()["drives"]


class TestSpecs:
    def test_writing_specs_canonicalises_the_string(self, part):
        p = part(type="sound", specs="Interface: ISA | Chip: ES1869F")
        assert p["specs"] == "Chip: ES1869F | Interface: ISA"

    def test_a_spec_the_columns_cannot_hold_is_still_shown(self, client, part):
        p = part(type="motherboard", specs="Cache: Fake")
        assert "Cache: Fake" in p["specs"]

    def test_the_typed_rows_are_the_read_path_for_the_page(self, client, part):
        aid = part(type="motherboard", specs="Onboard RAM: 64-256KB")["asset_id"]
        assert "64-256KB" in client.get(f"/parts/{aid}").text

    def test_saving_a_part_keeps_a_spec_the_form_does_not_manage(self, client, part):
        """The form has no field for an unrecognised key, so it is read back from
        part_attribute and re-appended rather than being dropped on save."""
        aid = part(type="video", specs="Chip: S3 | Voltage: 5V")["asset_id"]
        client.post(f"/parts/{aid}/edit",
                    data={"type": "video", "spec_chip": "S3"}, follow_redirects=False)
        assert "Voltage: 5V" in client.get(f"/api/parts/{aid}").json()["specs"]


class TestAStoragePartsBezel:
    """The front of a full-height drive is as beige as any floppy's, so a storage
    part records the same shade and yellowing a fitted drive row does -- through the
    spec machinery rather than its own columns, which is where a part's other typed
    facts already live.
    """

    def test_the_form_records_both(self, client):
        r = client.post("/parts/new",
                        data={"type": "storage", "kind": "Hard disk",
                              "spec_interface": "MFM", "spec_colour": "Off-white",
                              "spec_yellowing": "Yellowed"},
                        follow_redirects=False)
        aid = r.headers["location"].rsplit("/", 1)[-1]
        specs = client.get(f"/api/parts/{aid}").json()["specs"]
        assert specs == ("Kind: Hard disk | Interface: MFM | Colour: Off-white "
                         "| Yellowing: Yellowed")

    def test_they_come_back_into_the_form(self, client, part):
        aid = part(type="storage",
                   specs="Kind: Tape | Colour: Black")["asset_id"]
        page = client.get(f"/parts/{aid}/edit").text
        assert '<option value="Black" selected>' in page
        assert "colour chart" in page

    def test_editing_keeps_them(self, client, part):
        aid = part(type="storage", specs="Kind: Hard disk | Colour: Beige | "
                                         "Yellowing: Browned")["asset_id"]
        client.post(f"/parts/{aid}/edit",
                    data={"type": "storage", "kind": "Hard disk",
                          "spec_colour": "Beige", "spec_yellowing": "Browned"},
                    follow_redirects=False)
        assert client.get(f"/api/parts/{aid}").json()["specs"] == \
            "Kind: Hard disk | Colour: Beige | Yellowing: Browned"

    def test_the_part_page_shows_the_swatch_for_the_pair(self, client, part):
        """One piece of plastic, so both rows carry the swatch of the two together
        rather than a shade beside a separate stage."""
        from app import entry
        aid = part(type="storage", specs="Kind: Hard disk | Colour: Beige | "
                                         "Yellowing: Heavily yellowed")["asset_id"]
        page = client.get(f"/parts/{aid}").text
        css = entry.bezel_css("Beige", "Heavily yellowed")
        assert page.count(f'style="background:{css}"') == 2

    def test_a_drive_with_no_bezel_recorded_shows_no_swatch(self, client, part):
        aid = part(type="storage", specs="Kind: Hard disk")["asset_id"]
        assert 'class="swatch"' not in client.get(f"/parts/{aid}").text


class TestPagesAndDiscovery:
    def test_the_index_lists_what_exists(self, client, computer, part):
        computer(model="Findable")
        part(model="Alsofindable")
        page = client.get("/").text
        assert "Findable" in page and "Alsofindable" in page

    def test_an_item_page_titles_itself_by_name(self, client, computer):
        """The title used to be the asset id alone, which told a search result
        nothing about the machine."""
        c = computer(manufacturer="IBM", model="PS/1 Model 2121")
        page = client.get(f"/computers/{c['asset_id']}").text
        assert f"<title>IBM PS/1 Model 2121 · {c['asset_id']}" in page

    def test_an_unnamed_item_does_not_repeat_its_id(self, client, part):
        aid = part(manufacturer="", model="", name="")["asset_id"]
        assert f"<title>{aid} —" in client.get(f"/parts/{aid}").text

    def test_the_sitemap_lists_every_item(self, client, computer, part):
        c = computer()["asset_id"]
        p = part()["asset_id"]
        body = client.get("/sitemap.xml").text
        assert f"/computers/{c}</loc>" in body and f"/parts/{p}</loc>" in body

    def test_the_sitemap_omits_pages_it_asks_robots_to_skip(self, client):
        body = client.get("/sitemap.xml").text
        assert "/login" not in body and "/edit" not in body

    def test_robots_points_at_the_sitemap(self, client):
        assert "Sitemap: https://example.test/sitemap.xml" in client.get("/robots.txt").text

    def test_an_item_url_redirects_to_the_right_kind(self, client, computer, part):
        c = computer()["asset_id"]
        p = part()["asset_id"]
        assert client.get(f"/items/{c}", follow_redirects=False
                          ).headers["location"].endswith(f"/computers/{c}")
        assert client.get(f"/items/{p}", follow_redirects=False
                          ).headers["location"].endswith(f"/parts/{p}")

    def test_a_label_renders_as_a_pdf(self, client, computer):
        r = client.get(f"/computers/{computer()['asset_id']}/label.pdf")
        assert r.status_code == 200
        assert r.headers["content-type"] == "application/pdf"
        assert r.content.startswith(b"%PDF")


class TestHowBigTheDriveIsOnItsLabel:
    """The small label is what goes on the drive, and it is the default for a part.
    It has no room for a spec list, and a bare disk on a shelf is known by its
    capacity as much as by the model on the casing -- so that one spec goes on it.
    """

    def body(self, db, aid):
        from app import labels, main, specdb
        from app.models import Part
        p = db.get(Part, aid)
        return labels.small_body(main.to_dict(p), False, specdb.pairs(db, p))

    def test_a_drive_says_how_big_it_is(self, client, db, part):
        aid = part(type="storage", manufacturer="Seagate", model="ST-225",
                   specs="Kind: Hard disk | Capacity: 20 MB")["asset_id"]
        assert self.body(db, aid) == "Seagate ST-225, 20 MB"

    def test_a_drive_with_no_capacity_recorded_just_says_what_it_is(self, client, db,
                                                                   part):
        """Half the drives on file have no capacity against them; none of them should
        pick up a stray comma waiting for one."""
        aid = part(type="storage", manufacturer="Mitsumi", model="D503V",
                   specs="Kind: Floppy/Gotek")["asset_id"]
        assert self.body(db, aid) == "Mitsumi D503V"

    def test_capacity_worked_out_from_the_geometry_counts_too(self, client, db, part):
        """A drive recorded by its cylinders/heads/sectors has its capacity derived
        rather than stated, and the label carries that just the same. It arrives in
        the unit the rest of the app renders it in -- KB when nothing said MB."""
        aid = part(type="storage", manufacturer="Quantum", model="LPS 52A",
                   specs="Kind: Hard disk | CHS: 571/8/17")["asset_id"]
        assert self.body(db, aid) == "Quantum LPS 52A, 38828 KB"

    def test_other_kinds_of_part_are_left_alone(self, client, db, part):
        """Only the types whose name does not say the thing you want off the label.
        A video card's memory is on the full label, where there is room for it."""
        aid = part(type="video", manufacturer="Trident", model="8900C",
                   specs="Memory: 1 MB")["asset_id"]
        assert self.body(db, aid) == "Trident 8900C"

    def test_a_machine_is_left_alone(self, client, computer):
        from app import labels, main
        from app.models import Computer
        from app.db import SessionLocal
        aid = computer(manufacturer="Acme", model="PC-1")["asset_id"]
        s = SessionLocal()
        try:
            c = main.to_dict(s.get(Computer, aid))
        finally:
            s.close()
        assert labels.small_body(c, True) == "Acme PC-1"

    def test_the_full_label_still_lists_it_among_the_specs(self, client, db, part):
        from app import labels, main, specdb
        from app.models import Part
        aid = part(type="storage", manufacturer="Seagate", model="ST-225",
                   specs="Kind: Hard disk | Capacity: 20 MB")["asset_id"]
        p = db.get(Part, aid)
        lines = labels.part_lines(main.to_dict(p), specdb.pairs(db, p))
        assert "Capacity: 20 MB" in lines

    def test_the_drive_s_own_label_still_renders(self, client, part):
        aid = part(type="storage", model="ST-225",
                   specs="Kind: Hard disk | Capacity: 20 MB")["asset_id"]
        r = client.get(f"/parts/{aid}/label.pdf")
        assert r.status_code == 200
        assert r.content.startswith(b"%PDF")


class TestTheBrandOnThePage:
    """Where the logo shows: the header, and the card a shared link previews as."""

    def test_the_header_carries_the_logo_and_the_name(self, client):
        page = client.get("/").text
        assert re.search(r'<a class="brand" href="/">\s*<img src="/static/logo-256'
                         r'\.png\?v=[a-f0-9]+"', page)
        assert "<span>Retro Hardware Database</span>" in page

    def test_a_page_with_no_photo_shares_as_the_site_card(self, client, part):
        """It used to share as bare text. An item with no photograph of its own, the
        gallery and the figures all get the logo card instead."""
        for path in ("/", "/stats", f"/parts/{part()['asset_id']}"):
            page = client.get(path).text
            assert 'property="og:image" content="https://example.test/static/' \
                   'og-image.png?v=' in page, path
            assert '<meta property="og:image:width" content="1200">' in page, path
            assert 'name="twitter:card" content="summary_large_image"' in page, path

    def test_a_photographed_item_still_shares_its_own_photo(self, client, part):
        """The card is the fallback, not a replacement: a photograph of the thing
        itself is a better preview than a logo."""
        from PIL import Image

        from app import main
        aid = part()["asset_id"]
        folder = main.IMAGES_DIR / "parts"
        folder.mkdir(parents=True, exist_ok=True)
        photo = folder / f"{aid}.jpg"
        Image.new("RGB", (800, 600), (120, 90, 60)).save(photo, "JPEG")
        try:
            page = client.get(f"/parts/{aid}").text
            assert f'property="og:image" content="https://example.test/images/parts/{aid}.jpg' \
                   in page
            assert "og-image.png" not in page
        finally:
            photo.unlink()


class TestWalkingFromItemToItem:
    """Prev/next on an item page. The browser rewrites them to whatever order the
    gallery was showing; what is reachable from here is the fallback the server
    renders, which is register order -- what an item reached from a printed label
    gets, with nothing in sessionStorage to go on.
    """

    @staticmethod
    def links(page):
        return {rel: re.search(rf'id="nav-{rel}"[^>]*href="([^"]*)"', page).group(1)
                for rel in ("prev", "next")}

    def test_the_middle_item_points_both_ways(self, client, computer, part):
        first, middle, last = sorted(computer()["asset_id"] for _ in range(3))
        page = client.get(f"/computers/{middle}").text
        assert self.links(page) == {"prev": f"/computers/{first}",
                                    "next": f"/computers/{last}"}

    def test_the_ends_have_nothing_beyond_them(self, client, computer):
        first, last = sorted(computer()["asset_id"] for _ in range(2))
        assert re.search(r'id="nav-prev"[^>]*hidden', client.get(
            f"/computers/{first}").text)
        assert re.search(r'id="nav-next"[^>]*hidden', client.get(
            f"/computers/{last}").text)

    def test_it_walks_across_computers_and_parts_alike(self, client, computer, part):
        """One register, so the walk is over both -- the next asset after a machine
        may well be a card that is not in it."""
        kind = {computer()["asset_id"]: "computers", part()["asset_id"]: "parts"}
        first, second = sorted(kind)  # ids are assigned, so either may come first
        page = client.get(f"/{kind[first]}/{first}").text
        assert self.links(page)["next"] == f"/{kind[second]}/{second}"

    def test_the_buttons_name_where_they_go(self, client, computer):
        """The title is the neighbour's name, so a walk is not blind."""
        first = sorted([computer(model="Aaa")["asset_id"],
                        computer(model="Zzz")["asset_id"]])[0]
        page = client.get(f"/computers/{first}").text
        assert re.search(r'id="nav-next"[^>]*title="Acme (Aaa|Zzz)"', page)

    def test_a_lone_item_offers_neither(self, client, part):
        page = client.get(f"/parts/{part()['asset_id']}").text
        assert re.search(r'id="nav-prev"[^>]*hidden', page)
        assert re.search(r'id="nav-next"[^>]*hidden', page)

    def test_the_gallery_hands_over_the_order_it_is_showing(self, client, computer):
        """Sorted and filtered as the visitor left it, which is the order their
        prev/next should follow -- not the register's."""
        computer()
        page = client.get("/").text
        assert "sessionStorage.setItem('rhdb-order'" in page
        assert "el.style.display !== 'none'" in page

    def test_the_item_page_prefers_that_order(self, client, part):
        page = client.get(f"/parts/{part()['asset_id']}").text
        assert "sessionStorage.getItem('rhdb-order')" in page
        # ...and a swipe follows the same two links.
        assert "touchend" in page and "nav-next" in page


class TestSortingTheGallery:
    """The toolbar's sort menu reorders the cards in the browser, so the ordering
    itself is not reachable from here. What is reachable, and what silently breaks
    a sort if it goes missing, is the key each card carries."""

    @staticmethod
    def _card(page, aid):
        match = re.search(rf'<a class="card"[^>]*/{aid}"(.*?)>', page, re.S)
        assert match, f"no card for {aid}"
        return match.group(1)

    def test_a_machine_carries_every_key_the_menu_sorts_on(self, client, computer):
        c = computer(manufacturer="Amstrad", model="PC1512", year=1986,
                     acquired_date="2026-05-01")
        card = self._card(client.get("/").text, c["asset_id"])
        assert 'data-year="1986"' in card
        assert 'data-maker="amstrad"' in card
        assert 'data-acquired="2026-05-01"' in card
        assert f'data-aid="{c["asset_id"]}"' in card

    def test_a_part_carries_them_too(self, client, part):
        p = part(type="video", manufacturer="Tseng", model="ET4000", year=1990,
                 acquired_date="2026-05-02")
        card = self._card(client.get("/").text, p["asset_id"])
        assert 'data-year="1990"' in card
        assert 'data-maker="tseng"' in card
        assert 'data-acquired="2026-05-02"' in card

    def test_what_is_not_recorded_is_blank_rather_than_absent(self, client, part):
        """A missing attribute reads as undefined in the sort; an empty one is
        what the blanks-last rule looks for."""
        p = part(manufacturer="", year=None, acquired_date=None)
        card = self._card(client.get("/").text, p["asset_id"])
        assert 'data-year=""' in card
        assert 'data-maker=""' in card
        assert 'data-acquired=""' in card

    def test_machines_lead_the_category_order(self, client, computer, part):
        """Category sorts by the vocabulary's own order, not the label's spelling,
        and a computer is not one of the part types."""
        c = computer()
        p = part(type="video")
        page = client.get("/").text
        assert 'data-catsort="0"' in self._card(page, c["asset_id"])
        assert 'data-catsort="0"' not in self._card(page, p["asset_id"])

    def test_the_menu_offers_each_of_them(self, client):
        page = client.get("/").text
        for mode in ("updated", "added", "acquired", "yearnew", "yearold",
                     "name", "maker", "cat", "aid"):
            assert f'<option value="{mode}">' in page


class TestHistory:
    def test_creating_an_item_is_recorded(self, client, part):
        aid = part()["asset_id"]
        assert [e["message"] for e in client.get(f"/api/items/{aid}/log").json()] \
            == ["created"]

    def test_a_change_is_recorded_field_by_field(self, client, part):
        aid = part(model="Before")["asset_id"]
        client.patch(f"/api/parts/{aid}", json={"model": "After"})
        messages = [e["message"] for e in client.get(f"/api/items/{aid}/log").json()]
        assert any("model: Before → After" in m for m in messages)

    def test_deleting_an_item_takes_its_history_with_it(self, client, part):
        aid = part()["asset_id"]
        client.delete(f"/api/parts/{aid}")
        assert client.get(f"/api/items/{aid}/log").json() == []


class TestTheClockShowsOnlyWhenSignedIn:
    """A visitor gets the date something happened; what time of night the collection
    gets worked on is nobody else's business. Auth is off in these tests, so the
    anonymous half has to ask for it.
    """
    DATE = r"\d{4}-\d{2}-\d{2}"
    DATE_TIME = r"\d{4}-\d{2}-\d{2} \d{2}:\d{2}"

    def test_the_history_gives_the_minute_to_whoever_can_edit_it(self, client, part):
        aid = part()["asset_id"]
        page = client.get(f"/parts/{aid}").text
        assert re.search(self.DATE_TIME, page)

    def test_a_visitor_gets_the_day_alone(self, client, part, monkeypatch):
        from app import main
        aid = part()["asset_id"]
        monkeypatch.setattr(main, "AUTH_ENABLED", True)
        page = client.get(f"/parts/{aid}").text
        assert re.search(self.DATE, page)
        assert not re.search(self.DATE_TIME, page)

    def test_a_machine_history_is_the_same(self, client, computer, monkeypatch):
        from app import main
        aid = computer()["asset_id"]
        monkeypatch.setattr(main, "AUTH_ENABLED", True)
        page = client.get(f"/computers/{aid}").text
        assert re.search(self.DATE, page)
        assert not re.search(self.DATE_TIME, page)

    def test_the_gallery_sort_keys_lose_the_time_too(self, client, part, monkeypatch):
        """They are not on show, but a timestamp in the page source is a timestamp
        published all the same."""
        from app import main
        p = part()
        card = TestSortingTheGallery._card(client.get("/").text, p["asset_id"])
        assert re.search(rf'data-updated="{self.DATE}T', card)
        monkeypatch.setattr(main, "AUTH_ENABLED", True)
        card = TestSortingTheGallery._card(client.get("/").text, p["asset_id"])
        assert re.search(rf'data-updated="{self.DATE}"', card)
        assert re.search(rf'data-added="{self.DATE}"', card)

    def test_the_cards_arrive_newest_change_first(self, client, part, db):
        """Dates alone are all the sort keys a visitor gets, and the browser's sort
        is stable, so the order the cards arrive in is what still settles a run of
        edits made on the same day."""
        from app.models import LogEntry
        old = part(model="Older")["asset_id"]
        new = part(model="Newer")["asset_id"]
        db.query(LogEntry).filter(LogEntry.asset_id == old).update(
            {"created_at": datetime(2020, 1, 1)})
        db.commit()
        page = client.get("/").text
        assert page.index(f'/parts/{new}"') < page.index(f'/parts/{old}"')


class TestPhotoLookup:
    """Ordering and grouping of an asset's photos.

    A list page reads each folder once and picks from the result; an item page
    reads it for one asset. Both go through pick_images, so the ordering is
    pinned here rather than in two places.
    """

    @staticmethod
    def listing(*stems):
        return [(s, f"{s}.jpg") for s in stems]

    def test_the_bare_asset_id_is_the_primary(self):
        from app.main import pick_images
        got = pick_images("parts", "RH-0001",
                          self.listing("RH-0001-2", "RH-0001"))
        assert got[0] == "parts/RH-0001.jpg"

    def test_numbered_extras_sort_numerically_not_as_text(self):
        from app.main import pick_images
        got = pick_images("parts", "RH-0001",
                          self.listing("RH-0001-10", "RH-0001-2", "RH-0001"))
        assert got == ["parts/RH-0001.jpg", "parts/RH-0001-2.jpg",
                       "parts/RH-0001-10.jpg"]

    def test_a_named_suffix_comes_after_the_numbered_ones(self):
        from app.main import pick_images
        got = pick_images("parts", "RH-0001",
                          self.listing("RH-0001-back", "RH-0001-2"))
        assert got == ["parts/RH-0001-2.jpg", "parts/RH-0001-back.jpg"]

    def test_another_asset_is_not_picked_up(self):
        from app.main import pick_images
        got = pick_images("parts", "RH-0001", self.listing("RH-0002", "RH-00012"))
        assert got == []

    def test_an_asset_whose_id_is_a_prefix_of_another(self):
        """RH-0001 must not swallow RH-00019's photo, and the hyphen is what
        separates an id from a suffix."""
        from app.main import pick_images
        got = pick_images("parts", "RH-0001",
                          self.listing("RH-0001", "RH-00019", "RH-0001-2"))
        assert got == ["parts/RH-0001.jpg", "parts/RH-0001-2.jpg"]

    def test_the_index_shows_a_photo_it_finds_on_disk(self, client, part, tmp_path):
        from app import main
        aid = part()["asset_id"]
        folder = main.IMAGES_DIR / "parts"
        folder.mkdir(parents=True, exist_ok=True)
        (folder / f"{aid}.jpg").write_bytes(b"not really a jpeg")
        try:
            assert f"/images/parts/{aid}.jpg" in client.get("/").text
        finally:
            (folder / f"{aid}.jpg").unlink()


class TestDuplication:
    """A duplicate is a second physical unit of the same model.

    It takes what describes the model and leaves behind what belongs to the
    original object: its photos, its disposal, its provenance, and where it sits.
    """

    def test_a_duplicated_part_is_not_in_the_same_machine(self, client, part, computer):
        cid = computer()["asset_id"]
        src = part(type="video", model="ET4000", computer_id=cid)["asset_id"]
        r = client.post(f"/parts/{src}/duplicate", follow_redirects=False)
        copy = client.get(f"/api/parts/{r.headers['location'].split('/')[-1]}").json()
        assert copy["computer_id"] is None

    def test_a_duplicated_part_is_not_mounted_on_the_same_host(self, client, part):
        host = part(type="io")["asset_id"]
        src = part(type="storage", parent_id=host)["asset_id"]
        r = client.post(f"/parts/{src}/duplicate", follow_redirects=False)
        copy = client.get(f"/api/parts/{r.headers['location'].split('/')[-1]}").json()
        assert copy["parent_id"] is None

    def test_a_duplicated_part_keeps_what_describes_the_model(self, client, part):
        src = part(type="video", manufacturer="Tseng", model="ET4000", year=1993,
                   specs="Chip: ET4000 | Interface: VLB", url="https://example.test/x",
                   condition="Working")
        r = client.post(f"/parts/{src['asset_id']}/duplicate", follow_redirects=False)
        copy = client.get(f"/api/parts/{r.headers['location'].split('/')[-1]}").json()
        for field in ("type", "manufacturer", "model", "year", "specs", "url",
                      "condition"):
            assert copy[field] == src[field], field

    def test_a_duplicated_part_drops_what_belongs_to_the_original(self, client, part):
        src = part(source="eBay", acquired_date="2026-01-05", notes="a bit bent")
        client.post(f"/parts/{src['asset_id']}/dispose", data={"note": "binned"},
                    follow_redirects=False)
        r = client.post(f"/parts/{src['asset_id']}/duplicate", follow_redirects=False)
        copy = client.get(f"/api/parts/{r.headers['location'].split('/')[-1]}").json()
        assert copy["source"] == "" and copy["acquired_date"] is None
        assert copy["notes"] == "" and copy["disposed"] is False

    def test_a_computer_can_be_duplicated(self, client, computer):
        src = computer(manufacturer="IBM", model="5170", year=1984, chassis="desktop",
                       cpu="Intel 80286-6", os="MS DOS 5.0", condition="Working")
        r = client.post(f"/computers/{src['asset_id']}/duplicate",
                        follow_redirects=False)
        assert r.status_code == 303
        copy = client.get(f"/api/computers/{r.headers['location'].split('/')[-1]}").json()
        assert copy["asset_id"] != src["asset_id"]
        for field in ("manufacturer", "model", "year", "chassis", "cpu", "os",
                      "condition"):
            assert copy[field] == src[field], field

    def test_a_duplicated_computer_has_none_of_the_original_s_parts(
            self, client, computer, part):
        cid = computer()["asset_id"]
        part(computer_id=cid)
        part(computer_id=cid, type="video")
        r = client.post(f"/computers/{cid}/duplicate", follow_redirects=False)
        copy_id = r.headers["location"].split("/")[-1]
        assert client.get("/api/parts", params={"computer_id": copy_id}).json() == []
        assert len(client.get("/api/parts", params={"computer_id": cid}).json()) == 2

    def test_a_duplicated_computer_keeps_its_memory_and_drives(self, client, computer):
        cid = computer(drives='2x 5.25" 360K')["asset_id"]
        client.post(f"/computers/{cid}/edit",
                    data={"rammod:30p1m": "4", "installed_ram": "",
                          "drive0_count": "2", "drive0_kind": "floppy",
                          "drive0_form_factor": '5.25"', "drive0_size": "360K"},
                    follow_redirects=False)
        r = client.post(f"/computers/{cid}/duplicate", follow_redirects=False)
        copy = client.get(f"/api/computers/{r.headers['location'].split('/')[-1]}").json()
        assert copy["installed_ram"] == "4× 1MB 30-pin (4 MB)"
        assert copy["installed_ram_kb"] == 4096
        assert copy["drives"] == '2× 5.25" 360K floppy'

    def test_a_duplicated_computer_s_memory_survives_editing_it(self, client, computer):
        """The copy needs its own child rows, not just the rendered strings, or the
        first save would render them away."""
        cid = computer()["asset_id"]
        client.post(f"/computers/{cid}/edit", data={"ramchip:41256": "9"},
                    follow_redirects=False)
        r = client.post(f"/computers/{cid}/duplicate", follow_redirects=False)
        copy_id = r.headers["location"].split("/")[-1]
        page = client.get(f"/computers/{copy_id}/edit").text
        assert 'name="ramchip:41256" value="9"' in page

    def test_both_sides_record_the_duplication(self, client, computer):
        cid = computer()["asset_id"]
        r = client.post(f"/computers/{cid}/duplicate", follow_redirects=False)
        copy_id = r.headers["location"].split("/")[-1]
        assert any(f"duplicated to {copy_id}" in e["message"]
                   for e in client.get(f"/api/items/{cid}/log").json())
        assert any(f"duplicate of {cid}" in e["message"]
                   for e in client.get(f"/api/items/{copy_id}/log").json())


class TestChoosingPhotos:
    """Choosing the photos is the whole gesture: they upload on selection, and the
    button says so in the site's own words rather than the browser's.
    """

    def test_the_button_is_the_site_s_own_lower_case_one(self, client, part):
        page = client.get(f"/parts/{part()['asset_id']}").text
        assert '<label class="btn sm filebtn">choose files' in page
        # The native input lives inside that label, which is the only way the
        # browser's own "Choose Files" button and "no file chosen" never appear.
        assert re.search(r'<label class="btn sm filebtn">choose files\s*'
                         r'<input type="file"', page)

    def test_it_uploads_without_a_button_press(self, client, part):
        page = client.get(f"/parts/{part()['asset_id']}").text
        assert "input.addEventListener('change'" in page
        assert "requestSubmit" in page

    def test_the_button_is_still_there_for_a_browser_without_scripts(self, client,
                                                                     part):
        """The submit hides itself from the script above rather than being absent, so
        the form still works where that script never runs."""
        page = client.get(f"/parts/{part()['asset_id']}").text
        assert '<button class="btn sm" type="submit" id="photo-upload-go">' in page


class TestPhotographsOnACreateForm:
    """A thing has no asset tag until it is saved, so photographs chosen while it is
    being created cannot upload as they are picked the way they do on an item's own
    page. They wait, travel with the rest of the form, and are written once the tag
    has been assigned.
    """

    @staticmethod
    def image(name="shot.jpg", size=(400, 300)):
        import io
        from PIL import Image
        buf = io.BytesIO()
        Image.new("RGB", size, (90, 120, 60)).save(buf, "JPEG", quality=90)
        buf.seek(0)
        return (name, buf, "image/jpeg")

    def created(self, r, kind="computers"):
        return r.headers["location"].split(f"/{kind}/")[1].split("?")[0]

    def test_a_machine_is_photographed_as_it_is_created(self, client):
        from app import main
        r = client.post("/computers/new", data={"model": "Snapped"},
                        files={"photos": self.image()}, follow_redirects=False)
        aid = self.created(r)
        assert (main.IMAGES_DIR / "computers" / f"{aid}.jpg").exists()
        # The first one becomes the machine's own photo, as it would on the item page.
        assert client.get(f"/api/computers/{aid}").json()["image"] == \
            f"computers/{aid}.jpg"

    def test_a_part_is_photographed_as_it_is_created(self, client):
        from app import main
        r = client.post("/parts/new", data={"type": "video", "model": "Trident"},
                        files={"photos": self.image()}, follow_redirects=False)
        aid = self.created(r, "parts")
        assert (main.IMAGES_DIR / "parts" / f"{aid}.jpg").exists()
        assert client.get(f"/api/parts/{aid}").json()["image"] == f"parts/{aid}.jpg"

    def test_several_arrive_together_and_the_first_is_the_primary(self, client):
        from app import main
        r = client.post("/computers/new", data={"model": "Gallery"},
                        files=[("photos", self.image("a.jpg")),
                               ("photos", self.image("b.jpg")),
                               ("photos", self.image("c.jpg"))],
                        follow_redirects=False)
        aid = self.created(r)
        folder = main.IMAGES_DIR / "computers"
        assert (folder / f"{aid}.jpg").exists()
        assert (folder / f"{aid}-2.jpg").exists()
        assert (folder / f"{aid}-3.jpg").exists()
        assert client.get(f"/api/computers/{aid}").json()["image"] == \
            f"computers/{aid}.jpg"

    def test_a_file_that_is_not_an_image_creates_nothing_at_all(self, client):
        """Checked before the machine is written rather than after. A file refused
        half way would leave photographs filed under a tag the machine never kept --
        and the next thing created, taking that tag, would inherit them."""
        import io

        from app import main
        folder = main.IMAGES_DIR / "computers"
        folder.mkdir(parents=True, exist_ok=True)
        before = sorted(p.name for p in folder.iterdir())
        r = client.post("/computers/new", data={"model": "Rejected"},
                        files={"photos": ("notes.txt", io.BytesIO(b"nope"),
                                          "text/plain")},
                        follow_redirects=False)
        assert r.status_code == 400
        assert client.get("/api/computers").json() == []
        assert sorted(p.name for p in folder.iterdir()) == before

    def test_a_drive_folded_into_a_machine_photographs_the_machine(self, client,
                                                                   computer):
        """A floppy becomes a row on the machine rather than an asset of its own, so
        it has no tag of its own to file a photograph under: the machine it went
        into is the only place they can go."""
        aid = computer()["asset_id"]
        client.post("/parts/new",
                    data={"type": "storage", "kind": "Floppy/Gotek",
                          "computer_id": aid, "drive_desc": '3.5" 1.44MB'},
                    files={"photos": self.image()}, follow_redirects=False)
        assert client.get(f"/api/computers/{aid}").json()["image"] == \
            f"computers/{aid}.jpg"

    @pytest.mark.parametrize("path", ["/computers/new", "/parts/new"])
    def test_the_form_offers_the_picker_and_can_carry_a_file(self, client, path):
        page = client.get(path).text
        assert 'name="photos"' in page
        assert 'enctype="multipart/form-data"' in page

    def test_an_edit_form_does_not_offer_it(self, client, computer, part):
        """The item already has a page, where a photograph uploads the moment it is
        picked; a second, slower way to do the same thing on the edit form would
        only be a way of doing it worse."""
        for path in (f"/computers/{computer()['asset_id']}/edit",
                     f"/parts/{part()['asset_id']}/edit"):
            assert 'name="photos"' not in client.get(path).text

    def test_the_picker_is_not_the_one_that_uploads_on_selection(self, client):
        """That script is bound by id to the item page's form. A create form's picker
        must fall outside it, or choosing a file would submit the half-filled form."""
        assert 'id="photo-upload"' not in client.get("/computers/new").text


class TestTheIconSet:
    """The favicons, app icons and photo watermark, all generated from one master by
    tools/make_icons.py. The artwork is a design matter; that it keeps its
    transparency on the way into every format is not.
    """
    STATIC = Path(__file__).resolve().parent.parent / "app" / "static"

    def open(self, name):
        from PIL import Image
        return Image.open(self.STATIC / name)

    @pytest.mark.parametrize("name", ["app-icon.png", "favicon-16x16.png",
                                      "favicon-32x32.png", "icon-192.png",
                                      "icon-512.png", "logo-512.png",
                                      "logo-256.png", "favicon.ico"])
    def test_the_background_stays_transparent(self, name):
        im = self.open(name).convert("RGBA")
        assert im.getchannel("A").getextrema()[0] == 0, f"{name} lost its alpha"

    def test_the_apple_icon_is_deliberately_not(self):
        """iOS composites transparency on black, so this one is flattened on white.
        The exception is the reason the rule above is worth stating."""
        im = self.open("apple-touch-icon.png").convert("RGBA")
        assert im.getchannel("A").getextrema() == (255, 255)

    @pytest.mark.parametrize("name,size", [("favicon-16x16.png", 16),
                                           ("favicon-32x32.png", 32),
                                           ("apple-touch-icon.png", 180),
                                           ("icon-192.png", 192),
                                           ("icon-512.png", 512)])
    def test_each_slot_is_the_square_it_claims(self, name, size):
        assert self.open(name).size == (size, size)

    @pytest.mark.parametrize("name", ["logo-512.png", "logo-256.png"])
    def test_the_logo_keeps_its_own_shape(self, name):
        """The header and the photo watermark are not square slots, so they get the
        tight crop: letterboxing the mark would shrink it on the photo, and the
        header would carry a logo with air above and below it."""
        master, logo = self.open("app-icon.png"), self.open(name)
        assert abs(master.width / master.height - logo.width / logo.height) < 0.02

    def test_the_share_card_is_opaque_and_the_shape_those_slots_want(self):
        """Several of the sites that show a card composite a transparent PNG onto
        black, so this one brings its own background."""
        card = self.open("og-image.png")
        assert card.size == (1200, 630)
        assert card.convert("RGBA").getchannel("A").getextrema() == (255, 255)

    def test_the_master_is_cropped_to_its_artwork(self):
        """No transparent margin left on the master, so every icon made from it uses
        the whole slot."""
        from PIL import Image
        im: Image.Image = self.open("app-icon.png").convert("RGBA")
        solid = im.getchannel("A").point(lambda v: 255 if v > 32 else 0)
        assert solid.getbbox() == (0, 0, im.width, im.height)


class TestWatermark:
    """Our own photos are served marked; someone else's are served untouched.

    The size is a visual choice and not pinned here, but which photos get marked
    at all is behaviour worth keeping.
    """

    @staticmethod
    def write_photo(path):
        from PIL import Image
        path.parent.mkdir(parents=True, exist_ok=True)
        Image.new("RGB", (600, 400), (90, 110, 130)).save(path, "JPEG", quality=95)

    def test_our_own_photo_comes_back_marked(self, client, part):
        from app import main
        aid = part()["asset_id"]
        photo = main.IMAGES_DIR / "parts" / f"{aid}.jpg"
        self.write_photo(photo)
        try:
            served = client.get(f"/images/parts/{aid}.jpg").content
            assert served != photo.read_bytes()
            assert (main.WM_CACHE / "parts" / f"{aid}.jpg").exists()
        finally:
            photo.unlink()
            main._wm_forget(f"parts/{aid}.jpg")

    def test_the_mark_grows_with_the_photo(self, client, part):
        """It is a proportion of the short edge, not a fixed number of pixels, so
        it stays legible on a 5712px photo and unobtrusive on a small one."""
        from PIL import Image
        from app import main
        marks = []
        for size in ((400, 300), (2000, 1500)):
            mark = Image.open(main.WM_SRC).convert("RGBA")
            target = max(34, int(min(size) * 0.18))
            mark.thumbnail((target, target), Image.LANCZOS)
            marks.append(mark.width)
        assert marks[1] > marks[0] * 4

    def test_a_reference_photo_is_left_alone(self, client, part):
        """Someone else's picture of the same model is not ours to sign."""
        from app import main
        aid = part()["asset_id"]
        rel = f"parts/{aid}.jpg"
        photo = main.IMAGES_DIR / rel
        self.write_photo(photo)
        main._ref_sidecar(rel).write_text('{"note": "", "source": ""}', encoding="utf-8")
        try:
            assert client.get(f"/images/{rel}").content == photo.read_bytes()
        finally:
            main._ref_sidecar(rel).unlink()
            photo.unlink()

    def test_the_cache_directory_is_not_served(self, client):
        from app import main
        assert client.get("/images/.wm/parts/anything.jpg").status_code == 404
        assert client.get(f"/images/.wm/{main.WM_CACHE.name}/parts/x.jpg").status_code == 404

    def test_the_cache_is_keyed_on_the_mark_s_parameters(self):
        """A cached copy is otherwise only rebuilt when its source photo changes,
        so changing the size used to leave every existing watermark at the old one.
        The parameters are in the directory name, so a change misses the cache."""
        from app import main
        assert main.WM_CACHE.parent.name == ".wm"
        assert str(main.WM_SCALE) in main.WM_CACHE.name
        assert str(main.WM_MIN_PX) in main.WM_CACHE.name

    def test_the_cache_is_keyed_on_the_compositing_too(self):
        """Changing how the copy is made, rather than the numbers it is made with,
        also has to miss the old cache -- baking in the orientation did."""
        from app import main
        assert f"b{main.WM_BUILD}" in main.WM_CACHE.name


class TestAPhotoLyingOnItsSide:
    """A phone writes the pixels landscape and says "turn me" in an EXIF tag. The
    served copy is re-encoded without that tag, so the turn has to be applied before
    it is written. Left off, the photo was shown on its side -- and a crop dragged on
    that view was mapped onto the upright original, keeping a different region of the
    photo altogether: off centre, and the wrong shape.
    """

    ORIENT = 6      # "turn 90° clockwise to view"
    SIZE = (1200, 900)   # landscape pixels, so it should be served 900x1200

    def upload(self, client, aid):
        import io

        from PIL import Image, ImageDraw
        im = Image.new("RGB", self.SIZE, (40, 40, 50))
        d = ImageDraw.Draw(im)
        d.rectangle([0, 0, 300, 220], fill=(220, 60, 60))
        exif = im.getexif()
        exif[274] = self.ORIENT
        buf = io.BytesIO()
        im.save(buf, "JPEG", quality=90, exif=exif)
        buf.seek(0)
        client.post(f"/parts/{aid}/photo",
                    files={"photos": ("phone.jpeg", buf, "image/jpeg")},
                    follow_redirects=False)
        return f"parts/{aid}.jpeg"

    def served(self, client, rel):
        import io

        from PIL import Image
        return Image.open(io.BytesIO(client.get(f"/images/{rel}").content))

    def test_it_arrives_the_way_up_it_should_be_seen(self, client, part):
        aid = part()["asset_id"]
        rel = self.upload(client, aid)
        assert self.served(client, rel).size == (self.SIZE[1], self.SIZE[0])

    def test_a_crop_keeps_the_region_it_was_dragged_over(self, client, part):
        """The box arrives as fractions of the photo as displayed, so it has to land
        on the same way up that the serving path produced. Deliberately off centre:
        a centred box stays centred even when the two disagree, and hides this."""
        from PIL import Image

        from app import main
        aid = part()["asset_id"]
        rel = self.upload(client, aid)
        sw, sh = self.served(client, rel).size
        x, y, w, h = 0.10, 0.55, 0.40, 0.30
        client.post(f"/parts/{aid}/photo-crop",
                    data={"image": rel, "x": x, "y": y, "w": w, "h": h},
                    follow_redirects=False)
        # Rounded the way the crop rounds, from the size the browser was given.
        want = (round((x + w) * sw) - round(x * sw),
                round((y + h) * sh) - round(y * sh))
        with Image.open(main.IMAGES_DIR / rel) as out:
            assert out.size == want

    def test_a_preview_is_told_the_size_that_will_arrive(self, client, part):
        """The og:image dimensions let a link preview lay the image out without
        fetching it, so they have to describe the copy that is actually served."""
        from app import main
        aid = part()["asset_id"]
        self.upload(client, aid)
        assert main._image_size(f"parts/{aid}.jpeg") == (self.SIZE[1], self.SIZE[0])


class TestStartingFromAnExistingPart:
    """Entering a make and model already in the collection usually means a second
    of the same thing, so the form offers to start from it.

    This is the duplicate button's copy semantics moved earlier: nothing is saved
    until the form is submitted, so it can be corrected first.
    """

    def test_the_form_offers_the_makers_already_recorded(self, client, part):
        part(manufacturer="Tseng", model="ET4000")
        part(manufacturer="Adaptec", model="AHA-1542CF")
        page = client.get("/parts/new").text
        assert '<datalist id="dl_makes">' in page
        assert 'value="Tseng"' in page and 'value="Adaptec"' in page

    def test_the_models_already_recorded_are_offered_too(self, client, part):
        part(manufacturer="Tseng", model="ET4000")
        assert 'value="ET4000"' in client.get("/parts/new").text

    def test_a_make_and_model_pair_is_matchable_with_its_asset_id(self, client, part):
        aid = part(type="video", manufacturer="Tseng", model="ET4000")["asset_id"]
        page = client.get("/parts/new").text
        assert '"m": "Tseng"' in page and '"d": "ET4000"' in page
        assert f'"id": "{aid}"' in page

    def test_starting_from_a_part_fills_in_what_describes_the_model(self, client, part):
        src = part(type="video", manufacturer="Tseng", model="ET4000", year=1993,
                   specs="Chip: ET4000 | Interface: VLB")
        page = client.get(f"/parts/new?from={src['asset_id']}").text
        assert 'value="Tseng"' in page and 'value="ET4000"' in page
        assert 'value="1993"' in page
        assert 'value="ET4000"' in page and "VLB" in page

    def test_the_prefilled_form_creates_rather_than_edits(self, client, part):
        """The source must not be overwritten: the form posts to /parts/new."""
        src = part(type="video", manufacturer="Tseng", model="ET4000")
        page = client.get(f"/parts/new?from={src['asset_id']}").text
        form = page[page.index('<form class="edit"'):]
        assert 'action="/parts/new"' in form[:200]
        assert f"/parts/{src['asset_id']}/edit" not in form[:200]

    def test_it_says_where_the_values_came_from(self, client, part):
        src = part(manufacturer="Tseng", model="ET4000")
        page = client.get(f"/parts/new?from={src['asset_id']}").text
        assert "Started from" in page and src["asset_id"] in page

    def test_nothing_of_the_original_object_is_offered(self, client, part):
        src = part(manufacturer="Tseng", model="ET4000", source="eBay",
                   acquired_date="2026-01-05", notes="a bit bent")
        page = client.get(f"/parts/new?from={src['asset_id']}").text
        assert 'value="eBay"' not in page
        assert "2026-01-05" not in page
        assert "a bit bent" not in page

    def test_opening_the_prefilled_form_changes_nothing(self, client, part):
        src = part(type="video", manufacturer="Tseng", model="ET4000")
        before = client.get(f"/api/parts/{src['asset_id']}").json()
        client.get(f"/parts/new?from={src['asset_id']}")
        assert client.get(f"/api/parts/{src['asset_id']}").json() == before

    def test_the_type_follows_the_part_it_started_from(self, client, part):
        src = part(type="sound", manufacturer="Creative", model="CT2830")
        page = client.get(f"/parts/new?from={src['asset_id']}").text
        assert '<option value="sound" selected>' in page

    def test_a_stale_link_gives_a_blank_form_rather_than_an_error(self, client):
        r = client.get("/parts/new?from=RH-NOPE")
        assert r.status_code == 200
        assert "Started from" not in r.text

    def test_it_keeps_the_machine_the_part_is_being_added_to(self, client, part,
                                                            computer):
        cid = computer()["asset_id"]
        src = part(type="video", manufacturer="Tseng", model="ET4000")
        page = client.get(f"/parts/new?from={src['asset_id']}&computer_id={cid}").text
        assert f'name="computer_id" value="{cid}"' in page


class TestTheNumbersPage:
    """A public page of figures about the collection.

    Everything is counted from typed columns and child tables, so the page cannot
    disagree with what the database sorts on.
    """

    def test_it_is_public(self, client, computer):
        computer()
        assert client.get("/stats").status_code == 200

    def test_it_renders_with_nothing_in_the_register(self, client):
        """A fresh install is a real state, and several figures are ratios: the
        page must not divide by zero on day one."""
        r = client.get("/stats")
        assert r.status_code == 200
        assert '<div class="n"><a href="/browse?f=all">0</a></div>' in r.text

    def test_the_headline_counts_everything(self, client, computer, part):
        computer()
        computer()
        part()
        page = client.get("/stats").text
        assert '<div class="n"><a href="/browse?f=all">3</a></div>' in page
        assert "2 machines</a> and" in page and "1 parts</a>" in page

    def test_the_top_maker_is_the_one_with_most_parts(self, client, part):
        for i in range(3):
            part(manufacturer="IBM", model=f"x{i}")
        part(manufacturer="Amstrad", model="y")
        page = client.get("/stats").text
        assert "Most represented maker" in page and "IBM" in page

    def test_bars_are_scaled_to_the_largest_value(self, client, part):
        for i in range(4):
            part(type="video", manufacturer="Tseng", model=f"ET400{i}")
        part(type="sound", manufacturer="Creative", model="CT2830")
        page = client.get("/stats").text
        assert "width: 100.0%" in page
        assert "width: 25.0%" in page

    def test_memory_totals_come_from_the_typed_column(self, client, computer):
        aid = computer()["asset_id"]
        client.patch(f"/api/computers/{aid}", json={"installed_ram": "8MB"})
        assert "8 MB" in client.get("/stats").text

    def test_the_traffic_report_is_still_private(self, client, monkeypatch):
        from app import main
        monkeypatch.setattr(main, "AUTH_ENABLED", True)
        r = client.get("/traffic", follow_redirects=False)
        assert r.status_code == 303 and "/login" in r.headers["location"]

    def test_it_is_offered_to_search_engines(self, client):
        assert "/stats</loc>" in client.get("/sitemap.xml").text
        robots = client.get("/robots.txt").text
        assert "Disallow: /traffic" in robots
        assert "Disallow: /stats" not in robots


class TestFollowingAFigureToItsItems:
    """Every figure on /stats links to /browse, which shows the items it counted.

    The tiles were dead ends before: the page could say eleven parts were made by
    IBM and give no way to see which eleven.
    """

    @staticmethod
    def _offered(page):
        """Every /browse link the page renders."""
        return sorted(set(re.findall(r'href="(/browse\?[^"]*)"', page)))

    @staticmethod
    def _cards(page):
        """The asset ids of the cards in the grid."""
        return [href.rsplit("/", 1)[1]
                for href in re.findall(r'class="card" href="([^"]+)"', page)]

    def _a_bit_of_everything(self, client, computer, part):
        """One machine with memory, chips and drives, and parts with the child rows
        the aggregate figures are summed from, so every tile renders."""
        c = computer(year=1991, condition="Working", acquired_date="2026-05-01",
                     drives='2x 5.25" 360K; 1x Gotek 1.44MB')
        client.post(f"/computers/{c['asset_id']}/edit",
                    data={"ramchip:41256": "18"}, follow_redirects=False)
        part(computer_id=c["asset_id"], type="motherboard", manufacturer="IBM",
             model="Planar", year=1988, condition="Working",
             specs="Form factor: AT | Slots: 8× 8-bit ISA | Ports: DIN keyboard")
        part(type="storage", manufacturer="SanDisk", model="CF card", year=1999,
             specs="Kind: CF | Capacity: 4GB")
        return c

    def test_every_figure_on_the_page_leads_somewhere_real(self, client, computer,
                                                           part):
        """A sweep of the whole page. A filter name misspelt in one tile would
        otherwise stay hidden until someone clicked that one tile."""
        self._a_bit_of_everything(client, computer, part)
        offered = self._offered(client.get("/stats").text)
        # Every tile, both ends of the hero, and every bar in the ranked lists.
        assert len(offered) > 15
        for href in offered:
            assert client.get(href).status_code == 200, href

    def test_a_maker_leads_to_that_maker_s_parts(self, client, part):
        mine = {part(manufacturer="IBM", model=f"x{i}")["asset_id"] for i in range(3)}
        part(manufacturer="Amstrad", model="y")
        page = client.get("/browse?f=maker&v=IBM").text
        assert set(self._cards(page)) == mine
        assert "3 computers · 0 parts" not in page and "0 computers · 3 parts" in page

    def test_a_category_leads_to_the_parts_in_it(self, client, part):
        card = part(type="video", model="ET4000")["asset_id"]
        part(type="sound", model="CT2830")
        assert self._cards(client.get("/browse?f=type&v=video").text) == [card]

    def test_the_best_equipped_machine_leads_to_the_parts_in_it(self, client,
                                                                computer, part):
        cid = computer()["asset_id"]
        fitted = part(computer_id=cid, model="fitted")["asset_id"]
        part(model="spare")
        page = client.get(f"/browse?f=in&v={cid}").text
        assert self._cards(page) == [fitted]
        # The machine itself stays one click away, named rather than an asset id.
        assert f'href="/computers/{cid}"' in page

    def test_the_disposed_count_shows_the_disposed_items(self, client, part):
        """The gallery hides disposed items unless asked; a page reached from the
        figure that counted them must not, or it contradicts the number clicked."""
        aid = part(model="gone")["asset_id"]
        client.patch(f"/api/parts/{aid}", json={"disposed": True})
        page = client.get("/browse?f=disposed").text
        assert self._cards(page) == [aid]
        assert 'id="showdisposed" checked>' in page

    def test_the_gallery_itself_still_hides_them(self, client, part):
        client.patch(f"/api/parts/{part(model='gone')['asset_id']}",
                     json={"disposed": True})
        assert 'id="showdisposed">' in client.get("/").text

    def test_an_unknown_view_is_a_404(self, client):
        assert client.get("/browse?f=nonsense").status_code == 404
        assert client.get("/browse").status_code == 404

    def test_a_view_of_a_machine_that_is_gone_is_a_404(self, client):
        assert client.get("/browse?f=in&v=RH-NOPE").status_code == 404

    def test_it_is_public_like_the_figures_it_came_from(self, client, monkeypatch):
        from app import main
        monkeypatch.setattr(main, "AUTH_ENABLED", True)
        r = client.get("/browse?f=all", follow_redirects=False)
        assert r.status_code == 200

    def test_it_is_kept_out_of_the_search_index(self, client):
        """Filtered slices of the gallery are not pages worth indexing; the items in
        them already have their own."""
        assert "Disallow: /browse" in client.get("/robots.txt").text
        assert 'content="noindex, follow"' in client.get("/browse?f=all").text


class TestSearchTerms:
    """A query is the set of things that must all appear."""

    def test_words_are_separate_terms(self):
        from app.main import search_terms
        assert search_terms("amstrad faulty") == ["amstrad", "faulty"]

    def test_case_and_spacing_do_not_matter(self):
        from app.main import search_terms
        assert search_terms("  AMSTRAD   PC1640 ") == ["amstrad", "pc1640"]

    def test_a_quoted_run_is_one_term(self):
        from app.main import search_terms
        assert search_terms('"etherlink iii"') == ["etherlink iii"]

    def test_quoted_and_bare_terms_mix(self):
        from app.main import search_terms
        assert search_terms('ibm "16-bit isa"') == ["ibm", "16-bit isa"]

    def test_an_empty_query_asks_for_nothing(self):
        from app.main import search_terms
        assert search_terms("") == [] and search_terms("   ") == []


class TestSearchingEveryField:
    """The point of the server-side search: a word anywhere about an item finds it,
    including the fields too bulky to ship to the browser for instant filtering."""

    def test_no_query_shows_everything(self, client, computer, part):
        computer()
        part()
        page = client.get("/").text
        assert page.count('class="card"') == 2
        assert "Searched every field" not in page

    def test_a_word_only_in_the_notes(self, client, part):
        aid = part(model="Widget", notes="battery damage on the corner")["asset_id"]
        part(model="Other")
        page = client.get("/?q=battery").text
        assert aid in page
        assert 'class="card"' in page and page.count('class="card"') == 1

    def test_a_word_only_in_the_summary(self, client, computer):
        aid = computer(model="Portable", summary="A luggable machine of its day")["asset_id"]
        computer(model="Desktop")
        page = client.get("/?q=luggable").text
        assert aid in page and page.count('class="card"') == 1

    def test_a_word_only_in_the_history(self, client, part):
        aid = part(model="Widget")["asset_id"]
        client.post(f"/parts/{aid}/note", data={"message": "recapped the lot"},
                    follow_redirects=False)
        part(model="Other")
        page = client.get("/?q=recapped").text
        assert aid in page and page.count('class="card"') == 1

    def test_a_word_only_in_the_specs(self, client, part):
        aid = part(type="video", specs="Chip: ET4000 | Interface: VLB")["asset_id"]
        part(type="sound")
        assert client.get("/?q=et4000").text.count('class="card"') == 1
        assert aid in client.get("/?q=et4000").text

    def test_every_term_must_appear_somewhere(self, client, part):
        """The words may be in different fields -- maker in one, condition in
        another -- which is what makes it a search rather than a phrase match."""
        wanted = part(manufacturer="Amstrad", model="A", condition="Faulty")["asset_id"]
        part(manufacturer="Amstrad", model="B", condition="Working")
        part(manufacturer="IBM", model="C", condition="Faulty")
        page = client.get("/?q=amstrad+faulty").text
        assert wanted in page and page.count('class="card"') == 1

    def test_a_quoted_phrase_must_be_contiguous(self, client, part):
        run = part(model="Etherlink III combo")["asset_id"]
        part(model="Etherlink", name="III elsewhere in the record")
        page = client.get('/?q=%22etherlink+iii%22').text
        assert run in page and page.count('class="card"') == 1

    def test_nothing_matching_says_so(self, client, part):
        part()
        page = client.get("/?q=zzzznotathing").text
        assert page.count('class="card"') == 0
        assert "Searched every field" in page

    def test_it_reports_what_it_searched(self, client, computer, part):
        computer()
        part()
        page = client.get("/?q=nothinghere").text
        assert "all\n  2 items" in page or "2 items" in page

    def test_the_browser_is_told_what_the_server_matched(self, client, part):
        """Otherwise the instant filter would hide rows that matched on a field the
        browser's own copy does not carry."""
        part(notes="battery damage")
        page = client.get("/?q=battery").text
        assert 'const serverQuery = "battery"' in page
        card = page[page.index('<a class="card"'):]
        assert "battery" not in card[:card.index("</a>")]

    def test_searching_is_public(self, client, part, monkeypatch):
        from app import main
        part(notes="battery damage")
        monkeypatch.setattr(main, "AUTH_ENABLED", True)
        assert client.get("/?q=battery").status_code == 200


class TestTheBigPhotoView:
    """The big view is also the editor when logged in, so a run of corrections does
    not mean a round trip through the item page between each one."""

    @staticmethod
    def upload(client, kind, aid, size=(900, 600)):
        import io
        from PIL import Image
        buf = io.BytesIO()
        Image.new("RGB", size, (120, 90, 60)).save(buf, "JPEG", quality=92)
        buf.seek(0)
        client.post(f"/{kind}/{aid}/photo",
                    files={"photos": (f"{aid}.jpg", buf, "image/jpeg")},
                    follow_redirects=False)
        return f"{kind}/{aid}.jpg"

    @staticmethod
    def served_size(client, rel):
        import io
        from PIL import Image
        return Image.open(io.BytesIO(client.get(f"/images/{rel}").content)).size

    def test_each_photo_says_where_it_lives(self, client, part):
        """One toolbar in the overlay serves every photo, so each carries its own
        item and filename."""
        aid = part()["asset_id"]
        rel = self.upload(client, "parts", aid)
        try:
            page = client.get(f"/parts/{aid}").text
            assert f'data-kind="parts" data-aid="{aid}" data-rel="{rel}"' in page
        finally:
            client.post(f"/parts/{aid}/photo-delete", data={"image": rel},
                        follow_redirects=False)

    def test_the_editing_tools_are_only_for_the_logged_in(self, client, part,
                                                          monkeypatch):
        from app import main
        aid = part()["asset_id"]
        rel = self.upload(client, "parts", aid)
        try:
            assert 'id="lb-tools"' in client.get(f"/parts/{aid}").text
            monkeypatch.setattr(main, "AUTH_ENABLED", True)
            anon = client.get(f"/parts/{aid}").text
            assert 'id="lb-tools"' not in anon
            assert "zoomable" in anon
        finally:
            monkeypatch.setattr(main, "AUTH_ENABLED", False)
            client.post(f"/parts/{aid}/photo-delete", data={"image": rel},
                        follow_redirects=False)

    def test_the_old_editor_page_opens_the_big_view_instead(self, client, part):
        """It was its own page; keeping the link working means one crop
        implementation rather than two."""
        aid = part()["asset_id"]
        r = client.get(f"/parts/{aid}/edit-photo?image=parts%2F{aid}.jpg",
                       follow_redirects=False)
        assert r.status_code == 303
        assert r.headers["location"] == f"/parts/{aid}?photo=parts/{aid}.jpg"

    def test_rotating_from_the_view_returns_to_the_same_photo(self, client, part):
        aid = part()["asset_id"]
        rel = self.upload(client, "parts", aid)
        back = f"/parts/{aid}?photo={rel}"
        try:
            assert self.served_size(client, rel) == (900, 600)
            r = client.post(f"/parts/{aid}/photo-rotate",
                            data={"image": rel, "dir": "cw", "next": back},
                            follow_redirects=False)
            assert r.status_code == 303 and r.headers["location"] == back
            assert self.served_size(client, rel) == (600, 900)
        finally:
            client.post(f"/parts/{aid}/photo-delete", data={"image": rel},
                        follow_redirects=False)

    def test_cropping_from_the_view_returns_to_the_same_photo(self, client, part):
        aid = part()["asset_id"]
        rel = self.upload(client, "parts", aid)
        back = f"/parts/{aid}?photo={rel}"
        try:
            r = client.post(f"/parts/{aid}/photo-crop",
                            data={"image": rel, "x": "0.25", "y": "0.25",
                                  "w": "0.5", "h": "0.5", "next": back},
                            follow_redirects=False)
            assert r.status_code == 303 and r.headers["location"] == back
            assert self.served_size(client, rel) == (450, 300)
        finally:
            client.post(f"/parts/{aid}/photo-delete", data={"image": rel},
                        follow_redirects=False)

    def test_a_nonsense_crop_box_is_refused(self, client, part):
        aid = part()["asset_id"]
        rel = self.upload(client, "parts", aid)
        try:
            r = client.post(f"/parts/{aid}/photo-crop",
                            data={"image": rel, "x": "a", "y": "b", "w": "c", "h": "d"},
                            follow_redirects=False)
            assert r.status_code == 400
        finally:
            client.post(f"/parts/{aid}/photo-delete", data={"image": rel},
                        follow_redirects=False)

    def test_an_edit_is_recorded_in_the_history(self, client, part):
        aid = part()["asset_id"]
        rel = self.upload(client, "parts", aid)
        try:
            client.post(f"/parts/{aid}/photo-rotate", data={"image": rel, "dir": "ccw"},
                        follow_redirects=False)
            messages = [e["message"] for e in client.get(f"/api/items/{aid}/log").json()]
            assert "rotated a photo" in messages
        finally:
            client.post(f"/parts/{aid}/photo-delete", data={"image": rel},
                        follow_redirects=False)

    def test_one_mode_of_the_toolbar_at_a_time(self, client, part):
        """crop swaps its button for an apply/cancel form using the hidden
        attribute, and author rules that set display outrank the browser's
        `[hidden] { display: none }` -- which showed every control at once whatever
        mode it was in, and later left the upload button on screen too. One rule
        answers both, so it has to stay in the stylesheet."""
        page = client.get(f"/parts/{part()['asset_id']}").text
        assert "[hidden] { display: none !important; }" in page

    def test_there_is_no_separate_button_to_open_the_view(self, client, part):
        """The photo is the way in: a button beside it did nothing that clicking it
        does not. It is focusable so the keyboard has a way in as well."""
        aid = part()["asset_id"]
        rel = self.upload(client, "parts", aid)
        try:
            page = client.get(f"/parts/{aid}").text
            assert "rotate or crop" not in page
            assert f'?photo=parts%2F{aid}' not in page
            assert 'tabindex="0" role="button"' in page
        finally:
            client.post(f"/parts/{aid}/photo-delete", data={"image": rel},
                        follow_redirects=False)
