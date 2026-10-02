"""Labels with a barcode, a location's label, a sheet of them, and the face they are
set in (MANUAL §13: "A location has one too", "QR code, barcode or both", "The type
on a label"; ADR-0034).

A barcode is read back out of the label's own dots here, by the same arithmetic a
scanner does, because "the label carries the tag" is a promise about what a scanner
will type and not about what the code that drew it meant to draw.
"""

import io
import re
from pathlib import Path

import pytest
from PIL import Image
from reportlab.lib.units import mm
from reportlab.pdfgen import canvas

from app import barcode, labels, settings, surfaces

ROOT = Path(__file__).parents[1] / "app"
TAG = "RH-K7Q2"
PART = {
    "asset_id": TAG,
    "manufacturer": "Trident",
    "model": "TVGA8900",
    "type": "video",
    "specs": "",
}
PLACE = {
    "asset_id": "RH-9J2X",
    "name": "Box 14",
    "path": "Workshop / Rack 3 / Shelf 2",
    "kind": "Box",
    "notes": "",
}


def save_labels(client, **fields):
    r = client.post("/settings/labels", data=fields, follow_redirects=False)
    assert r.status_code == 303, r.text


# --- reading a barcode back off a label's dots ---------------------------------


def runs_of(row):
    """Light and dark runs along a row of a one-bit image, light first."""
    runs, dark, n = [], False, 0
    for px in row:
        d = px == 0
        if d == dark:
            n += 1
            continue
        runs.append(n)
        dark, n = d, 1
    runs.append(n)
    return runs


def read_barcode(image):
    """The text of the first Code 128 barcode found along any row, and the widths in
    dots of its bars and spaces -- or (None, None)."""
    shapes = {p: n for n, p in enumerate(barcode.PATTERNS)}
    pixels = image.load()
    for y in range(image.height):
        runs = runs_of(pixels[x, y] for x in range(image.width))
        for at in range(1, len(runs) - 6, 2):
            unit = sum(runs[at : at + 6]) / 11
            key = "".join(str(round(r / unit)) for r in runs[at : at + 6])
            if shapes.get(key) != barcode.START_B:
                continue
            values, k = [barcode.START_B], at + 6
            while k + 7 <= len(runs):
                seven = runs[k : k + 7]
                if "".join(str(round(r / (sum(seven) / 13))) for r in seven) == "2331112":
                    break
                six = runs[k : k + 6]
                code = "".join(str(round(r / (sum(six) / 11))) for r in six)
                if code not in shapes:
                    break
                values.append(shapes[code])
                k += 6
            if len(values) < 3:
                continue
            data, check = values[1:-1], values[-1]
            if (barcode.START_B + sum(i * v for i, v in enumerate(data, 1))) % 103 != check:
                continue
            return "".join(chr(v + 32) for v in data), runs[at : k + 7]
    return None, None


def picture(client, url):
    r = client.get(url)
    assert r.status_code == 200, r.text[:200]
    return Image.open(io.BytesIO(r.content))


def has_image(pdf: bytes) -> bool:
    """Whether a PDF has a picture in it: the QR code is drawn as one, and the bars
    of a barcode are not."""
    return b"/Subtype /Image" in pdf


# --- the table ------------------------------------------------------------------


class TestTheTable:
    def test_it_is_the_standard_one(self):
        """Held to ReportLab's own, which is a second implementation written by
        somebody else from the same specification."""
        from reportlab.graphics.barcode import code128

        widths = {c: str(n) for n, c in enumerate("abcd", 1)} | {
            c: str(n) for n, c in enumerate("ABCD", 1)
        }
        theirs = tuple("".join(widths[ch] for ch in code128._patterns[n]) for n in range(107))
        assert theirs == barcode.PATTERNS

    def test_the_browsers_reader_carries_the_same_table(self):
        source = (ROOT / "static" / "code128.js").read_text(encoding="utf-8")
        body = source.split("const PATTERNS = [", 1)[1].split("];", 1)[0]
        assert tuple(re.findall(r"'(\d+)'", body)) == barcode.PATTERNS

    def test_a_tag_is_the_symbols_it_should_be(self):
        """Start B, the seven characters, the checksum, the stop."""
        got = barcode.symbols(TAG)
        assert got[0] == barcode.START_B and got[-1] == barcode.STOP
        assert [chr(v + 32) for v in got[1:-2]] == list(TAG)
        assert got[-2] == (104 + sum(i * (ord(c) - 32) for i, c in enumerate(TAG, 1))) % 103


