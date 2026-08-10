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


def dispose(client, kind, aid, note="binned"):
    client.post(f"/{kind}/{aid}/dispose", data={"note": note},
                follow_redirects=False)


def photo_for(kind, aid, name=None):
    """A stored photo, as an upload would leave it."""
    from PIL import Image

    from app import main
    path = main.IMAGES_DIR / kind / (name or f"{aid}.jpg")
    path.parent.mkdir(parents=True, exist_ok=True)
    Image.new("RGB", (60, 40), (90, 110, 130)).save(path, "JPEG")
    return path


class TestDeletingIsOnlyForWhatIsAlreadyDisposed:
    """Disposal is reversible and deletion is not, so the reversible step is a
    precondition of the other: nothing can be deleted that has not already been
    marked as gone once, deliberately, on an earlier day."""

    def test_the_item_page_offers_it_once_disposed(self, client, part):
        aid = part()["asset_id"]
        assert f"/parts/{aid}/delete" not in client.get(f"/parts/{aid}").text
        dispose(client, "parts", aid)
        assert f"/parts/{aid}/delete" in client.get(f"/parts/{aid}").text

    @pytest.mark.parametrize("kind", ["computers", "parts"])
    def test_the_confirmation_refuses_an_item_still_held(self, client, computer,
                                                         part, kind):
        aid = (computer() if kind == "computers" else part())["asset_id"]
        assert client.get(f"/{kind}/{aid}/delete").status_code == 400

    def test_and_so_does_the_delete_itself(self, client, part):
        """Not only the page that leads to it: a form posted at a restored item
        must not go through on the strength of having once been offered."""
        aid = part()["asset_id"]
        url = f"http://testserver/parts/{aid}"
        assert client.post(f"/parts/{aid}/delete", data={"confirm": url},
                           follow_redirects=False).status_code == 400
        assert client.get(f"/api/parts/{aid}").status_code == 200


class TestTheDeleteConfirmation:
    """The safety net: the item's own URL, pasted, so that deleting the wrong
    thing takes a deliberate act rather than a stray click."""

    def setup_part(self, client, part):
        aid = part()["asset_id"]
        dispose(client, "parts", aid)
        return aid

    def test_the_right_url_deletes_it(self, client, part):
        aid = self.setup_part(client, part)
        r = client.post(f"/parts/{aid}/delete",
                        data={"confirm": f"http://testserver/parts/{aid}"},
                        follow_redirects=False)
        assert r.status_code == 303
        assert client.get(f"/api/parts/{aid}").status_code == 404

    @pytest.mark.parametrize("typed", ["", "yes", "delete", "/parts/RH-9999",
                                       "http://testserver/parts/",
                                       "http://testserver/computers/{aid}"])
    def test_anything_else_deletes_nothing(self, client, part, typed):
        aid = self.setup_part(client, part)
        r = client.post(f"/parts/{aid}/delete",
                        data={"confirm": typed.format(aid=aid)},
                        follow_redirects=False)
        assert r.status_code == 400
        assert client.get(f"/api/parts/{aid}").status_code == 200
        assert "not this item&#39;s URL" in r.text

    def test_the_bare_path_is_enough(self, client, part):
        """Pasting from the address bar is the expected act, but the host is not
        the part that identifies anything -- the asset id is."""
        aid = self.setup_part(client, part)
        assert client.post(f"/parts/{aid}/delete", data={"confirm": f"/parts/{aid}"},
                           follow_redirects=False).status_code == 303

    @pytest.mark.parametrize("typed", ["http://db.2600.me/parts/{aid}",
                                       "http://testserver/parts/{aid}/",
                                       "http://testserver/parts/{aid}?from=gallery",
                                       "  http://testserver/parts/{aid}  "])
    def test_and_so_is_a_paste_that_travelled(self, client, part, typed):
        """Another host, a trailing slash, a query the gallery added, whitespace a
        copy picked up: all the same act of fetching the thing's identity."""
        aid = self.setup_part(client, part)
        assert client.post(f"/parts/{aid}/delete",
                           data={"confirm": typed.format(aid=aid)},
                           follow_redirects=False).status_code == 303

    def test_the_page_shows_the_url_to_paste(self, client, part):
        aid = self.setup_part(client, part)
        assert f"/parts/{aid}</code>" in client.get(f"/parts/{aid}/delete").text


class TestADeleteTakesEverythingWithIt:
    """What the confirmation page promises is what the delete does: no rows left
    filed under an asset id that no longer exists, and no photos left on disk."""

    def test_the_rows_filed_under_it_go(self, client, part, db):
        from app.models import LogEntry, StorageSpec
        aid = part(type="storage", specs="Capacity: 40 MB")["asset_id"]
        assert db.query(StorageSpec).filter_by(part_id=aid).count() == 1
        dispose(client, "parts", aid)
        client.post(f"/parts/{aid}/delete", data={"confirm": f"/parts/{aid}"},
                    follow_redirects=False)
        db.expire_all()
        assert db.query(StorageSpec).filter_by(part_id=aid).count() == 0
        assert db.query(LogEntry).filter_by(asset_id=aid).count() == 0

    def test_the_photos_go_from_disk(self, client, part):
        from app import main
        aid = part()["asset_id"]
        primary, extra = photo_for("parts", aid), photo_for("parts", aid, f"{aid}-2.jpg")
        sidecar = main._ref_sidecar(f"parts/{aid}-2.jpg")
        sidecar.write_text("https://example.test/listing")
        client.get(f"/images/parts/{aid}.jpg")  # so there is a watermark cached
        cached = main.WM_CACHE / "parts" / f"{aid}.jpg"
        assert cached.exists()
        dispose(client, "parts", aid)
        client.post(f"/parts/{aid}/delete", data={"confirm": f"/parts/{aid}"},
                    follow_redirects=False)
        assert not primary.exists() and not extra.exists()
        assert not sidecar.exists(), "a reference marker outlived its photo"
        assert not cached.exists(), "a watermark cached under a freed name"

    def test_a_machines_drive_and_memory_rows_go(self, client, computer, db):
        from app.models import ComputerDrive, ComputerRamModule
        aid = computer()["asset_id"]
        client.post(f"/computers/{aid}/edit",
                    data={"drive0_kind": "floppy", "drive0_form_factor": '3.5"',
                          "drive0_size": "1.44MB", "drive0_count": "1",
                          "rammod:30p1m": "4"}, follow_redirects=False)
        assert db.query(ComputerDrive).filter_by(computer_id=aid).count() == 1
        assert db.query(ComputerRamModule).filter_by(computer_id=aid).count() == 1
        dispose(client, "computers", aid)
        client.post(f"/computers/{aid}/delete",
                    data={"confirm": f"/computers/{aid}"}, follow_redirects=False)
        db.expire_all()
        assert db.query(ComputerDrive).filter_by(computer_id=aid).count() == 0
        assert db.query(ComputerRamModule).filter_by(computer_id=aid).count() == 0

    def test_the_json_api_cleans_up_the_same_way(self, client, part, db):
        """The MCP server and the command-line tools delete through here, and used
        to leave the photos behind on disk."""
        from app.models import StorageSpec
        aid = part(type="storage", specs="Capacity: 40 MB")["asset_id"]
        photo = photo_for("parts", aid)
        assert client.delete(f"/api/parts/{aid}").json()["photos"] == 1
        db.expire_all()
        assert not photo.exists()
        assert db.query(StorageSpec).filter_by(part_id=aid).count() == 0


