"""Files kept beside the register: drivers, manuals, ROM dumps, receipts.

MANUAL.md section 11 is the specification and these are its promises, a class to
a heading and a test to a promise. A file is linked to the things it is for by
their asset tags and to nothing else (ADR-0028): the model suggests, in two places,
and never links anything itself. Everything done to a file is done on its own page,
and the lists change nothing. A file says what it is by the end of its name. And
nothing is public until it is ticked (ADR-0009), wherever the owner has the tick
start (ADR-0029).

The tests press what a page offers rather than posting field names of their own
wherever a page offers something to press: the manual promises a button, and
pressing it is what a reader does.
"""

import re
from html.parser import HTMLParser

import pytest

from app import filekinds, main
from app.models import StoredFile


def upload(client, name, body=b"driver bytes", note="", **extra):
    r = client.post(
        "/files",
        files={"uploads": (name, body)},
        data={"note": note, **extra},
        follow_redirects=False,
    )
    assert r.status_code == 303, r.text
    return r


def publish(client, fid, public=True):
    """Tick the box, or untick it. An unticked checkbox sends no field at all,
    which is what the off case posts here."""
    r = client.post(
        f"/files/{fid}/public", data={"public": "1"} if public else {}, follow_redirects=False
    )
    assert r.status_code == 303, r.text
    return r


def ids_on(client, url):
    """The files a page offers for download, by id."""
    return {int(i) for i in re.findall(r'href="/files/(\d+)/', client.get(url).text)}


def file_ids(client):
    """Every file's id, newest first, as the API lists them."""
    return [f["id"] for f in client.get("/api/files").json()]


def newest(client):
    return file_ids(client)[0]


def linked_to(client, fid):
    """The asset ids a file is linked to, as the API says."""
    return set(next(f for f in client.get("/api/files").json() if f["id"] == fid)["assets"])


def visitor(monkeypatch):
    """Everything after this is asked by somebody who is not logged in."""
    monkeypatch.setattr(main.auth, "AUTH_ENABLED", True)


def project(client, name="Recap the PC1512", private=False):
    r = client.post("/api/projects", json={"name": name, "private": private})
    assert r.status_code == 200, r.text
    return r.json()["asset_id"]


def prefer_public(client, on=True):
    """Save the settings page with New files are public ticked, and the rest as it
    stands -- a browser sends the whole form."""
    data = {"site_name": "", "theme": "system", "watermark": "1", "remember_locations": "1"}
    if on:
        data["files_public"] = "1"
    r = client.post("/settings", data=data, follow_redirects=False)
    assert r.status_code == 303, r.text


class Forms(HTMLParser):
    """The forms on a page, each as the fields it would post and the words on its
    button."""

    def __init__(self, action_contains=""):
        super().__init__(convert_charrefs=True)
        self.wanted = action_contains
        self.forms = []
        self._open = None

    def handle_starttag(self, tag, attrs):
        got = dict(attrs)
        if tag == "form":
            action = got.get("action", "")
            self._open = ({}, [], action) if self.wanted in action else None
        elif self._open is not None and tag == "input" and got.get("name"):
            if got.get("type") == "checkbox" and "checked" not in got:
                return
            self._open[0][got["name"]] = got.get("value", "")
        elif self._open is not None and tag == "button" and got.get("aria-label"):
            self._open[1].append(got["aria-label"] + " ")

    def handle_data(self, data):
        if self._open is not None:
            self._open[1].append(data)

    def handle_endtag(self, tag):
        if tag == "form" and self._open is not None:
            fields, words, action = self._open
            self.forms.append(
                {"fields": fields, "action": action, "says": " ".join("".join(words).split())}
            )
            self._open = None


def forms_on(html, action_contains=""):
    parser = Forms(action_contains)
    parser.feed(html)
    return parser.forms


def press(client, html, action_contains, says, **typed):
    """Press the button on this page whose words say `says`, posting what its form
    carries and anything `typed` into its boxes. Fails loudly when the page does not
    offer it."""
    offered = forms_on(html, action_contains)
    match = [f for f in offered if says in f["says"]]
    assert match, (
        f"no button saying {says!r} posting to {action_contains!r}; "
        f"the page offers {[f['says'] for f in offered]}"
    )
    r = client.post(match[0]["action"], data=match[0]["fields"] | typed, follow_redirects=False)
    assert r.status_code == 303, r.text
    return r