class TestTheCodesSetting:
    def test_it_is_on_the_labels_tab_with_three_answers(self, client):
        page = client.get("/settings/labels").text
        box = page.split('name="label_codes"', 1)[1].split("</select>", 1)[0]
        assert re.findall(r'<option value="([a-z0-9]+)"', box) == ["qr", "code128", "both"]

    def test_qr_is_the_default(self, client):
        assert settings.value("label_codes") == "qr"

    @pytest.mark.parametrize("kind", ["computers", "parts", "projects"])
    def test_the_default_label_has_a_qr_code_and_no_barcode(self, client, computer, part, kind):
        aid = _item(client, computer, part, kind)
        pdf = client.get(f"/{kind}/{aid}/label.pdf?small=1").content
        assert has_image(pdf)
        assert read_barcode(picture(client, f"/{kind}/{aid}/label.png"))[0] is None

    @pytest.mark.parametrize("kind", ["computers", "parts", "projects", "locations"])
    def test_code_128_puts_the_tag_in_bars_and_no_qr_code(self, client, computer, part, kind):
        aid = _item(client, computer, part, kind)
        save_labels(client, label_codes="code128")
        pdf = client.get(f"/{kind}/{aid}/label.pdf?small=1").content
        assert not has_image(pdf)
        text, _ = read_barcode(picture(client, f"/{kind}/{aid}/label.png"))
        assert text == aid, "the barcode holds the tag and nothing else"

    @pytest.mark.parametrize("kind", ["computers", "parts", "projects", "locations"])
    def test_both_puts_both_on_the_label(self, client, computer, part, kind):
        aid = _item(client, computer, part, kind)
        save_labels(client, label_codes="both")
        assert has_image(client.get(f"/{kind}/{aid}/label.pdf?small=0").content)
        bitmap = picture(client, f"/{kind}/{aid}/label.png?media=niimbot-50x30")
        assert read_barcode(bitmap)[0] == aid

    @pytest.mark.parametrize("kind", ["computers", "parts", "projects", "locations"])
    def test_on_the_tape_both_is_the_barcode_alone(self, client, computer, part, kind):
        """The 51x19mm tape is too short for both at sizes worth scanning: with the
        bars as wide as they need, a QR code would be under 12mm beside them."""
        aid = _item(client, computer, part, kind)
        save_labels(client, label_codes="both")
        assert not has_image(client.get(f"/{kind}/{aid}/label.pdf?small=1").content)
        assert read_barcode(picture(client, f"/{kind}/{aid}/label.png"))[0] == aid

    @pytest.mark.parametrize("media", ["niimbot-50x30", "niimbot-40x30"])
    def test_a_label_with_room_for_both_carries_both(self, media):
        stock = labels.MEDIA[media]
        codes = []

        class Listening(surfaces.RasterSurface):
            def qr(self, x, y, size, data, error="M"):
                codes.append(size)
                super().qr(x, y, size, data, error)

        image = surfaces.blank(*labels.size_dots(stock))
        surface = Listening(image, stock["dpi"])
        labels._draw(surface, stock, PART, [], labels.PART, True, codes=labels.BOTH)
        assert codes and codes[0] >= labels.QR_MIN, media
        assert read_barcode(image)[0] == TAG

    def test_the_full_label_follows_it_too(self, client, computer):
        aid = computer()["asset_id"]
        save_labels(client, label_codes="code128")
        assert not has_image(client.get(f"/computers/{aid}/label.pdf?small=0").content)
        full = picture(client, f"/computers/{aid}/label.png?media=full-6x4&small=0")
        assert read_barcode(full)[0] == aid

    @pytest.mark.parametrize("media", sorted(labels.MEDIA))
    @pytest.mark.parametrize("codes", [labels.BARCODE, labels.BOTH])
    def test_every_bar_is_a_whole_number_of_dots(self, media, codes):
        """For the reason the QR code's squares are: a bar a dot wider than its
        neighbour is a different bar to a scanner."""
        stock = labels.MEDIA[media]
        image = surfaces.blank(*labels.size_dots(stock))
        surface = surfaces.RasterSurface(image, stock["dpi"])
        labels._draw(surface, stock, PART, [], labels.PART, media != labels.FULL, codes=codes)
        text, widths = read_barcode(image)
        assert text == TAG, media
        unit = min(widths)
        assert unit >= 2, f"{media}: {unit} dot(s) a module is too fine to scan"
        assert all(w % unit == 0 for w in widths), f"{media}: a bar between two widths"

    @pytest.mark.parametrize("media", sorted(labels.MEDIA))
    @pytest.mark.parametrize("codes", [labels.BARCODE, labels.BOTH])
    def test_in_the_pdf_too_a_bar_is_a_whole_number_of_the_printers_dots(self, media, codes):
        """A PDF bar scaled to whatever the box left is 3.8 of the DYMO's dots, which
        it prints as three or four depending on where the bar falls."""
        stock = labels.MEDIA[media]
        modules = []

        class Listening(surfaces.PdfSurface):
            def barcode(self, x, y, w, h, data):
                modules.append(w / barcode.width(data))
                super().barcode(x, y, w, h, data)

        c = canvas.Canvas(io.BytesIO(), pagesize=labels.rotated_page(stock))
        surface = Listening(c, surfaces.LABEL, stock["dpi"])
        labels._draw(surface, stock, PART, [], labels.PART, media != labels.FULL, codes=codes)
        dots = modules[0] * stock["dpi"] / 72
        assert abs(dots - round(dots)) < 1e-6, f"{media}: {dots:.2f} dots a bar"

    @pytest.mark.parametrize("media", sorted(labels.MEDIA))
    def test_no_bar_is_narrower_than_a_quarter_of_a_millimetre(self, media):
        stock = labels.MEDIA[media]
        image = surfaces.blank(*labels.size_dots(stock))
        surface = surfaces.RasterSurface(image, stock["dpi"])
        labels._draw(
            surface, stock, PART, [], labels.PART, media != labels.FULL, codes=labels.BARCODE
        )
        _, widths = read_barcode(image)
        assert min(widths) * 25.4 / stock["dpi"] >= 0.25, media

    def test_across_the_tape_a_bar_is_four_of_the_dymos_dots(self):
        """The white a scanner needs either side of the bars stands in the margin at
        the tape's ends, which prints nothing, and the bars get the room it saves."""
        stock = labels.MEDIA[labels.SMALL]
        image = surfaces.blank(*labels.size_dots(stock))
        surface = surfaces.RasterSurface(image, stock["dpi"])
        labels._draw(surface, stock, PART, [], labels.PART, True, codes=labels.BARCODE)
        assert min(read_barcode(image)[1]) == 4

    @pytest.mark.parametrize("media", sorted(m for m in labels.MEDIA if m != labels.FULL))
    def test_the_bars_themselves_keep_out_of_the_tapes_end_margin(self, media):
        stock = labels.MEDIA[media]
        drawn = []

        class Listening(surfaces.RasterSurface):
            def barcode(self, x, y, w, h, data):
                drawn.append((x, w, data))
                super().barcode(x, y, w, h, data)

        surface = Listening(surfaces.blank(*labels.size_dots(stock)), stock["dpi"])
        labels._draw(surface, stock, PART, [], labels.PART, True, codes=labels.BARCODE)
        x, w, data = drawn[0]
        quiet = w * barcode.QUIET / barcode.width(data)
        W, _ = labels.layout_size(stock)
        allowance = labels.SMALL_MARGIN + stock["safe_mm"] * mm
        assert x + quiet >= allowance - 0.01 and x + w - quiet <= W - allowance + 0.01

    @pytest.mark.parametrize("small", [True, False])
    @pytest.mark.parametrize("codes", [labels.BARCODE, labels.BOTH])
    def test_nothing_is_printed_under_the_bars(self, small, codes):
        """The tag is already the largest line on an item's label, so under the bars
        it was the same seven characters again, in room the bars could use."""
        stock = labels.MEDIA[labels.SMALL if small else labels.FULL]
        said = []

        class Listening(surfaces.RasterSurface):
            def text(self, x, y, text, font, size):
                said.append(text)
                super().text(x, y, text, font, size)

            def text_centred(self, x, y, text, font, size):
                said.append(text)
                super().text_centred(x, y, text, font, size)

        surface = Listening(surfaces.blank(*labels.size_dots(stock)), stock["dpi"])
        labels._draw(surface, stock, PART, [], labels.PART, small, codes=codes)
        assert said.count(TAG) == 1