class TestWhatALinkedItemIsToldWhenItsHostGoes:
    """Removing the references first is the point: nothing is left pointing at an
    asset id that has stopped existing, and what survives says in its own history
    why it is suddenly standing on its own."""

    def test_a_part_in_a_deleted_machine_is_kept_and_unlinked(self, client,
                                                              computer, part):
        cid = computer()["asset_id"]
        pid = part(computer_id=cid)["asset_id"]
        dispose(client, "computers", cid)
        client.post(f"/computers/{cid}/delete",
                    data={"confirm": f"/computers/{cid}"}, follow_redirects=False)
        p = client.get(f"/api/parts/{pid}").json()
        assert p["computer_id"] is None
        assert any(cid in e["message"] for e in
                   client.get(f"/api/items/{pid}/log").json())

    def test_a_part_mounted_on_a_deleted_part_is_kept_and_unlinked(self, client,
                                                                   part):
        card = part(type="io")["asset_id"]
        disk = part(type="storage", parent_id=card)["asset_id"]
        dispose(client, "parts", card)
        client.post(f"/parts/{card}/delete", data={"confirm": f"/parts/{card}"},
                    follow_redirects=False)
        assert client.get(f"/api/parts/{disk}").json()["parent_id"] is None

    def test_the_tick_deletes_the_parts_that_went_with_it(self, client, computer,
                                                          part):
        cid = computer()["asset_id"]
        pid = part(computer_id=cid)["asset_id"]
        dispose(client, "computers", cid)  # takes the part with it
        client.post(f"/computers/{cid}/delete",
                    data={"confirm": f"/computers/{cid}", "with_parts": "1"},
                    follow_redirects=False)
        assert client.get(f"/api/parts/{pid}").status_code == 404

    def test_without_the_tick_they_stay(self, client, computer, part):
        cid = computer()["asset_id"]
        pid = part(computer_id=cid)["asset_id"]
        dispose(client, "computers", cid)
        client.post(f"/computers/{cid}/delete",
                    data={"confirm": f"/computers/{cid}"}, follow_redirects=False)
        assert client.get(f"/api/parts/{pid}").status_code == 200

    def test_the_tick_follows_the_whole_tree(self, client, computer, part):
        """A disk on a controller carries the card's id, not the machine's. It went
        to the tip when the machine was disposed, so it goes when the machine is
        deleted -- following computer_id alone would leave it behind."""
        cid = computer()["asset_id"]
        card = part(type="io", computer_id=cid)["asset_id"]
        disk = part(type="storage", parent_id=card)["asset_id"]
        dispose(client, "computers", cid)
        page = client.get(f"/computers/{cid}/delete").text
        assert "<strong>2</strong> parts in it" in " ".join(page.split())
        client.post(f"/computers/{cid}/delete",
                    data={"confirm": f"/computers/{cid}", "with_parts": "1"},
                    follow_redirects=False)
        assert client.get(f"/api/parts/{card}").status_code == 404
        assert client.get(f"/api/parts/{disk}").status_code == 404

    def test_a_held_part_deep_in_the_tree_is_unlinked_not_deleted(self, client,
                                                                  computer, part):
        """The disk was restored on its own, so it stays -- and must not be left
        pointing at the controller card that went."""
        cid = computer()["asset_id"]
        card = part(type="io", computer_id=cid)["asset_id"]
        disk = part(type="storage", parent_id=card)["asset_id"]
        dispose(client, "computers", cid)
        client.post(f"/parts/{disk}/restore", follow_redirects=False)
        client.post(f"/computers/{cid}/delete",
                    data={"confirm": f"/computers/{cid}", "with_parts": "1"},
                    follow_redirects=False)
        assert client.get(f"/api/parts/{card}").status_code == 404
        d = client.get(f"/api/parts/{disk}").json()
        assert d["parent_id"] is None and d["computer_id"] is None
        assert any(card in e["message"] for e in
                   client.get(f"/api/items/{disk}/log").json())

    def test_a_part_still_held_survives_the_tick(self, client, computer, part):
        """A part restored on its own, or fitted after the machine went, is still in
        the collection. The tick deletes what went to the tip, not the shelf."""
        cid = computer()["asset_id"]
        gone = part(computer_id=cid)["asset_id"]
        kept = part(computer_id=cid)["asset_id"]
        dispose(client, "computers", cid)
        client.post(f"/parts/{kept}/restore", follow_redirects=False)
        client.post(f"/computers/{cid}/delete",
                    data={"confirm": f"/computers/{cid}", "with_parts": "1"},
                    follow_redirects=False)
        assert client.get(f"/api/parts/{gone}").status_code == 404
        assert client.get(f"/api/parts/{kept}").json()["computer_id"] is None

    def test_a_deleted_part_leaves_no_history_behind_it(self, client, computer,
                                                        part, db):
        """The parts deleted alongside the machine take their own history with
        them, and are not told they came out of something on the way out."""
        from app.models import LogEntry
        cid = computer()["asset_id"]
        pid = part(computer_id=cid)["asset_id"]
        dispose(client, "computers", cid)
        client.post(f"/computers/{cid}/delete",
                    data={"confirm": f"/computers/{cid}", "with_parts": "1"},
                    follow_redirects=False)
        db.expire_all()
        assert db.query(LogEntry).filter(LogEntry.asset_id.in_([cid, pid])).count() == 0


class TestTheConfirmationPageSaysWhatWillGo:
    """The page is the only warning there is, so its figures come from the same
    queries the delete runs rather than from a guess."""

    def test_it_counts_the_photos_and_the_history(self, client, part):
        aid = part()["asset_id"]
        photo_for("parts", aid)
        photo_for("parts", aid, f"{aid}-2.jpg")
        client.post(f"/parts/{aid}/note", data={"message": "cleaned the contacts"},
                    follow_redirects=False)
        dispose(client, "parts", aid)
        text = " ".join(client.get(f"/parts/{aid}/delete").text.split())
        assert "<strong>2</strong> photos deleted from disk" in text
        # created, the note, disposed.
        assert "<strong>3</strong> history entries" in text

    def test_it_counts_one_of_a_thing_without_the_s(self, client, part):
        aid = part()["asset_id"]
        photo_for("parts", aid)
        dispose(client, "parts", aid)
        text = " ".join(client.get(f"/parts/{aid}/delete").text.split())
        assert "<strong>1</strong> photo deleted from disk" in text

    @staticmethod
    def going_list(page):
        """Just the list of what will be deleted -- the page says 'photo' in its
        own stylesheet too, so a bare `not in` over the whole thing proves little."""
        body = page.split('<ul class="going">', 1)[1]
        return " ".join(body.split("</ul>", 1)[0].split())

    def test_it_leaves_out_a_line_it_has_no_number_for(self, client, part):
        """A part with no photograph does not get told that no photographs will be
        deleted; the list is what is going, not a form with blanks."""
        aid = part()["asset_id"]
        dispose(client, "parts", aid)
        going = self.going_list(client.get(f"/parts/{aid}/delete").text)
        assert "photo" not in going
        assert "own record" in going, "the list should not be empty either"

    def test_it_offers_the_tick_only_when_there_is_something_to_tick(self, client,
                                                                     computer, part):
        bare = computer()["asset_id"]
        dispose(client, "computers", bare)
        assert 'name="with_parts"' not in client.get(f"/computers/{bare}/delete").text
        full = computer()["asset_id"]
        part(computer_id=full)
        dispose(client, "computers", full)
        assert 'name="with_parts"' in client.get(f"/computers/{full}/delete").text

    def test_it_says_which_parts_it_will_not_touch(self, client, computer, part):
        cid = computer()["asset_id"]
        kept = part(computer_id=cid)["asset_id"]
        dispose(client, "computers", cid)
        client.post(f"/parts/{kept}/restore", follow_redirects=False)
        page = client.get(f"/computers/{cid}/delete").text
        assert "still in the collection and will be kept" in page
        assert kept in page

    def test_a_failed_confirmation_keeps_the_tick(self, client, computer, part):
        cid = computer()["asset_id"]
        part(computer_id=cid)
        dispose(client, "computers", cid)
        r = client.post(f"/computers/{cid}/delete",
                        data={"confirm": "no", "with_parts": "1"},
                        follow_redirects=False)
        assert 'name="with_parts" value="1" checked' in r.text


