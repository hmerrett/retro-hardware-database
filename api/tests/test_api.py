"""End-to-end behaviour through the REST API and the GUI forms.

Weighted towards the things that have actually broken: typed columns rejecting or
silently eating form input, a select with no option for the value it holds, links
left pointing at deleted rows, and derived strings being written to directly.
"""
from datetime import date


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

    def test_routing_a_floppy_creates_no_part(self, client, computer):
        aid = computer()["asset_id"]
        client.post("/parts/new",
                    data={"type": "storage", "computer_id": aid,
                          "kind": "Floppy/Gotek", "drive_desc": "1x 3.5in 1.44MB"},
                    follow_redirects=False)
        assert client.get("/api/parts", params={"computer_id": aid}).json() == []


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