class TestALocationsLabel:
    def recorded(self, small=True, codes=labels.QR):
        said, sizes = [], []

        class Listening(surfaces.RasterSurface):
            def text(self, x, y, text, font, size):
                said.append(text)
                sizes.append(size)
                super().text(x, y, text, font, size)

        stock = labels.MEDIA[labels.SMALL if small else labels.FULL]
        surface = Listening(surfaces.blank(*labels.size_dots(stock)), stock["dpi"])
        labels._draw(surface, stock, PLACE, [], labels.LOCATION, small, codes=codes)
        return dict(zip(said, sizes, strict=False))

    @pytest.mark.parametrize("codes", labels.CODES)
    @pytest.mark.parametrize("small", [True, False])
    def test_it_carries_the_name_large_the_path_over_it_and_the_tag(self, small, codes):
        """With every code: under the bars was the one place a location's label had
        its tag in words when there was a barcode, and nothing is printed there now."""
        said = self.recorded(small, codes)
        assert "Box 14" in said and "RH-9J2X" in said
        path = next(line for line in said if "SHELF 2" in line)
        assert said["Box 14"] > said[path]
        if not small:
            assert path == "WORKSHOP / RACK 3 / SHELF 2"

    def test_a_path_too_long_for_the_tape_loses_its_far_end_first(self):
        """The near end says where the box is; the far end only which building."""
        path = next(line for line in self.recorded(True) if "SHELF 2" in line)
        assert path.startswith("…") or path == "WORKSHOP / RACK 3 / SHELF 2"
        assert path.endswith("SHELF 2")

    def test_the_word_up_the_end_says_location(self):
        assert labels.KIND_WORDS[labels.LOCATION] == "LOCATION"

    def test_the_small_one_is_the_default(self, client):
        tag = client.post("/api/locations", json={"name": "Box 14", "kind": "box"}).json()[
            "asset_id"
        ]
        default = client.get(f"/locations/{tag}/label.pdf").content
        small = client.get(f"/locations/{tag}/label.pdf?small=1").content
        assert _page_size(default) == _page_size(small)


