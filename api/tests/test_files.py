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
from app import filesdb
from app.models import FileTag, StoredFile


def upload(client, name, body=b"driver bytes", tags="", note="", **extra):
    r = client.post("/files", files={"uploads": (name, body)},
                    data={"tags": tags, "note": note, **extra},
                    follow_redirects=False)
    assert r.status_code == 303, r.text
    return r


def publish(client, fid, public=True):
    """Tick the box, or untick it. An unticked checkbox sends no field at all,
    which is what the off case posts here."""
    r = client.post(f"/files/{fid}/public",
                    data={"public": "1"} if public else {},
                    follow_redirects=False)
    assert r.status_code == 303, r.text
    return r


def ids_on(client, url):
    """The file ids offered on an item's page."""
    import re
    return set(re.findall(r'href="/files/(\d+)/', client.get(url).text))


class TestFilingUnderAName:
    """The whole point: one upload, and every item of that name has it."""

    def test_a_driver_reaches_every_card_of_that_model(self, client, part):
        one = part(manufacturer="Trident", model="TVGA8900", type="video")
        two = part(manufacturer="Trident", model="TVGA8900", type="video")
        other = part(manufacturer="Tseng", model="ET4000", type="video")
        upload(client, "tvga.zip", tags="Trident TVGA8900")
        assert ids_on(client, f"/parts/{one['asset_id']}")
        assert (ids_on(client, f"/parts/{one['asset_id']}")
                == ids_on(client, f"/parts/{two['asset_id']}"))
        assert not ids_on(client, f"/parts/{other['asset_id']}")

    def test_it_crosses_from_a_part_to_a_machine_of_the_same_name(self, client,
                                                                  computer, part):
        """"any device of any type": the disk that came with a card is often the
        disk that came with the machine, and the register does not care which of
        the two the name was typed on."""
        c = computer(manufacturer="Amstrad", model="PCW 8256")
        p = part(manufacturer="Amstrad", model="PCW 8256", type="other")
        upload(client, "pcw.img", tags="Amstrad PCW 8256")
        assert ids_on(client, f"/computers/{c['asset_id']}")
        assert ids_on(client, f"/parts/{p['asset_id']}")

    def test_the_model_alone_is_a_name_too(self, client, part):
        """Somebody filing a driver types what is written on the chip, which is
        the model without the maker in front of it."""
        p = part(manufacturer="Creative", model="CT2230", type="sound")
        upload(client, "sb16.zip", tags="CT2230")
        assert ids_on(client, f"/parts/{p['asset_id']}")

    def test_a_name_someone_gave_it_counts(self, client, part):
        p = part(name="The blue Adaptec", manufacturer="Adaptec", model="1542B")
        upload(client, "aha.zip", tags="the blue adaptec")
        assert ids_on(client, f"/parts/{p['asset_id']}")

    def test_an_asset_id_files_it_to_one_unit_alone(self, client, part):
        """A receipt or a repair photograph is about this one, and its asset id is
        how that is said without a second mechanism for it."""
        one = part(manufacturer="Trident", model="TVGA8900")
        two = part(manufacturer="Trident", model="TVGA8900")
        upload(client, "receipt.pdf", tags=one["asset_id"])
        assert ids_on(client, f"/parts/{one['asset_id']}")
        assert not ids_on(client, f"/parts/{two['asset_id']}")

    def test_case_and_spacing_are_not_a_different_name(self, client, part):
        p = part(manufacturer="Trident", model="TVGA8900")
        upload(client, "d.zip", tags="  trident   TVGA8900 ")
        assert ids_on(client, f"/parts/{p['asset_id']}")

    def test_a_name_written_closed_up_is_the_same_name(self, client, part):
        """Nobody agrees where the spaces go in SoundBlaster, and neither spelling
        is the wrong one to have typed."""
        p = part(manufacturer="Creative Labs", model="Sound Blaster 16")
        upload(client, "sb.zip", tags="soundblaster")
        assert ids_on(client, f"/parts/{p['asset_id']}")

    def test_a_name_covers_everything_that_has_it_in(self, client, part):
        """One tag for a family: "Creative Labs Sound Blaster" is the driver disk
        for the AWE32, the 16 and the Pro, because each of them is called that and
        then some."""
        awe = part(manufacturer="Creative Labs", model="Sound Blaster AWE32")
        pro = part(manufacturer="Creative Labs", model="Sound Blaster Pro")
        gus = part(manufacturer="Gravis", model="UltraSound")
        upload(client, "sbdrivers.zip", tags="Creative Labs Sound Blaster")
        assert ids_on(client, f"/parts/{awe['asset_id']}")
        assert ids_on(client, f"/parts/{pro['asset_id']}")
        assert not ids_on(client, f"/parts/{gus['asset_id']}")

    def test_it_reaches_the_narrower_name_and_not_the_broader_one(self, client,
                                                                  part):
        """One direction only. A disk written for the AWE32 is not the disk for
        every Sound Blaster, and putting it on the plain one would be a claim
        nobody made."""
        plain = part(manufacturer="Creative Labs", model="Sound Blaster")
        awe = part(manufacturer="Creative Labs", model="Sound Blaster AWE32")
        upload(client, "awe32.zip", tags="Sound Blaster AWE32")
        assert ids_on(client, f"/parts/{awe['asset_id']}")
        assert not ids_on(client, f"/parts/{plain['asset_id']}")

    def test_a_tag_holding_a_wildcard_is_read_as_the_characters_it_is(self, client,
                                                                      part):
        """% and _ mean something to the LIKE that narrows the search and nothing to
        anybody typing a name, so the answer is checked again after it."""
        p = part(manufacturer="Iomega", model="Zip 100")
        upload(client, "zip.zip", tags="100%")
        assert not ids_on(client, f"/parts/{p['asset_id']}")

    def test_one_file_can_be_filed_under_several(self, client, computer, part):
        c = computer(manufacturer="Amstrad", model="CPC 464")
        p = part(manufacturer="Amstrad", model="DDI-1", type="storage")
        upload(client, "cpm.dsk", tags="Amstrad CPC 464, Amstrad DDI-1")
        assert ids_on(client, f"/computers/{c['asset_id']}")
        assert ids_on(client, f"/parts/{p['asset_id']}")

    def test_an_item_with_no_name_at_all_matches_nothing(self, client, db):
        """A blank model must not be a name every unnamed thing answers to."""
        assert filesdb.keys_for({"manufacturer": "", "model": "", "name": "",
                                 "asset_id": ""}) == set()