def card(part, **fields):
    return part(**({"manufacturer": "Trident", "model": "TVGA8900", "type": "video"} | fields))[
        "asset_id"
    ]


class TestLinkingOne:
    """Section 11: a file is linked to the things it is for, by their asset tags,
    and an item's panel shows the files linked to it and nothing else."""

    def test_an_upload_is_linked_to_the_item_it_started_on(self, client, part):
        aid = card(part)
        upload(client, "tvga.zip", aid=aid)
        assert linked_to(client, newest(client)) == {aid}
        assert ids_on(client, f"/parts/{aid}") == {newest(client)}

    def test_and_to_nothing_else(self, client, part):
        """Another card of the same model is not offered it by being one: that is
        the difference between a link and the model links it replaced."""
        one, two = card(part), card(part)
        upload(client, "tvga.zip", aid=one)
        assert ids_on(client, f"/parts/{two}") == set()

    def test_one_file_can_be_linked_to_several_things_and_is_on_each_page(
        self, client, part, computer
    ):
        board = card(part)
        machine = computer(manufacturer="Amstrad", model="PC1512")["asset_id"]
        upload(client, "tvga.zip", aid=board)
        fid = newest(client)
        press(client, client.get(f"/files/{fid}").text, "/link", "link", aid=machine)
        assert linked_to(client, fid) == {board, machine}
        assert fid in ids_on(client, f"/parts/{board}")
        assert fid in ids_on(client, f"/computers/{machine}")

    def test_renaming_an_item_or_correcting_its_model_moves_nothing(self, client, part):
        """A link names an asset tag, and a tag never changes."""
        aid = card(part)
        upload(client, "tvga.zip", aid=aid)
        r = client.patch(f"/api/parts/{aid}", json={"model": "TVGA8900C", "name": "The spare"})
        assert r.status_code == 200, r.text
        assert ids_on(client, f"/parts/{aid}") == {newest(client)}
        later = card(part)
        assert ids_on(client, f"/parts/{later}") == set()


class TestTheOtherUnitsOfTheModel:
    """Section 11, "Uploading one": the upload box offers the other units of the
    same model still held, as one tick, and says in the tooltip which they are."""

    def test_the_upload_box_offers_them(self, client, part):
        one, two, three = card(part), card(part), card(part)
        page = client.get(f"/parts/{one}").text
        assert re.search(r'name="siblings"[^>]*>\s*the other 2 Trident TVGA8900', page)
        tooltip = re.search(
            r'<label class="tickbox" title="([^"]*)"><input type="checkbox" name="siblings"', page
        )
        assert tooltip and set(tooltip.group(1).split(", ")) == {two, three}

    def test_ticking_it_links_the_file_to_them_as_well(self, client, part):
        one, two, three = card(part), card(part), card(part)
        upload(client, "tvga.zip", aid=one, siblings="1")
        assert linked_to(client, newest(client)) == {one, two, three}

    def test_left_alone_it_links_the_file_to_this_one(self, client, part):
        one, _two = card(part), card(part)
        upload(client, "tvga.zip", aid=one)
        assert linked_to(client, newest(client)) == {one}

    def test_a_unit_that_has_been_disposed_of_is_not_counted(self, client, part):
        one, two, gone = card(part), card(part), card(part)
        r = client.patch(f"/api/parts/{gone}", json={"disposed": True})
        assert r.status_code == 200, r.text
        assert "the other Trident TVGA8900" in client.get(f"/parts/{one}").text
        upload(client, "tvga.zip", aid=one, siblings="1")
        assert linked_to(client, newest(client)) == {one, two}

    def test_case_and_spacing_make_no_difference(self, client, part):
        one = card(part)
        two = card(part, manufacturer="trident", model="tvga  8900")
        upload(client, "tvga.zip", aid=one, siblings="1")
        assert linked_to(client, newest(client)) == {one, two}

    def test_a_machine_the_catalogue_names_is_the_model_however_it_was_typed(
        self, client, computer
    ):
        one = computer(
            manufacturer="Sinclair",
            model="ZX Spectrum 48K",
            machine={"model_key": "zx-spectrum-48k"},
        )["asset_id"]
        two = computer(
            manufacturer="sinclair research",
            model="Spectrum",
            machine={"model_key": "zx-spectrum-48k"},
        )["asset_id"]
        upload(client, "manual.pdf", aid=one, siblings="1")
        assert linked_to(client, newest(client)) == {one, two}

    def test_the_tick_is_the_models_and_nothing_else(self, client, part):
        """Which units it means is worked out when the upload arrives, not read from
        the form: a list of ids posted from a page would be a way to link a file to
        anything at all."""
        one = card(part)
        other = card(part, manufacturer="Tseng", model="ET4000")
        upload(client, "tvga.zip", aid=one, siblings="1", also=other)
        assert linked_to(client, newest(client)) == {one}

    def test_a_card_with_no_other_units_is_not_offered_a_tick(self, client, part):
        aid = card(part)
        assert 'name="siblings"' not in client.get(f"/parts/{aid}").text


