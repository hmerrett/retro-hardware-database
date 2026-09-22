"""The catalogue list and a model's own page, as MANUAL.md section 3 promises them
("The list of what it knows", "A model's own page"): every name on /machines leads
to /machines/<key>, which says what the catalogue records about the model, its chip
sockets, the units filed as it and the files attached to it -- in public, with a
visitor shown the published files alone.

Auth is off in these tests, so the client is the owner; `visitor` turns it on.
"""

import re

import pytest

from app import machines, main
from test_files import publish, upload


def visitor(monkeypatch):
    """Turn the site into what an anonymous reader sees."""
    monkeypatch.setattr(main.auth, "AUTH_ENABLED", True)


def panel(page: str, title: str) -> str:
    """The markup of the panel with this title, up to the next panel or the page's end."""
    m = re.search(
        rf"<section class=\"panel[^\"]*\">\s*<header>\s*<h3>{re.escape(title)}</h3>", page
    )
    if not m:
        return ""
    rest = page[m.end() :]
    stop = re.search(r'<section class="panel|</main>', rest)
    return rest[: stop.start()] if stop else rest


def file_as(client, aid, filename, key="vic-20"):
    """A machine filed as a catalogue model, with a file uploaded from its page --
    which attaches the file to the model, as the Files panel does."""
    client.patch(f"/api/computers/{aid}", json={"machine": {"model_key": key}})
    upload(client, filename, aid=aid)
    return client.get("/api/files").json()[0]["id"]


def edited(monkeypatch, key, **changes):
    """The catalogue with one model's entry changed, for the promises about what it
    does not say: every model in the real one has chips, a summary and an OS."""
    real = machines.model

    def model(k):
        m = real(k)
        return {**m, **changes} if m is not None and k == key else m

    monkeypatch.setattr(machines, "model", model)


class TestTheList:
    def test_every_name_leads_to_its_own_page(self, client):
        page = client.get("/machines").text
        for m in machines.models():
            assert f'href="/machines/{m["key"]}"' in page, m["key"]

    def test_a_model_held_is_set_heavier_with_its_count(self, client, computer):
        aid = computer()["asset_id"]
        client.patch(f"/api/computers/{aid}", json={"machine": {"model_key": "c64"}})
        page = client.get("/machines").text
        row = re.search(r'<div class="m have">.*?</div>', page, re.S).group(0)
        assert 'href="/machines/c64"' in row
        assert '<span class="n">1<span class="sr-only"> here</span></span>' in row

    def test_a_model_nothing_is_filed_as_carries_no_count(self, client):
        page = client.get("/machines").text
        assert 'class="m have"' not in page
        assert 'class="n"' not in page

    def test_the_paragraph_is_no_longer_folded_into_the_list(self, client):
        page = client.get("/machines").text
        assert "<details" not in page.split('<div class="models')[1]
        assert "machines.js" not in page