class TestTheDeleteConfirmationIsNotPublic:
    """Every other editing GET is behind the login; this one lists what would go
    and must not be readable by whoever is passing."""

    def test_a_visitor_is_sent_to_the_login(self, client, part, monkeypatch):
        from app import main
        aid = part()["asset_id"]
        dispose(client, "parts", aid)
        monkeypatch.setattr(main, "AUTH_ENABLED", True)
        r = client.get(f"/parts/{aid}/delete", follow_redirects=False)
        assert r.status_code == 303 and "/login" in r.headers["location"]

    def test_the_item_page_it_hangs_off_is_still_public(self, client, part,
                                                        monkeypatch):
        """Only the confirmation moved behind the login, not the item itself."""
        from app import main
        aid = part()["asset_id"]
        dispose(client, "parts", aid)
        monkeypatch.setattr(main, "AUTH_ENABLED", True)
        assert client.get(f"/parts/{aid}", follow_redirects=False).status_code == 200

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


class TestPickingAFloppySCapacity:
    """The capacity had to be typed into the drive's description and picked back
    out of the prose. It is a short, closed list of designations, so it is offered
    as one -- with a box for the disks the list does not name."""

    def add(self, client, **extra):
        data = {"type": "storage", "kind": "Floppy/Gotek"} | extra
        r = client.post("/parts/new", data=data, follow_redirects=False)
        return r.headers["location"]

    def part(self, client, **extra):
        return self.add(client, **extra).rsplit("/", 1)[-1]

    def specs(self, client, aid):
        return client.get(f"/api/parts/{aid}").json()["specs"]

    def test_the_pick_lands_on_the_machines_drive_row(self, client, computer):
        cid = computer()["asset_id"]
        self.add(client, computer_id=cid, drive_desc='3.5in floppy',
                 drive_size="1.44MB")
        assert "1.44MB" in client.get(f"/api/computers/{cid}").json()["drives"]

    def test_the_picker_wins_over_the_description(self, client, computer):
        """The same rule the bezel menus follow: a pick is a deliberate answer, so
        it beats the same thing said in passing in the prose."""
        cid = computer()["asset_id"]
        self.add(client, computer_id=cid, drive_desc='3.5in 1.44MB floppy',
                 drive_size="720K")
        drives = client.get(f"/api/computers/{cid}").json()["drives"]
        assert "720K" in drives and "1.44MB" not in drives

    def test_picking_nothing_leaves_what_the_description_said(self, client, computer):
        cid = computer()["asset_id"]
        self.add(client, computer_id=cid, drive_desc='3.5in 1.44MB floppy',
                 drive_size="")
        assert "1.44MB" in client.get(f"/api/computers/{cid}").json()["drives"]

    def test_a_drive_kept_as_a_part_records_it_too(self, client):
        aid = self.part(client, drive_desc="3.5in floppy", drive_size="1.44MB")
        assert "Size: 1.44MB" in self.specs(client, aid)

    def test_a_designation_is_not_turned_into_a_byte_count(self, client):
        """1.44MB is 1475 KB only by convention. A RAM 'Size' is a quantity and
        normalises to KB; a disk's is what the disk is called, and must not."""
        aid = self.part(client, drive_desc="3.5in floppy", drive_size="1.44MB")
        specs = self.specs(client, aid)
        assert "1475" not in specs and "KB" not in specs

    def test_a_ram_size_still_normalises(self, client, db):
        """The other half of that guard: only storage is exempt, and a memory
        amount still lands in the KB column that makes it sort and compare."""
        from app.models import RamSpec
        r = client.post("/parts/new", data={"type": "ram", "spec_size": "4MB"},
                        follow_redirects=False)
        aid = r.headers["location"].rsplit("/", 1)[-1]
        assert db.query(RamSpec).filter(RamSpec.part_id == aid).one().size_kb == 4096

    def test_a_floppys_size_is_no_column_at_all(self, client, db):
        """It is not a quantity, so it is not one of storage_spec's typed columns:
        it rides as a plain attribute, the way an unmanaged key does."""
        from app.models import PartAttribute
        aid = self.part(client, drive_desc="3.5in floppy", drive_size="1.44MB")
        rows = {a.akey: a.avalue for a
                in db.query(PartAttribute).filter(PartAttribute.part_id == aid)}
        assert rows.get("Size") == "1.44MB"

    def test_custom_records_what_was_typed(self, client):
        aid = self.part(client, drive_desc="3.5in floppy", drive_size="custom",
                        drive_size_custom="21MB Floptical")
        assert "Size: 21MB Floptical" in self.specs(client, aid)

    def test_custom_with_nothing_typed_records_nothing(self, client):
        aid = self.part(client, drive_desc="3.5in floppy", drive_size="custom",
                        drive_size_custom="   ")
        assert "Size:" not in self.specs(client, aid)

    def test_a_kind_that_takes_no_such_disk_ignores_a_stale_pick(self, client):
        """Choosing 1.44MB and then changing the kind leaves the radio checked and
        off-screen. An optical drive is not a 1.44MB anything."""
        r = client.post("/parts/new",
                        data={"type": "storage", "kind": "Optical",
                              "drive_desc": "Sony CDU55", "drive_size": "1.44MB"},
                        follow_redirects=False)
        aid = r.headers["location"].rsplit("/", 1)[-1]
        assert "Size:" not in self.specs(client, aid)

    def test_a_hard_disk_ignores_it_as_well(self, client):
        r = client.post("/parts/new",
                        data={"type": "storage", "kind": "Hard disk",
                              "spec_capacity": "540 MB", "drive_size": "1.44MB"},
                        follow_redirects=False)
        aid = r.headers["location"].rsplit("/", 1)[-1]
        assert "Size:" not in self.specs(client, aid)

    def test_the_form_opens_on_the_pick_again(self, client):
        aid = self.part(client, drive_desc="3.5in floppy", drive_size="720K")
        flat = " ".join(client.get(f"/parts/{aid}/edit").text.split())
        assert 'value="720K" checked' in flat

    def test_a_custom_one_opens_on_the_box(self, client):
        aid = self.part(client, drive_desc="3.5in floppy", drive_size="custom",
                        drive_size_custom="21MB Floptical")
        page = client.get(f"/parts/{aid}/edit").text
        assert 'id="drive_size_custom"' in page and "21MB Floptical" in page
        # ...and it is the custom radio that is chosen, not one of the standard ones.
        flat = " ".join(page.split())
        assert 'value="custom" checked' in flat

    def test_a_capacity_alone_still_describes_a_floppy(self, client, computer):
        """Picking a capacity and typing no description is an ordinary gesture now
        the picker exists; the kind's menu label must not land in the model."""
        cid = computer()["asset_id"]
        self.add(client, computer_id=cid, drive_size="1.44MB")
        drives = client.get(f"/api/computers/{cid}").json()["drives"]
        assert drives == "1.44MB floppy"

    def test_editing_a_kept_drive_changes_it(self, client):
        aid = self.part(client, drive_desc="3.5in floppy", drive_size="1.44MB")
        client.post(f"/parts/{aid}/edit",
                    data={"type": "storage", "kind": "Floppy/Gotek",
                          "drive_desc": "3.5in floppy", "drive_size": "720K"},
                    follow_redirects=False)
        specs = self.specs(client, aid)
        assert "Size: 720K" in specs and "1.44MB" not in specs