class TestKeepingThem:
    def test_what_was_uploaded_comes_back_byte_for_byte(self, client, part):
        p = part(manufacturer="Trident", model="TVGA8900")
        upload(client, "tvga.zip", b"PK\x03\x04 not really a zip",
               tags="Trident TVGA8900")
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
        assert {(filesdb.FILES_DIR / r.stored).read_bytes() for r in rows} == \
            {b"first", b"second"}

    def test_an_empty_upload_is_not_a_file(self, client, db):
        upload(client, "nothing.txt", b"", tags="x")
        assert db.query(StoredFile).count() == 0

    def test_one_over_the_limit_is_refused_and_leaves_nothing_behind(self, client,
                                                                     db,
                                                                     monkeypatch):
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
        client.post(f"/files/{row.id}/delete", data={"next": "/files"},
                    follow_redirects=False)
        assert db.query(StoredFile).count() == 0
        assert db.query(FileTag).count() == 0
        assert not path.exists()
        assert not ids_on(client, f"/parts/{p['asset_id']}")


class TestRefiling:
    def test_the_box_is_the_whole_list(self, client, db, part):
        """A name taken out of it stops matching, which is the only way to correct
        a file put under the wrong one."""
        wrong = part(manufacturer="Tseng", model="ET4000")
        right = part(manufacturer="Trident", model="TVGA8900")
        upload(client, "tvga.zip", tags="Tseng ET4000")
        fid = db.query(StoredFile).one().id
        client.post(f"/files/{fid}/tags",
                    data={"tags": "Trident TVGA8900", "next": "/files"},
                    follow_redirects=False)
        assert not ids_on(client, f"/parts/{wrong['asset_id']}")
        assert ids_on(client, f"/parts/{right['asset_id']}")

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

    def test_asking_for_a_name_answers_as_an_item_of_that_name_would(self, client):
        """Following a tag from a page shows what that page shows: the broader
        disks a thing of this name would be offered, not only the file whose tag
        was clicked."""
        upload(client, "sbdrivers.zip", tags="Creative Labs Sound Blaster")
        upload(client, "awe32.zip", tags="Creative Labs Sound Blaster AWE32")
        upload(client, "gus.zip", tags="Gravis UltraSound")
        got = client.get("/api/files?tag=Creative Labs Sound Blaster AWE32").json()
        assert sorted(f["filename"] for f in got) == ["awe32.zip", "sbdrivers.zip"]