class TestAModelsPage:
    def test_it_is_public(self, client, monkeypatch):
        visitor(monkeypatch)
        assert client.get("/machines/vic-20", follow_redirects=False).status_code == 200

    def test_a_key_the_catalogue_does_not_have_is_not_found(self, client):
        assert client.get("/machines/zx-spectrum-1024k").status_code == 404

    def test_it_is_named_in_the_sitemap(self, client):
        assert "/machines/vic-20</loc>" in client.get("/sitemap.xml").text

    def test_the_way_back_is_to_every_model(self, client):
        page = client.get("/machines/vic-20").text
        assert re.search(r'<nav class="itemnav"[^>]*>\s*<a href="/machines">', page)

    def test_the_name_heads_it_with_its_family_and_year_under(self, client):
        page = client.get("/machines/vic-20").text
        assert '<h1 class="title">Commodore VIC-20</h1>' in page
        assert re.search(r'<div class="tag muted">Commodore 8-bit · 1980</div>', page)

    def test_the_paragraph_is_printed_in_ordinary_ink(self, client):
        page = client.get("/machines/vic-20").text
        para = re.search(r'<p class="([^"]*)">The first computer of any kind', page)
        assert para and para.group(1) == "prose"

    def test_as_catalogued_says_what_the_catalogue_records(self, client):
        kv = panel(client.get("/machines/vic-20").text, "As catalogued")
        pairs = dict(re.findall(r"<dt>([^<]+)</dt><dd>([^<]*)</dd>", kv))
        assert pairs == {
            "Maker": "Commodore",
            "CPU": "MOS 6502A-1.02",
            "Memory": "5K",
            "Board issues": "ASSY 324003, ASSY 250403 (VIC-20CR)",
            "Styles": "VIC-20 (1980 case), VIC-20CR",
            "Regions": "PAL, NTSC",
            "Chassis": "breadbin",
            "OS": "Commodore BASIC 2.0",
        }

    def test_what_the_catalogue_does_not_say_is_left_out(self, client, monkeypatch):
        edited(monkeypatch, "vic-20", os="", styles=[], chassis="")
        kv = panel(client.get("/machines/vic-20").text, "As catalogued")
        dts = re.findall(r"<dt>([^<]+)</dt>", kv)
        assert "OS" not in dts and "Styles" not in dts and "Chassis" not in dts
        assert "Maker" in dts

    def test_a_model_without_a_paragraph_prints_none(self, client, monkeypatch):
        edited(monkeypatch, "vic-20", summary="")
        assert 'class="prose"' not in client.get("/machines/vic-20").text

    def test_each_socket_is_a_cell_with_the_chips_seen_in_it(self, client):
        chips = panel(client.get("/machines/vic-20").text, "Chips")
        cells = re.findall(
            r'<div class="cell"><div class="k">([^<]+)</div><div class="v">([^<]+)</div>', chips
        )
        assert ("VIC", "MOS 6560 (NTSC), MOS 6561 (PAL)") in cells
        assert ("CPU", "MOS 6502, MOS 6502A") in cells
        assert len(cells) == len(machines.model("vic-20")["chips"])

    def test_a_model_with_no_sockets_has_no_chips_panel(self, client, monkeypatch):
        edited(monkeypatch, "vic-20", chips=[])
        assert panel(client.get("/machines/vic-20").text, "Chips") == ""


class TestInThisCollection:
    def test_nothing_filed_says_so(self, client):
        units = panel(client.get("/machines/vic-20").text, "In this collection")
        assert "None here yet." in units
        assert 'class="result"' not in units

    def test_machines_and_boards_filed_as_it_are_listed(self, client, computer, part):
        c = computer()["asset_id"]
        p = part(type="motherboard")["asset_id"]
        other = computer()["asset_id"]
        client.patch(f"/api/computers/{c}", json={"machine": {"model_key": "vic-20"}})
        client.patch(f"/api/parts/{p}", json={"machine": {"model_key": "vic-20"}})
        client.patch(f"/api/computers/{other}", json={"machine": {"model_key": "c64"}})
        units = panel(client.get("/machines/vic-20").text, "In this collection")
        assert sorted(re.findall(r'<a class="result" href="([^"]+)"', units)) == sorted(
            [f"/computers/{c}", f"/parts/{p}"]
        )
        assert re.search(r'<span class="meta">2</span>', client.get("/machines/vic-20").text)

    def test_a_disposed_one_is_listed_and_says_so(self, client, computer):
        aid = computer()["asset_id"]
        client.patch(f"/api/computers/{aid}", json={"machine": {"model_key": "vic-20"}})
        client.post(f"/computers/{aid}/dispose", data={"note": "", "date": ""})
        units = panel(client.get("/machines/vic-20").text, "In this collection")
        row = re.search(r'<a class="result".*?</a>', units, re.S).group(0)
        assert aid in row and "Disposed" in row


class TestItsFiles:
    def test_a_file_attached_to_the_model_is_listed(self, client, computer):
        fid = file_as(client, computer()["asset_id"], "vic-manual.pdf")
        files = panel(client.get("/machines/vic-20").text, "Files")
        assert f'href="/files/{fid}/vic-manual.pdf"' in files

    @pytest.mark.parametrize("published", [True, False])
    def test_a_visitor_sees_the_published_ones_alone(
        self, client, computer, monkeypatch, published
    ):
        fid = file_as(client, computer()["asset_id"], "receipt.pdf")
        if published:
            publish(client, fid)
        visitor(monkeypatch)
        files = panel(client.get("/machines/vic-20").text, "Files")
        assert (f'href="/files/{fid}/' in files) is published

    def test_there_is_nothing_to_attach_or_detach_here(self, client, computer):
        file_as(client, computer()["asset_id"], "vic-manual.pdf")
        page = client.get("/machines/vic-20").text
        assert "/attach" not in page and "/detach" not in page