class TestWhenAnotherOfTheSameModelArrives:
    """Section 11: a unit is offered the files its siblings have and it has not,
    each with "link", and only the owner sees the list."""

    def test_a_new_unit_is_offered_its_siblings_files(self, client, part):
        first = card(part)
        upload(client, "tvga.zip", aid=first)
        fid = newest(client)
        later = card(part)
        page = client.get(f"/parts/{later}").text
        assert "Your other Trident TVGA8900 have a file this one has not" in page
        press(client, page, f"/files/{fid}/link", "link")
        assert ids_on(client, f"/parts/{later}") == {fid}

    def test_a_file_it_already_has_is_not_offered(self, client, part):
        one, two = card(part), card(part)
        upload(client, "tvga.zip", aid=one, siblings="1")
        assert "this one has not" not in client.get(f"/parts/{two}").text

    def test_nothing_reaches_it_until_it_is_linked(self, client, part):
        upload(client, "tvga.zip", aid=card(part))
        later = card(part)
        assert ids_on(client, f"/parts/{later}") == set()

    def test_a_visitor_is_not_shown_the_offer(self, client, part, monkeypatch):
        upload(client, "tvga.zip", aid=card(part))
        publish(client, newest(client))
        later = card(part)
        visitor(monkeypatch)
        assert "this one has not" not in client.get(f"/parts/{later}").text


class TestAFilesPage:
    """Section 11, "A file's page": what it is, how big, when it came, what it is
    linked to and a download -- and, for the owner, everything done to a file."""

    def test_it_says_what_the_file_is_and_what_it_is_for(self, client, part):
        aid = card(part)
        upload(client, "sbbasic.img", body=b"\0" * 1_474_560, aid=aid)
        fid = newest(client)
        page = client.get(f"/files/{fid}").text
        assert "sbbasic.img" in page
        assert "floppy image · 3½″ 1.44M" in page
        assert f'href="/parts/{aid}"' in page
        assert f'href="/files/{fid}/sbbasic.img">download</a>' in page

    def test_the_note_is_changed_there(self, client, part):
        upload(client, "tvga.zip", aid=card(part))
        fid = newest(client)
        press(client, client.get(f"/files/{fid}").text, "/note", "save", note="DOS drivers")
        assert "DOS drivers" in client.get(f"/files/{fid}").text
        assert client.get("/api/files").json()[0]["note"] == "DOS drivers"

    def test_it_is_linked_to_one_more_by_asset_tag(self, client, part):
        one, two = card(part), card(part, manufacturer="Tseng", model="ET4000")
        upload(client, "tvga.zip", aid=one)
        fid = newest(client)
        press(client, client.get(f"/files/{fid}").text, "/link", "link", aid=two.lower())
        assert linked_to(client, fid) == {one, two}

    def test_a_tag_not_in_the_register_is_refused_with_a_line_saying_so(self, client, part):
        aid = card(part)
        upload(client, "tvga.zip", aid=aid)
        fid = newest(client)
        r = press(client, client.get(f"/files/{fid}").text, "/link", "link", aid="RH-ZZZZ")
        page = client.get(r.headers["location"]).text
        assert "RH-ZZZZ is not a machine, a part or a project in the register." in page
        assert linked_to(client, fid) == {aid}

    def test_a_project_can_have_it_too(self, client, part):
        aid = card(part)
        upload(client, "tvga.zip", aid=aid)
        fid = newest(client)
        work = project(client)
        press(client, client.get(f"/files/{fid}").text, "/link", "link", aid=work)
        assert linked_to(client, fid) == {aid, work}
        assert fid in ids_on(client, f"/projects/{work}")

    def test_unlinking_takes_it_off_and_keeps_the_file(self, client, part):
        aid = card(part)
        upload(client, "tvga.zip", aid=aid)
        fid = newest(client)
        press(client, client.get(f"/files/{fid}").text, "/unlink", f"unlink from {aid}")
        assert ids_on(client, f"/parts/{aid}") == set()
        assert file_ids(client) == [fid]

    def test_a_file_linked_to_nothing_is_unlinked_and_found_under_that_name(self, client, part):
        aid = card(part)
        upload(client, "tvga.zip", aid=aid)
        fid = newest(client)
        client.post(f"/files/{fid}/unlink", data={"aid": aid})
        assert "Unlinked: it is on no item's page." in client.get(f"/files/{fid}").text
        assert ids_on(client, "/files?show=unlinked") == {fid}

    def test_delete_removes_it_and_every_link(self, client, part, db):
        aid = card(part)
        upload(client, "tvga.zip", aid=aid)
        fid = newest(client)
        stored = db.get(StoredFile, fid).stored
        from app import filesdb

        assert (filesdb.FILES_DIR / stored).exists()
        press(client, client.get(f"/files/{fid}").text, "/delete", "delete")
        assert file_ids(client) == []
        assert not (filesdb.FILES_DIR / stored).exists()
        assert ids_on(client, f"/parts/{aid}") == set()

    def test_a_visitor_sees_a_published_files_page_without_the_controls(
        self, client, part, monkeypatch
    ):
        aid = card(part)
        upload(client, "tvga.zip", note="DOS drivers", aid=aid)
        fid = newest(client)
        publish(client, fid)
        visitor(monkeypatch)
        page = client.get(f"/files/{fid}").text
        assert "DOS drivers" in page and f'href="/parts/{aid}"' in page
        assert forms_on(page, f"/files/{fid}/") == []

    def test_a_visitor_is_told_an_unpublished_files_page_is_not_there(
        self, client, part, monkeypatch
    ):
        upload(client, "receipt.pdf", aid=card(part))
        fid = newest(client)
        visitor(monkeypatch)
        r = client.get(f"/files/{fid}", follow_redirects=False)
        assert r.status_code == 404
        assert "www-authenticate" not in r.headers