class TestPickingTheBayADriveFits:
    """The form factor, the same way: a closed list of three, offered rather than
    typed. Unlike the capacity it fits every drive that lives on the drives field
    -- an optical drive is 5.25" as surely as a floppy is 3.5"."""

    def add(self, client, kind="Floppy/Gotek", **extra):
        r = client.post("/parts/new",
                        data={"type": "storage", "kind": kind} | extra,
                        follow_redirects=False)
        return r.headers["location"]

    def specs(self, client, aid):
        return client.get(f"/api/parts/{aid}").json()["specs"]

    def test_the_pick_lands_on_the_machines_drive_row(self, client, computer):
        cid = computer()["asset_id"]
        self.add(client, computer_id=cid, drive_desc="floppy", drive_form='3.5"',
                 drive_size="1.44MB")
        assert client.get(f"/api/computers/{cid}").json()["drives"] \
            == '3.5" 1.44MB floppy'

    def test_the_picker_wins_over_the_description(self, client, computer):
        cid = computer()["asset_id"]
        self.add(client, computer_id=cid, drive_desc="5.25in 360K floppy",
                 drive_form='3.5"')
        drives = client.get(f"/api/computers/{cid}").json()["drives"]
        assert '3.5"' in drives and "5.25" not in drives

    def test_picking_nothing_leaves_what_the_description_said(self, client, computer):
        cid = computer()["asset_id"]
        self.add(client, computer_id=cid, drive_desc="5.25in 360K floppy",
                 drive_form="")
        assert '5.25"' in client.get(f"/api/computers/{cid}").json()["drives"]

    def test_an_optical_drive_gets_one_too(self, client):
        """The capacity picker is a floppy's alone; this one is not."""
        aid = self.add(client, kind="Optical", drive_desc="Sony CDU55",
                       drive_form='5.25"').rsplit("/", 1)[-1]
        assert 'Form factor: 5.25"' in self.specs(client, aid)

    def test_a_hard_disk_ignores_a_stale_pick(self, client):
        aid = self.add(client, kind="Hard disk", spec_capacity="540 MB",
                       drive_form='3.5"').rsplit("/", 1)[-1]
        assert "Form factor:" not in self.specs(client, aid)

    def test_custom_records_a_bay_the_list_does_not_name(self, client):
        """An Amstrad CF-2 is a 3" disk, and drivedb's parser reads a typed 3" as
        3.5" -- the shorthand it has always meant. Picked, it is not guessed at."""
        aid = self.add(client, drive_desc="Amstrad CF-2", drive_form="custom",
                       drive_form_custom='3"').rsplit("/", 1)[-1]
        assert 'Form factor: 3"' in self.specs(client, aid)

    def test_a_description_that_names_no_kind_gets_one_from_the_menu(
            self, client, computer):
        """drivedb infers "floppy" from a size only a floppy has -- but it infers
        while reading the text, and "Sony MPF920" names neither a kind nor a size.
        Picked rather than typed, the facts arrive after that rule has run, so the
        row came out with no kind at all."""
        cid = computer()["asset_id"]
        self.add(client, computer_id=cid, drive_desc="Sony MPF920",
                 drive_form='3.5"', drive_size="1.44MB")
        assert client.get(f"/api/computers/{cid}").json()["drives"] \
            == 'Sony MPF920 3.5" 1.44MB floppy'

    def test_an_optical_drive_is_not_called_a_floppy(self, client, computer):
        """Which is why the menu answers rather than the 5.25" being taken as
        proof: early CD-ROM drives are 5.25" too."""
        cid = computer()["asset_id"]
        self.add(client, kind="Optical", computer_id=cid, drive_desc="Sony CDU55",
                 drive_form='5.25"')
        assert client.get(f"/api/computers/{cid}").json()["drives"] \
            == 'Sony CDU55 5.25" optical'

    def test_a_kind_the_description_does_name_is_left_alone(self, client, computer):
        cid = computer()["asset_id"]
        self.add(client, computer_id=cid, drive_desc="Gotek emulator",
                 drive_form='3.5"')
        assert "Gotek" in client.get(f"/api/computers/{cid}").json()["drives"]

    def test_a_routed_drive_takes_its_make_and_model_from_identity(
            self, client, computer):
        """A routed drive never becomes a Part, so what was typed under Identity
        used to be dropped on the floor -- survivable while the description was
        always on screen and could carry the name, not now that it is not."""
        cid = computer()["asset_id"]
        self.add(client, computer_id=cid, manufacturer="Sony", model="MPF920",
                 drive_form='3.5"', drive_size="1.44MB")
        assert client.get(f"/api/computers/{cid}").json()["drives"] \
            == 'Sony MPF920 3.5" 1.44MB floppy'

    def test_what_the_description_still_says_is_not_written_over(
            self, client, computer):
        """What is left of a description once the pickers have taken their share is
        the words they could not say. Identity fills a blank; it does not win."""
        cid = computer()["asset_id"]
        self.add(client, computer_id=cid, manufacturer="Tandon", model="TM100-1",
                 drive_desc="SS/DD", drive_form='5.25"', drive_size="180K")
        assert "SS/DD" in client.get(f"/api/computers/{cid}").json()["drives"]

    def test_the_form_reopens_on_the_pick(self, client):
        aid = self.add(client, drive_desc="floppy",
                       drive_form='5.25"').rsplit("/", 1)[-1]
        flat = " ".join(client.get(f"/parts/{aid}/edit").text.split())
        assert 'value="5.25&#34;" checked' in flat or 'value="5.25"" checked' in flat

    def test_the_typed_box_cannot_outgrow_the_column_it_lands_in(self, client):
        """The drive row's form_factor is a String(16); a picker that let you type
        more than that would fail on save rather than on the form."""
        from app.models import ComputerDrive
        page = client.get("/parts/new?type=storage").text
        assert f'name="drive_form_custom" maxlength="{ComputerDrive.form_factor.type.length}"' \
            in " ".join(page.split())
        assert f'name="drive_size_custom" maxlength="{ComputerDrive.size.type.length}"' \
            in " ".join(page.split())


