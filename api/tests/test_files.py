"""Files kept beside the register: drivers, manuals, ROM dumps.

What makes these different from photographs is that they are not about one object.
A driver is about a model, so a file is filed under the names it covers and every
item answering to one of them offers it. These tests are mostly about that matching
-- who sees a file and who does not -- and about the two things that make serving
somebody else's uploads back out of your own domain safe.

Since 0035 there is a second sense of "who sees a file": the same box that takes a
driver disk takes a receipt with an address on it, so nothing is published until
it is ticked (ADR-0009). TestPublishingOne is that half.
"""

import re
from html.parser import HTMLParser

from app import filesdb
from app.models import FileTag, StoredFile


def upload(client, name, body=b"driver bytes", tags="", note="", **extra):
    r = client.post(
        "/files",
        files={"uploads": (name, body)},
        data={"tags": tags, "note": note, **extra},
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
    """The file ids offered on an item's page."""
    import re

    return set(re.findall(r'href="/files/(\d+)/', client.get(url).text))


def file_ids(client):
    """Every file's id, newest first, as the API lists them."""
    return [f["id"] for f in client.get("/api/files").json()]


class Forms(HTMLParser):
    """The forms on a page, each as the fields it would post and the words on its
    button.

    The tests below press what the page offers rather than posting field names of
    their own. A test that knows a model is keyed `trident|tvga8900` is a test of
    how the links are stored; what the manual promises is a button that says
    "attach to every Trident TVGA8900", and pressing it is what a reader does."""

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
            self._open[0][got["name"]] = got.get("value", "")

    def handle_data(self, data):
        if self._open is not None:
            self._open[1].append(data)

    def handle_endtag(self, tag):
        if tag == "form" and self._open is not None:
            fields, buttons, action = self._open
            self.forms.append(
                {"fields": fields, "action": action, "says": " ".join("".join(buttons).split())}
            )
            self._open = None


def forms_on(html, action_contains):
    parser = Forms(action_contains)
    parser.feed(html)
    return parser.forms


def press(client, html, action_contains, says):
    """Press the button on this page whose words say `says`, posting what its form
    carries. Fails loudly when the page does not offer it, since "the other is one
    click away" is the promise being kept."""
    offered = forms_on(html, action_contains)
    match = [f for f in offered if says in f["says"]]
    assert match, (
        f"no button saying {says!r} posting to {action_contains!r}; "
        f"the page offers {[f['says'] for f in offered]}"
    )
    r = client.post(match[0]["action"], data=match[0]["fields"], follow_redirects=False)
    assert r.status_code == 303, r.text
    return r


def upload_hint(html):
    """The upload box's tooltip, which says where a file put there will go."""
    tip = re.search(r'id="file-upload"[^>]*?title="([^"]*)"', html, re.S)
    assert tip, "the upload box does not say where an upload goes"
    return " ".join(tip.group(1).split())


def attached_to(client, fid):
    """What a file says it is for, in the words a person is shown: asset ids, and
    the models by their labels."""
    one = next(f for f in client.get("/api/files").json() if f["id"] == int(fid))
    return set(one["assets"]), {m["label"] for m in one["models"]}


class TestAttachingOne:
    """MANUAL.md section 11, "A file is attached to what it is for".

    One test to a promise the manual makes, and each of them pressing what a page
    offers rather than posting fields of its own -- a test that knows how a model
    is keyed is a test of the storage, and the manual promises a button."""

    def test_a_driver_attached_to_a_model_reaches_every_card_of_it(self, client, part):
        """ "to a model -- every machine or card of that model". The case the whole
        design is for: one upload, three identical cards."""
        one = part(manufacturer="Trident", model="TVGA8900", type="video")
        two = part(manufacturer="Trident", model="TVGA8900", type="video")
        three = part(manufacturer="Trident", model="TVGA8900", type="video")
        upload(client, "tvga.zip", aid=one["asset_id"])
        offered = ids_on(client, f"/parts/{one['asset_id']}")
        assert offered
        assert ids_on(client, f"/parts/{two['asset_id']}") == offered
        assert ids_on(client, f"/parts/{three['asset_id']}") == offered

    def test_and_a_card_of_another_model_is_not_offered_it(self, client, part):
        """Both halves, because "not offered" is true of a file that reached
        nothing at all: the driver has to be on the Trident card to say anything
        about its being off the Tseng one."""
        one = part(manufacturer="Trident", model="TVGA8900", type="video")
        other = part(manufacturer="Tseng", model="ET4000", type="video")
        upload(client, "tvga.zip", aid=one["asset_id"])
        assert ids_on(client, f"/parts/{one['asset_id']}")
        assert not ids_on(client, f"/parts/{other['asset_id']}")

    def test_a_card_bought_next_year_is_offered_it_too(self, client, part):
        """ "the ones on the shelf now and the one bought next year". The link names
        a model, not the items that happened to exist when it was made."""
        one = part(manufacturer="Trident", model="TVGA8900", type="video")
        upload(client, "tvga.zip", aid=one["asset_id"])
        later = part(manufacturer="Trident", model="TVGA8900", type="video")
        assert ids_on(client, f"/parts/{later['asset_id']}")

    def test_disposing_of_two_takes_nothing_away_from_the_third(self, client, part):
        """ "disposing of two of them takes nothing away from the third" -- the
        disposal case the old docstring was right to worry about."""
        one = part(manufacturer="Trident", model="TVGA8900", type="video")
        two = part(manufacturer="Trident", model="TVGA8900", type="video")
        three = part(manufacturer="Trident", model="TVGA8900", type="video")
        upload(client, "tvga.zip", aid=one["asset_id"])
        for gone in (one, two):
            r = client.patch(f"/api/parts/{gone['asset_id']}", json={"disposed": True})
            assert r.status_code == 200, r.text
        assert ids_on(client, f"/parts/{three['asset_id']}")

    def test_a_receipt_attached_to_one_unit_reaches_that_unit_alone(self, client, part):
        """ "to one unit -- that machine, that card, by its asset tag"."""
        one = part(manufacturer="Trident", model="TVGA8900")
        two = part(manufacturer="Trident", model="TVGA8900")
        upload(client, "receipt.pdf", aid=one["asset_id"])
        page = client.get(f"/parts/{one['asset_id']}").text
        fid = ids_on(client, f"/parts/{one['asset_id']}").pop()
        press(client, page, f"/files/{fid}/attach", "attach to this one")
        press(
            client,
            client.get(f"/parts/{one['asset_id']}").text,
            f"/files/{fid}/detach",
            "every Trident TVGA8900",
        )
        assert ids_on(client, f"/parts/{one['asset_id']}")
        assert not ids_on(client, f"/parts/{two['asset_id']}")

    def test_an_upload_is_attached_to_the_model_of_the_page_it_started_on(self, client, part):
        """ "Upload a file there and it is attached to the item's model where the
        item has one". Read as a reader reads it: every other card of that model is
        offered it, which is what being attached to a model means."""
        one = part(manufacturer="Trident", model="TVGA8900")
        two = part(manufacturer="Trident", model="TVGA8900")
        upload(client, "tvga.zip", aid=one["asset_id"])
        assert ids_on(client, f"/parts/{two['asset_id']}")

    def test_an_upload_on_something_with_no_model_is_attached_to_that_thing(self, client, computer):
        """ "and to the item itself where it has not -- a custom build". Two builds,
        both with nothing to call them, and the file is on one of them."""
        built = computer(name="The beige one", manufacturer="", model="")
        another = computer(name="The other beige one", manufacturer="", model="")
        upload(client, "notes.pdf", aid=built["asset_id"])
        assert ids_on(client, f"/computers/{built['asset_id']}")
        assert not ids_on(client, f"/computers/{another['asset_id']}")

    def test_the_panel_says_which_of_the_two_it_did(self, client, part, computer):
        """ "The upload box's tooltip says which of the two it will do." Both ways
        round, because it is the only thing telling you where an upload will go."""
        card = part(manufacturer="Trident", model="TVGA8900")
        said = upload_hint(client.get(f"/parts/{card['asset_id']}").text)
        assert said.startswith("Attached to every Trident TVGA8900")
        built = computer(name="The beige one", manufacturer="", model="")
        said = upload_hint(client.get(f"/computers/{built['asset_id']}").text)
        assert said.startswith(f"Attached to {built['asset_id']}")

    def test_the_other_of_the_two_is_one_click_away(self, client, part):
        """ "and the other is one click away". Pressed, not posted: the test finds
        the button by the words on it."""
        card = part(manufacturer="Trident", model="TVGA8900")
        upload(client, "tvga.zip", aid=card["asset_id"])
        fid = ids_on(client, f"/parts/{card['asset_id']}").pop()
        press(
            client,
            client.get(f"/parts/{card['asset_id']}").text,
            f"/files/{fid}/attach",
            "attach to this one",
        )
        assets, models = attached_to(client, fid)
        assert assets == {card["asset_id"]}
        assert models == {"Trident TVGA8900"}

    def test_one_file_can_be_attached_to_several_things(self, client, computer, part):
        """ "A file has as many of either as it needs, because one disk often covers
        a card and the machine it shipped in"."""
        machine = computer(manufacturer="Amstrad", model="CPC 464")
        drive = part(manufacturer="Amstrad", model="DDI-1", type="storage")
        upload(client, "cpm.dsk", aid=machine["asset_id"])
        fid = ids_on(client, f"/computers/{machine['asset_id']}").pop()
        client.post(
            f"/files/{fid}/attach",
            data={"aid": drive["asset_id"], "what": "model"},
            follow_redirects=False,
        )
        assert ids_on(client, f"/computers/{machine['asset_id']}")
        assert ids_on(client, f"/parts/{drive['asset_id']}")

    def test_detaching_takes_it_off_and_keeps_the_file(self, client, part):
        """ "detach takes it off again. Detaching never deletes anything"."""
        card = part(manufacturer="Trident", model="TVGA8900")
        upload(client, "tvga.zip", aid=card["asset_id"])
        fid = ids_on(client, f"/parts/{card['asset_id']}").pop()
        press(
            client, client.get(f"/parts/{card['asset_id']}").text, f"/files/{fid}/detach", "detach"
        )
        assert not ids_on(client, f"/parts/{card['asset_id']}")
        assert file_ids(client) == [int(fid)]
        assert attached_to(client, fid) == (set(), set())

    def test_a_file_attached_to_nothing_says_so(self, client):
        """ "a file attached to nothing is unfiled, and says so on the /files page".
        It is on no item page by definition, which is how one goes unnoticed."""
        upload(client, "orphan.zip")
        assert "unfiled" in client.get("/files").text

    def test_and_is_filed_from_that_page(self, client, part):
        """ "which is where one is found and filed". The box on the files page takes
        an asset id and attaches the file to its model."""
        card = part(manufacturer="Trident", model="TVGA8900")
        upload(client, "orphan.zip")
        fid = file_ids(client)[0]
        offered = forms_on(client.get("/files").text, f"/files/{fid}/attach")
        assert offered, "the files page offers no way to file an unfiled file"
        r = client.post(
            offered[0]["action"],
            data=offered[0]["fields"] | {"aid": card["asset_id"]},
            follow_redirects=False,
        )
        assert r.status_code == 303, r.text
        assert ids_on(client, f"/parts/{card['asset_id']}")

    def test_identifying_a_machine_does_not_take_its_files_away(self, client, computer):
        """ "A machine the catalogue names is both, and answers to a file attached
        either way." The file was attached before the machine was identified."""
        made = computer(manufacturer="Sinclair", model="ZX Spectrum 48K")
        upload(client, "manual.pdf", aid=made["asset_id"])
        r = client.patch(
            f"/api/computers/{made['asset_id']}", json={"machine": {"model_key": "zx-spectrum-48k"}}
        )
        assert r.status_code == 200, r.text
        assert ids_on(client, f"/computers/{made['asset_id']}")

    def test_a_file_on_a_catalogue_model_reaches_another_of_it(self, client, computer):
        """The other half of "both": attached to the catalogue's model, it reaches a
        machine identified as that model however its maker and model were typed."""
        one = computer(
            manufacturer="Sinclair",
            model="ZX Spectrum 48K",
            machine={"model_key": "zx-spectrum-48k"},
        )
        upload(client, "manual.pdf", aid=one["asset_id"])
        two = computer(
            manufacturer="sinclair research",
            model="Spectrum",
            machine={"model_key": "zx-spectrum-48k"},
        )
        assert ids_on(client, f"/computers/{two['asset_id']}")

    def test_the_same_model_written_two_ways_is_one_model(self, client, part):
        """ "Case and spacing make no difference." Nobody agrees where the spaces go
        in SoundBlaster, and neither spelling is the wrong one to have typed."""
        one = part(manufacturer="Creative Labs", model="Sound Blaster 16")
        two = part(manufacturer="creative  labs", model="soundblaster 16")
        upload(client, "sb.zip", aid=one["asset_id"])
        assert ids_on(client, f"/parts/{two['asset_id']}")

    def test_a_model_is_the_whole_model_and_not_a_piece_of_it(self, client, part):
        """A model is named or it is not. Containment is what let a tag of "16"
        reach half the register, and it is the thing ADR-0006 ends."""
        awe = part(manufacturer="Creative Labs", model="Sound Blaster AWE32")
        plain = part(manufacturer="Creative Labs", model="Sound Blaster")
        upload(client, "awe32.zip", aid=awe["asset_id"])
        assert ids_on(client, f"/parts/{awe['asset_id']}")
        assert not ids_on(client, f"/parts/{plain['asset_id']}")

    def test_renaming_an_item_does_not_move_its_files(self, client, part):
        """ "Renaming an item does not move its files" -- the fault ADR-0006 reports,
        where an edit silently detached one."""
        card = part(manufacturer="Trident", model="TVGA8900")
        upload(client, "tvga.zip", aid=card["asset_id"])
        r = client.patch(f"/api/parts/{card['asset_id']}", json={"name": "The video card"})
        assert r.status_code == 200, r.text
        assert ids_on(client, f"/parts/{card['asset_id']}")

    def test_correcting_a_parts_model_does_move_it(self, client, part):
        """ "But correcting a part's model does" -- and the manual says so plainly
        rather than leaving it to be discovered."""
        card = part(manufacturer="Trident", model="TVGA8900")
        upload(client, "tvga.zip", aid=card["asset_id"])
        assert ids_on(client, f"/parts/{card['asset_id']}"), "it was never there to move"
        r = client.patch(f"/api/parts/{card['asset_id']}", json={"model": "TVGA8900C"})
        assert r.status_code == 200, r.text
        assert not ids_on(client, f"/parts/{card['asset_id']}")

    def test_a_tag_decides_nothing(self, client, part):
        """ "A tag does not decide where a file appears". One that reads like the
        name of a card is still only a tag."""
        card = part(manufacturer="Trident", model="TVGA8900")
        upload(client, "loose.zip", tags="Trident TVGA8900")
        assert not ids_on(client, f"/parts/{card['asset_id']}")

    def test_deleting_an_item_takes_the_link_and_not_the_bytes(self, client, part):
        """Detaching never deletes, and neither does deleting the thing a file was
        about: unfiled is a state, not a reason to bin something (ADR-0006)."""
        card = part(manufacturer="Trident", model="TVGA8900")
        upload(client, "receipt.pdf", aid=card["asset_id"])
        fid = file_ids(client)[0]
        press(
            client,
            client.get(f"/parts/{card['asset_id']}").text,
            f"/files/{fid}/attach",
            "attach to this one",
        )
        client.delete(f"/api/parts/{card['asset_id']}")
        assert file_ids(client) == [int(fid)]
        assert attached_to(client, fid)[0] == set()

    def test_attaching_to_something_that_is_not_there_is_a_404(self, client):
        """Rather than a link to nowhere, which would read as unfiled while looking
        filed."""
        upload(client, "loose.zip")
        r = client.post(
            f"/files/{file_ids(client)[0]}/attach", data={"aid": "RH-9999"}, follow_redirects=False
        )
        assert r.status_code == 404


class TestKeepingThem:
    def test_what_was_uploaded_comes_back_byte_for_byte(self, client, part):
        p = part(manufacturer="Trident", model="TVGA8900")
        upload(client, "tvga.zip", b"PK\x03\x04 not really a zip", aid=p["asset_id"])
        fid = ids_on(client, f"/parts/{p['asset_id']}").pop()
        r = client.get(f"/files/{fid}/tvga.zip")
        assert r.status_code == 200
        assert r.content == b"PK\x03\x04 not really a zip"

    def test_it_is_handed_over_as_a_download_and_never_as_a_page(self, client, db):
        """An upload is whatever somebody sent, and some of what people send is
        HTML. Served as a page it would run as this site, with this site's
        cookies -- so one content type for everything, an attachment, and nosniff
        so the browser does not decide it knows better."""
        upload(client, "readme.html", b"<script>alert(1)</script>", tags="x")
        fid = db.query(StoredFile).one().id
        r = client.get(f"/files/{fid}/readme.html")
        assert r.headers["content-type"] == "application/octet-stream"
        assert r.headers["content-disposition"].startswith("attachment")
        assert r.headers["x-content-type-options"] == "nosniff"

    def test_the_name_it_was_sent_under_is_never_a_path(self, client, db):
        """The one part of an upload chosen entirely by whoever sent it."""
        upload(client, "../../etc/passwd", b"nope", tags="x")
        row = db.query(StoredFile).one()
        assert "/" not in row.stored and ".." not in row.stored
        assert (filesdb.FILES_DIR / row.stored).is_file()
        # What was typed is kept, for the download to be called by.
        assert row.filename == "passwd"

    def test_two_files_of_the_same_name_do_not_land_on_each_other(self, client, db):
        upload(client, "driver.zip", b"first", tags="a")
        upload(client, "driver.zip", b"second", tags="b")
        rows = db.query(StoredFile).all()
        assert len({r.stored for r in rows}) == 2
        assert {(filesdb.FILES_DIR / r.stored).read_bytes() for r in rows} == {b"first", b"second"}

    def test_an_empty_upload_is_not_a_file(self, client, db):
        upload(client, "nothing.txt", b"", tags="x")
        assert db.query(StoredFile).count() == 0

    def test_one_over_the_limit_is_refused_and_leaves_nothing_behind(self, client, db, monkeypatch):
        monkeypatch.setattr(filesdb, "MAX_BYTES", 32)
        r = upload(client, "big.bin", b"x" * 200, tags="x")
        assert r.headers["location"].endswith("fileerr=1")
        assert db.query(StoredFile).count() == 0
        assert not list(filesdb.FILES_DIR.glob("*.bin"))

    def test_deleting_one_takes_its_bytes_and_its_names(self, client, db, part):
        p = part(manufacturer="Trident", model="TVGA8900")
        upload(client, "tvga.zip", tags="Trident TVGA8900")
        row = db.query(StoredFile).one()
        path = filesdb.FILES_DIR / row.stored
        client.post(f"/files/{row.id}/delete", data={"next": "/files"}, follow_redirects=False)
        assert db.query(StoredFile).count() == 0
        assert db.query(FileTag).count() == 0
        assert not path.exists()
        assert not ids_on(client, f"/parts/{p['asset_id']}")


class TestTagging:
    """Tags say what a file is. Since ADR-0006 they say nothing about where it
    appears, which is the half of this that is worth a test of its own."""

    def test_the_box_is_the_whole_list(self, client, db):
        """What the box shows is what a save means, so a tag taken out of it is
        gone rather than added to."""
        upload(client, "tvga.zip", tags="driver")
        fid = db.query(StoredFile).one().id
        client.post(
            f"/files/{fid}/tags",
            data={"tags": "manual, scanned", "next": "/files"},
            follow_redirects=False,
        )
        assert client.get("/api/files").json()[0]["tags"] == ["manual", "scanned"]

    def test_relabelling_moves_nothing(self, client, db, part):
        """The whole demotion in one test: the tags box used to be how a file was
        re-filed, and now it is how a file is described."""
        card = part(manufacturer="Trident", model="TVGA8900")
        upload(client, "tvga.zip", aid=card["asset_id"])
        fid = db.query(StoredFile).one().id
        client.post(
            f"/files/{fid}/tags",
            data={"tags": "Tseng ET4000", "next": "/files"},
            follow_redirects=False,
        )
        assert ids_on(client, f"/parts/{card['asset_id']}")

    def test_a_name_written_twice_is_kept_once(self, client, db):
        upload(client, "a.zip", tags="Trident TVGA8900, trident tvga8900")
        assert db.query(FileTag).count() == 1

    def test_the_tags_are_shown_back_as_they_were_written(self, client, db):
        upload(client, "a.zip", tags="Trident TVGA8900")
        assert db.query(FileTag).one().tag == "Trident TVGA8900"


class TestTheFilesPage:
    def test_it_lists_what_is_there(self, client):
        upload(client, "tvga.zip", tags="Trident TVGA8900", note="DOS drivers")
        page = client.get("/files").text
        assert "tvga.zip" in page and "DOS drivers" in page
        assert "Trident TVGA8900" in page

    def test_it_can_be_narrowed_to_one_name(self, client):
        upload(client, "tvga.zip", tags="Trident TVGA8900")
        upload(client, "et4000.zip", tags="Tseng ET4000")
        page = client.get("/files?tag=trident+tvga8900").text
        assert "tvga.zip" in page and "et4000.zip" not in page


class TestOverTheWire:
    def test_the_api_lists_them_with_their_names(self, client):
        upload(client, "tvga.zip", tags="Trident TVGA8900, CT2230")
        body = client.get("/api/files").json()
        assert len(body) == 1
        assert body[0]["filename"] == "tvga.zip"
        assert body[0]["tags"] == ["Trident TVGA8900", "CT2230"]
        assert body[0]["url"].startswith("/files/") and body[0]["size"] > 0

    def test_it_can_be_asked_for_one_name(self, client):
        upload(client, "tvga.zip", tags="Trident TVGA8900")
        upload(client, "et4000.zip", tags="Tseng ET4000")
        got = client.get("/api/files?tag=TRIDENT tvga8900").json()
        assert [f["filename"] for f in got] == ["tvga.zip"]

    def test_asking_for_a_tag_answers_with_what_carries_it(self, client):
        """Equality on the fold, not containment on a name: a tag says what a file
        is, so following one asks for the manuals rather than for whatever a machine
        of that name would be offered."""
        upload(client, "sbdrivers.zip", tags="driver")
        upload(client, "awe32.zip", tags="driver, scanned")
        upload(client, "gus.zip", tags="manual")
        got = client.get("/api/files?tag=driver").json()
        assert sorted(f["filename"] for f in got) == ["awe32.zip", "sbdrivers.zip"]


class TestWhoMayDoWhat:
    def test_a_visitor_may_download_but_not_upload(self, client, part, monkeypatch):
        """Downloading reads like a photograph does. Putting one there, re-filing
        it and deleting it are writes, and writes need a login."""
        p = part(manufacturer="Trident", model="TVGA8900")
        upload(client, "tvga.zip", aid=p["asset_id"])
        fid = ids_on(client, f"/parts/{p['asset_id']}").pop()
        publish(client, fid)
        from app import main

        monkeypatch.setattr(main.auth, "AUTH_ENABLED", True)
        assert client.get(f"/files/{fid}/tvga.zip").status_code == 200
        assert client.get("/files").status_code == 200
        for path in (f"/files/{fid}/delete", f"/files/{fid}/tags", "/files"):
            r = client.post(path, data={}, follow_redirects=False)
            assert r.status_code == 303 and "/login" in r.headers["location"], path

    def test_a_visitor_is_not_shown_the_upload_box(self, client, part, monkeypatch):
        p = part(manufacturer="Trident", model="TVGA8900")
        from app import main

        monkeypatch.setattr(main.auth, "AUTH_ENABLED", True)
        page = client.get(f"/parts/{p['asset_id']}").text
        assert "Files" in page and 'action="/files"' not in page


class TestPublishingOne:
    """Nothing is on the open web until somebody says so.

    The register is a public catalogue and its drivers and manuals are part of
    what it is for, but the box that takes them takes receipts too, and a receipt
    carries a name and an address. So the tick, and these tests: that the default
    is off, that the tick is the whole answer, and that a file kept back is kept
    back everywhere rather than only where it is listed."""

    def test_a_new_upload_is_not_public(self, client, part, monkeypatch):
        p = part(manufacturer="Trident", model="TVGA8900")
        upload(client, "tvga.zip", aid=p["asset_id"])
        fid = ids_on(client, f"/parts/{p['asset_id']}").pop()
        from app import main

        monkeypatch.setattr(main.auth, "AUTH_ENABLED", True)
        assert client.get(f"/files/{fid}/tvga.zip").status_code == 404
        assert not ids_on(client, f"/parts/{p['asset_id']}")

    def test_ticking_the_box_publishes_it(self, client, part, monkeypatch):
        p = part(manufacturer="Trident", model="TVGA8900")
        upload(client, "tvga.zip", body=b"driver", aid=p["asset_id"])
        fid = ids_on(client, f"/parts/{p['asset_id']}").pop()
        publish(client, fid)
        from app import main

        monkeypatch.setattr(main.auth, "AUTH_ENABLED", True)
        assert client.get(f"/files/{fid}/tvga.zip").content == b"driver"
        assert ids_on(client, f"/parts/{p['asset_id']}") == {fid}

    def test_unticking_it_takes_it_back(self, client, part, monkeypatch):
        """The point of a toggle rather than a publish button: something put up by
        mistake has to come down, and come down everywhere."""
        p = part(manufacturer="Trident", model="TVGA8900")
        upload(client, "tvga.zip", aid=p["asset_id"])
        fid = ids_on(client, f"/parts/{p['asset_id']}").pop()
        publish(client, fid)
        publish(client, fid, public=False)
        from app import main

        monkeypatch.setattr(main.auth, "AUTH_ENABLED", True)
        assert client.get(f"/files/{fid}/tvga.zip").status_code == 404
        assert not ids_on(client, f"/parts/{p['asset_id']}")
        assert "tvga.zip" not in client.get("/files").text

    def test_a_file_kept_back_is_not_reachable_by_its_tag(self, client, part, monkeypatch):
        """The tag chips lead from an item page to /files?tag=..., which asks the
        same question of the same names. A file hidden on the page and listed
        under its own tag would be hidden in the one place nobody looks."""
        upload(client, "receipt.pdf", tags="Trident TVGA8900")
        from app import main

        monkeypatch.setattr(main.auth, "AUTH_ENABLED", True)
        assert "receipt.pdf" not in client.get("/files?tag=Trident TVGA8900").text

    def test_an_unpublished_file_is_missing_rather_than_forbidden(self, client, monkeypatch):
        """404 and not 401. There is no account a visitor could log in to, so an
        invitation to authenticate would say only that the file is there -- which
        for a receipt filed under an asset id is most of what was being kept."""
        upload(client, "invoice.pdf", tags="RH-0001")
        fid = str(client.get("/api/files").json()[0]["id"])
        from app import main

        monkeypatch.setattr(main.auth, "AUTH_ENABLED", True)
        r = client.get(f"/files/{fid}/invoice.pdf", follow_redirects=False)
        assert r.status_code == 404
        assert "www-authenticate" not in r.headers

    def test_the_owner_is_shown_both(self, client, part):
        """Whoever can publish has to be able to see what is not published, or
        there is no page to tick the box on."""
        p = part(manufacturer="Trident", model="TVGA8900")
        upload(client, "public.zip", aid=p["asset_id"])
        upload(client, "private.zip", aid=p["asset_id"])
        publish(client, sorted(ids_on(client, f"/parts/{p['asset_id']}"))[0])
        page = client.get(f"/parts/{p['asset_id']}").text
        assert "public.zip" in page and "private.zip" in page
        assert len(ids_on(client, "/files")) == 2

    def test_only_the_owner_may_publish(self, client, part, monkeypatch):
        upload(client, "tvga.zip", tags="Trident TVGA8900")
        fid = str(client.get("/api/files").json()[0]["id"])
        from app import main

        monkeypatch.setattr(main.auth, "AUTH_ENABLED", True)
        r = client.post(f"/files/{fid}/public", data={"public": "1"}, follow_redirects=False)
        assert r.status_code == 303 and "/login" in r.headers["location"]
        monkeypatch.setattr(main.auth, "AUTH_ENABLED", False)
        assert client.get("/api/files").json()[0]["public"] is False

    def test_an_unpublished_file_is_not_cached_anywhere(self, client):
        """The owner is the only person who can fetch one, and unticking the box
        has to stop the copy being handed out -- which a cache holding it for the
        hour the published header asks for would carry on doing."""
        upload(client, "invoice.pdf", tags="RH-0001")
        fid = client.get("/api/files").json()[0]["id"]
        r = client.get(f"/files/{fid}/invoice.pdf")
        assert r.headers["cache-control"] == "private, no-store"
        publish(client, fid)
        r = client.get(f"/files/{fid}/invoice.pdf")
        assert r.headers["cache-control"] == "public, max-age=3600"

    def test_the_wire_format_says_which(self, client):
        upload(client, "manual.pdf", tags="Amstrad PCW 8256")
        fid = client.get("/api/files").json()[0]["id"]
        publish(client, fid)
        assert client.get("/api/files").json()[0]["public"] is True


class TestSizesRead:
    def test_a_size_is_said_the_way_it_would_be_said(self):
        assert filesdb.human_size(0) == "0 B"
        assert filesdb.human_size(900) == "900 B"
        assert filesdb.human_size(2048) == "2.0 KiB"
        assert filesdb.human_size(20 * 1024) == "20 KiB"
        assert filesdb.human_size(5 * 1024**2) == "5.0 MiB"