class TestTheFilesPage:
    """Section 11, "The files page"."""

    def test_it_lists_every_file_newest_first_with_what_it_is_linked_to(self, client, part):
        aid = card(part)
        upload(client, "old.zip", aid=aid)
        upload(client, "new.zip", aid=aid)
        page = client.get("/files").text
        assert page.index("new.zip") < page.index("old.zip")
        assert f'<a class="linkchip" href="/parts/{aid}"' in page

    def test_nothing_on_a_row_changes_anything(self, client, part):
        """A row used to carry six forms. Everything done to a file is on its page."""
        aid = card(part)
        upload(client, "tvga.zip", aid=aid)
        for path in ("/files", f"/parts/{aid}"):
            rows = re.search(r'<ul class="filerows">.*?</ul>', client.get(path).text, re.S)
            assert rows and "<form" not in rows.group(0), path

    def test_a_row_opens_the_files_page_and_its_button_downloads_it(self, client, part):
        upload(client, "tvga.zip", aid=card(part))
        fid = newest(client)
        page = client.get("/files").text
        assert f'<a class="fname" href="/files/{fid}">tvga.zip</a>' in page
        assert f'<a class="fdl" href="/files/{fid}/tvga.zip" aria-label="download tvga.zip"' in page

    def test_units_of_one_model_are_one_chip_and_all_of_them_on_its_page(self, client, part):
        units = [card(part, model="PicoGUS", manufacturer="Polpo", type="sound") for _ in range(5)]
        upload(client, "picogus.img", aid=units[0], siblings="1")
        fid = newest(client)
        page = client.get("/files").text
        assert "<b>5 ×</b> Polpo PicoGUS" in page
        own = client.get(f"/files/{fid}").text
        assert all(f'href="/parts/{u}"' in own for u in units)

    def test_it_can_be_narrowed_to_one_kind(self, client, part):
        aid = card(part)
        upload(client, "manual.pdf", aid=aid)
        upload(client, "drivers.img", body=b"\0" * 1_474_560, aid=aid)
        page = client.get("/files").text
        assert "documents <span>1</span>" in page and "disk images <span>1</span>" in page
        narrowed = client.get("/files?kind=disk").text
        assert "drivers.img" in narrowed and "manual.pdf" not in narrowed

    def test_a_kind_is_offered_only_when_there_is_another_to_tell_it_from(self, client, part):
        aid = card(part)
        upload(client, "one.pdf", aid=aid)
        upload(client, "two.pdf", aid=aid)
        assert "documents <span>" not in client.get("/files").text

    def test_unlinked_and_private_are_the_owners_alone(self, client, part, monkeypatch):
        aid = card(part)
        upload(client, "kept.pdf", aid=aid)
        upload(client, "shown.pdf", aid=aid)
        publish(client, newest(client))
        shown, kept = file_ids(client)
        page = client.get("/files").text
        assert "private <span>1</span>" in page
        assert ids_on(client, "/files?show=private") == {kept}
        visitor(monkeypatch)
        page = client.get("/files").text
        assert "private <span>" not in page and "unlinked <span>" not in page
        # Asked for anyway, it is not a list a visitor has: they get what they may see.
        assert ids_on(client, "/files?show=private") == {shown}

    def test_the_search_finds_a_file_by_its_name_its_note_or_what_it_is_linked_to(
        self, client, part
    ):
        aid = card(part)
        other = card(part, manufacturer="Tseng", model="ET4000")
        upload(client, "tvga.zip", note="Windows 3.1 drivers", aid=aid)
        upload(client, "et4000.zip", aid=other)
        tvga, et4000 = file_ids(client)[1], file_ids(client)[0]
        assert ids_on(client, "/files?q=tvga.zip") == {tvga}
        assert ids_on(client, "/files?q=windows 3.1") == {tvga}
        assert ids_on(client, f"/files?q={other}") == {et4000}
        assert ids_on(client, "/files?q=tseng") == {et4000}

    def test_the_list_marks_the_private_ones_for_the_owner(self, client, part):
        upload(client, "receipt.pdf", aid=card(part))
        assert '<span class="lock"' in client.get("/files").text