class TestPickingWhatAnOpticalDriveTakes:
    """A floppy is known by the disk it takes; an optical drive is known by the
    discs it takes and the rating on its front. Neither is a capacity, so they are
    two pickers of their own rather than the floppy list pointed at other words --
    and both had been going into the description for want of anywhere else."""

    def add(self, client, **extra):
        data = {"type": "storage", "kind": "Optical"} | extra
        r = client.post("/parts/new", data=data, follow_redirects=False)
        return r.headers["location"]

    def part(self, client, **extra):
        return self.add(client, **extra).rsplit("/", 1)[-1]

    def specs(self, client, aid):
        return client.get(f"/api/parts/{aid}").json()["specs"]

    def test_both_picks_land_on_the_machines_drive_row(self, client, computer):
        cid = computer()["asset_id"]
        self.add(client, computer_id=cid, drive_media="CD-RW", drive_speed="48×")
        assert client.get(f"/api/computers/{cid}").json()["drives"] \
            == "48× CD-RW optical"

    def test_a_drive_kept_as_a_part_records_them(self, client):
        specs = self.specs(client, self.part(client, drive_media="CD-ROM",
                                             drive_speed="24×"))
        assert "Media: CD-ROM" in specs and "Speed: 24×" in specs

    def test_the_rating_is_stored_as_a_number_of_its_own(self, client, db):
        """Not in the rpm column: 48× and 5400 rpm are different quantities, and
        one column could not sort or compare both."""
        from app.models import StorageSpec
        aid = self.part(client, drive_media="CD-RW", drive_speed="48×")
        row = db.query(StorageSpec).filter(StorageSpec.part_id == aid).one()
        assert (row.speed_x, row.speed_rpm) == (48, None)

    def test_a_hard_disks_speed_is_still_its_spindles(self, client, db):
        """The same key, and the same text box it has always been typed into: the
        pickers appear for an optical drive, and must not swallow this one."""
        from app.models import StorageSpec
        r = client.post("/parts/new",
                        data={"type": "storage", "kind": "Hard disk",
                              "spec_capacity": "540 MB", "spec_speed": "5400 rpm",
                              "spec_media": "MFM"}, follow_redirects=False)
        aid = r.headers["location"].rsplit("/", 1)[-1]
        row = db.query(StorageSpec).filter(StorageSpec.part_id == aid).one()
        assert (row.speed_rpm, row.speed_x, row.media) == (5400, None, "MFM")

    def test_a_kind_that_takes_no_disc_ignores_a_stale_pick(self, client):
        """Choosing CD-RW and then changing the kind leaves the radio checked and
        off-screen. A floppy drive is not a CD-RW anything."""
        r = client.post("/parts/new",
                        data={"type": "storage", "kind": "Floppy/Gotek",
                              "drive_desc": "3.5in floppy", "drive_media": "CD-RW",
                              "drive_speed": "48×"}, follow_redirects=False)
        specs = self.specs(client, r.headers["location"].rsplit("/", 1)[-1])
        assert "Media:" not in specs and "Speed:" not in specs

    def test_the_picker_wins_over_the_description(self, client, computer):
        cid = computer()["asset_id"]
        self.add(client, computer_id=cid, drive_desc="24x CD-ROM",
                 drive_media="CD-RW", drive_speed="48×")
        drives = client.get(f"/api/computers/{cid}").json()["drives"]
        assert "48× CD-RW" in drives and "24×" not in drives

    def test_picking_nothing_leaves_what_the_description_said(self, client, computer):
        cid = computer()["asset_id"]
        self.add(client, computer_id=cid, drive_desc="48x CD-RW")
        assert client.get(f"/api/computers/{cid}").json()["drives"] \
            == "48× CD-RW optical"

    def test_custom_records_what_was_typed(self, client):
        specs = self.specs(client, self.part(
            client, drive_media="custom", drive_media_custom="magneto-optical",
            drive_speed="custom", drive_speed_custom="48×/24×/48×"))
        assert "Media: magneto-optical" in specs
        assert "Speed: 48×/24×/48×" in specs

    def test_a_rating_the_list_does_not_name_is_kept_as_it_was_typed(self, client):
        """It is no kind of number, so it lands where every unparseable quantity
        does -- kept verbatim rather than dropped on the floor."""
        aid = self.part(client, drive_media="CD-RW", drive_speed="custom",
                        drive_speed_custom="48×/24×/48×")
        assert "Speed: 48×/24×/48×" in self.specs(client, aid)

    def test_the_form_opens_on_the_picks_again(self, client):
        aid = self.part(client, drive_media="CD-RW", drive_speed="48×")
        flat = " ".join(client.get(f"/parts/{aid}/edit").text.split())
        assert 'value="CD-RW" checked' in flat
        assert 'value="48×" checked' in flat

    def test_a_pick_can_be_taken_back_off(self, client):
        """Choosing "not recorded" has to clear it, rather than the hidden text box
        below quietly putting it back."""
        aid = self.part(client, drive_media="CD-RW", drive_speed="48×")
        client.post(f"/parts/{aid}/edit",
                    data={"type": "storage", "kind": "Optical", "drive_media": "",
                          "drive_speed": "", "spec_media": "CD-RW",
                          "spec_speed": "48×"}, follow_redirects=False)
        specs = self.specs(client, aid)
        assert "Media:" not in specs and "Speed:" not in specs

    def test_a_medium_alone_still_describes_the_drive(self, client, computer):
        """Picking a medium and typing no description is an ordinary gesture now
        the picker exists; the kind's menu label must not land in the model."""
        cid = computer()["asset_id"]
        self.add(client, computer_id=cid, drive_media="DVD-ROM")
        assert client.get(f"/api/computers/{cid}").json()["drives"] \
            == "DVD-ROM optical"

    def test_the_typed_boxes_cannot_outgrow_the_columns_they_land_in(self, client):
        from app.models import ComputerDrive
        flat = " ".join(client.get("/parts/new?type=storage").text.split())
        assert f'name="drive_media_custom" maxlength="{ComputerDrive.media.type.length}"' \
            in flat
        assert f'name="drive_speed_custom" maxlength="{ComputerDrive.speed.type.length}"' \
            in flat

    def test_an_optical_drive_says_what_it_takes_on_its_label(self, client):
        from app import labels
        _, lines = labels.small_body(
            {"asset_id": "RH-0031", "name": "Plextor PX-W4012A", "type": "storage",
             "specs": "Kind: Optical | Media: CD-RW | Speed: 48×"}, False)
        assert lines == ["CD-RW 48×"]


class TestTheOpticalSplitMigration:
    """The two optical drives that were on file before any of this asked for them.
    The migration writes down what each becomes; this is the claim that those are
    the parser's own answers, so the table cannot drift from the code behind it."""

    @staticmethod
    def splits():
        import importlib.util
        from pathlib import Path
        path = (Path(__file__).resolve().parent.parent / "migrations" / "versions"
                / "0017_optical_media_and_speed.py")
        spec = importlib.util.spec_from_file_location("m0017", path)
        mod = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(mod)
        return mod.SPLITS

    def test_each_row_is_what_the_parser_gives(self):
        from app import drivedb
        for aid, before, media, speed in self.splits():
            d = drivedb.parse_segment(before)
            assert (d["media"], d["speed"], d["model"]) == (media, speed, ""), aid

    def test_every_one_of_them_is_an_optical_drive(self):
        from app import drivedb
        for aid, before, *_ in self.splits():
            assert drivedb.parse_segment(before)["kind"] == "optical", aid

    def test_every_medium_is_one_the_picker_offers(self):
        """A split that produced something off the list would open on "custom"
        rather than on the radio it should be."""
        from app import drivedb
        for aid, _b, media, _s in self.splits():
            assert media in drivedb.MEDIA, aid

    def test_a_rating_is_offered_or_fits_the_box_that_takes_it(self):
        """A single figure is on the list; a writer's three are what the custom box
        is for, and must fit the column that box is sized to."""
        from app import drivedb
        from app.models import ComputerDrive
        for aid, _b, _m, speed in self.splits():
            assert (speed in drivedb.SPEEDS
                    or len(speed) <= ComputerDrive.speed.type.length), aid

    def test_a_single_figure_reads_back_from_the_column_it_is_stored_in(self):
        """The migration writes those as a number; the spec key renders them."""
        from app import specstruct
        for _aid, _b, _m, speed in self.splits():
            if speed not in [f"{n}×" for n in range(1, 100)]:
                continue
            st = specstruct.Struct()
            st.scalars["speed_x"] = int(speed.rstrip("×"))
            assert specstruct.format("storage", st) == f"Speed: {speed}"

    def test_the_three_figure_ones_survive_as_they_are_written(self):
        """They are no kind of a number, so they ride as a verbatim attribute --
        and come back out under the same key, in the same notation."""
        from app import specstruct
        for _aid, _b, _m, speed in self.splits():
            if speed in [f"{n}×" for n in range(1, 100)]:
                continue
            st = specstruct.parse("storage", f"Speed: {speed}")
            assert st.attributes == [("Speed", speed)]
            assert specstruct.format("storage", st) == f"Speed: {speed}"


class TestTheMakerLeagueTable:
    """Most and least reliable maker. Reliability means one thing here -- the share
    of a maker's parts recorded as Working -- and the entry conditions matter more
    than the ranking does, because a league table nobody can see the rules of is
    just an opinion with a bar chart."""

    def table(self, db):
        from app import main
        return main._maker_reliability(db)

    def stock(self, part, maker, working, broken, **extra):
        for i in range(working):
            part(manufacturer=maker, model=f"{maker}-w{i}", condition="Working", **extra)
        for i in range(broken):
            part(manufacturer=maker, model=f"{maker}-f{i}", condition="Faulty", **extra)

    def test_best_record_first_worst_last(self, client, db, part):
        self.stock(part, "Goodco", 6, 0)
        self.stock(part, "Middling", 3, 3)
        self.stock(part, "Dudco", 1, 5)
        assert [r[0] for r in self.table(db)] == ["Goodco", "Middling", "Dudco"]
        assert [r[3] for r in self.table(db)] == [100, 50, 17]

    def test_a_maker_with_too_few_parts_does_not_qualify(self, client, db, part):
        """One working card is not a record, and on a sample of one it would top
        the table."""
        from app import main
        self.stock(part, "Tiny", main.RELIABILITY_MIN - 1, 0)
        self.stock(part, "Realco", main.RELIABILITY_MIN, 0)
        assert [r[0] for r in self.table(db)] == ["Realco"]

    def test_a_tie_goes_to_the_bigger_sample(self, client, db, part):
        """Equal records; the one who earned it over more parts has the better
        case for it."""
        self.stock(part, "Fewer", 5, 0)
        self.stock(part, "More", 9, 0)
        assert [r[0] for r in self.table(db)] == ["More", "Fewer"]

    def test_unknown_is_not_a_maker(self, client, db, part):
        """"Unknown" and "Generic" stand for "we do not know" and "nobody in
        particular"; neither belongs in a league table of manufacturers."""
        self.stock(part, "Unknown", 6, 0)
        self.stock(part, "Generic", 6, 0)
        self.stock(part, "Realco", 5, 1)
        assert [r[0] for r in self.table(db)] == ["Realco"]

    def test_restored_does_not_count_as_working(self, client, db, part):
        """A part that had to be restored is evidence of the opposite."""
        self.stock(part, "Fixedco", 3, 0)
        for i in range(3):
            part(manufacturer="Fixedco", model=f"r{i}", condition="Restored")
        assert self.table(db)[0][3] == 50

    def test_a_part_no_longer_here_is_not_counted(self, client, db, part):
        """It may have been sold in perfect order; the register is what is here."""
        gone = part(manufacturer="Goneco", model="g", condition="Faulty")["asset_id"]
        self.stock(part, "Goneco", 5, 0)
        client.post(f"/parts/{gone}/dispose", data={"note": "sold", "date": ""},
                    follow_redirects=False)
        assert self.table(db)[0] == ("Goneco", 5, 5, 100)

    def test_the_bars_are_drawn_against_a_hundred(self, client, part):
        """A percentage scaled to its own best row would draw 92% as a full bar and
        read as "all of them"."""
        self.stock(part, "Halfco", 3, 3)
        self.stock(part, "Nearlyco", 5, 1)
        page = client.get("/stats").text
        # 5 of 6 is 83%, and 83% of a 100 ceiling is 83% of the track. Against the
        # best row instead it would have been the full width.
        assert 'style="width: 50.0%"' in page and 'style="width: 83.0%"' in page