class TestWhoMayDoWhat:
    def test_a_visitor_may_download_but_not_upload(self, client, part,
                                                   monkeypatch):
        """Downloading reads like a photograph does. Putting one there, re-filing
        it and deleting it are writes, and writes need a login."""
        p = part(manufacturer="Trident", model="TVGA8900")
        upload(client, "tvga.zip", tags="Trident TVGA8900")
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
        upload(client, "tvga.zip", tags="Trident TVGA8900")
        fid = ids_on(client, f"/parts/{p['asset_id']}").pop()
        from app import main
        monkeypatch.setattr(main.auth, "AUTH_ENABLED", True)
        assert client.get(f"/files/{fid}/tvga.zip").status_code == 404
        assert not ids_on(client, f"/parts/{p['asset_id']}")

    def test_ticking_the_box_publishes_it(self, client, part, monkeypatch):
        p = part(manufacturer="Trident", model="TVGA8900")
        upload(client, "tvga.zip", body=b"driver", tags="Trident TVGA8900")
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
        upload(client, "tvga.zip", tags="Trident TVGA8900")
        fid = ids_on(client, f"/parts/{p['asset_id']}").pop()
        publish(client, fid)
        publish(client, fid, public=False)
        from app import main
        monkeypatch.setattr(main.auth, "AUTH_ENABLED", True)
        assert client.get(f"/files/{fid}/tvga.zip").status_code == 404
        assert not ids_on(client, f"/parts/{p['asset_id']}")
        assert "tvga.zip" not in client.get("/files").text

    def test_a_file_kept_back_is_not_reachable_by_its_tag(self, client, part,
                                                          monkeypatch):
        """The tag chips lead from an item page to /files?tag=..., which asks the
        same question of the same names. A file hidden on the page and listed
        under its own tag would be hidden in the one place nobody looks."""
        upload(client, "receipt.pdf", tags="Trident TVGA8900")
        from app import main
        monkeypatch.setattr(main.auth, "AUTH_ENABLED", True)
        assert "receipt.pdf" not in client.get("/files?tag=Trident TVGA8900").text

    def test_an_unpublished_file_is_missing_rather_than_forbidden(self, client,
                                                                  monkeypatch):
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
        upload(client, "public.zip", tags="Trident TVGA8900")
        upload(client, "private.zip", tags="Trident TVGA8900")
        publish(client, sorted(ids_on(client, f"/parts/{p['asset_id']}"))[0])
        page = client.get(f"/parts/{p['asset_id']}").text
        assert "public.zip" in page and "private.zip" in page
        assert len(ids_on(client, "/files")) == 2

    def test_only_the_owner_may_publish(self, client, part, monkeypatch):
        upload(client, "tvga.zip", tags="Trident TVGA8900")
        fid = str(client.get("/api/files").json()[0]["id"])
        from app import main
        monkeypatch.setattr(main.auth, "AUTH_ENABLED", True)
        r = client.post(f"/files/{fid}/public", data={"public": "1"},
                        follow_redirects=False)
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
        assert filesdb.human_size(5 * 1024 ** 2) == "5.0 MiB"