class TestWhatKindOfFileItIs:
    """Section 11, "What kind of file it is"."""

    @pytest.mark.parametrize(
        ("name", "drawing"),
        [
            ("manual.pdf", "document"),
            ("readme.txt", "document"),
            ("drivers.zip", "archive"),
            ("board.jpg", "picture"),
            ("bios.rom", "rom"),
            ("setup.exe", "program"),
            ("tune.mid", "sound"),
            ("game.tzx", "tape"),
            ("win95.iso", "cd"),
            ("drive.vhd", "harddisk"),
            ("thing.xyz", "other"),
            ("README", "other"),
        ],
    )
    def test_it_is_read_from_the_end_of_its_name(self, name, drawing):
        assert filekinds.of(name, 1000).drawing == drawing

    @pytest.mark.parametrize(
        ("kib", "drawing", "said"),
        [
            (160, "floppy525", "5¼″ 160K"),
            (180, "floppy525", "5¼″ 180K"),
            (320, "floppy525", "5¼″ 320K"),
            (360, "floppy525", "5¼″ 360K"),
            (1200, "floppy525", "5¼″ 1.2M"),
            (720, "floppy35", "3½″ 720K"),
            (1440, "floppy35", "3½″ 1.44M"),
            (1680, "floppy35", "3½″ 1.68M"),
            (2880, "floppy35", "3½″ 2.88M"),
        ],
    )
    def test_a_floppy_image_says_which_floppy_it_is(self, kib, drawing, said):
        what = filekinds.of("disk.img", kib * 1024)
        assert (what.drawing, what.size) == (drawing, said)

    def test_the_other_names_for_a_raw_image_are_read_the_same_way(self):
        for name in ("disk.ima", "disk.vfd", "disk.flp", "DISK.IMG"):
            assert filekinds.of(name, 1440 * 1024).size == "3½″ 1.44M", name

    def test_an_image_of_any_other_size_is_a_floppy_under_3_mib_and_a_hard_disk_over(self):
        small = filekinds.of("odd.img", 1000 * 1024)
        assert (small.drawing, small.size) == ("floppy35", "1000 KiB")
        big = filekinds.of("drive.img", 20 * 1024 * 1024)
        assert (big.drawing, big.size) == ("harddisk", "20 MiB")

    def test_an_amiga_disk_is_880k(self):
        what = filekinds.of("workbench.adf", 880 * 1024)
        assert (what.drawing, what.size) == ("floppy35", "3½″ 880K")

    def test_a_bin_is_a_rom_under_4_mib_and_a_cd_image_over(self):
        assert filekinds.of("bios.bin", 64 * 1024).drawing == "rom"
        assert filekinds.of("game.bin", 600 * 1024 * 1024).drawing == "cd"

    def test_the_list_draws_each_file_as_its_kind_with_its_extension(self, client, part):
        upload(client, "sbbasic.img", body=b"\0" * 1_474_560, aid=card(part))
        page = client.get("/files").text
        assert 'data-drawing="floppy35"' in page
        assert '<span class="fileext">IMG</span>' in page
        assert "3½″ 1.44M" in page

    def test_the_kind_decides_nothing_about_who_sees_it(self, client, part, monkeypatch):
        aid = card(part)
        upload(client, "manual.pdf", aid=aid)
        upload(client, "drivers.img", body=b"\0" * 1_474_560, aid=aid)
        visitor(monkeypatch)
        assert ids_on(client, "/files") == set()

    def test_a_size_is_said_the_way_it_would_be_said(self):
        assert filekinds.human_size(0) == "0 B"
        assert filekinds.human_size(900) == "900 B"
        assert filekinds.human_size(2048) == "2.0 KiB"
        assert filekinds.human_size(20 * 1024) == "20 KiB"
        assert filekinds.human_size(5 * 1024**2) == "5.0 MiB"


