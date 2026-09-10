"""End-to-end behaviour through the REST API and the GUI forms.

Weighted towards the things that have actually broken: typed columns rejecting or
silently eating form input, a select with no option for the value it holds, links
left pointing at deleted rows, and derived strings being written to directly.
"""
import html
import re
from datetime import date, datetime, timedelta
from html.parser import HTMLParser
from pathlib import Path
from typing import ClassVar

import pytest

from app import main, schemas


def served(client, page):
    """A page together with the static CSS/JS it links, so an assertion about a
    style or a script holds whether that content is inline or in a static file.
    Lets these tests keep checking what actually reaches the browser as the CSS
    and JS move out of the templates."""
    out = [page]
    for url in re.findall(r'(?:href|src)="(/static/[^"?#]+\.(?:css|js))', page):
        out.append(client.get(url).text)
    return "\n".join(out)


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

    @pytest.mark.parametrize("typed", ["http://another.example/parts/{aid}",
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
        assert c["installed_ram"] == "8× 1MiB 30-pin (8 MiB)"
        assert c["installed_ram_kb"] == 8192

    def test_a_plain_amount_over_the_wire_becomes_a_number(self, client, computer):
        aid = computer()["asset_id"]
        c = client.patch(f"/api/computers/{aid}",
                         json={"installed_ram": "640KB"}).json()
        assert c["installed_ram"] == "640 KiB" and c["installed_ram_kb"] == 640

    def test_setting_a_total_does_not_wipe_a_breakdown(self, client, computer):
        aid = computer()["asset_id"]
        client.post(f"/computers/{aid}/edit",
                    data={"rammod:30p1m": "8", "installed_ram": ""},
                    follow_redirects=False)
        c = client.patch(f"/api/computers/{aid}",
                         json={"installed_ram": "32MB"}).json()
        assert c["installed_ram"] == "8× 1MiB 30-pin (8 MiB)"

    def test_replacing_a_total_with_a_note_does_not_leave_the_old_figure(
            self, client, computer):
        """Passing None once meant "leave the total alone", so the stale number
        stayed and the string read '16 MiB; 16MB (2 banks)'."""
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
                              "spec_interface": "34-pin floppy",
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
                              "spec_interface": "34-pin floppy",
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
                          "spec_interface": "34-pin floppy",
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
        data = {"type": "storage", "kind": "Floppy/Gotek",
                "spec_interface": "34-pin floppy"} | extra
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
        """1.44MB is 1475 KiB only by convention. A RAM 'Size' is a quantity and
        normalises to KiB; a disk's is what the disk is called, and must not."""
        aid = self.part(client, drive_desc="3.5in floppy", drive_size="1.44MB")
        specs = self.specs(client, aid)
        assert "1475" not in specs and "KiB" not in specs

    def test_a_ram_size_still_normalises(self, client, db):
        """The other half of that guard: only storage is exempt, and a memory
        amount still lands in the KiB column that makes it sort and compare."""
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
                              "spec_interface": "IDE",
                              "drive_desc": "Sony CDU55", "drive_size": "1.44MB"},
                        follow_redirects=False)
        aid = r.headers["location"].rsplit("/", 1)[-1]
        assert "Size:" not in self.specs(client, aid)

    def test_a_hard_disk_ignores_it_as_well(self, client):
        r = client.post("/parts/new",
                        data={"type": "storage", "kind": "Hard disk",
                              "spec_interface": "IDE",
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
                          "spec_interface": "34-pin floppy",
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
                        data={"type": "storage", "kind": kind,
                              "spec_interface": "IDE"} | extra,
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

    def test_a_hard_disk_is_asked_its_bay_as_well(self, client):
        """It used to be a routed drive's question alone. A hard disk fits a bay like
        anything else, and knowing which is how you tell a full-height 5.25" from a
        3.5" without getting it out of the box."""
        aid = self.add(client, kind="Hard disk", spec_capacity="540 MB",
                       drive_form='3.5"').rsplit("/", 1)[-1]
        assert 'Form factor: 3.5"' in self.specs(client, aid)

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
        data = {"type": "storage", "kind": "Optical",
                "spec_interface": "IDE"} | extra
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
        """The same key, from a group of its own: a disk is asked its rpm and a reader
        its × rating, and one list must never offer both. It lands in the rpm column
        either way."""
        from app.models import StorageSpec
        r = client.post("/parts/new",
                        data={"type": "storage", "kind": "Hard disk",
                              "spec_interface": "IDE",
                              "spec_capacity": "540 MB", "drive_speed": "5400 rpm",
                              "spec_media": "MFM"}, follow_redirects=False)
        aid = r.headers["location"].rsplit("/", 1)[-1]
        row = db.query(StorageSpec).filter(StorageSpec.part_id == aid).one()
        assert (row.speed_rpm, row.speed_x) == (5400, None)

    def test_a_kind_that_takes_no_disc_ignores_a_stale_pick(self, client):
        """Choosing CD-RW and then changing the kind leaves the radio checked and
        off-screen. A floppy is asked its media too, but from its own list, so a disc
        arriving under that name is not an answer to it -- and a floppy is asked no
        speed at all."""
        r = client.post("/parts/new",
                        data={"type": "storage", "kind": "Floppy/Gotek",
                              "spec_interface": "34-pin floppy",
                              "drive_desc": "3.5in floppy", "drive_media": "CD-RW",
                              "drive_speed": "48×"}, follow_redirects=False)
        specs = self.specs(client, r.headers["location"].rsplit("/", 1)[-1])
        assert "Media: CD-RW" not in specs and "Speed:" not in specs

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
                    data={"type": "storage", "kind": "Optical",
                          "spec_interface": "IDE", "drive_media": "",
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


class TestAStoragePartSInterface:
    """How a drive attaches is the one thing every storage part has to say, so that
    "every SCSI drive" stays a question the collection can answer. It is picked from
    a closed list rather than typed, with a box for the buses the list does not name.

    It also had to become reachable at all: the part fields were hidden for every
    routed kind, whether or not there was a machine to route to, which is why all 53
    floppy and all 12 optical drives on file had no interface recorded."""

    def add(self, client, **extra):
        data = {"type": "storage", "kind": "Hard disk",
                "spec_interface": "SCSI"} | extra
        return client.post("/parts/new", data=data, follow_redirects=False)

    def part(self, client, **extra):
        r = self.add(client, **extra)
        assert r.status_code == 303, r.text
        return r.headers["location"].rsplit("/", 1)[-1]

    def specs(self, client, aid):
        return client.get(f"/api/parts/{aid}").json()["specs"]

    def test_it_is_recorded(self, client):
        aid = self.part(client)
        assert "Interface: SCSI" in self.specs(client, aid)

    def test_a_part_with_none_is_refused(self, client):
        assert self.add(client, spec_interface="").status_code == 400

    def test_an_edit_that_drops_it_is_refused_too(self, client):
        aid = self.part(client)
        r = client.post(f"/parts/{aid}/edit",
                        data={"type": "storage", "kind": "Hard disk",
                              "spec_interface": ""}, follow_redirects=False)
        assert r.status_code == 400
        assert "Interface: SCSI" in self.specs(client, aid)

    def test_another_type_is_not_asked(self, client):
        """Only storage attaches by a bus worth naming this way; a sound card's
        interface is its own free-text field and must not start being required."""
        r = client.post("/parts/new", data={"type": "sound", "model": "SB16"},
                        follow_redirects=False)
        assert r.status_code == 303

    def test_a_drive_routed_to_a_machine_is_not_asked(self, client, computer):
        """It becomes a row on that machine rather than a part, and has no interface
        column of its own to fill."""
        cid = computer()["asset_id"]
        r = client.post("/parts/new",
                        data={"type": "storage", "kind": "Floppy/Gotek",
                              "computer_id": cid, "drive_desc": "3.5in floppy"},
                        follow_redirects=False)
        assert r.status_code == 303
        assert "floppy" in client.get(f"/api/computers/{cid}").json()["drives"]

    def test_custom_records_a_bus_the_list_does_not_name(self, client):
        aid = self.part(client, kind="Tape", spec_interface="custom",
                        spec_interface_custom="QIC-02")
        assert "Interface: QIC-02" in self.specs(client, aid)

    def test_custom_with_nothing_typed_is_refused(self, client):
        assert self.add(client, spec_interface="custom",
                        spec_interface_custom="  ").status_code == 400

    def test_the_form_opens_on_the_pick_again(self, client):
        aid = self.part(client)
        flat = " ".join(client.get(f"/parts/{aid}/edit").text.split())
        assert 'value="SCSI" checked' in flat

    def test_a_bus_outside_the_list_opens_on_the_box(self, client):
        """The one disk on file recorded as 'ATA' has to survive being edited: a
        radio group with no room for it would retag it as whatever was ticked."""
        aid = self.part(client, spec_interface="custom",
                        spec_interface_custom="ATA")
        page = client.get(f"/parts/{aid}/edit").text
        assert 'id="spec_interface_custom"' in page and "ATA" in page
        assert 'value="custom" checked' in " ".join(page.split())

    def test_a_spare_of_a_routed_kind_is_asked_on_screen(self, client):
        """The bug: no machine to route to, so it becomes a part -- and the field it
        has to fill was hidden by the kind alone."""
        page = client.get("/parts/new?type=storage").text
        assert "const routes = false;" in page
        assert 'name="spec_interface" value="34-pin floppy"' in \
            " ".join(page.split())

    def test_editing_a_routed_kind_is_asked_on_screen_too(self, client):
        aid = self.part(client, kind="Floppy/Gotek",
                        spec_interface="34-pin floppy")
        assert "const routes = false;" in client.get(f"/parts/{aid}/edit").text

    def test_building_a_drive_into_a_machine_still_routes(self, client, computer):
        cid = computer()["asset_id"]
        page = client.get(f"/parts/new?type=storage&computer_id={cid}").text
        assert "const routes = true;" in page

    def test_a_spare_optical_drive_records_its_discs_and_its_bus_together(self, client):
        """The two questions are independent: what the drive is, from the pickers the
        kind brings, and how it attaches, from the part's own field. A spare optical
        drive answers both."""
        aid = self.part(client, kind="Optical", spec_interface="IDE",
                        drive_media="CD-RW", drive_speed="32×")
        specs = self.specs(client, aid)
        assert "Interface: IDE" in specs
        assert "Media: CD-RW" in specs and "Speed: 32×" in specs

    def test_the_blocks_the_script_toggles_are_all_still_there(self, client):
        """Which of these is on screen is decided in the script, so it is not
        something this suite can see. What it can hold onto is that every block the
        script reaches for still exists under the name it uses -- renaming or
        dropping one leaves a rule silently toggling nothing, which is how the
        pickers and then the part fields each went missing once."""
        page = client.get("/parts/new?type=storage").text
        for hook in ('id="drive-bezel"', 'id="part-bezel"', 'id="drive-desc-row"',
                     'class="ask"', 'data-kinds=', 'data-row=1', 'data-required=1'):
            assert hook in page, hook

    def test_a_slimline_drive_and_a_sound_card_bus_are_on_offer(self, client):
        """A 26-pin flex cable is not the 34-pin header of a desktop drive, and the
        early CD-ROMs hung off a sound card rather than a disk controller."""
        flat = " ".join(client.get("/parts/new?type=storage").text.split())
        for bus in ("26-pin floppy", "Proprietary"):
            assert f'name="spec_interface" value="{bus}"' in flat


class TestReopeningADriveOnWhatItSaved:
    """A question asked of more than one kind has a group per kind, and they share a
    field name -- so the browser reads them as one group and the last `checked` in the
    markup wins. Every group deciding for itself whether the recorded answer was one
    of its own is how an optical drive's speed came to be posted back blank: the hard
    disk's rpm group did not recognise "12×", called it custom, and checked its own
    custom radio further down the page.

    So: exactly one answer checked per group, and a form reopened and saved with
    nothing touched must give back the record it was opened on."""

    CASES: ClassVar[list[tuple[str, str]]] = [
        ("Optical", "Kind: Optical | Interface: IDE | Media: CD-ROM | Speed: 12×"),
        ("Optical", "Kind: Optical | Interface: IDE | Media: CD-RW | Speed: 4×/2×/20×"),
        ("Hard disk", "Kind: Hard disk | Interface: SCSI | Protocol: SCSI | "
                      "Speed: 7200 rpm"),
        ("Hard disk", 'Kind: Hard disk | Interface: IDE | Capacity: 540 MiB | '
                      'CHS: 1057/16/63 | Form factor: 3.5"'),
        ("Tape", "Kind: Tape | Interface: SCSI | Media: QIC-80"),
        ("Floppy/Gotek", 'Kind: Floppy/Gotek | Interface: 34-pin floppy | '
                         'Media: 3.5" | Form factor: 5.25" | Size: 1.44MB'),
        ("SD/CF card", "Kind: SD/CF card | Interface: CF | Capacity: 512 MiB"),
    ]

    GROUPS = ("drive_speed", "drive_media", "drive_size", "drive_form",
              "spec_interface", "spec_protocol")

    def edit_page(self, client, specs):
        aid = client.post("/api/parts", json={"type": "storage", "model": "X",
                                              "specs": specs}).json()["asset_id"]
        return aid, " ".join(client.get(f"/parts/{aid}/edit").text.split())

    def reopened(self, flat):
        """The form as a browser would post it straight back, untouched."""
        out = {}
        for m in re.finditer(r'name="(\w+)" value="([^"]*)"[^>]*?\schecked', flat):
            out[m.group(1)] = html.unescape(m.group(2))
        for m in re.finditer(r'<input id="\w+" name="(\w+)"[^>]*?value="([^"]*)"', flat):
            out.setdefault(m.group(1), html.unescape(m.group(2)))
        return out

    @pytest.mark.parametrize("kind,specs", CASES)
    def test_one_answer_is_checked_per_group(self, client, kind, specs):
        _aid, flat = self.edit_page(client, specs)
        for name in self.GROUPS:
            checked = re.findall(rf'name="{name}" value="([^"]*)"[^>]*?\schecked', flat)
            assert len(checked) <= 1, f"{name} has {checked}"

    @pytest.mark.parametrize("kind,specs", CASES)
    def test_saving_it_untouched_changes_nothing(self, client, kind, specs):
        aid, flat = self.edit_page(client, specs)
        form = self.reopened(flat) | {"type": "storage", "kind": kind}
        r = client.post(f"/parts/{aid}/edit", data=form, follow_redirects=False)
        assert r.status_code == 303, r.text
        assert client.get(f"/api/parts/{aid}").json()["specs"] == specs

    def test_a_group_for_another_kind_is_sitting_on_nothing(self, client):
        """Not even on "not recorded", which is an answer too and would post a blank
        over the real one for exactly the same reason."""
        _aid, flat = self.edit_page(
            client, "Kind: Optical | Interface: IDE | Speed: 12×")
        # The optical group holds the answer, so every other speed group -- the hard
        # disk's -- must hold nothing at all.
        checked = re.findall(r'name="drive_speed" value="([^"]*)"[^>]*?\schecked', flat)
        assert checked == ["12×"]


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


class TestAPickerOpensOnNothing:
    """"Install in computer" opened on the first machine in the register, which reads
    as a statement that the part is in it -- next to a table whose "Installed in" row
    is absent precisely because it is not. Every one of these menus now opens on
    nothing and refuses to submit until something is chosen."""

    @staticmethod
    def _select(page, name):
        cut = page[page.index(f'<select name="{name}"'):]
        return cut[:cut.index("</select>")]

    def test_the_install_menu_opens_on_nothing(self, client, computer, part):
        computer(model="PS/1")
        p = part(model="a card")
        select = self._select(client.get(f"/parts/{p['asset_id']}").text, "computer_id")
        assert re.findall(r'<option value="([^"]*)"', select)[0] == "", select
        assert "required" in select.split(">")[0]

    def test_it_says_nothing_about_where_the_part_is(self, client, computer, part):
        """The machine's name must not be the chosen option -- that is the
        misreading."""
        computer(model="PS/1")
        p = part(model="a card")
        page = client.get(f"/parts/{p['asset_id']}").text
        assert "selected" not in self._select(page, "computer_id")
        # ...and the table above says nothing either, the part being installed nowhere.
        assert "Installed in" not in page

    def test_choosing_one_still_installs_it(self, client, computer, part):
        c = computer(model="PS/1")
        p = part(model="a card")
        client.post(f"/parts/{p['asset_id']}/link",
                    data={"computer_id": c["asset_id"]}, follow_redirects=False)
        assert "Installed in" in client.get(f"/parts/{p['asset_id']}").text
        assert client.get(f"/api/parts/{p['asset_id']}").json()["computer_id"] \
            == c["asset_id"]

    @pytest.mark.parametrize("path,field", [
        ("/parts/{aid}/link", "computer_id"),
        ("/parts/{aid}/attach", "part_id"),
    ])
    def test_posting_a_blank_does_nothing_rather_than_404(self, client, part, path,
                                                         field):
        """The menus will not submit empty, so this only arrives from something posting
        straight at the endpoint -- where the empty string used to be looked up as an
        asset id."""
        p = part(model="a card")
        r = client.post(path.format(aid=p["asset_id"]), data={field: ""},
                        follow_redirects=False)
        assert r.status_code == 303, r.text
        got = client.get(f"/api/parts/{p['asset_id']}").json()
        assert not got["computer_id"] and not got["parent_id"]

    def test_the_board_menu_on_a_machine_opens_on_nothing_too(self, client, computer,
                                                              part):
        c = computer(model="PS/1")
        part(type="motherboard", model="a board")
        select = self._select(client.get(f"/computers/{c['asset_id']}").text, "part_id")
        assert re.findall(r'<option value="([^"]*)"', select)[0] == ""
        r = client.post(f"/computers/{c['asset_id']}/link-motherboard",
                        data={"part_id": ""}, follow_redirects=False)
        assert r.status_code == 303


class TestRememberingHowYouLeftIt:
    """The sort order is kept in a cookie, so the shelf opens the way you left it --
    and a first visit, having no cookie, opens shuffled."""

    def test_the_cookie_the_page_writes_is_the_one_the_server_names(self, client,
                                                                   computer):
        """The name is a template global rather than a string in two places, because
        a cookie written under one name and read under another is not remembered."""
        from app import main
        computer(model="A")
        page = client.get("/").text
        assert main.SORT_COOKIE == "rhdb_sort"
        assert f'rhdbCookie.read("{main.SORT_COOKIE}")' in page
        assert f'rhdbCookie.write("{main.SORT_COOKIE}"' in page

    def test_a_sort_that_no_longer_exists_is_not_trusted(self, client, computer):
        """A stale or hand-edited cookie naming a sort the page dropped would
        otherwise leave the grid sorted by nothing."""
        computer(model="A")
        assert "if (saved && SORTS[saved]) sortSel.value = saved;" \
            in client.get("/").text

    def test_it_is_written_on_the_sorts_own_change_and_not_on_every_keystroke(
            self, client, computer):
        computer(model="A")
        page = client.get("/").text
        assert "sortSel.addEventListener('change', function () {" in page

    def test_the_helpers_are_defined_before_the_page_uses_them(self, client, computer):
        """The gallery's script lives in the content block, so anything it calls has
        to be defined above it in the document. Put after, it threw on load and took
        the sorting and filtering with it."""
        computer(model="A")
        page = client.get("/").text
        assert page.index("window.rhdbCookie = {") < page.index("</head>")


class TestTheCookieNotice:
    """Said once, dismissible, and gone from the markup afterwards. No accept-or-reject
    pair, because nothing is stored until the reader picks a sort order or the dark
    theme -- there is nothing to consent to in advance."""

    def test_it_is_offered_on_a_first_visit(self, client, computer):
        computer(model="A")
        page = client.get("/").text
        assert 'id="cookienote"' in page
        # What it actually says matters: no analytics and no third party is the claim
        # the page is making, and it should stay true. Flattened, because the sentence
        # is wrapped across lines in the template.
        flat = " ".join(page.split())
        assert "no analytics" in flat and "nothing shared with anyone" in flat

    def test_dismissing_it_takes_it_out_of_the_markup(self, client, computer):
        """Not hidden by a script on every page thereafter -- the server knows from
        the cookie and leaves it out."""
        from app import main
        computer(model="A")
        client.cookies.set(main.NOTICE_COOKIE, "1")
        assert 'id="cookienote"' not in client.get("/").text
        client.cookies.delete(main.NOTICE_COOKIE)

    def test_it_is_on_every_page_not_just_the_gallery(self, client, computer):
        c = computer(model="A")
        for path in ("/", "/stats", f"/computers/{c['asset_id']}"):
            assert 'id="cookienote"' in client.get(path).text, path

    def test_it_does_not_block_the_page(self, client, computer):
        """A notice, not a gate: no overlay, and the cards are reachable behind it."""
        computer(model="A")
        page = served(client, client.get("/").text)
        note = page[page.index('id="cookienote"'):]
        assert "position: fixed" in page and 'class="card"' in page
        assert "Got it" in note[:600]


class TestTheGalleryOpensShuffled:
    """A shelf is more interesting shuffled than in the order things were last
    touched, and a recency sort only ever shows the same dozen items."""

    def test_random_is_the_first_option_and_so_the_default(self, client, computer):
        computer(model="A")
        page = client.get("/").text
        select = page[page.index('<select id="sort"'):page.index("</select>", page.index('<select id="sort"'))]
        values = re.findall(r'<option value="([^"]*)"', select)
        assert values[0] == "random", values
        # No `selected` anywhere in the group, so the first option is what opens --
        # asserted because adding one elsewhere would silently take the default away.
        assert "selected" not in select

    def test_the_shuffle_is_dealt_once_and_held(self, client, computer):
        """Filtering and searching re-sort on every keystroke, so a shuffle that
        re-dealt each time would throw the cards up in the air while you typed."""
        computer(model="A")
        page = client.get("/").text
        assert "function deal()" in page and "el._shuffle = Math.random()" in page
        # Dealt again only when Random is chosen afresh, which is what makes the
        # option useful once you are already on it.
        assert "if (mode === 'random' && mode !== lastMode) deal();" in page

    def test_a_photoless_item_still_sorts_last(self, client, computer):
        """The same rule the recency sorts follow: a shuffle that opens on a screenful
        of unphotographed things looks like a broken page, not a random one."""
        computer(model="A")
        page = client.get("/").text
        assert "random: (a, b) => hasImg(b) - hasImg(a) || a._shuffle - b._shuffle" \
            in page


class TestWhatIsGoneIsNotCounted:
    """A disposed item is a record of something that has left the collection, so it
    should not swell a figure about what the collection has. The exception is the one
    figure that is about disposal, which would otherwise always read nought."""

    def facts(self, db):
        from app import main
        return {f["k"]: f for f in
                main._facts(db, main._collection_stats(db), date.today().year)}

    def test_a_binned_part_leaves_the_totals(self, client, db, part):
        from app import main
        keep = part(manufacturer="Goodco", model="stays", condition="Working")
        gone = part(manufacturer="Dudco", model="goes", condition="Working")
        before = main._collection_stats(db)["n_parts"]
        client.post(f"/parts/{gone['asset_id']}/dispose", data={"note": "sold"},
                    follow_redirects=False)
        db.expire_all()
        after = main._collection_stats(db)
        assert after["n_parts"] == before - 1
        assert after["working"] == 1
        # ...and it is not among the makers either, which is what a league table of
        # them would otherwise reward.
        assert [m for m, _n, _v in after["makers"]] == ["Goodco"]
        assert keep["asset_id"] and after["disposed"] == 1

    def test_the_count_of_disposals_does_count_them(self, client, db, part):
        gone = part(model="goes")
        client.post(f"/parts/{gone['asset_id']}/dispose", data={"note": "binned"},
                    follow_redirects=False)
        db.expire_all()
        assert self.facts(db)["No longer with us"]["v"] == "1"

    def test_a_disposed_year_does_not_stretch_the_range(self, client, db, part):
        from app import main
        part(model="held", year=1990)
        part(model="also", year=1995)
        gone = part(model="goes", year=1970)
        client.post(f"/parts/{gone['asset_id']}/dispose", data={"note": "sold"},
                    follow_redirects=False)
        db.expire_all()
        assert min(main._all_years(db)) == 1990

    def test_a_disposed_machine_is_not_the_best_equipped(self, client, db, computer,
                                                        part):
        from app import main
        c = computer(model="gone")
        for i in range(3):
            part(model=f"p{i}", computer_id=c["asset_id"])
        assert main._collection_stats(db)["fullest"] is not None
        client.post(f"/computers/{c['asset_id']}/dispose", data={"note": "sold"},
                    follow_redirects=False)
        db.expire_all()
        assert main._collection_stats(db)["fullest"] is None


class TestTheShuffledFigures:
    """One pool of figures, a handful drawn per visit -- the fixed tiles and the odd
    ones together, since the split only meant the interesting half was below the fold.
    What matters is that the pool holds only what the collection can currently answer,
    and that every one of them leads somewhere real -- not just the eight that
    happened to come up on the render a test looked at."""

    def pool(self, db):
        from app import main
        return main._facts(db, main._collection_stats(db), date.today().year)

    def furnish(self, client, computer, part):
        """Enough of everything that most of the pool has something to say.

        Deliberately broad rather than minimal: the sweep below is only as good as
        the figures this answers, and a group of them that stays silent here is a
        group whose links nothing checks. So there is a board with a board's specs,
        one card of each kind, drives that state a speed and a geometry, a machine
        that names its processor and what it boots, and provenance on some of it
        and not on the rest."""
        c = computer(year=1991, condition="Working", acquired_date="2026-05-01",
                     manufacturer="IBM", model="PS/2", drives='2x 3.5" 1.44MB',
                     os="MS DOS 5.0", cpu="Intel 80286-6", chassis="luggable",
                     topbench=42, machine={"model_key": "ps2-8530"})
        client.post(f"/computers/{c['asset_id']}/edit", data={"ramchip:41256": "18"},
                    follow_redirects=False)
        client.post(f"/computers/{c['asset_id']}/note", data={"message": "cleaned"},
                    follow_redirects=False)
        # A machine with nothing fitted, and one with a card standing in for a disk.
        # The Amstrad repeats the IBM's processor, because "the commonest processor"
        # needs two machines to agree before it is a commonest anything.
        computer(year=1989, manufacturer="Amstrad", model="PC1512",
                 installed_ram="640KB", cpu="Intel 80286-6")
        flash = computer(year=1987, manufacturer="Olivetti", model="M21",
                         drives='1x CF 1GB')
        part(computer_id=flash["asset_id"], type="video", model="anachronism",
             year=2024, specs="Chip: RP2040 | Interface: 8-bit ISA | Connector: VGA")
        for i in range(6):
            part(manufacturer="Goodco", model=f"g{i}", condition="Working",
                 year=1988, acquired_date="2026-02-0%d" % (i + 1), source="a rally",
                 computer_id=c["asset_id"])
        for i in range(6):
            part(manufacturer="Dudco", model=f"d{i}", condition="Faulty", year=1990)
        # Fitted to a machine of its own year, which is a figure of its own.
        part(manufacturer="Goodco", model="contemporary", year=1991,
             computer_id=c["asset_id"])
        part(type="storage", model="Big", specs="Kind: Hard disk | Capacity: 4GB")
        part(type="storage", model="Small", specs="Kind: Hard disk | Capacity: 20MB")
        # A board with everything a board is asked, so the whole board group fires.
        board = part(type="motherboard", manufacturer="IBM", model="Planar",
                     year=1991, condition="Working", url="https://example.test/b",
                     summary="the board out of it", source="eBay order no. 1-2-3",
                     specs="Form factor: Baby-AT | Chipset: discrete | "
                           "CPU family: 286-class | BIOS: Award | Cache: 256KB | "
                           "Onboard video: VGA | Slots: 6x 16-bit ISA | "
                           "RAM slots: 4x 30-pin SIMM | Ports: 2x Serial")
        part(type="motherboard", model="Bare", year=1990,
             specs="Form factor: proprietary")
        part(parent_id=board["asset_id"], type="other", model="riser",
             source="Self-made", disk_image="boot.img")
        # Two of the same thing, which is what the duplicate figures count.
        for i in range(2):
            part(type="sound", manufacturer="Creative", model="CT2830", year=1994,
                 specs=f"Chip: CT1747{i} | Interface: 16-bit ISA")
        part(type="network", manufacturer="3Com", model="Etherlink III",
             specs="Interface: 16-bit ISA")
        part(type="network", manufacturer="Intel", model="Pro/100",
             specs="Interface: PCI")
        part(type="io", model="Multi-IO", specs="Interface: 8-bit ISA")
        part(type="video", manufacturer="Trident", model="TVGA9000i", year=1992,
             specs="Chip: TVGA9000i | Interface: 16-bit ISA | "
                   "Connector: VGA, CGA | Memory: 512KB")
        part(type="storage", model="Spinner", year=1993,
             specs="Kind: Hard disk | Interface: MFM | Capacity: 40MB | "
                   "Speed: 3600rpm | CHS: 977/5/17")
        part(type="storage", model="Reader",
             specs="Kind: Optical | Interface: IDE | Media: CD-ROM | Speed: 48x")
        part(type="storage", model="Slowreader",
             specs="Kind: Optical | Interface: IDE | Media: CD-ROM | Speed: 2x")
        return c

    def test_every_figure_in_the_pool_leads_somewhere_real(self, client, db,
                                                           computer, part):
        """The page's own sweep only sees the handful it drew, and some of these
        lead to an item page rather than to /browse, so neither is covered there."""
        from app import main
        self.furnish(client, computer, part)
        pool = self.pool(db)
        assert len(pool) > main.FACTS_SHOWN       # or there is nothing to shuffle
        for c in pool:
            if c["href"]:
                assert client.get(c["href"]).status_code == 200, (c["k"], c["href"])

    def test_the_fixture_reaches_every_group_of_figures(self, client, db, computer,
                                                       part):
        """The sweep above proves the links work; this proves the sweep saw them.

        One figure named from each themed group. Enough of the pool would still
        answer with an empty spec table that a group falling silent -- a join
        written wrong, a column renamed -- would otherwise pass unnoticed, its
        links unvisited."""
        self.furnish(client, computer, part)
        keys = {c["k"] for c in self.pool(db)}
        for expected in ("The usual board shape", "Video outputs counted",
                         "The fastest spindle here", "The 640 KiB club",
                         "The biggest anachronism", "Made here rather than bought",
                         "Parts with a link out", "Broken and kept anyway"):
            assert expected in keys, expected

    def test_a_figure_about_the_register_itself_need_not_link(self, client, db,
                                                              computer, part):
        """Most tiles are links; the ones counting history entries are not, because
        an entry in a history is not an item the gallery can show. A link to
        everything would be a link that lied about what it counted."""
        self.furnish(client, computer, part)
        pool = {c["k"]: c for c in self.pool(db)}
        assert pool["The register is younger than everything in it"]["href"] is None
        assert pool["Parts with a link out"]["href"]

    def test_a_binned_board_is_not_a_board_the_collection_has(self, client, db,
                                                              computer, part):
        """The themed groups read the spec tables, and a spec row has no disposed
        flag of its own -- so each of them joins back to the part that owns it. One
        group checked here stands for all of them: the join is the same join."""
        from app import main
        self.furnish(client, computer, part)
        gone = part(type="motherboard", model="Doomed",
                    specs="Form factor: Baby-AT | BIOS: Award")
        before = {c["k"]: c["s"] for c in self.pool(db)}
        client.post(f"/parts/{gone['asset_id']}/dispose", data={"note": "binned"},
                    follow_redirects=False)
        db.expire_all()
        after = {c["k"]: c["s"] for c in self.pool(db)}
        assert before["Whose BIOS it usually is"] != after["Whose BIOS it usually is"]
        assert main._facts  # the pool is still built, not merely smaller

    def test_a_tile_with_no_link_still_renders_as_a_tile(self, client, monkeypatch):
        """The figures about the register carry no href, which is a shape the tile
        markup has to answer for: not a link with an empty destination, but a plain
        tile. Forced rather than waited for -- a draw of eight from a hundred cannot
        be relied on to include the one under test."""
        from app import main
        monkeypatch.setattr(main, "_facts", lambda *_a: [
            {"k": "Entries in the register", "v": "12", "s": "no page to show",
             "href": None}])
        page = client.get("/stats").text
        assert '<div class="tile">' in page
        assert 'class="tile" href=""' not in page

    def test_every_condition_beyond_the_two_above_gets_a_figure(self, client, db,
                                                                part):
        """Four of the six values in entry.CONDITIONS have a figure naming them, and
        they name it as a string. A value renamed there would turn these into counts
        that are always nought -- and a figure that never fires never fails."""
        from app import entry
        for cond in entry.CONDITIONS:
            part(model=f"p-{cond}", condition=cond)
        keys = {c["k"] for c in self.pool(db)}
        assert {"Broken and kept anyway", "Works, but not all of it", "Brought back",
                "Good only for parts", "Still working", "Never tested"} <= keys

    def test_no_figure_is_offered_with_nothing_to_say(self, client, db):
        """An empty register answers none of them rather than answering them
        blank."""
        assert self.pool(db) == []
        assert client.get("/stats").status_code == 200

    def test_only_a_handful_is_shown(self, client, db, computer, part):
        from app import main
        self.furnish(client, computer, part)
        page = client.get("/stats").text
        assert len(self.department(page)) == main.FACTS_SHOWN
        flat = " ".join(page.split())
        assert f"of {len(self.pool(db))}" in flat      # and it says what it drew from

    def test_no_two_tiles_show_the_same_number(self, client, computer, part):
        """The storage total and the hard disks that are nearly all of it both read
        the same figure on the real register. Drawn together they look like a bug."""
        self.furnish(client, computer, part)
        for _ in range(12):
            page = client.get("/stats").text
            body = page[page.index("Eight things about it"):]
            values = re.findall(r'<div class="v">([^<]+)</div>', body)
            assert len(values) == len(set(values)), values

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
        body = page[page.index("Eight things about it"):]
        return re.findall(r'<div class="k">([^<]+)</div>', body)

    def test_the_share_link_says_the_collection_not_the_draw(self, client, computer,
                                                             part):
        """Whichever eight came up is not what a crawler or a chat window should
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
        _, lines = self.body({"Capacity": "1281 MiB", "CHS": "2482/16/63"})
        assert lines == ["1281 MiB", "CHS 2482/16/63"]

    def test_it_reaches_the_printed_label(self, client):
        r = client.post("/parts/new",
                        data={"type": "storage", "kind": "Floppy/Gotek",
                              "spec_interface": "34-pin floppy",
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


class TestTheBuildWalk:
    """The banner that lands you on the next step after creating a machine. It reads
    "give it a motherboard, then add its expansion cards", which is a PC's shape."""

    def test_a_pc_is_walked_through_building_it_out(self, client, computer):
        aid = computer(manufacturer="Compaq", model="Deskpro 386")["asset_id"]
        assert "Build walk" in client.get(f"/computers/{aid}?build=1").text

    def test_a_catalogue_machine_is_not(self, client, computer):
        """A Spectrum is a sealed thing described by what it was built as. It has no
        board to link and nothing on a shelf goes in one -- which is why its board
        and parts sections are not even on the page while nothing is fitted, and why
        pointing somebody at them is pointing at the wrong machine."""
        aid = computer(manufacturer="Sinclair", model="ZX Spectrum 48K",
                       machine={"model_key": "zx-spectrum-48k"})["asset_id"]
        page = client.get(f"/computers/{aid}?build=1").text
        assert "Build walk" not in page

    def test_the_banner_is_only_for_whoever_is_signed_in(self, client, computer):
        """It is an instruction to do the next thing, and a reader has nothing to do."""
        aid = computer(manufacturer="Compaq", model="Deskpro 386")["asset_id"]
        assert "Build walk" in client.get(f"/computers/{aid}?build=1").text
        assert "Build walk" not in client.get(f"/computers/{aid}").text


class TestASerialNumber:
    """The one field on a record that belongs to the object rather than to the
    model, and so the one that tells two of the same thing apart."""

    def test_a_machine_records_and_shows_one(self, client, computer):
        aid = computer(manufacturer="Acorn", model="A5000",
                       serial="27-AKD52-1234567")["asset_id"]
        assert client.get(f"/api/computers/{aid}").json()["serial"] == \
            "27-AKD52-1234567"
        assert "27-AKD52-1234567" in client.get(f"/computers/{aid}").text

    def test_a_part_does_too(self, client, part):
        aid = part(type="display", model="AKF18", serial="AKF18-9901234")["asset_id"]
        assert client.get(f"/api/parts/{aid}").json()["serial"] == "AKF18-9901234"
        assert "AKF18-9901234" in client.get(f"/parts/{aid}").text

    def test_both_forms_ask_for_one(self, client, computer, part):
        cid = computer(manufacturer="Acorn", model="A5000",
                       serial="27-AKD52-1234567")["asset_id"]
        pid = part(type="cpu", serial="L4210229")["asset_id"]
        for page in (client.get(f"/computers/{cid}/edit").text,
                     client.get(f"/parts/{pid}/edit").text):
            assert 'name="serial"' in page
        assert 'value="27-AKD52-1234567"' in client.get(f"/computers/{cid}/edit").text
        assert 'value="L4210229"' in client.get(f"/parts/{pid}/edit").text

    def test_the_form_can_take_a_serial_back_off(self, client, part):
        aid = part(type="cpu", manufacturer="Intel", serial="L4210229")["asset_id"]
        client.post(f"/parts/{aid}/edit",
                    data={"type": "cpu", "manufacturer": "Intel", "serial": ""},
                    follow_redirects=False)
        assert client.get(f"/api/parts/{aid}").json()["serial"] == ""

    def test_a_duplicate_does_not_carry_the_serial_across(self, client, part):
        """The whole point of the field: no two objects ever wore the same number,
        so a copy that inherited one would be asserting something false about the
        second thing -- and the copy is made to be filled in, not to be believed."""
        aid = part(type="ram", model="72-pin SIMM", serial="M366-0031")["asset_id"]
        copy = client.post(f"/parts/{aid}/duplicate", follow_redirects=False
                           ).headers["location"].rsplit("/", 1)[-1]
        got = client.get(f"/api/parts/{copy}").json()
        assert got["model"] == "72-pin SIMM"
        assert got["serial"] == ""

    def test_an_item_is_found_by_its_serial(self, client, computer):
        """A machine can be looked up by the number on its own back, which is the
        question a serial is written down to answer."""
        computer(manufacturer="Acorn", model="A5000", serial="27-AKD52-1234567")
        computer(manufacturer="Acorn", model="A5000", serial="27-AKD52-7654321")
        page = client.get("/machines?q=27-AKD52-1234567").text
        assert "27-AKD52-7654321" not in page
        assert page.count("RH-") >= 1


class TestNotesKeepTheirLines:
    """A note is typed into a textarea, in paragraphs. It was stored with its
    newlines and then read back as one run-on line, because a table cell does not
    show them without being told to."""

    def test_a_parts_notes_are_shown_in_the_lines_they_were_typed_in(self, client,
                                                                     part):
        aid = part(type="cpu",
                   notes="recapped 2026-08\nsocket cleaned\nstill untested")["asset_id"]
        page = client.get(f"/parts/{aid}").text
        cell = page[page.index("<th>Notes</th>"):]
        cell = cell[:cell.index("</td>")]
        assert 'class="lines"' in cell
        assert "recapped 2026-08\nsocket cleaned\nstill untested" in cell

    def test_a_machines_notes_are_too(self, client, computer):
        aid = computer(manufacturer="Acorn", model="A5000",
                       notes="two lines\nnot one")["asset_id"]
        page = client.get(f"/computers/{aid}").text
        cell = page[page.index("<th>Notes</th>"):]
        cell = cell[:cell.index("</td>")]
        assert 'class="lines"' in cell
        assert "two lines\nnot one" in cell


class TestALinkInWhatWasTypedIsALink:
    """A URL in a note, a summary, a source or a history entry is one you meant to
    follow, and it used to be text to select and paste. The linkifier is unit-tested
    in test_entry; what these check is that the pages it belongs on have it, and that
    the text around it is still text."""

    def _cell(self, page, th):
        cell = page[page.index(f"<th>{th}</th>"):]
        return cell[:cell.index("</td>")]

    def test_a_url_in_a_parts_notes(self, client, part):
        aid = part(type="cpu", notes="datasheet at http://x.test/74ls00.pdf")["asset_id"]
        cell = self._cell(client.get(f"/parts/{aid}").text, "Notes")
        assert ('<a class="url" href="http://x.test/74ls00.pdf" target="_blank"'
                ' rel="noopener noreferrer">http://x.test/74ls00.pdf</a>') in cell

    def test_a_url_in_a_machines_summary(self, client, computer):
        aid = computer(manufacturer="Acorn", model="A5000",
                       summary="the story is at www.acorn.test/a5000")["asset_id"]
        page = client.get(f"/computers/{aid}").text
        assert '<a class="url" href="http://www.acorn.test/a5000"' in page

    def test_a_url_in_the_source_it_came_from(self, client, part):
        aid = part(source="https://www.ebay.test/itm/12345")["asset_id"]
        cell = self._cell(client.get(f"/parts/{aid}").text, "Source")
        assert 'href="https://www.ebay.test/itm/12345"' in cell

    def test_a_url_in_a_history_note(self, client, part):
        aid = part()["asset_id"]
        client.post(f"/parts/{aid}/note",
                    data={"message": "recapped, see http://forum.test/t/9911"},
                    follow_redirects=False)
        page = client.get(f"/parts/{aid}").text
        msg = page[page.index('class="logmsg"'):]
        msg = msg[:msg.index("</div>")]
        assert 'href="http://forum.test/t/9911"' in msg

    def test_a_part_number_is_not_a_hostname(self, client, part):
        aid = part(type="cpu", notes="boots from config.sys on a 1.44MB floppy")["asset_id"]
        cell = self._cell(client.get(f"/parts/{aid}").text, "Notes")
        assert "<a " not in cell
        assert "boots from config.sys on a 1.44MB floppy" in cell

    def test_the_note_around_the_link_is_still_text(self, client, part):
        aid = part(type="cpu",
                   notes="<b>bent pin</b> — http://x.test/p\nsecond line")["asset_id"]
        cell = self._cell(client.get(f"/parts/{aid}").text, "Notes")
        assert "<b>" not in cell and "&lt;b&gt;bent pin&lt;/b&gt;" in cell
        assert 'class="lines"' in cell and "\nsecond line" in cell


class TestADisplayPart:
    """A screen is a part with a table of its own, which is what makes "every CRT",
    "every 14-inch and under" and "every Trinitron" questions rather than text
    searches. Filed as a peripheral, which is where monitors used to go, none of
    them were answerable.
    """

    def test_the_form_records_what_a_screen_is(self, client):
        """Every answer picked from the group it is offered in, and the sockets
        ticked rather than chosen between."""
        r = client.post("/parts/new",
                        data={"type": "display", "manufacturer": "Sony",
                              "model": "GDM-F520", "spec_type": "CRT",
                              "spec_panel": "Aperture grille (Trinitron)",
                              "spec_screen_size": '21"', "spec_aspect": "4:3",
                              "spec_resolution": "1600×1200",
                              "spec_refresh": "85 Hz", "spec_dot_pitch": "0.25 mm",
                              "spec_interface": ["VGA (HD-15)", "BNC"],
                              "spec_picture": "Colour"},
                        follow_redirects=False)
        assert r.status_code == 303
        aid = r.headers["location"].rsplit("/", 1)[-1]
        assert client.get(f"/api/parts/{aid}").json()["specs"] == (
            'Type: CRT | Panel: Aperture grille (Trinitron) | Screen size: 21" | '
            "Aspect: 4:3 | Resolution: 1600×1200 | Refresh: 85 Hz | "
            "Dot pitch: 0.25 mm | Interface: VGA (HD-15), BNC | Picture: Colour")

    def test_an_answer_that_is_not_offered_is_typed_beside_custom(self, client):
        aid = client.post("/parts/new",
                          data={"type": "display", "spec_type": "custom",
                                "spec_type_custom": "Nixie tube",
                                "spec_screen_size": "custom",
                                "spec_screen_size_custom": '2.5"'},
                          follow_redirects=False
                          ).headers["location"].rsplit("/", 1)[-1]
        assert client.get(f"/api/parts/{aid}").json()["specs"] == \
            'Type: Nixie tube | Screen size: 2.5"'

    def test_a_socket_the_list_does_not_name_joins_the_ticked_ones(self, client):
        aid = client.post("/parts/new",
                          data={"type": "display",
                                "spec_interface": ["SCART", "RF"],
                                "spec_interface_custom": "6-pin DIN"},
                          follow_redirects=False
                          ).headers["location"].rsplit("/", 1)[-1]
        assert client.get(f"/api/parts/{aid}").json()["specs"] == \
            "Interface: SCART, RF, 6-pin DIN"

    def test_an_answer_never_offered_is_refused_rather_than_kept(self, client):
        """A group's answer is checked against the list it was offered from, the
        same way a drive's is: something posted straight at the endpoint that was
        never on the form is not an answer to the question that was asked."""
        aid = client.post("/parts/new",
                          data={"type": "display", "spec_type": "Cathode ray",
                                "spec_aspect": "4:3"},
                          follow_redirects=False
                          ).headers["location"].rsplit("/", 1)[-1]
        assert client.get(f"/api/parts/{aid}").json()["specs"] == "Aspect: 4:3"

    def test_the_groups_are_built_from_the_one_table(self, client):
        """The form and the server read the same list, so a question cannot appear
        on screen that the server passes over."""
        from app import entry
        page = client.get("/parts/new?type=display").text
        for ask in entry.DISPLAY_ASKS:
            field = "spec_" + ask["key"].lower().replace(" ", "_")
            kind = "checkbox" if ask.get("multi") else "radio"
            assert f'type="{kind}" name="{field}"' in page, ask["key"]
            from markupsafe import escape
            for option in ask["options"]:
                assert f'value="{escape(option)}"' in page, \
                    f'{ask["key"]}: {option}'

    def test_a_screen_records_every_refresh_rate_it_does(self, client, db):
        """The 50 Hz is the point: a tube that meets a television-rate mode and also
        does 85 Hz at its best VGA one is two useful screens, and recording only the
        higher figure would answer the question nobody driving an Archimedes asks."""
        from app.models import DisplaySpec
        aid = client.post("/parts/new",
                          data={"type": "display", "spec_type": "CRT",
                                "spec_refresh": ["50 Hz", "60 Hz", "85 Hz"]},
                          follow_redirects=False
                          ).headers["location"].rsplit("/", 1)[-1]
        assert client.get(f"/api/parts/{aid}").json()["specs"] == \
            "Type: CRT | Refresh: 50 Hz, 60 Hz, 85 Hz"
        assert db.get(DisplaySpec, aid).refresh == "50 Hz, 60 Hz, 85 Hz"

    def test_a_screen_with_two_rates_records_both(self, client, db):
        """The reason the rates are ticked rather than chosen between: a tube that
        locks to 15 kHz and to 31 kHz does both, and made to choose, its record
        would have to leave out the half that makes it worth owning."""
        from app.models import DisplaySpec
        aid = client.post("/parts/new",
                          data={"type": "display", "spec_type": "CRT",
                                "spec_screen_size": '14"',
                                "spec_sync": ["15 kHz", "31 kHz"],
                                "spec_interface": ["9-pin TTL (CGA)"]},
                          follow_redirects=False
                          ).headers["location"].rsplit("/", 1)[-1]
        assert client.get(f"/api/parts/{aid}").json()["specs"] == (
            'Type: CRT | Screen size: 14" | Sync: 15 kHz, 31 kHz | '
            "Interface: 9-pin TTL (CGA)")
        assert db.get(DisplaySpec, aid).sync == "15 kHz, 31 kHz"

    def test_a_multiscan_records_the_range_it_claims(self, client, db):
        """An Acorn AKF18 is 15-38 kHz by its user guide -- a range, not a set --
        and ticking every figure inside it would be recording rates nobody stated.
        So the box takes the range, the same box a socket the list cannot name goes
        in."""
        from app.models import DisplaySpec
        aid = client.post("/parts/new",
                          data={"type": "display", "manufacturer": "Acorn",
                                "model": "AKF18", "spec_type": "CRT",
                                "spec_sync_custom": "15–38 kHz"},
                          follow_redirects=False
                          ).headers["location"].rsplit("/", 1)[-1]
        assert client.get(f"/api/parts/{aid}").json()["specs"] == \
            "Type: CRT | Sync: 15–38 kHz"
        assert db.get(DisplaySpec, aid).sync == "15–38 kHz"

    def test_the_numbers_land_in_typed_columns(self, db, part):
        """Not in the string. A screen size sorts against other screen sizes, which
        is the whole point of the table. The two rates are not among them: each holds
        a set or a range, and so is text -- see the two tests above."""
        from app.models import DisplaySpec
        aid = part(type="display",
                   specs='Screen size: 13.3" | Dot pitch: 0.28 mm')["asset_id"]
        row = db.get(DisplaySpec, aid)
        assert (row.screen_in_tenths, row.dot_pitch_um) == (133, 280)

    def test_a_trinitron_is_still_found_by_asking_for_crts(self, db, part):
        from app.models import DisplaySpec
        part(type="display", model="GDM-F520",
             specs="Type: CRT | Panel: Aperture grille (Trinitron)")
        part(type="display", model="1084S", specs="Type: CRT | Panel: Shadow mask")
        part(type="display", model="ThinkVision", specs="Type: LCD | Panel: IPS")
        crts = db.query(DisplaySpec).filter(DisplaySpec.tech == "CRT").all()
        assert len(crts) == 2

    def test_the_form_reopens_on_what_it_saved(self, client, part):
        """The answers come back checked, in the units a person writes: the group
        sits on 21", not on 210."""
        aid = part(type="display",
                   specs='Type: CRT | Screen size: 21" | Dot pitch: 0.25 mm | '
                         "Refresh: 85 Hz")["asset_id"]
        page = client.get(f"/parts/{aid}/edit").text
        for field, value in (("spec_type", "CRT"), ("spec_screen_size", '21"'),
                             ("spec_dot_pitch", "0.25 mm"),
                             ("spec_refresh", "85 Hz")):
            # markupsafe, not html.escape: Jinja writes a quote as &#34;.
            from markupsafe import escape
            assert re.search(
                f'name="{field}" value="{re.escape(str(escape(value)))}"'
                r'[^>]*\schecked', page), field

    def test_a_saved_answer_from_outside_the_list_reopens_on_custom(self, client,
                                                                    part):
        """Somebody else's record, or one typed before the list said otherwise, is
        not lost by being reopened: the group chooses custom and the box holds it."""
        aid = part(type="display", specs="Type: Vacuum fluorescent")["asset_id"]
        page = client.get(f"/parts/{aid}/edit").text
        assert re.search(r'name="spec_type" value="custom"[^>]*\schecked', page)
        assert 'id="spec_type_custom" name="spec_type_custom"' in page
        assert "Vacuum fluorescent" in page
        # And saving it again keeps it.
        client.post(f"/parts/{aid}/edit",
                    data={"type": "display", "spec_type": "custom",
                          "spec_type_custom": "Vacuum fluorescent"},
                    follow_redirects=False)
        assert client.get(f"/api/parts/{aid}").json()["specs"] == \
            "Type: Vacuum fluorescent"

    def test_editing_a_screen_keeps_its_numbers(self, client, part):
        aid = part(type="display", specs='Type: CRT | Screen size: 14"')["asset_id"]
        client.post(f"/parts/{aid}/edit",
                    data={"type": "display", "spec_type": "CRT",
                          "spec_screen_size": '14"', "spec_picture": "Amber"},
                    follow_redirects=False)
        assert client.get(f"/api/parts/{aid}").json()["specs"] == \
            'Type: CRT | Screen size: 14" | Picture: Amber'

    def test_a_screen_records_a_bezel_like_a_drive(self, client):
        r = client.post("/parts/new",
                        data={"type": "display", "spec_type": "CRT",
                              "spec_colour": "Beige",
                              "spec_yellowing": "Heavily yellowed"},
                        follow_redirects=False)
        aid = r.headers["location"].rsplit("/", 1)[-1]
        assert client.get(f"/api/parts/{aid}").json()["specs"] == \
            "Type: CRT | Colour: Beige | Yellowing: Heavily yellowed"

    def test_the_page_shows_the_swatch_for_the_pair(self, client, part):
        from app import entry
        aid = part(type="display",
                   specs="Colour: Beige | Yellowing: Yellowed")["asset_id"]
        css = entry.bezel_css("Beige", "Yellowed")
        assert client.get(f"/parts/{aid}").text.count(
            f'style="background:{css}"') == 2

    def test_a_screen_with_no_photograph_gets_a_monitor(self, client, part):
        """Rather than the box every unrecognised type falls back to."""
        aid = part(type="display", model="1084S")["asset_id"]
        assert "placeholders/monitor.svg" in client.get(f"/parts/{aid}").text

    def test_the_small_label_leads_with_the_size_and_the_tube(self):
        """What identifies a monitor across a room. Joined on one line, because "a
        21-inch Trinitron CRT" is one thing said and not three."""
        from app import labels
        _, lines = labels.small_body(
            {"asset_id": "RH-0044", "name": "Sony GDM-F520", "type": "display",
             "specs": 'Type: CRT | Panel: Aperture grille (Trinitron) | '
                      'Screen size: 21" | Resolution: 1600×1200 | '
                      "Interface: VGA (HD-15)"}, False)
        assert lines == ['21" Aperture grille (Trinitron) CRT', "1600×1200",
                         "VGA (HD-15)"]

    def test_it_reaches_the_printed_label(self, client, part):
        aid = part(type="display", model="GDM-F520",
                   specs='Type: CRT | Screen size: 21"')["asset_id"]
        pdf = client.get(f"/parts/{aid}/label.pdf?small=1")
        assert pdf.status_code == 200 and pdf.content[:4] == b"%PDF"

    def test_the_type_menu_offers_it(self, client):
        assert '<option value="display"' in client.get("/parts/new").text


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

    def test_the_sitemap_omits_pages_it_does_not_want_indexed(self, client):
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
        assert self.body(db, aid) == ("Seagate ST-225", ["20 MiB"])

    def test_a_drive_with_no_capacity_recorded_just_says_what_it_is(self, client, db,
                                                                   part):
        """Half the drives on file have no capacity against them; none of them should
        get a blank line held open for one."""
        aid = part(type="storage", manufacturer="Mitsumi", model="D503V",
                   specs="Kind: Floppy/Gotek")["asset_id"]
        assert self.body(db, aid) == ("Mitsumi D503V", [])

    def test_capacity_worked_out_from_the_geometry_counts_too(self, client, db, part):
        """A drive recorded by its cylinders/heads/sectors has its capacity derived
        rather than stated, and the label carries that just the same. 38828 KiB is
        a 38 MiB drive, and the label says so rather than reciting the KiB."""
        aid = part(type="storage", manufacturer="Quantum", model="LPS 52A",
                   specs="Kind: Hard disk | CHS: 571/8/17")["asset_id"]
        assert self.body(db, aid) == ("Quantum LPS 52A", ["37.9 MiB", "CHS 571/8/17"])

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
        assert "Capacity: 20 MiB" in lines

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
    """A quantity is stored as plain KiB and said in whatever unit suits. Text that is
    only ever read -- a page, a label -- rounds an amount that cannot be said exactly.
    The edit form keeps it to the KiB, because what the form shows is parsed back on
    the next save, and a rounded figure would quietly move the number.
    """

    # 571x8x17 sectors of 512 bytes: 38828 KiB, which is not a whole MiB and cannot
    # be written as one to two decimal places either.
    SPECS = "Kind: Hard disk | CHS: 571/8/17"

    def make(self, part):
        return part(type="storage", manufacturer="Quantum", model="LPS 52A",
                    specs=self.SPECS)["asset_id"]

    def test_the_page_says_it_the_way_a_person_would(self, client, part):
        aid = self.make(part)
        page = client.get(f"/parts/{aid}").text
        assert "37.9 MiB" in page
        assert "38828 KiB" not in page

    def test_the_form_is_given_it_to_the_kilobyte(self, client, part):
        aid = self.make(part)
        page = client.get(f"/parts/{aid}/edit").text
        assert 'name="spec_capacity" value="38828 KiB"' in page
        assert "37.9 MiB" not in page

    def test_saving_that_form_back_untouched_does_not_move_the_number(self, client,
                                                                     db, part):
        """The corruption the split exists to prevent. Had the form been handed
        '37.9 MiB', saving it without touching it would have written 38810 KiB.

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
        assert "38828 KiB" in db.get(Part, aid).specs

    @pytest.mark.parametrize("typed,shown", [
        ("2 MB", "2 MiB"),         # was rendered back as '2048 KiB'
        ("1024 KB", "1 MiB"),
        ("8192 KiB", "8 MiB"),
        ("640 KiB", "640 KiB"),
    ])
    def test_memory_is_said_in_megabytes_where_that_is_the_word_for_it(
            self, client, db, part, typed, shown):
        """Not only drives: a 2 MiB SIMM read '2048 KiB' on every page it appeared on."""
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
        assert "nav-next" in page

    def test_a_swipe_across_the_page_is_left_to_the_browser(self, client, part):
        """Walking the register is the two buttons' job. A sideways swipe is how a
        phone goes back, and the page taking it over left no way to leave an item.
        The lightbox still binds touches, but only on itself."""
        page = client.get(f"/parts/{part()['asset_id']}").text
        assert not re.search(r"(?<![.\w])addEventListener\('touch", page)


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
        assert copy["installed_ram"] == "4× 1MiB 30-pin (4 MiB)"
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
        assert '<button class="btn sm" type="submit" data-send-go>' in page


class TestTheCodeThatPutsAPhoneOnTheItem:
    """An item page ends in a QR of its own URL, because the register is edited at a
    desk and the hardware is photographed on the bench: the camera that takes the
    picture belongs to the phone, and this is how the phone gets to the right item
    without anyone typing an asset tag into it.

    It says the page's own address rather than the /items/<tag> one the labels carry,
    so there is no redirect between the code and the upload button.
    """

    def expected(self, kind, aid):
        from app import labels
        return labels.qr_svg(f"https://example.test/{kind}/{aid}#photo-upload")

    def test_a_machine_page_carries_a_code_for_its_own_url(self, client, computer):
        aid = computer()["asset_id"]
        assert self.expected("computers", aid) in client.get(f"/computers/{aid}").text

    def test_a_part_page_carries_one_too(self, client, part):
        """Not only machines: a card or a drive is photographed off the bench as
        often as the machine it came out of."""
        aid = part()["asset_id"]
        assert self.expected("parts", aid) in client.get(f"/parts/{aid}").text

    def test_the_code_lands_on_something_that_is_really_there(self, client, part):
        """The fragment is the upload form's own id, and the code sits in the same
        column as that form -- a desktop being scanned from across the bench."""
        page = client.get(f"/parts/{part()['asset_id']}").text
        assert 'id="photo-upload"' in page

    @staticmethod
    def in_the_photo_column(page):
        """Whether the QR block is nested inside the item page's right-hand column,
        rather than sitting under the two columns as it once did."""
        # div and section alike: the column is a div and the blocks inside it are
        # panels, which are sections.
        boxes = ("div", "section")

        class Nesting(HTMLParser):
            def __init__(self):
                super().__init__()
                self.open, self.found = [], False

            def handle_starttag(self, tag, attrs):
                if tag not in boxes:
                    return
                cls = dict(attrs).get("class", "").split()
                self.open.append(cls)
                if "photo-qr" in cls:
                    self.found = any("photo-col" in c for c in self.open)

            def handle_endtag(self, tag):
                if tag in boxes and self.open:
                    self.open.pop()

        parser = Nesting()
        parser.feed(page)
        return parser.found

    @pytest.mark.parametrize("kind", ["computers", "parts"])
    def test_the_code_rides_in_the_photo_column(self, client, computer, part, kind):
        aid = (computer() if kind == "computers" else part())["asset_id"]
        assert self.in_the_photo_column(client.get(f"/{kind}/{aid}").text)

    def test_it_is_a_standard_symbol_not_a_micro_one(self):
        """Same reason as the labels: most readers, the gallery's own scanner
        included, decode standard QR only."""
        from app import labels
        svg = labels.qr_svg("https://example.test/parts/RH-0001#photo-upload")
        side = int(re.search(r'viewBox="0 0 (\d+) ', svg).group(1))
        assert side >= 21 + 2 * 2                       # smallest standard, plus border

    def test_a_visitor_is_not_offered_one(self, client, part, monkeypatch):
        """A code leading to a page with no upload button on it is a promise the site
        will not keep. Auth is off in these tests, so this asks for it."""
        from app import main
        aid = part()["asset_id"]
        monkeypatch.setattr(main, "AUTH_ENABLED", True)
        page = client.get(f"/parts/{aid}").text
        assert 'class="section photo-qr"' not in page   # the block, not the stylesheet
        assert self.expected("parts", aid) not in page

    def test_a_phone_that_arrives_logged_out_is_sent_back_to_the_item(
            self, client, part, monkeypatch):
        """Scanning is most of the way to the picture; being handed the gallery after
        logging in and told to find the thing in your hands again is not."""
        from app import main
        aid = part()["asset_id"]
        monkeypatch.setattr(main, "AUTH_ENABLED", True)
        # The header shows a log-in button only where there is a login to do, and
        # the template reads that from a global settled at import.
        monkeypatch.setitem(main.templates.env.globals, "auth_enabled", True)
        assert f'href="/login?next=/parts/{aid}"' in client.get(f"/parts/{aid}").text


class TestLoggingOutStaysWhereYouAre:
    """Logging in comes back to the page you asked for. Logging out dropped you at
    the front door, whatever you had been reading -- and the two are the same
    courtesy from opposite ends."""

    def test_it_goes_back_to_the_page_it_was_done_from(self, client, part):
        aid = part()["asset_id"]
        r = client.post("/logout", data={"next": f"/parts/{aid}"},
                        follow_redirects=False)
        assert r.status_code == 303 and r.headers["location"] == f"/parts/{aid}"

    def test_a_search_is_part_of_where_you_were(self, client):
        """The gallery with a search in the address is not the gallery."""
        r = client.post("/logout", data={"next": "/?q=amiga&sort=year"},
                        follow_redirects=False)
        assert r.headers["location"] == "/?q=amiga&sort=year"

    def test_an_edit_form_lands_on_the_item_it_was_editing(self, client, part):
        """The form is behind the login, so going back to it would bounce straight
        to the login just left. The item behind it is public, and is what was being
        looked at anyway."""
        aid = part()["asset_id"]
        r = client.post("/logout", data={"next": f"/parts/{aid}/edit"},
                        follow_redirects=False)
        assert r.headers["location"] == f"/parts/{aid}"

    @pytest.mark.parametrize("nxt", [
        "/computers/new",            # nothing behind it yet
        "/parts/RH-0001/delete",     # a door, not a page
        "/computers/RH-0001/label.pdf",
        "/api/parts", "/docs",
        "//evil.test/x", "https://evil.test/x", "",   # and not off the site at all
    ])
    def test_anything_else_is_the_gallery(self, client, nxt):
        r = client.post("/logout", data={"next": nxt}, follow_redirects=False)
        assert r.headers["location"] == "/"

    def _as_logged_in(self, monkeypatch):
        from app import main
        monkeypatch.setattr(main, "AUTH_ENABLED", True)
        monkeypatch.setattr(main, "_check_cookie", lambda request: True)
        monkeypatch.setitem(main.templates.env.globals, "auth_enabled", True)

    def test_the_form_carries_the_page_it_is_on(self, client, part, monkeypatch):
        self._as_logged_in(monkeypatch)
        aid = part()["asset_id"]
        page = client.get(f"/parts/{aid}?photo=front.jpg").text
        assert (f'<input type="hidden" name="next"'
                f' value="/parts/{aid}?photo=front.jpg">') in page

    def test_the_way_in_carries_it_the_same_way(self, client, part, monkeypatch):
        from app import main
        aid = part()["asset_id"]
        monkeypatch.setattr(main, "AUTH_ENABLED", True)
        monkeypatch.setitem(main.templates.env.globals, "auth_enabled", True)
        page = client.get(f"/parts/{aid}?photo=front.jpg").text
        assert f'href="/login?next=/parts/{aid}%3Fphoto%3Dfront.jpg"' in page


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
        """The boxes, specifically, and not the whole page. `source` carries a pick
        list of everywhere the collection has ever got anything from, and "eBay" is
        on it -- being offered the answer is the opposite of being given it, which
        is the distinction this test is about."""
        import re
        src = part(manufacturer="Tseng", model="ET4000", source="eBay",
                   acquired_date="2026-01-05", notes="a bit bent")
        page = client.get(f"/parts/new?from={src['asset_id']}").text
        for field in ("source", "acquired_date"):
            box = re.search(rf'<input[^>]*\bname="{field}"[^>]*>', page, re.S)
            assert box, field
            assert re.search(r'value="[^"]+"', box.group(0)) is None, box.group(0)
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
        assert "8 MiB" in client.get("/stats").text

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
        """Every /browse link the page renders, as a browser would read it.

        Unescaped, because a link built in Python and interpolated into the attribute
        comes out with its separator as `&amp;` -- which is the correct way to write
        an `&` in HTML, and what a browser turns back into `&` before requesting it.
        Comparing the raw attribute would be testing the escaping, not the link."""
        return sorted({html.unescape(h)
                       for h in re.findall(r'href="(/browse\?[^"]*)"', page)})

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
        otherwise stay hidden until someone clicked that one tile.

        Over several renders rather than one: the tiles are eight drawn from a much
        larger pool now, so a single render sweeps only the eight it happened to deal
        -- and a threshold on one draw is a test that fails on an unlucky shuffle."""
        self._a_bit_of_everything(client, computer, part)
        offered = set()
        for _ in range(20):
            offered |= set(self._offered(client.get("/stats").text))
        # Both ends of the hero, every bar in the ranked lists, and by now most of
        # the pool's tiles.
        assert len(offered) > 15
        for href in sorted(offered):
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


class TestEveryObjectHasItsPortrait:
    """How many things still here have no photograph of themselves, and which ones.

    Every object in the register is meant to have a portrait: that is what makes the
    register checkable against the shelf by somebody who was not there when it was
    written. So this figure is not a curiosity like the rest of /stats -- it is a job
    list, it stands outside the shuffle, and the queue behind it has to be the same
    answer as the number, not a second opinion that resembles it.

    The truth is the filesystem, because that is what the item page and the gallery
    card draw. The `image` column is a note of which file was chosen last, and on the
    live register a dozen rows have a photograph on disk and a blank column.
    """

    @pytest.fixture
    def shoot(self):
        """Put a photograph on disk under a name of the test's choosing. The
        register is emptied between tests; the image folders are not, so what a test
        writes it takes away again."""
        written = []

        def make(kind, stem):
            folder = main.IMAGES_DIR / kind
            folder.mkdir(parents=True, exist_ok=True)
            f = folder / f"{stem}.jpg"
            f.write_bytes(b"not really a jpeg")
            written.append(f)
            return f
        yield make
        for f in written:
            f.unlink(missing_ok=True)

    @staticmethod
    def standing(page):
        """The coverage line under the headline, whitespace flattened the way a
        browser reads it."""
        m = re.search(r'<p class="cover">(.*?)</p>', page, re.S)
        return " ".join(m.group(1).split()) if m else ""

    def counted(self, page):
        m = re.search(r'<span class="n">(\d+)</span>', self.standing(page))
        return int(m.group(1)) if m else None

    @staticmethod
    def queued(page):
        """The asset ids the queue behind the figure lists."""
        return sorted(href.rsplit("/", 1)[1]
                      for href in re.findall(r'class="card" href="([^"]+)"', page))

    def test_the_figure_is_on_the_page_every_visit(self, client, computer):
        """The tiles are eight drawn from a pool of dozens, so a figure in there is
        on the page perhaps a quarter of the time. A work queue that turns up on some
        visits and not others is not a work queue."""
        computer()
        for _ in range(12):
            assert "have no portrait yet" in self.standing(client.get("/stats").text)

    def test_it_is_not_dealt_into_the_shuffle_as_well(self, client, db, computer,
                                                      part):
        """Promoted out, not copied out. A figure in both places would come up beside
        itself on a fair fraction of renders, which reads as the shuffle being broken
        -- and gui_stats' own guard against that compares tiles with each other, not
        with the rest of the page, so it could not catch this one."""
        computer()
        part()
        pool = main._facts(db, main._collection_stats(db), date.today().year)
        assert pool                                   # or this proves nothing
        assert not [f for f in pool if f["href"] == "/browse?f=nophotos"]

    def test_the_figure_and_the_queue_are_the_same_answer(self, client, computer,
                                                          part, shoot):
        """The whole point of the stage. The headline said five and the list behind
        it named fourteen, which means one of them was wrong and a visitor had no way
        to tell which."""
        seen = part()["asset_id"]
        shoot("parts", seen)
        unseen = sorted([computer()["asset_id"], part()["asset_id"]])
        assert self.counted(client.get("/stats").text) == 2
        assert self.queued(client.get("/browse?f=nophotos").text) == unseen

    def test_what_has_gone_is_not_waiting_for_a_camera(self, client, part):
        """A disposed item is a record of something that has left, and nobody can go
        and photograph it. It was the disposed that made the two numbers differ: the
        figure counted only what is held, the list counted everything."""
        gone = part(model="binned")["asset_id"]
        client.patch(f"/api/parts/{gone}", json={"disposed": True})
        here = part(model="here")["asset_id"]
        assert self.counted(client.get("/stats").text) == 1
        assert self.queued(client.get("/browse?f=nophotos").text) == [here]

    def test_a_photograph_of_what_happened_is_not_a_portrait(self, client, computer):
        """Six pictures of a recap say what happened to a machine. They do not say
        which machine this is, so an object with nothing but those is still an object
        nobody has photographed in the sense this figure means.

        Two things keep them out and either would do it alone -- they are in log/,
        which the count never reads, and they are filed under the history entry's id
        rather than the asset's -- so this is a lock on the promise rather than on
        one line of it. That is the point: the promise is what someone reading the
        figure relies on, and the next person to touch either half should find out
        here that both halves were meant."""
        import io

        from PIL import Image
        aid = computer()["asset_id"]
        buf = io.BytesIO()
        Image.new("RGB", (400, 300), (60, 90, 120)).save(buf, "JPEG", quality=90)
        buf.seek(0)
        client.post(f"/computers/{aid}/note", data={"message": "recapped it"},
                    files={"photos": ("shot.jpg", buf, "image/jpeg")},
                    follow_redirects=False)
        assert self.counted(client.get("/stats").text) == 1
        assert self.queued(client.get("/browse?f=nophotos").text) == [aid]

    def test_a_photograph_named_for_the_side_it_shows_still_counts(self, client,
                                                                   part, shoot):
        """RH-0001-back-left is the part's photograph the same way RH-0001-2 is, and
        the gallery has always thought so. The count used to take one hyphen off the
        stem and not the second, so a folder of them would have left the part in the
        queue while its picture was on its page."""
        aid = part()["asset_id"]
        shoot("parts", f"{aid}-back-left")
        assert main.detect_images("parts", aid) == [f"parts/{aid}-back-left.jpg"]
        assert "Every one of them" in self.standing(client.get("/stats").text)
        assert self.queued(client.get("/browse?f=nophotos").text) == []

    def test_a_photograph_in_the_wrong_folder_is_nobody_s_portrait(self, client,
                                                                   computer, shoot):
        """A picture in parts/ is a picture of a part. Filed under a machine's tag it
        is not the machine's portrait -- the machine's page does not show it -- so it
        must not answer the machine's question either."""
        aid = computer()["asset_id"]
        shoot("parts", aid)
        assert main.detect_images("computers", aid) == []
        assert self.counted(client.get("/stats").text) == 1
        assert self.queued(client.get("/browse?f=nophotos").text) == [aid]

    def test_a_register_that_is_all_photographed_says_so(self, client, part, shoot):
        """The end of the job is a state worth rendering, not a blank."""
        shoot("parts", part()["asset_id"])
        line = self.standing(client.get("/stats").text)
        assert "Every one of them" in line and "no portrait" not in line

    def test_an_empty_register_claims_nothing(self, client):
        """"Every one of them has had its portrait taken" is true of nothing and
        reads as a boast on a fresh install."""
        page = client.get("/stats")
        assert page.status_code == 200
        assert self.standing(page.text) == ""


class TestTheCataloguePage:
    """The catalogue read rather than picked from: every machine the register knows
    as a model, on one page.

    It exists because "does it know my machine?" is asked before anything is typed,
    and the two answers that existed -- a text file in the repository and a JSON
    endpoint -- are not answers you can give somebody with a link.
    """

    def test_every_model_in_the_catalogue_is_on_it(self, client):
        from app import machines
        page = client.get("/machines").text
        for m in machines.models():
            assert html.escape(m["model"]) in page, m["key"]

    def test_it_says_which_of_them_are_actually_here(self, client, computer, db):
        """The other view of the catalogue: not what was made, but how much of it
        is on the shelf."""
        from app.models import Computer
        aid = computer()["asset_id"]
        client.patch(f"/api/computers/{aid}", json={"machine": {"model_key": "c64"}})
        page = client.get("/machines").text
        assert 'title="1 in the register"' in page
        assert ">(1)</a>" in page
        assert '/browse?f=model&amp;v=c64' in page
        assert db.get(Computer, aid) is not None

    def test_a_model_nothing_is_filed_as_says_nothing(self, client):
        """Most of the catalogue is machines this collection has not got, which is
        the ordinary state and reads as a catalogue rather than as a gap."""
        page = client.get("/machines").text
        assert 'class="got"' not in page

    def test_the_count_leads_to_the_machines_behind_it(self, client, computer, part):
        """A board files as a model the same way a whole machine does, so both turn
        up here -- that is what the catalogue's board side is for."""
        c = computer()["asset_id"]
        p = part(type="motherboard")["asset_id"]
        client.patch(f"/api/computers/{c}", json={"machine": {"model_key": "amiga-500"}})
        client.patch(f"/api/parts/{p}", json={"machine": {"model_key": "amiga-500"}})
        page = client.get("/browse?f=model&v=amiga-500").text
        assert sorted(re.findall(r'class="card" href="[^"]*/([A-Z0-9-]+)"', page)) \
            == sorted([c, p])

    def test_a_model_the_catalogue_never_had_is_a_404(self, client):
        assert client.get("/browse?f=model&v=zx-spectrum-1024k").status_code == 404

    def test_it_is_public(self, client, monkeypatch):
        """The whole point of the page. It holds nothing of the register -- it is
        what was made, not what is here -- so there is nothing on it to sign in
        for, and the JSON behind it is public for the same reason."""
        from app import main
        monkeypatch.setattr(main, "AUTH_ENABLED", True)
        for path in ("/machines", "/api/machines"):
            r = client.get(path, follow_redirects=False)
            assert r.status_code == 200, path

    def test_the_rest_of_the_api_is_still_not(self, client, monkeypatch):
        from app import main
        monkeypatch.setattr(main, "AUTH_ENABLED", True)
        assert client.get("/api/computers", follow_redirects=False).status_code == 401

    def test_it_is_offered_to_search_engines(self, client):
        assert "/machines</loc>" in client.get("/sitemap.xml").text
        assert "Disallow: /machines" not in client.get("/robots.txt").text


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

    def test_the_zoom_is_not_shut_inside_the_photo_shape(self, client, part):
        """A tall photo opens with a black band either side of it, and zooming in
        used to magnify within that same tall rectangle -- the band stayed black
        and most of the screen went unused. The zoom rides on a wrapper inside a
        stage sized to the window rather than on the photo's own box, which is
        what lets the enlarged photo spread into the band."""
        aid = part()["asset_id"]
        rel = self.upload(client, "parts", aid)
        try:
            page = served(client, client.get(f"/parts/{aid}").text)
            assert '<div class="lb-fit" id="lb-fit">' in page
            assert "#lightbox .lb-stage { position: relative; width: 92vw; height: 84vh;" in page
            assert "fit.style.transform = " in page
        finally:
            client.post(f"/parts/{aid}/photo-delete", data={"image": rel},
                        follow_redirects=False)

    def test_a_mac_trackpad_is_answered_in_both_of_the_ways_it_is_reported(
            self, client, part):
        """A pinch on a trackpad reaches the page as ctrl+wheel in Chrome and in
        Firefox, and as Safari's own gesture events, which are non-standard and
        the only report Safari sends -- so both are listened for. The wheel is
        swallowed whichever it turns out to be: left alone, a sideways one is
        Safari swiping back out of the page, and one with a modifier is the
        browser zooming the page, banner and all."""
        aid = part()["asset_id"]
        rel = self.upload(client, "parts", aid)
        try:
            page = client.get(f"/parts/{aid}").text
            assert "addEventListener('gesturestart'" in page
            assert "addEventListener('gesturechange'" in page
            assert "e.ctrlKey || e.metaKey" in page
            assert re.search(r"'wheel', e => \{\s*if \(cropping\(\)\) return;"
                             r"\s*(//[^\n]*\n\s*)*e.preventDefault\(\);", page)
        finally:
            client.post(f"/parts/{aid}/photo-delete", data={"image": rel},
                        follow_redirects=False)

    def test_a_photograph_on_a_phone_is_flicked_away_to_close_it(self, client, part):
        """A photograph at its own size on a phone is not on a page you can leave,
        and the close button is a small target in a corner. So it goes the way
        anything goes on iOS: pushed off the screen, coming with the finger and
        letting the page behind show through, and back again if the finger changes
        its mind. Zoomed in, the same drag moves about the photograph, so this is
        the fitted one only -- and a mouse is left out, having a button and a key
        for the job."""
        aid = part()["asset_id"]
        rel = self.upload(client, "parts", aid)
        try:
            page = client.get(f"/parts/{aid}").text
            assert "function away(dx, dy)" in page
            assert "e.pointerType !== 'mouse'" in page
            assert "Math.abs(dy) > AWAY" in page
        finally:
            client.post(f"/parts/{aid}/photo-delete", data={"image": rel},
                        follow_redirects=False)

    def test_a_trip_home_cut_short_still_puts_the_overlay_away(self, client, part):
        """The overlay closes by sending the photo back into its thumbnail, and
        while that is running the photo is uninterruptible -- which is the flag
        every way out of the big view checks before doing anything. Anything that
        stopped the movement threw away the trip's promise to put the overlay away
        with it, and the flag was left set for good: a photo frozen halfway home,
        over a page that could not be reached, and neither Escape nor the close
        button nor a click on the black would answer. A trackpad was enough to do
        it -- it goes on sending its momentum for a moment after the fingers lift,
        and that momentum landed in the middle of the trip."""
        aid = part()["asset_id"]
        rel = self.upload(client, "parts", aid)
        try:
            page = client.get(f"/parts/{aid}").text
            # Stopped mid-trip, the trip is finished rather than dropped
            assert "const done = tween && tween.then;" in page
            assert re.search(r"frame = null; tween = null; idle = null; vx = vy = 0;"
                             r"\s*if \(done\) done\(\);", page)
            # and the things that stop it leave a photo on its way home alone
            assert re.search(r"e\.preventDefault\(\);\s*if \(going\) return;", page)
            assert "if (cropping() || held.size || going) return;" in page
        finally:
            client.post(f"/parts/{aid}/photo-delete", data={"image": rel},
                        follow_redirects=False)

    def test_the_double_click_that_comes_back_out_of_a_zoom_is_heard(self, client,
                                                                     part):
        """Double click to go in, double click to come back out -- except the way
        back out was never heard. Panning a zoomed photo holds the pointer capture,
        and a captured pointer's click and double click are delivered to the
        element holding the capture rather than to the photo under the mouse, so a
        listener on the stage saw the one going in and none of the ones coming
        out. It is on the overlay, which is where they arrive."""
        aid = part()["asset_id"]
        rel = self.upload(client, "parts", aid)
        try:
            page = client.get(f"/parts/{aid}").text
            assert "box.addEventListener('dblclick'" in page
            assert "stage.addEventListener('dblclick'" not in page
        finally:
            client.post(f"/parts/{aid}/photo-delete", data={"image": rel},
                        follow_redirects=False)

    def test_a_click_on_a_zoomed_photo_is_not_a_click_on_the_black(self, client,
                                                                    part):
        """The same pointer capture makes a click on a zoomed photo arrive looking
        exactly like a click on the backdrop, which is the one click that means
        close -- so a zoomed photo dismissed itself at a touch. What the press
        landed on says which it was. The chrome keeps its own presses for the same
        reason: captured, the close button's own click went to the overlay instead
        of to the button."""
        aid = part()["asset_id"]
        rel = self.upload(client, "parts", aid)
        try:
            page = client.get(f"/parts/{aid}").text
            assert "downOn = e.target;" in page
            assert "if (!dragged && e.target === box && downOn === box) close();" in page
            assert "if (e.target.closest('button, #lb-tools')) return;" in page
        finally:
            client.post(f"/parts/{aid}/photo-delete", data={"image": rel},
                        follow_redirects=False)

    def test_the_whole_overlay_takes_the_gesture_not_just_the_photo(self, client,
                                                                     part):
        """On a phone most of what is on screen is the black around the photo, so
        a flick that starts there is still a flick -- and left to itself the phone
        scrolls the page underneath while the photo sits there doing nothing."""
        aid = part()["asset_id"]
        rel = self.upload(client, "parts", aid)
        try:
            page = served(client, client.get(f"/parts/{aid}").text)
            assert "box.addEventListener('pointerdown'" in page
            assert "box.addEventListener('pointermove'" in page
            assert re.search(r"#lightbox \{[^}]*touch-action: none", page, re.S)
        finally:
            client.post(f"/parts/{aid}/photo-delete", data={"image": rel},
                        follow_redirects=False)

    def test_the_movement_is_dropped_for_anyone_who_asked_for_less_of_it(
            self, client, part):
        """The glide, the spring at the edges and the eased zoom are all feel, and
        feel is exactly what a reader who has asked their system for less movement
        does not want. They get the same photo, put where it belongs at once."""
        aid = part()["asset_id"]
        rel = self.upload(client, "parts", aid)
        try:
            assert "matchMedia('(prefers-reduced-motion: reduce)')" in \
                client.get(f"/parts/{aid}").text
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
        page = served(client, client.get(f"/parts/{part()['asset_id']}").text)
        assert "[hidden] { display: none !important; }" in page

    def test_the_row_offers_a_delete(self, client, part):
        """Beside crop and the rotates, so a photograph that turned out badly goes
        from where you are looking at it rather than from the column behind."""
        aid = part()["asset_id"]
        rel = self.upload(client, "parts", aid)
        try:
            page = client.get(f"/parts/{aid}").text
            assert 'id="lb-delete"' in page
            assert 'data-act="photo-delete"' in page
        finally:
            client.post(f"/parts/{aid}/photo-delete", data={"image": rel},
                        follow_redirects=False)

    def test_it_asks_first(self, client, part):
        """The one tool in the row that cannot be undone, so it is the one that
        asks -- the same question the column's own delete asks."""
        page = client.get(f"/parts/{part()['asset_id']}").text
        assert page.count("Delete this photo? This cannot be undone.") >= 1
        assert re.search(r'id="lb-delete"[^>]*\n?\s*onsubmit="return confirm',
                         page) is not None

    def test_it_is_only_for_the_logged_in(self, client, part, monkeypatch):
        from app import main
        aid = part()["asset_id"]
        rel = self.upload(client, "parts", aid)
        try:
            monkeypatch.setattr(main, "AUTH_ENABLED", True)
            assert 'id="lb-delete"' not in client.get(f"/parts/{aid}").text
        finally:
            monkeypatch.setattr(main, "AUTH_ENABLED", False)
            client.post(f"/parts/{aid}/photo-delete", data={"image": rel},
                        follow_redirects=False)

    def test_it_carries_no_next_because_there_is_nowhere_to_return_to(
            self, client, part):
        """Its neighbours come back to the same photograph still open. A deleted one
        will not be there, so this form does not ask to be sent back to it -- and
        the script that fills the toolbar in has to cope with that."""
        page = client.get(f"/parts/{part()['asset_id']}").text
        form = page.split('id="lb-delete"')[1].split("</form>")[0]
        assert "name=\"image\"" in form and "name=\"next\"" not in form
        assert "const nxt = f.querySelector('[name=next]');" in page
        assert "if (nxt) nxt.value = back;" in page

    def test_deleting_from_the_view_lands_back_on_the_item(self, client, part):
        """Not on the photograph, which is the whole difference from a rotate."""
        aid = part()["asset_id"]
        rel = self.upload(client, "parts", aid)
        r = client.post(f"/parts/{aid}/photo-delete", data={"image": rel},
                        follow_redirects=False)
        assert r.status_code == 303 and r.headers["location"] == f"/parts/{aid}"
        assert client.get(f"/images/{rel}").status_code == 404
        assert "deleted a photo" in [
            e["message"] for e in client.get(f"/api/items/{aid}/log").json()]

    def test_it_steps_out_of_the_row_while_cropping(self, client, part):
        """Cropping puts an apply button where the row was. A delete left standing
        beside it is a misclick waiting to happen, so it goes with the crop
        button it sits next to."""
        page = client.get(f"/parts/{part()['asset_id']}").text
        assert "if (del) del.hidden = on;" in page

    def test_it_reads_as_the_destructive_one(self, client, part):
        """Colour is what says this tool is not like its neighbours, and the
        register's warning shade is unreadable on a black toolbar unlightened."""
        page = served(client, client.get(f"/parts/{part()['asset_id']}").text)
        assert "#lightbox .lb-tools .btn.danger" in page
        assert 'class="btn sm danger"' in page

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


class TestAPhotographIsNeverHalfWritten:
    """Cropping used to rewrite the photograph on top of itself. Saving onto a path
    truncates it first, so for as long as the encoder ran -- a tenth of a second for
    a phone photograph -- what was on disk was a fragment of a JPEG, and a fragment
    is what anything reading it at that moment got.

    That is not an error anybody notices. A fragment decodes to a picture that is
    half grey, so it is served, and both caches are built from whatever the file
    says when they look at it. Worse, an image URL carries a `?v=` stamp and is sent
    `immutable` for a year, so a browser handed the half-grey one keeps it.

    It was intermittent because it needed a reader inside that window -- another
    tab, a phone on the same item, the gallery. Writing beside the file and moving
    it into place closes the window: a reader holds either the whole old photograph
    or the whole new one.
    """

    @staticmethod
    def upload(client, aid, size=(1400, 1000)):
        import io
        from PIL import Image
        buf = io.BytesIO()
        # Noise rather than flat colour: a flat JPEG is small enough to write in one
        # go, and would hide the very window this is about.
        import random
        rnd = random.Random(7)
        im = Image.new("RGB", size)
        im.putdata([(rnd.randrange(256), rnd.randrange(256), rnd.randrange(256))
                    for _ in range(size[0] * size[1])])
        im.save(buf, "JPEG", quality=95)
        buf.seek(0)
        client.post(f"/parts/{aid}/photo",
                    files={"photos": (f"{aid}.jpg", buf, "image/jpeg")},
                    follow_redirects=False)
        return f"parts/{aid}.jpg"

    def test_a_reader_never_sees_a_fragment(self, client, part):
        """The regression itself, read where the bug was: on disk.

        Readers open the photograph over and over while it is cropped over and over.
        Every read must be a whole picture -- one size or the other, depending which
        side of a crop it landed -- and never a fragment.

        Deliberately not read over HTTP. Starlette's FileResponse takes the length
        from one stat and the bytes from a later open, so a file replaced between
        the two sends a short body: measured, 62 times in 18,155 reads while a file
        was replaced 400 times as fast as the disk would take it. That is a
        different fault from this one and a far smaller one -- a short body is a
        failed response, which a browser reports and does not cache, where a
        fragment on disk is a picture that is half grey, gets cached, and stays.
        """
        import threading
        from app.main import IMAGES_DIR
        from PIL import Image
        aid = part()["asset_id"]
        rel = self.upload(client, aid)
        src = IMAGES_DIR / rel
        seen, broken = [], []
        stop = threading.Event()

        def read():
            while not stop.is_set():
                try:
                    with Image.open(src) as im:
                        im.load()
                        seen.append(im.size)
                except Exception as err:
                    # Any failure at all counts: a fragment is the bug.
                    broken.append(f"{type(err).__name__}: {err}")

        readers = [threading.Thread(target=read) for _ in range(3)]
        for t in readers:
            t.start()
        try:
            for _ in range(6):
                client.post(f"/parts/{aid}/photo-crop",
                            data={"image": rel, "x": "0", "y": "0",
                                  "w": "1", "h": "0.8"}, follow_redirects=False)
        finally:
            stop.set()
            for t in readers:
                t.join()
        assert not broken, f"readers saw {len(broken)} broken images: {broken[:5]}"
        assert seen, "the readers never managed to read anything"

    def test_nothing_half_written_is_left_lying_in_the_folder(self, client, part):
        """The photograph is written beside itself first. That temporary file must
        not be mistaken for one of the item's photographs while it exists, and must
        not survive the move."""
        from app.main import IMAGES_DIR
        aid = part()["asset_id"]
        rel = self.upload(client, aid)
        client.post(f"/parts/{aid}/photo-crop",
                    data={"image": rel, "x": "0", "y": "0", "w": "1", "h": "0.5"},
                    follow_redirects=False)
        assert not list((IMAGES_DIR / "parts").glob("*.part"))
        # And were one there mid-write, the folder listing would pass over it.
        (IMAGES_DIR / "parts" / f"{aid}.jpg.part").write_bytes(b"not an image")
        try:
            from app.main import folder_images
            assert not [n for _stem, n in folder_images("parts")
                        if n.endswith(".part")]
            assert client.get(f"/parts/{aid}").status_code == 200
        finally:
            (IMAGES_DIR / "parts" / f"{aid}.jpg.part").unlink()

    def test_the_crop_still_actually_crops(self, client, part):
        """Writing it somewhere else first must not change what comes out."""
        aid = part()["asset_id"]
        rel = self.upload(client, aid, size=(1000, 800))
        client.post(f"/parts/{aid}/photo-crop",
                    data={"image": rel, "x": "0", "y": "0", "w": "0.5", "h": "0.5"},
                    follow_redirects=False)
        import io
        from PIL import Image
        with Image.open(io.BytesIO(client.get(f"/images/{rel}").content)) as im:
            assert im.size == (500, 400)

    def test_a_copy_is_dated_by_what_it_was_made_from(self, client, part):
        """A cached copy carries the mtime of the photograph it was made from, not
        the clock. A photograph replaced while a copy was being made would otherwise
        leave that copy -- of the picture before the crop -- looking newer than the
        photograph, and therefore fresh forever."""
        import os
        from app.main import IMAGES_DIR, WM_CACHE, _watermarked_file
        aid = part()["asset_id"]
        rel = self.upload(client, aid)
        src = IMAGES_DIR / rel
        # Backdate the photograph: a copy taking the clock would come out newer.
        os.utime(src, (1_600_000_000, 1_600_000_000))
        (WM_CACHE / rel).unlink(missing_ok=True)
        made = _watermarked_file(rel)
        assert made.stat().st_mtime == src.stat().st_mtime

class TestChangingAPartsType:
    """What a part is asked depends on what it is, so the type menu has to fetch the
    form again to have the new type's fields on screen at all. It did that on a new
    part and did nothing whatever on an existing one -- so retyping an old monitor
    to Display left the free-text specs box sitting there, with no way to reach the
    groups that had replaced it.
    """

    def test_the_form_can_be_built_for_another_type(self, client, part):
        aid = part(type="other", model="1084S", specs="Type: CRT")["asset_id"]
        assert 'name="specs"' in client.get(f"/parts/{aid}/edit").text
        page = client.get(f"/parts/{aid}/edit?type=display").text
        assert 'name="specs"' not in page
        assert 'name="spec_type"' in page

    def test_looking_does_not_change_the_record(self, client, part):
        """Nothing is saved until the form is submitted."""
        aid = part(type="other", model="1084S")["asset_id"]
        client.get(f"/parts/{aid}/edit?type=display")
        assert client.get(f"/api/parts/{aid}").json()["type"] == "other"

    def test_a_type_the_register_does_not_know_is_ignored(self, client, part):
        """It would render the free-text box and then become the part's type on
        save, which is a way to file a SIMM as a gizmo by editing a URL."""
        aid = part(type="ram", specs="Size: 4MiB")["asset_id"]
        page = client.get(f"/parts/{aid}/edit?type=gizmo").text
        assert 'name="spec_size"' in page

    def test_a_power_supply_stays_one(self, client, part):
        """A type the form does not offer is a type the form quietly changes: the
        select has no option to match it, so the browser sends the first one and a
        Delta 300W becomes a motherboard on the next save. Power supplies were out
        of the vocabulary and back in it, and this is the round trip that says so."""
        aid = part(type="psu", manufacturer="Delta Electronics Ltd",
                   model="DPS-300SB-1 B Rev. 00")["asset_id"]
        page = client.get(f"/parts/{aid}/edit").text
        assert '<option value="psu" selected>Power supply</option>' in page
        client.post(f"/parts/{aid}/edit", data={"type": "psu", "condition": "Working"},
                    follow_redirects=False)
        assert client.get(f"/api/parts/{aid}").json()["type"] == "psu"

    def test_what_the_old_type_recorded_comes_across(self, client, part):
        """The bug behind the question. Structured specs are read from the table the
        old type owns, and only what would not fit there is an attribute -- so
        retyping used to drop everything that did fit. A video card became a display
        and lost the chip it was built round."""
        aid = part(type="video",
                   specs="Chip: S3 Trio64 | Interface: PCI | Memory: 2MiB")["asset_id"]
        client.post(f"/parts/{aid}/edit",
                    data={"type": "display", "spec_type": "CRT"},
                    follow_redirects=False)
        specs = client.get(f"/api/parts/{aid}").json()["specs"]
        assert "Chip: S3 Trio64" in specs and "Memory: 2 MiB" in specs
        assert specs.startswith("Type: CRT")

    def test_a_key_both_types_ask_about_is_left_to_the_form(self, client, part):
        """It is the answer somebody has just given to a question they were shown."""
        aid = part(type="video", specs="Chip: S3 | Interface: PCI")["asset_id"]
        # The old value is offered back through the group, so it survives by being
        # answered rather than by being carried.
        page = client.get(f"/parts/{aid}/edit?type=display").text
        assert re.search(r'id="spec_interface_custom"[^>]*value="PCI"', page)
        client.post(f"/parts/{aid}/edit",
                    data={"type": "display", "spec_type": "CRT",
                          "spec_interface_custom": "PCI"}, follow_redirects=False)
        assert "Interface: PCI" in client.get(f"/api/parts/{aid}").json()["specs"]

    def test_an_ordinary_edit_still_carries_only_its_attributes(self, client, part):
        """Saving without retyping behaves exactly as it did."""
        aid = part(type="video", specs="Chip: S3 | Voltage: 5V")["asset_id"]
        client.post(f"/parts/{aid}/edit", data={"type": "video", "spec_chip": "S3"},
                    follow_redirects=False)
        assert client.get(f"/api/parts/{aid}").json()["specs"] == \
            "Chip: S3 | Voltage: 5V"

    def test_the_menu_asks_before_it_throws_away_what_you_typed(self, client, part):
        page = client.get(f"/parts/{part()['asset_id']}/edit").text
        assert "Anything you have entered since opening it will be lost." in page
        assert "window.location.pathname + u.search" in page


class TestDeletingAHistoryEntry:
    """A history is written by the register rather than by hand, so it collects lines
    nobody wants: a correction made twice, a photograph added and taken off again.
    """

    def ids_for(self, db, aid, message):
        from app.models import LogEntry
        return [i for (i,) in db.query(LogEntry.id)
                .filter(LogEntry.asset_id == aid, LogEntry.message == message)]

    def messages(self, client, aid):
        return [e["message"] for e in client.get(f"/api/items/{aid}/log").json()]

    def test_one_entry_goes(self, client, db, part):
        aid = part()["asset_id"]
        for i in range(3):
            client.post(f"/parts/{aid}/note", data={"message": f"note {i}"},
                        follow_redirects=False)
        r = client.post(f"/items/{aid}/log/delete",
                        data={"id": self.ids_for(db, aid, "note 1")},
                        follow_redirects=False)
        assert r.status_code == 303
        assert self.messages(client, aid) == ["note 2", "note 0", "created"]

    def test_a_folded_run_goes_as_the_one_line_it_reads_as(self, client, db, part):
        """A run of the same thing done in one sitting reads as a single line, so it
        has to delete as one: "deleted 3 photographs" that removed one of them and
        came back saying two would not be doing what it says."""
        aid = part()["asset_id"]
        # All three uploaded first and then all three removed, so the removals are
        # next to each other in the history -- only adjacent entries fold.
        rels = [TestAPhotographIsNeverHalfWritten.upload(client, aid, (60, 40))
                for _ in range(3)]
        for rel in rels:
            client.post(f"/parts/{aid}/photo-delete", data={"image": rel},
                        follow_redirects=False)
        deleted = self.ids_for(db, aid, "deleted a photo")
        assert len(deleted) == 3, deleted
        # The page reads them as one line and offers every id behind that one line.
        page = client.get(f"/parts/{aid}").text
        forms = [f.split("</form>")[0] for f in page.split("/log/delete")[1:]]
        assert any(all(f'value="{i}"' in form for i in deleted) for form in forms), \
            "no single form carried the whole run"
        client.post(f"/items/{aid}/log/delete", data={"id": deleted},
                    follow_redirects=False)
        assert "deleted a photo" not in self.messages(client, aid)

    def test_it_cannot_reach_another_items_history(self, client, db, part):
        """An id on its own would let one machine's history be deleted from
        another machine's page."""
        mine, theirs = part()["asset_id"], part()["asset_id"]
        client.post(f"/parts/{theirs}/note", data={"message": "theirs"},
                    follow_redirects=False)
        ids = self.ids_for(db, theirs, "theirs")
        r = client.post(f"/items/{mine}/log/delete", data={"id": ids},
                        follow_redirects=False)
        assert r.status_code == 404
        assert "theirs" in self.messages(client, theirs)

    def test_nothing_is_written_about_the_deleting(self, client, db, part):
        """The rule an entry losing a photograph already follows: editing the record
        is not something that happened to the machine, and a history that logged its
        own editing would grow a line for every line it lost."""
        aid = part()["asset_id"]
        client.post(f"/parts/{aid}/note", data={"message": "gone"},
                    follow_redirects=False)
        client.post(f"/items/{aid}/log/delete",
                    data={"id": self.ids_for(db, aid, "gone")},
                    follow_redirects=False)
        assert self.messages(client, aid) == ["created"]

    def test_the_photographs_on_it_go_with_it(self, client, db, part):
        """A photograph hung on an entry means nothing without the entry, and the
        file behind it is the one thing here that cannot be rolled back."""
        import io
        from app.models import LogPhoto
        from PIL import Image
        aid = part()["asset_id"]
        client.post(f"/parts/{aid}/note", data={"message": "recapped"},
                    follow_redirects=False)
        log_id = self.ids_for(db, aid, "recapped")[0]
        buf = io.BytesIO()
        Image.new("RGB", (60, 40), (10, 20, 30)).save(buf, "JPEG")
        buf.seek(0)
        client.post(f"/items/{aid}/log/{log_id}/photo",
                    files={"photos": ("x.jpg", buf, "image/jpeg")},
                    follow_redirects=False)
        db.expire_all()
        rels = [r for (r,) in db.query(LogPhoto.rel)
                .filter(LogPhoto.log_id == log_id)]
        assert rels, "the photograph did not attach"
        assert client.get(f"/images/{rels[0]}").status_code == 200
        client.post(f"/items/{aid}/log/delete", data={"id": [log_id]},
                    follow_redirects=False)
        assert client.get(f"/images/{rels[0]}").status_code == 404
        db.expire_all()
        assert not db.query(LogPhoto).filter(LogPhoto.log_id == log_id).count()

    def test_it_is_only_for_the_logged_in(self, client, part, monkeypatch):
        from app import main
        aid = part()["asset_id"]
        assert "log/delete" in client.get(f"/parts/{aid}").text
        monkeypatch.setattr(main, "AUTH_ENABLED", True)
        try:
            assert "log/delete" not in client.get(f"/parts/{aid}").text
        finally:
            monkeypatch.setattr(main, "AUTH_ENABLED", False)


class TestAPageNoticesItHasChanged:
    """The register is used from two places at once: you scan the label with a phone
    and photograph the thing while the desktop shows its page. The desktop had no way
    to know, so it sat there showing a record that was no longer true.

    Every change already writes a history entry, so the highest id in an item's
    history is a change token with no new column behind it. The page carries the one
    it was built with and asks whether it still holds.
    """

    def token(self, client, aid):
        r = client.get(f"/items/{aid}/version")
        assert r.status_code == 200
        return r.json()["v"]

    def test_the_page_carries_the_token_it_was_built_with(self, client, part):
        aid = part()["asset_id"]
        page = client.get(f"/parts/{aid}").text
        assert f'const BUILT = "{self.token(client, aid)}"' in page
        assert f'const AID = "{aid}"' in page

    def test_a_change_moves_it(self, client, part):
        aid = part(model="Before")["asset_id"]
        was = self.token(client, aid)
        client.post(f"/parts/{aid}/edit", data={"type": "other", "model": "After"},
                    follow_redirects=False)
        assert self.token(client, aid) != was

    def test_a_photograph_moves_it_too(self, client, part):
        """The case this is really for: the phone adds a picture, the desktop is
        still showing the page without it.

        The whole loop is checked in a browser rather than here -- two separate
        sessions, the photograph uploaded through the picker in one and the other
        refreshing itself -- because two browsers is not something pytest can drive.
        What is worth pinning down here is the part that decides it: the page is
        built with one token, a photograph arrives from somewhere else, and the
        token the page will ask for no longer matches the one it holds.
        """
        aid = part()["asset_id"]
        built_with = re.search(r'const BUILT = "([^"]+)"',
                               client.get(f"/parts/{aid}").text).group(1)
        assert built_with == self.token(client, aid)
        rel = TestAPhotographIsNeverHalfWritten.upload(client, aid)
        try:
            assert self.token(client, aid) != built_with
            # And the page served now agrees with itself again.
            assert re.search(r'const BUILT = "([^"]+)"',
                             client.get(f"/parts/{aid}").text).group(1) == \
                self.token(client, aid)
        finally:
            client.post(f"/parts/{aid}/photo-delete", data={"image": rel},
                        follow_redirects=False)

    def test_deleting_or_cropping_a_photograph_moves_it_as_well(self, client, part):
        """Every edit to a photograph is a change to the record, and the phone is
        not the only place they happen."""
        aid = part()["asset_id"]
        rel = TestAPhotographIsNeverHalfWritten.upload(client, aid)
        after_upload = self.token(client, aid)
        client.post(f"/parts/{aid}/photo-crop",
                    data={"image": rel, "x": "0", "y": "0", "w": "0.6", "h": "0.6"},
                    follow_redirects=False)
        after_crop = self.token(client, aid)
        assert after_crop != after_upload
        client.post(f"/parts/{aid}/photo-delete", data={"image": rel},
                    follow_redirects=False)
        assert self.token(client, aid) != after_crop

    def test_a_file_moves_it_although_it_belongs_to_no_item(self, client, part):
        """A driver is filed against a model rather than against the card on the
        shelf, so nothing about it reaches that item's history -- and an item page
        shows it all the same."""
        import io
        aid = part(manufacturer="Creative", model="SB16")["asset_id"]
        was = self.token(client, aid)
        client.post("/files", files={"uploads": ("sb16.zip", io.BytesIO(b"x"),
                                                 "application/zip")},
                    data={"tags": "SB16"}, follow_redirects=False)
        assert self.token(client, aid) != was

    def test_reading_the_page_does_not_move_it(self, client, part):
        """Or every page would reload itself for ever."""
        aid = part()["asset_id"]
        was = self.token(client, aid)
        client.get(f"/parts/{aid}")
        client.get(f"/parts/{aid}")
        assert self.token(client, aid) == was

    def test_an_item_that_is_gone_still_answers(self, client, part):
        """A page whose item has been deleted asks this too. A 404 would leave it
        sitting there for ever; a token that cannot match sends it to reload and
        find out properly."""
        aid = part()["asset_id"]
        was = self.token(client, aid)
        # Deleting takes a disposal first and the item's own URL as the
        # confirmation -- see _confirms_url.
        client.post(f"/parts/{aid}/dispose", data={"note": "gone"},
                    follow_redirects=False)
        r = client.post(f"/parts/{aid}/delete", data={"confirm": f"/parts/{aid}"},
                        follow_redirects=False)
        assert r.status_code == 303, r.text[:200]
        assert client.get(f"/parts/{aid}").status_code == 404
        assert self.token(client, aid) != was

    def test_it_is_asked_only_of_an_item_page(self, client, part):
        """The gallery has no one item to ask about, so it is not given the script."""
        part()
        assert 'const AID' not in client.get("/").text

    def test_it_waits_rather_than_reloading_under_your_hands(self, client, part):
        """A page that reloaded itself mid-crop or mid-sentence would be worse than
        one that is out of date."""
        page = client.get(f"/parts/{part()['asset_id']}").text
        assert "document.querySelector('#lightbox.open')" in page
        assert 'id="changed"' in page

    def test_it_only_asks_while_it_is_being_looked_at(self, client, part):
        page = client.get(f"/parts/{part()['asset_id']}").text
        assert "document.visibilityState !== 'visible'" in page
        assert "visibilitychange" in page


class TestATopBenchScore:
    """The one measured number on a machine's record: what it scores in TopBench,
    the DOS benchmark. A typed column like `year`, so it is held to the same rules
    -- a blank clears it, a non-number is refused rather than stored as zero, and
    not recorded is NULL."""

    def test_it_comes_back_typed(self, computer):
        assert computer(topbench=187)["topbench"] == 187

    def test_a_machine_it_has_not_been_run_on_has_no_score(self, computer):
        """Not zero: a machine nobody has benchmarked has no score, and zero is a
        result -- the one a machine that could not finish the run would get."""
        assert computer(cpu="Intel 486DX2-66")["topbench"] is None

    def test_a_score_that_is_not_a_number_is_refused(self, client):
        r = client.post("/api/computers", json={"model": "X", "topbench": "fast"})
        assert r.status_code == 422

    def test_the_form_takes_one_and_gives_it_back(self, client, computer):
        aid = computer()["asset_id"]
        client.post(f"/computers/{aid}/edit", data={"topbench": "187"},
                    follow_redirects=False)
        assert client.get(f"/api/computers/{aid}").json()["topbench"] == 187
        assert 'value="187"' in client.get(f"/computers/{aid}/edit").text

    def test_the_form_can_take_it_back_off(self, client, computer):
        aid = computer(topbench=187)["asset_id"]
        client.post(f"/computers/{aid}/edit", data={"topbench": ""},
                    follow_redirects=False)
        assert client.get(f"/api/computers/{aid}").json()["topbench"] is None

    def test_the_page_shows_it(self, client, computer):
        assert "TopBench" in client.get(
            f"/computers/{computer(topbench=187)['asset_id']}").text

    def test_and_says_nothing_about_a_machine_that_has_no_score(self, client,
                                                                computer):
        assert "TopBench" not in client.get(
            f"/computers/{computer()['asset_id']}").text

    def test_the_change_is_recorded_in_the_history(self, client, computer):
        aid = computer(topbench=187)["asset_id"]
        client.post(f"/computers/{aid}/edit", data={"topbench": "212"},
                    follow_redirects=False)
        messages = [e["message"] for e in client.get(f"/api/items/{aid}/log").json()]
        assert any("187 → 212" in m for m in messages)

    def test_the_box_is_marked_for_the_script_that_hides_it(self, client, computer):
        """TopBench is a DOS program, so the box is on screen for a PC and off it
        for a catalogue machine -- which the machine picker's script decides, since
        the model is chosen without reloading the page. It is hidden rather than
        dropped from the form, so a score already on file is not erased by someone
        filing the machine against the catalogue and saving."""
        page = client.get(f"/computers/{computer()['asset_id']}/edit").text
        assert "data-x86-only" in page

    def test_a_score_survives_the_machine_being_filed_as_a_catalogue_one(
            self, client, computer):
        aid = computer(topbench=187)["asset_id"]
        client.post(f"/computers/{aid}/edit",
                    data={"mach_model": "zx-spectrum-48k", "topbench": "187"},
                    follow_redirects=False)
        assert client.get(f"/api/computers/{aid}").json()["topbench"] == 187


class TestThePartsAndWhatTheyAreMadeOf:
    """A part's specs sit on a line of their own under the part, not in a fourth
    column: a card's specs are longer than the rest of the row put together, and as
    a column they took the width the asset id and the name needed."""

    def test_the_specs_are_not_a_column_of_a_table(self, client, computer, part):
        aid = computer()["asset_id"]
        part(type="video", computer_id=aid, specs="Chip: S3 Trio64")
        page = client.get(f"/computers/{aid}").text
        assert "<th>Specs</th>" not in page

    def test_each_part_is_one_card(self, client, computer, part):
        """Everything about a part inside one border: the tag and the kind on the
        strip, the name under it, the specs beneath that."""
        aid = computer()["asset_id"]
        part(type="video", computer_id=aid, name="Stealth 24", specs="Chip: S3")
        page = client.get(f"/computers/{aid}").text
        assert page.count('<article class="itemcard">') == 1
        assert "Stealth 24</h4>" in page

    def test_they_are_shown_as_labelled_pairs_below_the_part(self, client, computer,
                                                            part):
        aid = computer()["asset_id"]
        part(type="video", computer_id=aid, specs="Chip: S3 Trio64 | Interface: PCI")
        page = client.get(f"/computers/{aid}").text
        assert '<dl class="specs">' in page
        assert "<dt>Chip</dt><dd>S3 Trio64</dd>" in page
        assert "<dt>Interface</dt><dd>PCI</dd>" in page

    def test_a_part_with_nothing_recorded_gets_no_second_line(self, client,
                                                              computer, part):
        aid = computer()["asset_id"]
        part(type="peripheral", computer_id=aid, name="Keyboard")
        page = client.get(f"/computers/{aid}").text
        assert '<article class="itemcard">' in page
        assert '<dl class="specs">' not in page

    def test_a_card_s_mounted_parts_are_listed_the_same_way(self, client, part):
        """One list, two places: a machine's parts and a card's mounted parts are
        the same thing and have to read alike."""
        host = part(type="io", name="Multi-IO")["asset_id"]
        part(type="storage", parent_id=host, specs="Interface: IDE")
        page = client.get(f"/parts/{host}").text
        assert "<th>Specs</th>" not in page
        assert '<article class="itemcard">' in page
        assert "<dt>Interface</dt><dd>IDE</dd>" in page

    def test_the_board_above_them_is_drawn_as_one_too(self, client, computer, part):
        """A section that said a board's specs a second way would be two designs for
        one thing, and the board has the longest set of them on the page."""
        aid = computer()["asset_id"]
        part(type="motherboard", computer_id=aid, specs="Chipset: SiS 496")
        page = client.get(f"/computers/{aid}").text
        assert page.count('<article class="itemcard">') == 1
        assert "<dt>Chipset</dt><dd>SiS 496</dd>" in page


class TestAHistoryThatReadsAsOneSitting:
    """Clearing out a folder of photographs writes one history line per photograph,
    and twenty of those bury what the machine's history is actually for. A run of
    the same thing, done in one sitting, reads as one line -- while the rows behind
    it stay one per action."""

    @staticmethod
    def log_rows(client, aid, kind="computers"):
        page = client.get(f"/{kind}/{aid}").text
        section = page.split("History", 1)[1]
        return re.findall(r'<div class="logmsg">(.*?)</div>', section)

    @staticmethod
    def repeat(db, aid, message, times, apart_minutes=1, day=1):
        """`times` of the same thing, `apart_minutes` apart, oldest first."""
        from app.models import LogEntry
        when = datetime(2026, 8, day, 12, 0)
        for i in range(times):
            db.add(LogEntry(asset_id=aid, created_at=when + timedelta(
                minutes=i * apart_minutes), kind="change", message=message))
        db.commit()

    def test_ten_deleted_photos_are_one_line(self, client, computer, db):
        aid = computer()["asset_id"]
        self.repeat(db, aid, "deleted a photo", 10)
        rows = self.log_rows(client, aid)
        assert "deleted 10 photos" in rows
        assert "deleted a photo" not in rows

    def test_one_of_a_thing_is_still_written_as_one(self, client, computer, db):
        aid = computer()["asset_id"]
        self.repeat(db, aid, "deleted a photo", 1)
        assert "deleted a photo" in self.log_rows(client, aid)

    def test_the_same_thing_a_week_later_is_its_own_line(self, client, computer, db):
        aid = computer()["asset_id"]
        self.repeat(db, aid, "deleted a photo", 2, apart_minutes=60 * 24 * 7)
        assert self.log_rows(client, aid).count("deleted a photo") == 2

    def test_a_long_tidying_session_is_still_one_line(self, client, computer, db):
        """Chained, not windowed from the first: twenty photographs deleted a couple
        of minutes apart is one sitting however long it ran."""
        aid = computer()["asset_id"]
        self.repeat(db, aid, "deleted a photo", 20, apart_minutes=2)
        assert "deleted 20 photos" in self.log_rows(client, aid)

    def test_two_different_things_are_not_folded_together(self, client, computer, db):
        aid = computer()["asset_id"]
        self.repeat(db, aid, "rotated a photo", 2, day=1)
        self.repeat(db, aid, "deleted a photo", 3, day=2)
        rows = self.log_rows(client, aid)
        assert "rotated 2 photos" in rows and "deleted 3 photos" in rows

    def test_a_message_naming_no_single_thing_takes_a_count(self, client, computer,
                                                            db):
        aid = computer()["asset_id"]
        self.repeat(db, aid, "changed the default photo", 3)
        assert "changed the default photo ×3" in self.log_rows(client, aid)

    def test_a_note_is_never_folded(self, client, computer):
        """A note is a person's own words about the machine and stands as written,
        however like the last one it reads."""
        aid = computer()["asset_id"]
        for _ in range(3):
            client.post(f"/computers/{aid}/note", data={"message": "tested"},
                        follow_redirects=False)
        page = client.get(f"/computers/{aid}").text
        assert page.count("note</span> tested") == 3

    def test_the_record_behind_it_is_untouched(self, client, computer, db):
        """The page reads the history this way; it does not rewrite it. The rows
        stay one per action, and the API still lists every one."""
        aid = computer()["asset_id"]
        self.repeat(db, aid, "deleted a photo", 10)
        messages = [e["message"] for e in client.get(f"/api/items/{aid}/log").json()]
        assert messages.count("deleted a photo") == 10

    def test_a_parts_history_folds_the_same_way(self, client, part, db):
        aid = part()["asset_id"]
        self.repeat(db, aid, "deleted a photo", 4)
        assert "deleted 4 photos" in self.log_rows(client, aid, "parts")


class TestPhotographsOnTheHistory:
    """The portrait says which one this is; a photograph on a history entry says what
    happened to it. The board before the recap, the crack it arrived with, the label
    under the lid that settled the revision -- all of it already has a line in the
    history saying what it was, and that line is the caption.

    They are not the item's photographs and are never counted among them: they live
    under images/log/, keyed to the entry rather than to the asset, so nothing that
    reads an asset's folder by stem can claim one.
    """

    @staticmethod
    def image(name="shot.jpg"):
        import io

        from PIL import Image
        buf = io.BytesIO()
        Image.new("RGB", (400, 300), (60, 90, 120)).save(buf, "JPEG", quality=90)
        buf.seek(0)
        return (name, buf, "image/jpeg")

    @staticmethod
    def entries(db, aid, kind=None):
        """The rows, oldest first. Rolled back first so the reads that follow a POST
        see what the app committed rather than this session's older snapshot."""
        from app.models import LogEntry
        db.rollback()
        q = db.query(LogEntry).filter(LogEntry.asset_id == aid)
        if kind:
            q = q.filter(LogEntry.kind == kind)
        return q.order_by(LogEntry.id).all()

    def notes(self, db, aid):
        """The written ones only: creating anything writes a change entry of its own,
        which is not what these tests are hanging photographs on."""
        return self.entries(db, aid, "note")

    @staticmethod
    def shots(db, log_id):
        from app.models import LogPhoto
        db.rollback()
        return [p.rel for p in db.query(LogPhoto).filter(LogPhoto.log_id == log_id)
                .order_by(LogPhoto.id)]

    def note(self, client, aid, message, files=None, kind="computers"):
        return client.post(f"/{kind}/{aid}/note", data={"message": message},
                           files=files, follow_redirects=False)

    def test_a_note_and_its_photographs_arrive_together(self, client, computer, db):
        """One gesture: the sentence and the pictures of what it describes."""
        from app import main
        aid = computer()["asset_id"]
        self.note(client, aid, "recapped the PSU", {"photos": self.image()})
        [row] = self.notes(db, aid)
        assert row.message == "recapped the PSU"
        [rel] = self.shots(db, row.id)
        assert rel.startswith("log/")
        assert (main.IMAGES_DIR / rel).exists()

    def test_several_photographs_go_on_the_one_entry(self, client, computer, db):
        aid = computer()["asset_id"]
        self.note(client, aid, "before and after",
                  [("photos", self.image("a.jpg")), ("photos", self.image("b.jpg"))])
        [row] = self.notes(db, aid)
        assert len(self.shots(db, row.id)) == 2

    def test_a_part_carries_them_the_same_way(self, client, part, db):
        aid = part()["asset_id"]
        self.note(client, aid, "reflowed the socket", {"photos": self.image()},
                  kind="parts")
        [row] = self.notes(db, aid)
        assert len(self.shots(db, row.id)) == 1

    def test_it_is_not_one_of_the_item_s_own_photographs(self, client, computer, db):
        """The whole reason for a folder of its own. computers/ is read by stem, so a
        photograph of a repair filed there would have become one of the machine's
        gallery pictures and -- being the first -- its portrait."""
        from app import main
        aid = computer()["asset_id"]
        self.note(client, aid, "found a bulged cap", {"photos": self.image()})
        assert main.detect_images("computers", aid) == []
        assert not client.get(f"/api/computers/{aid}").json()["image"]

    def test_the_count_of_photographs_in_the_register_does_not_absorb_it(
            self, client, computer, db):
        """A picture of a recap is not a picture of the machine, and the figure that
        says how many photographs the collection has means the second thing."""
        from app import main
        aid = computer()["asset_id"]
        before = main._collection_stats(db)["photos"]
        self.note(client, aid, "cleaned the keyboard", {"photos": self.image()})
        db.rollback()
        assert main._collection_stats(db)["photos"] == before

    def test_photographs_with_no_words_are_an_entry_of_their_own(self, client,
                                                                 computer, db):
        """A photograph of the thing is a thing said about it. It used to need a
        sentence typed beside it before the register would keep it at all."""
        from app.models import LogPhoto
        aid = computer()["asset_id"]
        self.note(client, aid, "   ", {"photos": self.image()})
        [row] = self.entries(db, aid, "photo")
        assert row.message == ""
        assert self.shots(db, row.id) and db.query(LogPhoto).count() == 1
        # and not filed as a note: a note is somebody's words
        assert self.notes(db, aid) == []

    def test_it_gets_a_line_and_a_time_of_its_own(self, client, computer, db):
        """Separate entries, so the log says when the photograph was taken rather
        than when the sentence above it happened to be written."""
        aid = computer()["asset_id"]
        self.note(client, aid, "recapped it")
        self.note(client, aid, "", {"photos": self.image()})
        words, pictures = self.notes(db, aid)[0], self.entries(db, aid, "photo")[0]
        assert words.id != pictures.id
        assert self.shots(db, words.id) == [] and self.shots(db, pictures.id) != []

    def test_neither_half_needs_the_other(self, client, computer, db):
        """Words alone, photographs alone, and both together in one gesture -- three
        entries, and the one with words keeps its photographs as its caption."""
        aid = computer()["asset_id"]
        self.note(client, aid, "words only")
        self.note(client, aid, "", {"photos": self.image()})
        self.note(client, aid, "both", {"photos": self.image("second.jpg")})
        notes = self.notes(db, aid)
        assert [n.message for n in notes] == ["words only", "both"]
        assert self.shots(db, notes[0].id) == [] and self.shots(db, notes[1].id) != []
        assert len(self.entries(db, aid, "photo")) == 1

    def test_nothing_at_all_still_writes_nothing_at_all(self, client, computer, db):
        """An empty box and no photographs is somebody pressing the button by
        accident, not an entry about nothing."""
        from app.models import LogPhoto
        aid = computer()["asset_id"]
        self.note(client, aid, "  ")
        assert self.notes(db, aid) == [] and self.entries(db, aid, "photo") == []
        assert db.query(LogPhoto).count() == 0

    def test_the_last_photograph_off_a_photograph_entry_takes_the_entry(
            self, client, computer, db):
        """The photographs are what it said. An entry with words keeps its line,
        because the words are still what it said."""
        aid = computer()["asset_id"]
        self.note(client, aid, "", {"photos": self.image()})
        [row] = self.entries(db, aid, "photo")
        [rel] = self.shots(db, row.id)
        client.post(f"/items/{aid}/log/{row.id}/photo-delete", data={"image": rel},
                    follow_redirects=False)
        assert self.entries(db, aid, "photo") == []

    def test_a_worded_entry_keeps_its_line_when_its_photograph_goes(self, client,
                                                                   computer, db):
        aid = computer()["asset_id"]
        self.note(client, aid, "recapped it", {"photos": self.image()})
        [row] = self.notes(db, aid)
        [rel] = self.shots(db, row.id)
        client.post(f"/items/{aid}/log/{row.id}/photo-delete", data={"image": rel},
                    follow_redirects=False)
        assert [n.message for n in self.notes(db, aid)] == ["recapped it"]

    def test_a_file_that_is_not_an_image_writes_no_entry_either(self, client,
                                                               computer, db):
        """Checked before the entry is written, as a create form's are: a refused
        upload should not leave a note behind saying something was photographed."""
        import io
        aid = computer()["asset_id"]
        r = self.note(client, aid, "with a text file",
                      {"photos": ("notes.txt", io.BytesIO(b"nope"), "text/plain")})
        assert r.status_code == 400
        assert self.notes(db, aid) == []

    def test_the_page_shows_them_under_the_line_they_belong_to(self, client,
                                                              computer, db):
        aid = computer()["asset_id"]
        self.note(client, aid, "the underside", {"photos": self.image()})
        [row] = self.notes(db, aid)
        [rel] = self.shots(db, row.id)
        page = client.get(f"/computers/{aid}").text
        assert f"/images/{rel}" in page
        # The entry's message is the caption, and it is what a reader who cannot see
        # the photograph is told about it.
        assert 'alt="the underside"' in page

    def test_it_hangs_in_the_entry_s_own_column_and_not_the_date_s(self, client,
                                                                   computer, db):
        """A row across the entry, under whatever it says. The date column holds the
        date: a photograph in there stacks down a column 120px wide."""
        aid = computer()["asset_id"]
        self.note(client, aid, "the underside", {"photos": self.image()})
        [row] = self.notes(db, aid)
        [rel] = self.shots(db, row.id)
        page = client.get(f"/computers/{aid}").text
        stamp = page[page.index('<td class="logwhen">'):]
        assert f"/images/{rel}" not in stamp[:stamp.index("</td>")]
        assert page.index('class="logmsg"') < page.index(f"/images/{rel}")

    def test_a_photograph_has_no_delete_of_its_own(self, client, computer, db):
        """One button a line, at the right, where a line of words has it. On a
        photograph entry that button is the photographs."""
        aid = computer()["asset_id"]
        self.note(client, aid, "", {"photos": self.image()})
        [row] = self.entries(db, aid, "photo")
        page = client.get(f"/computers/{aid}").text
        assert f"/log/{row.id}/photo-delete" not in page
        assert '<span class="chip">photo</span>' in page
        assert page.count("/log/delete") >= 1

    def test_one_can_be_hung_on_an_entry_already_written(self, client, computer, db):
        """The swap the register logged last week, photographed when the lid next
        came off."""
        aid = computer()["asset_id"]
        self.note(client, aid, "fitted a new PSU")
        [row] = self.notes(db, aid)
        r = client.post(f"/items/{aid}/log/{row.id}/photo",
                        files={"photos": self.image()}, follow_redirects=False)
        assert r.headers["location"] == f"/computers/{aid}"
        assert len(self.shots(db, row.id)) == 1

    def test_a_part_s_entry_redirects_back_to_the_part(self, client, part, db):
        aid = part()["asset_id"]
        self.note(client, aid, "tested", kind="parts")
        [row] = self.notes(db, aid)
        r = client.post(f"/items/{aid}/log/{row.id}/photo",
                        files={"photos": self.image()}, follow_redirects=False)
        assert r.headers["location"] == f"/parts/{aid}"

    def test_an_entry_of_another_asset_is_not_somewhere_to_put_it(self, client,
                                                                  computer, db):
        """The id in the URL is checked against the entry's. An entry id on its own
        would let a photograph of one machine be hung on another's history."""
        mine, theirs = computer()["asset_id"], computer()["asset_id"]
        self.note(client, mine, "mine")
        [row] = self.notes(db, mine)
        r = client.post(f"/items/{theirs}/log/{row.id}/photo",
                        files={"photos": self.image()}, follow_redirects=False)
        assert r.status_code == 404
        assert self.shots(db, row.id) == []

    def test_removing_one_takes_the_row_and_the_file(self, client, computer, db):
        from app import main
        aid = computer()["asset_id"]
        self.note(client, aid, "a duplicate shot", {"photos": self.image()})
        [row] = self.notes(db, aid)
        [rel] = self.shots(db, row.id)
        client.post(f"/items/{aid}/log/{row.id}/photo-delete", data={"image": rel},
                    follow_redirects=False)
        assert self.shots(db, row.id) == []
        assert not (main.IMAGES_DIR / rel).exists()
        # The entry itself stays: what happened still happened.
        assert len(self.notes(db, aid)) == 1

    def test_a_photograph_on_another_entry_is_not_this_one_s_to_delete(
            self, client, computer, db):
        aid = computer()["asset_id"]
        self.note(client, aid, "first", {"photos": self.image()})
        self.note(client, aid, "second")
        first, second = self.notes(db, aid)
        [rel] = self.shots(db, first.id)
        r = client.post(f"/items/{aid}/log/{second.id}/photo-delete",
                        data={"image": rel}, follow_redirects=False)
        assert r.status_code == 404
        assert self.shots(db, first.id) == [rel]

    def test_the_removal_is_not_itself_written_into_the_history(self, client,
                                                               computer, db):
        """An entry gaining or losing a photograph is an edit to the record, not
        something that happened to the machine. A history that logged its own editing
        would grow a line for every line it has."""
        aid = computer()["asset_id"]
        self.note(client, aid, "one photo", {"photos": self.image()})
        [row] = self.notes(db, aid)
        [rel] = self.shots(db, row.id)
        client.post(f"/items/{aid}/log/{row.id}/photo-delete", data={"image": rel},
                    follow_redirects=False)
        assert [e.message for e in self.notes(db, aid)] == ["one photo"]

    def test_an_entry_carrying_photographs_is_never_folded(self, client, computer,
                                                           db):
        """Folding rewrites several entries as one sentence. The photographs would
        then be lost with the entries that are no longer shown, or gathered under a
        line that is not the one they were taken for."""
        from app.models import LogEntry
        from datetime import datetime
        from app import main
        aid = computer()["asset_id"]
        when = datetime(2026, 8, 1, 12, 0)
        for i in range(3):
            db.add(LogEntry(asset_id=aid, created_at=when.replace(minute=i),
                            kind="change", message="deleted a photo"))
        db.commit()
        middle = [e for e in self.entries(db, aid)
                  if e.message == "deleted a photo"][1]
        client.post(f"/items/{aid}/log/{middle.id}/photo",
                    files={"photos": self.image()}, follow_redirects=False)
        db.rollback()
        lines = [len(e.photos) for e in main._history(db, aid)
                 if e.message == "deleted a photo"]
        assert lines == [0, 1, 0]

    def test_the_api_lists_what_an_entry_carries(self, client, computer, db):
        aid = computer()["asset_id"]
        self.note(client, aid, "with a picture", {"photos": self.image()})
        [row] = self.notes(db, aid)
        [written] = [e for e in client.get(f"/api/items/{aid}/log").json()
                     if e["kind"] == "note"]
        assert written["message"] == "with a picture"
        assert written["photos"] == self.shots(db, row.id)

    def test_deleting_the_machine_takes_them_off_the_disk(self, client, computer,
                                                          db):
        """They go the way every other photograph of a deleted record goes: the rows
        first, because a file cannot be rolled back."""
        from app import main
        from app.models import LogPhoto
        aid = computer(disposed=True)["asset_id"]
        self.note(client, aid, "before it went", {"photos": self.image()})
        [row] = self.notes(db, aid)
        [rel] = self.shots(db, row.id)
        r = client.delete(f"/api/computers/{aid}")
        assert r.status_code == 200
        db.rollback()
        assert db.query(LogPhoto).count() == 0
        assert not (main.IMAGES_DIR / rel).exists()

    def test_deleting_a_part_takes_its_own_with_it(self, client, part, db):
        from app import main
        aid = part(disposed=True)["asset_id"]
        self.note(client, aid, "as found", {"photos": self.image()}, kind="parts")
        [row] = self.notes(db, aid)
        [rel] = self.shots(db, row.id)
        client.delete(f"/api/parts/{aid}")
        assert not (main.IMAGES_DIR / rel).exists()

    def test_the_confirmation_page_counts_them_among_what_goes(self, client,
                                                               computer, db):
        """The page can only promise what the delete actually does, and the delete
        takes these off the disk too."""
        aid = computer(disposed=True)["asset_id"]
        self.note(client, aid, "one for the record", {"photos": self.image()})
        page = client.get(f"/computers/{aid}/delete").text
        assert "<strong>1</strong> photo" in page

    def test_an_entry_s_photographs_cannot_be_claimed_by_a_longer_id(self):
        """Entry 12's photographs are 12.jpg and 12-2.jpg; entry 120's are 120.jpg.
        The hyphen is what keeps the second from swallowing the first, which is the
        whole of why a log entry's id can stand where an asset id stands."""
        from app import main
        listing = [("12", "12.jpg"), ("12-2", "12-2.jpg"), ("120", "120.jpg")]
        assert main.pick_images("log", "12", listing) == ["log/12.jpg",
                                                          "log/12-2.jpg"]
        assert main.pick_images("log", "120", listing) == ["log/120.jpg"]

    def test_they_are_marked_like_any_other_photograph_of_the_collection(self):
        """The watermark is about where a photograph goes, not which panel of the
        site it was shown on."""
        from app import main
        assert main._is_own_photo("log/1.jpg") == main._is_own_photo("computers/A.jpg")

    def test_the_note_bar_offers_the_picker(self, client, computer):
        page = client.get(f"/computers/{computer()['asset_id']}").text
        assert 'class="notebar"' in page and 'enctype="multipart/form-data"' in page
        assert 'name="photos"' in page


class TestWhereTheFilesSit:
    def test_they_come_before_the_history(self, client, computer, part):
        """Files are part of what the item is -- the driver disk it needs, the
        manual for it. The history is a log to be consulted, so it goes last."""
        for kind, aid in (("computers", computer()["asset_id"]),
                          ("parts", part()["asset_id"])):
            page = client.get(f"/{kind}/{aid}").text
            assert page.index("Files") < page.index(">History<")


class TestEverySectionIsAPanel:
    """An item page is a stack of panels: a title on a band, and what belongs to
    that section inside the border. What told you where one section ended and the
    next began used to be a gap and a bold word, which stopped working once a
    section was itself a list of things with gaps inside them."""

    @pytest.mark.parametrize("title", ["Details", "Files", "History"])
    def test_the_machine_page_says_where_each_section_starts(self, client, computer,
                                                             title):
        page = client.get(f"/computers/{computer()['asset_id']}").text
        assert f"<h3>{title}</h3>" in page

    @pytest.mark.parametrize("title", ["Details", "Files", "History"])
    def test_and_so_does_a_part_page(self, client, part, title):
        page = client.get(f"/parts/{part()['asset_id']}").text
        assert f"<h3>{title}</h3>" in page

    def test_a_section_of_cards_is_one_panel_and_not_a_box_each(self, client,
                                                                computer, part):
        """The panel draws the box, so the cards in it give theirs up and keep their
        bands -- a border round each inside a border round all of them is what makes
        a page look busy."""
        aid = computer()["asset_id"]
        part(type="motherboard", computer_id=aid, specs="Chipset: SiS 496")
        part(type="video", computer_id=aid, specs="Chip: S3")
        part(type="sound", computer_id=aid, specs="Chip: CT1745A")
        page = client.get(f"/computers/{aid}").text
        assert page.count('<section class="panel">') >= 3
        assert page.count('<div class="itemcards">') == 2   # the board, and the parts
        assert page.count('<article class="itemcard">') == 3

    def test_the_specs_of_a_part_are_their_own_panel(self, client, part):
        aid = part(type="video", specs="Chip: S3 Trio64")["asset_id"]
        page = client.get(f"/parts/{aid}").text
        assert "<h3>Specs</h3>" in page


class TestFilesReadLikeThePartsDo:
    """A file is a thing in a list, as a part is, so it is drawn as one. The row it
    used to be had a text box and two buttons squeezed into table cells beside a
    filename as long as it is."""

    @staticmethod
    def upload(client, aid, name="sb16.img", tags="", note=""):
        r = client.post("/files", data={"aid": aid, "tags": tags or aid, "note": note,
                                        "next": f"/computers/{aid}"},
                        files={"uploads": (name, b"\0" * 2048,
                                           "application/octet-stream")},
                        follow_redirects=False)
        assert r.status_code == 303, r.text

    def test_a_file_is_a_card_with_its_name_on_it(self, client, computer):
        aid = computer()["asset_id"]
        self.upload(client, aid, note="the driver disk that came with it")
        page = client.get(f"/computers/{aid}").text
        assert '<article class="itemcard">' in page
        assert "sb16.img</a></h4>" in page
        assert "the driver disk that came with it" in page

    def test_it_says_how_big_it_is_before_you_click_it(self, client, computer):
        aid = computer()["asset_id"]
        self.upload(client, aid)
        assert "2.0 KiB" in client.get(f"/computers/{aid}").text

    def test_the_names_it_is_filed_under_are_still_editable(self, client, computer):
        """Re-filing is the thing most often wanted here, so it stays a box rather
        than becoming a link to somewhere else."""
        aid = computer()["asset_id"]
        self.upload(client, aid, tags=f"{aid}, Creative Labs Sound Blaster")
        page = client.get(f"/computers/{aid}").text
        assert f'name="tags" value="{aid}, Creative Labs Sound Blaster"' in page

    def test_a_visitor_gets_the_names_without_the_box(self, client, computer,
                                                      monkeypatch):
        aid = computer()["asset_id"]
        self.upload(client, aid, tags=f"{aid}, Creative Labs Sound Blaster")
        # Published first, or there is no card for a visitor to be shown the
        # chips on: an upload is kept back until it is ticked (ADR-0009).
        fid = client.get("/api/files").json()[0]["id"]
        client.post(f"/files/{fid}/public", data={"public": "1"},
                    follow_redirects=False)
        monkeypatch.setattr(main, "AUTH_ENABLED", True)
        page = client.get(f"/computers/{aid}").text
        assert '<span class="chip">Creative Labs Sound Blaster</span>' in page
        assert 'name="tags"' not in page


class TestPagesAreNotKeptByBrowsers:
    """A page carrying no cache headers at all is a page a browser may keep for as
    long as it likes -- there is nothing in the answer to say otherwise. Safari
    does keep them, hardest of all on a phone, and the result is a deploy that
    went out, a server holding the new code, and a reader still running last
    week's. `no-cache` is not "do not store": it is "ask me first"."""

    def test_a_page_is_asked_for_every_time(self, client, part):
        for path in ("/", f"/parts/{part()['asset_id']}", "/machines", "/files"):
            r = client.get(path)
            assert r.headers["cache-control"] == "no-cache", path

    def test_but_a_stamped_photograph_is_still_kept_for_a_year(self, client,
                                                              tmp_path):
        """The opposite rule, on purpose: those URLs carry the version in them, so
        they can never go stale and never need asking about."""
        from PIL import Image
        aid = client.post("/api/computers",
                          json={"manufacturer": "Acme", "model": "PC"}).json()["asset_id"]
        src = tmp_path / "big.jpg"
        Image.new("RGB", (400, 300), (30, 60, 120)).save(src, "JPEG")
        with src.open("rb") as fh:
            client.post(f"/computers/{aid}/photo",
                        files={"photos": ("big.jpg", fh, "image/jpeg")},
                        follow_redirects=False)
        head = client.get(f"/images/computers/{aid}.jpg?v=123").headers["cache-control"]
        assert "immutable" in head and "no-cache" not in head


class TestPhotographsAreServedAtTheSizeAsked:
    """A photograph off a phone is several megabytes and four thousand pixels wide,
    and the gallery draws it into a card two hundred pixels wide. ?w= asks for a
    copy no bigger than it needs, made once and kept; the original is still there
    and is what the lightbox opens.
    """

    def shot(self, client, tmp_path, px=1600):
        """A real JPEG, big enough to be worth shrinking, on a real computer."""
        from PIL import Image
        aid = client.post("/api/computers",
                          json={"manufacturer": "Acme", "model": "PC"}).json()["asset_id"]
        src = tmp_path / "big.jpg"
        Image.new("RGB", (px, int(px * 0.75)), (30, 60, 120)).save(src, "JPEG")
        with src.open("rb") as fh:
            r = client.post(f"/computers/{aid}/photo",
                            files={"photos": ("big.jpg", fh, "image/jpeg")},
                            follow_redirects=False)
        assert r.status_code in (200, 303), r.status_code
        return aid

    def size_of(self, client, url):
        r = client.get(url)
        assert r.status_code == 200, url
        return len(r.content)

    def test_a_width_is_smaller_than_the_original(self, client, tmp_path):
        from PIL import Image
        import io
        aid = self.shot(client, tmp_path)
        rel = f"computers/{aid}.jpg"
        whole = self.size_of(client, f"/images/{rel}")
        card = client.get(f"/images/{rel}?w=300")
        assert card.status_code == 200
        assert len(card.content) < whole / 2, (len(card.content), whole)
        with Image.open(io.BytesIO(card.content)) as im:
            assert im.width == 300

    def test_the_same_copy_is_served_the_second_time(self, client, tmp_path):
        aid = self.shot(client, tmp_path)
        rel = f"computers/{aid}.jpg"
        first = client.get(f"/images/{rel}?w=300").content
        assert client.get(f"/images/{rel}?w=300").content == first

    def test_a_width_nobody_asked_for_is_not_made(self, client, tmp_path):
        """The width comes out of a URL, so a stranger could otherwise fill the disk
        with nine hundred copies of one photograph. An unsupported width gets the
        photograph itself rather than an error."""
        aid = self.shot(client, tmp_path)
        rel = f"computers/{aid}.jpg"
        whole = self.size_of(client, f"/images/{rel}")
        assert self.size_of(client, f"/images/{rel}?w=417") == whole

    def test_a_photograph_smaller_than_the_width_is_served_as_it_is(self, client,
                                                                    tmp_path):
        aid = self.shot(client, tmp_path, px=250)
        rel = f"computers/{aid}.jpg"
        whole = self.size_of(client, f"/images/{rel}")
        assert self.size_of(client, f"/images/{rel}?w=300") == whole

    def test_a_stamped_url_may_be_kept_and_an_unstamped_one_may_not(self, client,
                                                                    tmp_path):
        """?v= names which version of the photograph the URL wants, so it can never
        go stale and can be cached for a year. Without it, an hour."""
        aid = self.shot(client, tmp_path)
        rel = f"computers/{aid}.jpg"
        assert "immutable" in client.get(f"/images/{rel}?v=123").headers["cache-control"]
        assert "immutable" not in client.get(f"/images/{rel}").headers["cache-control"]

    def test_the_gallery_asks_for_card_sized_copies_and_keeps_the_original(
            self, client, tmp_path):
        aid = self.shot(client, tmp_path)
        page = client.get("/").text
        assert "w=300" in page and "srcset" in page
        item = client.get(f"/computers/{aid}").text
        # The page shows a copy; the lightbox is handed the original.
        assert "w=1200" in item
        assert f'data-full="/images/computers/{aid}.jpg?v=' in item

    def test_the_static_files_may_be_kept_when_the_url_says_which_version(self,
                                                                          client):
        stamped = client.get("/static/site.webmanifest?v=abc").headers["cache-control"]
        plain = client.get("/static/site.webmanifest").headers["cache-control"]
        assert "immutable" in stamped and "31536000" in stamped
        assert "immutable" not in plain


class TestASerialThatWasNeverRecorded:
    """0028 added `serial` nullable and backfilled nothing, while the model and the
    response shape both said an unrecorded one is "". Two spellings of the same
    state, and the API only spoke one: a single NULL row made
    `GET /api/computers` a 500 for the whole list, which took the public REST API
    and every MCP tool with it. 0034 settles it on "" and makes the column NOT
    NULL; these hold both ends of that.
    """

    def test_an_unrecorded_serial_reads_back_blank(self, computer, part):
        c = computer(model="No Number")
        assert c["serial"] == ""
        assert part(model="Also None")["serial"] == ""

    def test_listing_survives_a_machine_with_no_serial(self, client, computer):
        computer(model="No Number")
        r = client.get("/api/computers")
        assert r.status_code == 200
        assert [m["serial"] for m in r.json()] == [""]

    def test_listing_survives_a_part_with_no_serial(self, client, part):
        part(model="Also None")
        r = client.get("/api/parts")
        assert r.status_code == 200
        assert [p["serial"] for p in r.json()] == [""]

    @pytest.mark.parametrize("shape", [schemas.ComputerOut, schemas.PartOut])
    def test_a_null_from_an_older_database_still_reads_as_blank(self, shape):
        """The belt to 0034's braces, and not reachable end-to-end once the column
        is NOT NULL -- which is the point. A database restored from a backup taken
        before 0034 carries NULLs into a schema that no longer allows them, and one
        of those must not cost the caller the entire list. Asserted against the
        shape directly because the schema will no longer let the row exist."""
        assert shape.model_validate({"asset_id": "RH-0001", "serial": None}).serial == ""