class TestLabelsForEverythingInside:
    @pytest.fixture
    def shelf(self, client, computer):
        def place(name, parent=None):
            return client.post(
                "/api/locations", json={"name": name, "kind": "box", "parent": parent}
            ).json()["asset_id"]

        shelf = place("Shelf 2")
        box = place("Box 14", shelf)
        computer(location=shelf)
        for _ in range(20):
            computer(location=box)
        return shelf

    def test_one_to_a_page_for_a_label_printer(self, client, shelf):
        """The shelf's own, the box's, and the twenty-one things."""
        pdf = client.get(f"/locations/{shelf}/labels.pdf").content
        assert _pages(pdf) == 23
        assert _page_size(pdf) == _page_size(client.get(f"/locations/{shelf}/label.pdf").content)

    def test_or_on_a4_sheets_three_across_and_seven_down(self, client, shelf):
        pdf = client.get(f"/locations/{shelf}/labels.pdf?sheet=1").content
        assert _pages(pdf) == 2, "twenty-three labels is a sheet of twenty-one and two more"
        width, height = _page_size(pdf)
        assert (round(width), round(height)) == (595, 842)


class TestTheTypeSetting:
    def test_it_is_on_the_labels_tab_with_the_label_face_first(self, client):
        page = client.get("/settings/labels").text
        box = page.split('name="label_type"', 1)[1].split("</select>", 1)[0]
        assert re.findall(r'<option value="([a-z]+)"', box) == ["label", "look"]
        assert settings.value("label_type") == "label"

    def test_the_label_face_is_audiowide(self, client, part):
        aid = part()["asset_id"]
        pdf = client.get(f"/parts/{aid}/label.pdf").content
        assert b"Audiowide" in pdf and b"IBMPlex" not in pdf

    def test_as_the_look_is_the_looks_interface_face(self, client, part):
        aid = part()["asset_id"]
        save_labels(client, label_type="look")
        assert b"IBMPlexSans" in client.get(f"/parts/{aid}/label.pdf").content

    @pytest.mark.parametrize("appearance", [{"type": "ledger"}, {"preset": "phosphor"}])
    def test_a_monospaced_look_sets_the_label_monospaced(self, client, part, appearance):
        aid = part()["asset_id"]
        save_labels(client, label_type="look")
        client.post(
            "/settings", data={"site_name": "", "theme": "system", "watermark": "1"} | appearance
        )
        assert b"IBMPlexMono" in client.get(f"/parts/{aid}/label.pdf").content


class TestThePrintQueue:
    def test_a_location_can_be_sent_to_a_printer_somewhere_else(self, client, db):
        from app import printing

        tag = client.post("/api/locations", json={"name": "Box 14", "kind": "box"}).json()[
            "asset_id"
        ]
        png = printing.label_bytes(db, labels.LOCATION, tag, "niimbot-50x30", printing.PNG)
        assert png is not None and png.startswith(b"\x89PNG")


def _item(client, computer, part, kind):
    if kind == "computers":
        return computer()["asset_id"]
    if kind == "parts":
        return part()["asset_id"]
    if kind == "projects":
        return client.post("/api/projects", json={"name": "Recap the +2A"}).json()["asset_id"]
    return client.post("/api/locations", json={"name": "Box 14", "kind": "box"}).json()["asset_id"]


def _pages(pdf: bytes) -> int:
    return len(re.findall(rb"/Type /Page\b", pdf))


def _page_size(pdf: bytes) -> tuple[float, float]:
    box = re.search(rb"/MediaBox \[\s*([\d.]+) ([\d.]+) ([\d.]+) ([\d.]+)\s*\]", pdf)
    assert box, "no page size"
    return float(box[3]), float(box[4])