class TestWhoCanSeeAFile:
    """Section 11, "Who can see a file": nothing is public until the box is ticked,
    and a file kept back is kept back everywhere rather than only where it is
    listed."""

    def test_a_new_upload_is_not_public(self, client, part, monkeypatch):
        aid = card(part)
        upload(client, "tvga.zip", aid=aid)
        fid = newest(client)
        visitor(monkeypatch)
        assert client.get(f"/files/{fid}/tvga.zip").status_code == 404
        assert ids_on(client, f"/parts/{aid}") == set()
        assert "tvga.zip" not in client.get("/files").text

    def test_ticking_public_as_it_is_uploaded_publishes_it(self, client, part, monkeypatch):
        aid = card(part)
        upload(client, "tvga.zip", body=b"driver", aid=aid, public="1")
        fid = newest(client)
        visitor(monkeypatch)
        assert client.get(f"/files/{fid}/tvga.zip").content == b"driver"

    def test_ticking_the_box_on_its_page_publishes_it(self, client, part, monkeypatch):
        aid = card(part)
        upload(client, "tvga.zip", body=b"driver", aid=aid)
        fid = newest(client)
        press(client, client.get(f"/files/{fid}").text, "/public", "save", public="1")
        visitor(monkeypatch)
        assert client.get(f"/files/{fid}/tvga.zip").content == b"driver"
        assert ids_on(client, f"/parts/{aid}") == {fid}

    def test_unticking_it_takes_it_back_everywhere(self, client, part, monkeypatch):
        aid = card(part)
        upload(client, "tvga.zip", aid=aid)
        fid = newest(client)
        publish(client, fid)
        publish(client, fid, public=False)
        visitor(monkeypatch)
        assert client.get(f"/files/{fid}/tvga.zip").status_code == 404
        assert client.get(f"/files/{fid}").status_code == 404
        assert ids_on(client, f"/parts/{aid}") == set()
        assert "tvga.zip" not in client.get("/files?q=tvga").text

    def test_an_unpublished_file_is_missing_rather_than_forbidden(self, client, part, monkeypatch):
        """404 and not 401: there is no account a visitor could log in to, so an
        invitation to authenticate would say only that the file is there."""
        upload(client, "invoice.pdf", aid=card(part))
        fid = newest(client)
        visitor(monkeypatch)
        for path in (f"/files/{fid}/invoice.pdf", f"/files/{fid}"):
            r = client.get(path, follow_redirects=False)
            assert r.status_code == 404, path
            assert "www-authenticate" not in r.headers

    def test_the_owner_is_shown_both(self, client, part):
        aid = card(part)
        upload(client, "public.zip", aid=aid)
        upload(client, "private.zip", aid=aid)
        publish(client, file_ids(client)[1])
        page = client.get(f"/parts/{aid}").text
        assert "public.zip" in page and "private.zip" in page
        assert len(ids_on(client, "/files")) == 2

    def test_only_the_owner_may_publish(self, client, part, monkeypatch):
        upload(client, "tvga.zip", aid=card(part))
        fid = newest(client)
        visitor(monkeypatch)
        r = client.post(f"/files/{fid}/public", data={"public": "1"}, follow_redirects=False)
        assert r.status_code == 303 and "/login" in r.headers["location"]
        monkeypatch.setattr(main.auth, "AUTH_ENABLED", False)
        assert client.get("/api/files").json()[0]["public"] is False

    def test_an_unpublished_file_is_not_cached_anywhere(self, client, part):
        upload(client, "invoice.pdf", aid=card(part))
        fid = newest(client)
        assert client.get(f"/files/{fid}/invoice.pdf").headers["cache-control"] == (
            "private, no-store"
        )
        publish(client, fid)
        assert client.get(f"/files/{fid}/invoice.pdf").headers["cache-control"] == (
            "public, max-age=3600"
        )

    def test_the_wire_format_says_which(self, client, part):
        upload(client, "manual.pdf", aid=card(part))
        publish(client, newest(client))
        assert client.get("/api/files").json()[0]["public"] is True

    def test_a_visitor_is_never_told_a_file_is_linked_to_a_private_project(
        self, client, part, monkeypatch
    ):
        aid = card(part)
        secret = project(client, name="Selling the loft", private=True)
        upload(client, "valuation.pdf", aid=aid, public="1")
        fid = newest(client)
        client.post(f"/files/{fid}/link", data={"aid": secret})
        visitor(monkeypatch)
        for path in (f"/files/{fid}", "/files"):
            page = client.get(path).text
            assert secret not in page and "Selling the loft" not in page, path
            assert f'href="/parts/{aid}"' in page, path
        assert ids_on(client, "/files?q=selling the loft") == set()
        assert ids_on(client, f"/files?q={secret}") == set()