class TestTheShuffledFigures:
    """The pointless department: a pool of figures, a handful drawn per visit. What
    matters is that the pool only holds what the collection can currently answer,
    and that every one of them leads somewhere real -- not just the six that
    happened to come up on the render a test looked at."""

    def pool(self, db):
        from app import main
        return main._curios(db, main._collection_stats(db), date.today().year)

    def furnish(self, client, computer, part):
        """Enough of everything that most of the pool has something to say."""
        c = computer(year=1991, condition="Working", acquired_date="2026-05-01",
                     manufacturer="IBM", model="PS/2", drives='2x 3.5" 1.44MB')
        client.post(f"/computers/{c['asset_id']}/edit", data={"ramchip:41256": "18"},
                    follow_redirects=False)
        client.post(f"/computers/{c['asset_id']}/note", data={"message": "cleaned"},
                    follow_redirects=False)
        for i in range(6):
            part(manufacturer="Goodco", model=f"g{i}", condition="Working",
                 year=1988, acquired_date="2026-02-0%d" % (i + 1), source="a rally",
                 computer_id=c["asset_id"])
        for i in range(6):
            part(manufacturer="Dudco", model=f"d{i}", condition="Faulty", year=1990)
        part(type="storage", model="Big", specs="Kind: Hard disk | Capacity: 4GB")
        part(type="storage", model="Small", specs="Kind: Hard disk | Capacity: 20MB")
        return c

    def test_every_figure_in_the_pool_leads_somewhere_real(self, client, db,
                                                           computer, part):
        """The page's own sweep only sees the handful it drew, and some of these
        lead to an item page rather than to /browse, so neither is covered there."""
        from app import main
        self.furnish(client, computer, part)
        pool = self.pool(db)
        assert len(pool) > main.CURIOS_SHOWN      # or there is nothing to shuffle
        for c in pool:
            if c["href"]:
                assert client.get(c["href"]).status_code == 200, (c["k"], c["href"])

    def test_no_figure_is_offered_with_nothing_to_say(self, client, db):
        """An empty register answers none of them rather than answering them
        blank."""
        assert self.pool(db) == []
        assert client.get("/stats").status_code == 200

    def test_only_a_handful_is_shown(self, client, db, computer, part):
        from app import main
        self.furnish(client, computer, part)
        page = client.get("/stats").text
        assert len(self.department(page)) == main.CURIOS_SHOWN
        flat = " ".join(page.split())
        assert f"of {len(self.pool(db))}" in flat      # and it says what it drew from

    def test_a_different_draw_each_time(self, client, db, computer, part):
        """Seeded rather than looked at twice and hoped over: two draws from the
        same pool can legitimately coincide, and a test that fails once a fortnight
        is worse than no test."""
        import random
        self.furnish(client, computer, part)
        random.seed(1)
        first = client.get("/stats").text
        random.seed(2)
        second = client.get("/stats").text
        assert self.department(first) != self.department(second)

    @staticmethod
    def department(page):
        body = page[page.index("The pointless department"):]
        return re.findall(r'<div class="k">([^<]+)</div>', body)

    def test_the_share_link_says_the_collection_not_the_draw(self, client, computer,
                                                             part):
        """Whichever six came up is not what a crawler or a chat window should
        quote back."""
        self.furnish(client, computer, part)
        page = client.get("/stats").text
        blurb = re.search(r'og:description" content="([^"]+)"', page).group(1)
        assert "things in the register" in blurb



class TestReadingTheInchMarkAsTyped:
    """A straight quote is what a keyboard gives; a phone or a Mac autocorrects it
    to a curly one, and ″ is the typographically correct prime. Six of the eight
    drive descriptions on file used the curly quote, and drivedb did not know that
    character -- so 3.5” was read as the drive's *model*, the number going into the
    name of the thing rather than into its form factor."""

    @staticmethod
    def parsed(text):
        from app import drivedb
        return drivedb.parse_segment(text)

    def test_every_inch_mark_reads_the_same(self):
        for mark in ('"', "”", "“", "″", "''", "in", " inch"):
            d = self.parsed(f"3.5{mark} 1.44MB")
            assert d["form_factor"] == '3.5"', mark
            assert d["model"] == "", mark

    def test_the_number_no_longer_lands_in_the_model(self):
        assert self.parsed("3.5” 1.44MB") == self.parsed('3.5" 1.44MB')

    def test_a_quote_that_is_not_an_inch_mark_is_left_alone(self):
        """Only a number in front of it makes it a measurement."""
        assert self.parsed('Sony “Special” floppy')["form_factor"] == ""


class TestTheDescriptionSplitMigration:
    """The eight descriptions recorded before the pickers existed. The migration
    writes down what each becomes; this is the claim that those are the parser's
    own answers and not a second reading of the same words, so the table cannot
    drift from the code that justified it."""

    @staticmethod
    def splits():
        import importlib.util
        from pathlib import Path
        path = (Path(__file__).resolve().parent.parent / "migrations" / "versions"
                / "0016_drive_description_split.py")
        spec = importlib.util.spec_from_file_location("m0016", path)
        mod = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(mod)
        return mod.SPLITS

    def test_each_row_is_what_the_parser_gives(self):
        from app import drivedb
        for aid, before, form, size, after in self.splits():
            d = drivedb.parse_segment(before)
            assert (d["form_factor"], d["size"], d["model"]) == (form, size, after), aid

    def test_every_one_of_them_is_a_floppy(self):
        from app import drivedb
        for aid, before, *_ in self.splits():
            assert drivedb.parse_segment(before)["kind"] == "floppy", aid

    def test_the_capacities_are_ones_the_picker_offers(self):
        """A split that produced something off the list would open on "custom"
        rather than on the radio it should be."""
        from app import drivedb
        for aid, _b, form, size, _a in self.splits():
            assert size in drivedb.SIZES, aid
            assert form in drivedb.FORM_FACTORS, aid