class TestNewFilesArePublic:
    """Section 18, "New files", and section 11: the preference moves where the tick
    starts, and never publishes anything by itself (ADR-0029)."""

    def test_it_is_off_so_the_box_starts_unticked(self, client, part):
        page = client.get(f"/parts/{card(part)}").text
        assert '<input type="checkbox" name="public" value="1"> Public' in page

    def test_on_the_box_starts_ticked(self, client, part):
        prefer_public(client)
        page = client.get(f"/parts/{card(part)}").text
        assert '<input type="checkbox" name="public" value="1" checked> Public' in page

    def test_but_never_on_a_private_projects_page(self, client):
        prefer_public(client)
        page = client.get(f"/projects/{project(client, private=True)}").text
        assert '<input type="checkbox" name="public" value="1"> Public' in page
        assert '<input type="checkbox" name="public" value="1"> Public' not in (
            client.get(f"/projects/{project(client)}").text
        )

    def test_the_upload_sends_what_the_box_says(self, client, part):
        prefer_public(client)
        upload(client, "tvga.zip", aid=card(part))
        assert client.get("/api/files").json()[0]["public"] is False


class TestProjectsHaveFiles:
    """Section 12, "Files"."""

    def test_an_upload_on_a_project_is_linked_to_it(self, client):
        work = project(client)
        page = client.get(f"/projects/{work}").text
        assert 'action="/files"' in page and f'name="aid" value="{work}"' in page
        upload(client, "schematic.pdf", aid=work)
        fid = newest(client)
        assert linked_to(client, fid) == {work}
        assert ids_on(client, f"/projects/{work}") == {fid}

    def test_a_project_is_offered_no_other_units(self, client):
        assert 'name="siblings"' not in client.get(f"/projects/{project(client)}").text

    def test_deleting_a_project_takes_its_links_and_not_its_files(self, client):
        work = project(client)
        upload(client, "receipt.pdf", aid=work)
        fid = newest(client)
        r = client.post(f"/projects/{work}/delete", follow_redirects=False)
        assert r.status_code == 303, r.text
        assert file_ids(client) == [fid]
        assert linked_to(client, fid) == set()


class TestDeletingAnItem:
    def test_deleting_an_item_takes_the_link_and_not_the_bytes(self, client, part):
        """Unlinked is a state, not a reason to bin something (ADR-0006)."""
        aid = card(part)
        upload(client, "receipt.pdf", aid=aid)
        fid = newest(client)
        client.delete(f"/api/parts/{aid}")
        assert file_ids(client) == [fid]
        assert linked_to(client, fid) == set()


class TestTheBytes:
    def test_what_was_uploaded_comes_back_byte_for_byte(self, client, part):
        aid = card(part)
        upload(client, "tvga.zip", b"PK\x03\x04 not really a zip", aid=aid)
        fid = ids_on(client, f"/parts/{aid}").pop()
        r = client.get(f"/files/{fid}/tvga.zip")
        assert r.status_code == 200
        assert r.content == b"PK\x03\x04 not really a zip"

    def test_it_is_handed_over_as_a_download_and_never_as_a_page(self, client, db):
        """An upload is whatever somebody sent, and some of what people send is
        HTML. Served as a page it would run as this site, with this site's
        cookies -- so one content type for everything, an attachment, and nosniff
        so the browser does not decide it knows better."""
        upload(client, "readme.html", b"<script>alert(1)</script>")
        fid = db.query(StoredFile).one().id
        r = client.get(f"/files/{fid}/readme.html")
        assert r.headers["content-type"] == "application/octet-stream"
        assert r.headers["content-disposition"].startswith("attachment")
        assert r.headers["x-content-type-options"] == "nosniff"

    def test_the_name_it_was_sent_under_is_never_a_path(self, client, db):
        """The one part of an upload chosen entirely by whoever sent it."""
        from app import filesdb

        upload(client, "../../etc/passwd", b"nope")
        row = db.query(StoredFile).one()
        assert "/" not in row.stored and ".." not in row.stored
        assert (filesdb.FILES_DIR / row.stored).is_file()
        # What was typed is kept, for the download to be called by.
        assert row.filename == "passwd"

    def test_two_files_of_the_same_name_do_not_land_on_each_other(self, client, db):
        from app import filesdb

        upload(client, "driver.zip", b"first")
        upload(client, "driver.zip", b"second")
        rows = db.query(StoredFile).all()
        assert len({r.stored for r in rows}) == 2
        assert {(filesdb.FILES_DIR / r.stored).read_bytes() for r in rows} == {b"first", b"second"}

    def test_an_empty_upload_is_not_a_file(self, client, db):
        upload(client, "nothing.txt", b"")
        assert db.query(StoredFile).count() == 0

    def test_one_over_the_limit_is_refused_and_leaves_nothing_behind(self, client, db, monkeypatch):
        from app import filesdb

        monkeypatch.setattr(filesdb, "MAX_BYTES", 32)
        r = upload(client, "big.bin", b"x" * 200)
        assert r.headers["location"].endswith("fileerr=1")
        assert db.query(StoredFile).count() == 0
        assert not list(filesdb.FILES_DIR.glob("*.bin"))

    def test_an_upload_with_nothing_to_be_linked_to_is_kept_unlinked(self, client):
        """Nothing is lost for want of a page to have started on: the file is kept,
        and the files page lists it as unlinked."""
        upload(client, "found.pdf")
        fid = newest(client)
        assert linked_to(client, fid) == set()
        assert ids_on(client, "/files?show=unlinked") == {fid}


class TestWhoMayDoWhat:
    def test_a_visitor_may_download_but_not_change_anything(self, client, part, monkeypatch):
        aid = card(part)
        upload(client, "tvga.zip", aid=aid)
        fid = newest(client)
        publish(client, fid)
        visitor(monkeypatch)
        assert client.get(f"/files/{fid}/tvga.zip").status_code == 200
        assert client.get(f"/files/{fid}").status_code == 200
        for path in (
            f"/files/{fid}/delete",
            f"/files/{fid}/link",
            f"/files/{fid}/unlink",
            f"/files/{fid}/note",
            f"/files/{fid}/public",
            "/files",
        ):
            r = client.post(path, data={}, follow_redirects=False)
            assert r.status_code == 303 and "/login" in r.headers["location"], path

    def test_a_visitor_is_not_shown_the_upload_box(self, client, part, monkeypatch):
        aid = card(part)
        visitor(monkeypatch)
        page = client.get(f"/parts/{aid}").text
        assert "Files" in page and 'action="/files"' not in page


class TestTheApi:
    def test_it_lists_each_file_with_what_it_is_linked_to(self, client, part):
        aid = card(part)
        upload(client, "tvga.zip", note="drivers", aid=aid)
        got = client.get("/api/files").json()
        assert [(f["filename"], f["note"], f["assets"]) for f in got] == [
            ("tvga.zip", "drivers", [aid])
        ]
        assert "tags" not in got[0] and "models" not in got[0]