class TestAFloppySSmallLabel:
    """A drive on a shelf is known by the disk it takes. The small label carried a
    hard disk's capacity and geometry but nothing at all for a floppy, whose two
    facts live under different spec keys."""

    def body(self, specs):
        """The (name, spec lines) a small label would carry for a drive recorded
        like this. A mapping rather than keywords, because "Form factor" is two
        words on the label as it is in the spec key."""
        from app import labels
        rendered = " | ".join(f"{k}: {v}" for k, v in specs.items())
        return labels.small_body(
            {"asset_id": "RH-0031", "name": "Sony MPF920-E", "type": "storage",
             "specs": rendered}, False)

    def test_the_bay_and_the_disk_share_one_line(self):
        """They are read as one thing -- "a 3.5-inch 1.44MB" -- and joined they
        cannot be split by the squeeze that drops the last line, which would
        otherwise leave the less useful half behind."""
        _, lines = self.body({"Form factor": '3.5"', "Size": "1.44MB"})
        assert lines == ['3.5" 1.44MB']

    def test_either_alone_still_says_what_it_knows(self):
        assert self.body({"Form factor": '5.25"'})[1] == ['5.25"']
        assert self.body({"Size": "1.2MB"})[1] == ["1.2MB"]

    def test_a_drive_with_neither_holds_no_line_open(self):
        assert self.body({"Kind": "Floppy/Gotek"})[1] == []

    def test_a_hard_disk_reads_as_it_always_did(self):
        """One table serves both because the keys do not overlap."""
        _, lines = self.body({"Capacity": "1281 MB", "CHS": "2482/16/63"})
        assert lines == ["1281 MB", "CHS 2482/16/63"]

    def test_it_reaches_the_printed_label(self, client):
        r = client.post("/parts/new",
                        data={"type": "storage", "kind": "Floppy/Gotek",
                              "drive_desc": "Sony MPF920", "drive_form": '3.5"',
                              "drive_size": "1.44MB"}, follow_redirects=False)
        aid = r.headers["location"].rsplit("/", 1)[-1]
        pdf = client.get(f"/parts/{aid}/label.pdf?small=1")
        assert pdf.status_code == 200 and pdf.content[:4] == b"%PDF"


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
        # display=True, as the label route passes: a label is read, never parsed.
        return labels.small_body(main.to_dict(p), False,
                                 specdb.pairs(db, p, display=True))

    def test_a_drive_says_how_big_it_is(self, client, db, part):
        aid = part(type="storage", manufacturer="Seagate", model="ST-225",
                   specs="Kind: Hard disk | Capacity: 20 MB")["asset_id"]
        assert self.body(db, aid) == ("Seagate ST-225", ["20 MB"])

    def test_a_drive_with_no_capacity_recorded_just_says_what_it_is(self, client, db,
                                                                   part):
        """Half the drives on file have no capacity against them; none of them should
        get a blank line held open for one."""
        aid = part(type="storage", manufacturer="Mitsumi", model="D503V",
                   specs="Kind: Floppy/Gotek")["asset_id"]
        assert self.body(db, aid) == ("Mitsumi D503V", [])

    def test_capacity_worked_out_from_the_geometry_counts_too(self, client, db, part):
        """A drive recorded by its cylinders/heads/sectors has its capacity derived
        rather than stated, and the label carries that just the same. 38828 KB is a
        38 MB drive, and the label says so rather than reciting the KB."""
        aid = part(type="storage", manufacturer="Quantum", model="LPS 52A",
                   specs="Kind: Hard disk | CHS: 571/8/17")["asset_id"]
        assert self.body(db, aid) == ("Quantum LPS 52A", ["37.9 MB", "CHS 571/8/17"])

    def test_other_kinds_of_part_are_left_alone(self, client, db, part):
        """Only the types whose name does not say the thing you want off the label.
        A video card's memory is on the full label, where there is room for it."""
        aid = part(type="video", manufacturer="Trident", model="8900C",
                   specs="Memory: 1 MB")["asset_id"]
        assert self.body(db, aid) == ("Trident 8900C", [])

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
        assert labels.small_body(c, True) == ("Acme PC-1", [])

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


class TestALabelSCodeCanActuallyBeRead:
    """The codes are the point of the labels, and the gallery now reads them with a
    camera as well as a phone's own app. Both decode standard QR only.
    """

    # A Micro QR at the scale and border the labels use is at most (17+2)x10 px
    # across; the smallest standard symbol is (21+2)x10.
    LARGEST_MICRO_PX = (17 + 2) * 10

    def test_a_code_is_never_a_micro_qr(self):
        """Left to itself segno reaches for a Micro QR whenever the data will fit in
        one, and most readers cannot decode those. No URL is anywhere near short
        enough to trigger it, so this guards the day something short is encoded
        rather than a break anyone would see now."""
        import segno

        from app import labels
        tag = "RH-0001"
        assert segno.make(tag, error="m").is_micro          # what segno would choose
        w, h = labels._qr(tag).getSize()                    # what the label gets
        assert w == h and w > self.LARGEST_MICRO_PX

    def test_the_url_on_a_label_is_a_full_size_code_too(self):
        from app import labels
        w, _ = labels._qr(labels.item_url("RH-0001")).getSize()
        assert w > self.LARGEST_MICRO_PX

    def test_the_code_holds_the_url_that_resolves_to_either_kind(self, client,
                                                                 computer, part):
        """/items/<tag> is what the scanner navigates to and what the printed code
        says, so it has to keep working for a machine and for a part alike."""
        from app import labels
        for aid, kind in ((computer()["asset_id"], "computers"),
                          (part()["asset_id"], "parts")):
            assert labels.item_url(aid).endswith(f"/items/{aid}/")
            r = client.get(f"/items/{aid}", follow_redirects=False)
            assert r.headers["location"].endswith(f"/{kind}/{aid}")


class TestTheCapacityGetsALineOfItsOwn:
    """On its own line rather than trailing the name, so a shelf of drives reads
    down the capacities instead of finding each one wherever the name stopped
    wrapping. Which means the line has to be budgeted for, not hoped for.
    """

    @staticmethod
    def laid_out(title, tags, avail_mm=13.0):
        """The body lines a small label would draw, at the size chosen for them."""
        from reportlab.lib.units import mm
        from reportlab.pdfgen import canvas

        from app import labels
        c = canvas.Canvas("/dev/null")
        _, bfont = labels._fonts()
        # The body column on a 51x19mm label, and the height under the asset id.
        return labels._small_body_lines(c, title, tags, bfont, 69.4, avail_mm * mm)

    def test_the_capacity_is_the_last_line(self):
        _, lines = self.laid_out("Seagate ST-225", ["20 MB"])
        assert lines[-1] == "20 MB"
        assert "20 MB" not in lines[0]

    def test_the_longest_name_on_file_still_leaves_room(self):
        """It takes three lines of its own; the capacity gets a fourth, and on a
        51x19mm label all four fit without the type having to give."""
        long_name = "Magnetic Peripheraps Inc 91455-36"
        size, lines = self.laid_out(long_name, ["20 MB"])
        assert lines[-1] == "20 MB"
        assert " ".join(lines[:-1]) == long_name      # nothing of the name lost
        assert size == 6.5

    def test_where_the_height_does_run_short_the_type_gives_first(self):
        """Squeezed, it shrinks the name to buy the capacity its line rather than
        dropping the line."""
        long_name = "Magnetic Peripheraps Inc 91455-36"
        size, lines = self.laid_out(long_name, ["20 MB"], avail_mm=9.0)
        assert lines[-1] == "20 MB"
        assert size < 6.5

    def test_nothing_is_held_open_when_there_is_no_capacity(self):
        _, lines = self.laid_out("Copal / Fujitsu F-5002-3728", [])
        assert lines == ["Copal / Fujitsu", "F-5002-3728"]

    def test_the_capacity_survives_a_name_that_cannot_fit_at_all(self):
        """Past the point where shrinking helps, the name is clipped and the capacity
        is kept -- on a drive it is the thing being looked for."""
        _, lines = self.laid_out(" ".join(["Fujitsu Siemens Computers"] * 6), ["540 MB"])
        assert lines[-1] == "540 MB"

    def test_a_label_with_barely_any_room_still_says_something(self):
        """Rather than dividing by a line count of zero, or drawing off the label."""
        _, lines = self.laid_out("Seagate ST-225", ["20 MB"], avail_mm=1.0)
        assert lines and all(lines)

    def test_the_geometry_gets_a_line_under_the_capacity(self):
        """An old BIOS wants cylinders/heads/sectors before it will talk to the
        drive, so it goes on the label with them -- prefixed, because three numbers
        with no word in front of them could be anything."""
        _, lines = self.laid_out("Quantum LPS 52A", ["50 MB", "CHS 571/8/17"])
        assert lines[-2:] == ["50 MB", "CHS 571/8/17"]

    def test_the_capacity_outranks_the_geometry_when_only_one_fits(self):
        """Squeezed past shrinking the type, the last line is the one to go."""
        _, lines = self.laid_out("Quantum ProDrive LPS 52A",
                                 ["50 MB", "CHS 571/8/17"], avail_mm=4.5)
        assert "50 MB" in lines
        assert "CHS 571/8/17" not in lines


class TestWhereAFigureIsRoundedAndWhereItIsNot:
    """A quantity is stored as plain KB and said in whatever unit suits. Text that is
    only ever read -- a page, a label -- rounds an amount that cannot be said exactly.
    The edit form keeps it to the KB, because what the form shows is parsed back on
    the next save, and a rounded figure would quietly move the number.
    """

    # 571x8x17 sectors of 512 bytes: 38828 KB, which is not a whole MB and cannot
    # be written as one to two decimal places either.
    SPECS = "Kind: Hard disk | CHS: 571/8/17"

    def make(self, part):
        return part(type="storage", manufacturer="Quantum", model="LPS 52A",
                    specs=self.SPECS)["asset_id"]

    def test_the_page_says_it_the_way_a_person_would(self, client, part):
        aid = self.make(part)
        page = client.get(f"/parts/{aid}").text
        assert "37.9 MB" in page
        assert "38828 KB" not in page

    def test_the_form_is_given_it_to_the_kilobyte(self, client, part):
        aid = self.make(part)
        page = client.get(f"/parts/{aid}/edit").text
        assert 'name="spec_capacity" value="38828 KB"' in page
        assert "37.9 MB" not in page

    def test_saving_that_form_back_untouched_does_not_move_the_number(self, client,
                                                                     db, part):
        """The corruption the split exists to prevent. Had the form been handed
        '37.9 MB', saving it without touching it would have written 38810 KB.

        The geometry is deliberately not resubmitted: were it there, the capacity
        would be re-derived from it and this would pass whatever the box said.
        """
        from app import specdb
        from app.models import Part
        aid = self.make(part)
        page = client.get(f"/parts/{aid}/edit").text
        shown = re.search(r'name="spec_capacity" value="([^"]*)"', page).group(1)
        client.post(f"/parts/{aid}/edit",
                    data={"type": "storage", "model": "LPS 52A",
                          "spec_kind": "Hard disk", "spec_capacity": shown},
                    follow_redirects=False)
        db.expire_all()
        p = db.get(Part, aid)
        assert specdb.read(db, p).scalars["capacity_kb"] == 38828

    def test_the_stored_string_is_exact_too(self, client, db, part):
        """It is the wire format for the REST API and the MCP tools, and it is parsed
        back by the next write, so it holds the figure rather than a rounding."""
        from app.models import Part
        aid = self.make(part)
        db.expire_all()
        assert "38828 KB" in db.get(Part, aid).specs

    @pytest.mark.parametrize("typed,shown", [
        ("2 MB", "2 MB"),          # was rendered back as '2048 KB'
        ("1024 KB", "1 MB"),
        ("8192 KB", "8 MB"),
        ("640 KB", "640 KB"),
    ])
    def test_memory_is_said_in_megabytes_where_that_is_the_word_for_it(
            self, client, db, part, typed, shown):
        """Not only drives: a 2 MB SIMM read '2048 KB' on every page it appeared on."""
        from app.models import Part
        aid = part(type="ram", model="SIMM", specs=f"Size: {typed}")["asset_id"]
        db.expire_all()
        assert db.get(Part, aid).specs == f"Size: {shown}"


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


class TestTheFirstFewMatchesWhileYouType:
    """What the search bar offers under the box. It is the same search Enter runs
    -- so what it lists is a preview of that answer rather than a second, narrower
    one -- with an order laid over it, because ten rows under a half-typed word are
    being aimed at rather than read."""

    def sug(self, client, q):
        r = client.get("/suggest", params={"q": q})
        assert r.status_code == 200, r.text
        return r.json()

    def test_it_offers_the_matches_and_says_how_many_there_are(self, client, part):
        for i in range(14):
            part(manufacturer="Adaptec", model=f"AHA-{i:04d}")
        out = self.sug(client, "adaptec")
        assert out["total"] == 14
        assert len(out["items"]) == 10

    def test_nothing_is_offered_for_nothing_typed(self, client, part):
        part()
        assert self.sug(client, "")["items"] == []
        assert self.sug(client, "   ")["total"] == 0

    def test_an_asset_tag_typed_in_full_comes_first(self, client, part):
        """Typing a tag off a label is aiming at one item, whatever else mentions
        it -- and other items do mention it, because a part records the machine it
        is installed in."""
        wanted = part(model="Sound Blaster")["asset_id"]
        for i in range(6):
            part(model=f"Filler {i}", notes=f"pulled from {wanted}")
        out = self.sug(client, wanted)
        assert out["items"][0]["aid"] == wanted
        assert out["total"] > 1

    def test_a_name_that_starts_with_it_beats_one_that_merely_contains_it(
            self, client, part):
        starts = part(name="Adaptec AHA-1542CF")["asset_id"]
        contains = part(name="Cable for Adaptec host adapters")["asset_id"]
        order = [i["aid"] for i in self.sug(client, "adaptec")["items"]]
        assert order.index(starts) < order.index(contains)

    def test_a_hit_only_in_the_history_is_offered_but_sorts_below_a_named_one(
            self, client, part):
        named = part(name="Recapped PSU tester")["asset_id"]
        logged = part(name="Mystery board")["asset_id"]
        client.post(f"/parts/{logged}/note", data={"message": "recapped the lot"},
                    follow_redirects=False)
        order = [i["aid"] for i in self.sug(client, "recapped")["items"]]
        assert order == [named, logged]

    def test_a_disposed_item_is_offered_last_and_says_so(self, client, part):
        gone = part(name="Maxtor spare")["asset_id"]
        here = part(name="Maxtor keeper")["asset_id"]
        client.post(f"/parts/{gone}/dispose", data={"note": "died", "date": ""},
                    follow_redirects=False)
        items = self.sug(client, "maxtor")["items"]
        assert [i["aid"] for i in items] == [here, gone]
        assert items[1]["disposed"] is True and items[0]["disposed"] is False

    def test_each_row_carries_what_the_list_draws(self, client, computer):
        aid = computer(manufacturer="Commodore", model="Amiga 2000",
                       year=1987)["asset_id"]
        row = self.sug(client, "amiga")["items"][0]
        assert row["url"] == f"/computers/{aid}"
        assert row["name"] == "Commodore Amiga 2000"
        assert row["cat"] == "Computer" and row["year"] == 1987
        # No photo, so the card's own placeholder stands in for one.
        assert row["img"] == "" and row["icon"].startswith("/static/placeholders/")

    def test_a_part_wears_its_own_category_and_icon(self, client, part):
        part(type="video", model="ET4000")
        row = self.sug(client, "et4000")["items"][0]
        assert row["cat"] == "Video" and row["icon"] == "/static/placeholders/card.svg"

    def test_a_floppy_drive_is_not_drawn_as_a_hard_disk(self, client, part):
        """The gallery tells a floppy from a disc from a disk by its Kind spec; a
        list of ten under the search box has the same job and the same answer."""
        part(type="storage", model="TEAC FD-235HF", specs="Kind: Floppy")
        assert self.sug(client, "fd-235")["items"][0]["icon"] \
            == "/static/placeholders/floppy.svg"

    def test_suggesting_is_public(self, client, part, monkeypatch):
        from app import main
        part(notes="battery damage")
        monkeypatch.setattr(main, "AUTH_ENABLED", True)
        assert client.get("/suggest", params={"q": "battery"}).status_code == 200

    def test_it_is_not_offered_to_crawlers(self, client):
        assert "Disallow: /suggest" in client.get("/robots.txt").text


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
