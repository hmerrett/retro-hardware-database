"""A label is also a picture of itself, drawn in a particular printer's dots.

A PDF is a description of a label that something else decides how to print. A
small thermal label printer is not sent pages at all: it is sent a bitmap the
width of its print head, and the head burns a dot or leaves it blank. Scaling a
page down to fit gives grey, grey on a thermal head is a dither, and a dithered QR
code is a picture of a QR code rather than one (ADR-0024).

So the picture is asked for by the stock it is printed on, drawn at that stock's
size in that printer's dots, and its code is drawn a whole number of dots to the
square.
"""

import io

import pytest
from PIL import Image

from app import labels, surfaces

PNG = b"\x89PNG\r\n\x1a\n"


def picture(client, url):
    r = client.get(url)
    assert r.status_code == 200, r.text[:300]
    assert r.content.startswith(PNG)
    return Image.open(io.BytesIO(r.content))


def test_every_kind_of_item_has_a_label_as_a_picture(client, computer, part):
    made = computer()
    card = part(type="video", manufacturer="Trident", model="TVGA8900")
    r = client.post("/api/projects", json={"name": "Recap the PC1512"})
    assert r.status_code == 200, r.text
    for url in (
        f"/computers/{made['asset_id']}/label.png",
        f"/parts/{card['asset_id']}/label.png",
        f"/projects/{r.json()['asset_id']}/label.png",
    ):
        assert picture(client, url).width > 0


def test_the_picture_is_one_dot_deep(client, part):
    """Not greyscale, and not a palette. The head is on or off, and a label that
    says so in its own file cannot acquire a dither on the way to the printer."""
    card = part()
    assert picture(client, f"/parts/{card['asset_id']}/label.png").mode == "1"


def test_the_stock_decides_the_shape_and_the_printer_decides_the_dots(client, part):
    """Two questions that used to be one. `small` could say 51x19mm or 6x4in and
    nothing else -- not which of two 50mm Niimbot labels, and not how many dots a
    head puts in a millimetre."""
    aid = part()["asset_id"]
    dymo = picture(client, f"/parts/{aid}/label.png?media=dymo-11355")
    assert dymo.size == (602, 224)
    niimbot = picture(client, f"/parts/{aid}/label.png?media=niimbot-50x30")
    assert niimbot.size == (384, 240)


def test_a_head_narrower_than_its_tape_is_the_registers_fact_and_not_the_callers(client, part):
    """A B1 takes a 50mm label on a 48mm head. Nothing is laid out in the 2mm it
    cannot reach, and no caller has to know the number to get that right."""
    aid = part()["asset_id"]
    media = labels.MEDIA["niimbot-50x30"]
    assert media["dots"] == 384
    full_width = round(media["w_mm"] * media["dpi"] / 25.4)
    assert full_width > media["dots"]
    assert picture(client, f"/parts/{aid}/label.png?media=niimbot-50x30").width == media["dots"]


def test_the_dots_can_be_asked_for(client, part):
    """A stock has the resolution of the printer it belongs to, and a printer that
    is not that one says so."""
    aid = part()["asset_id"]
    assert picture(client, f"/parts/{aid}/label.png?media=dymo-11355&dpi=203").size == (408, 152)


def test_a_stock_the_register_does_not_know_is_refused_rather_than_guessed(client, part):
    """Guessing prints a label of the wrong size, which is discovered by peeling it
    off something."""
    aid = part()["asset_id"]
    assert client.get(f"/parts/{aid}/label.png?media=nonesuch").status_code == 404


def test_the_code_is_drawn_a_whole_number_of_dots_to_the_square():
    """A code fitted to the space left over has squares a dot wider than their
    neighbours. At eight dots to the millimetre that is a quarter of a square.

    Checked on the finder pattern, the ring in a code's corner: its runs are 1, 1,
    3, 1, 1 squares across by construction, so every run along its middle is a
    whole multiple of one square -- which it cannot be if the code was scaled."""
    size = 96.0
    url = "https://example.test/items/RH-0001/"
    image = surfaces.blank(round(size), round(size))
    surfaces.RasterSurface(image, dpi=72).qr(0, 0, size, url, "M")
    pixels = image.load()
    scale = surfaces.whole_dots(round(size), url, "M")
    assert scale >= 2
    row = [pixels[x, round(size / 2)] for x in range(round(size))]
    runs = []
    for value in row:
        if runs and runs[-1][0] == value:
            runs[-1][1] += 1
        else:
            runs.append([value, 1])
    # The margins at each end are whatever was left over after whole squares were
    # taken, so they are not themselves multiples; everything the code draws is.
    for _value, length in runs[1:-1]:
        assert length % scale == 0, f"a run of {length} dots is not a multiple of {scale}"


def test_the_picture_is_behind_the_login_like_the_pdf():
    """A label is an editing action: it is printed by whoever owns the collection.
    The gate that knew that named the PDF by its extension, so a label in any other
    format would have been public by being new."""
    from app import auth

    assert not auth._public_page("/parts/RH-0001/label.png")
    assert not auth._public_page("/parts/RH-0001/label.pdf")
    assert not auth._public_page("/computers/RH-0001/label.png")
    assert not auth._public_page("/projects/RH-J0Y7/label.png")
    assert auth._public_page("/parts/RH-0001")


@pytest.mark.parametrize("name", sorted(labels.MEDIA))
def test_every_stock_the_register_knows_can_be_drawn(name, client, part):
    """Including the 6x4in sheet: a raster is not only for the small labels, and a
    stock in the list that cannot be rendered is a menu entry that fails when it is
    chosen."""
    aid = part(type="storage", manufacturer="Seagate", model="ST-225")["asset_id"]
    image = picture(client, f"/parts/{aid}/label.png?media={name}")
    assert image.size[0] > 8 and image.size[1] > 8


class Recording:
    """A surface that notes what it was asked to write, and passes it on.

    Wrapping a real surface rather than standing in for one: the layout asks how
    wide a string is before it decides anything, so a stub that cannot measure
    would be answering a different question from the one under test.
    """

    def __init__(self, inner):
        self.inner = inner
        self.said = []
        self.sizes = []

    def __getattr__(self, name):
        return getattr(self.inner, name)

    def text(self, x, y, text, font, size):
        self.said.append(text)
        self.sizes.append(size)
        self.inner.text(x, y, text, font, size)

    def text_centred(self, x, y, text, font, size):
        self.said.append(text)
        self.inner.text_centred(x, y, text, font, size)

    def vertical(self, x0, x1, y, text, font, size):
        self.said.append(text)
        self.inner.vertical(x0, x1, y, text, font, size)


def both_surfaces(media, row, kind, small=True):
    """What each surface was asked to write for the same label."""
    from reportlab.pdfgen import canvas

    stock = labels.MEDIA[media]
    page = Recording(
        surfaces.PdfSurface(canvas.Canvas(io.BytesIO(), pagesize=labels.rotated_page(stock)))
    )
    labels._draw(page, stock, row, [], kind, small)
    dots = Recording(surfaces.RasterSurface(surfaces.blank(*labels.size_dots(stock)), stock["dpi"]))
    labels._draw(dots, stock, row, [], kind, small)
    return page.said, dots.said


def type_sizes(media, row, kind, small=True):
    """The type sizes a label was actually set in."""
    from reportlab.pdfgen import canvas

    stock = labels.MEDIA[media]
    page = Recording(
        surfaces.PdfSurface(canvas.Canvas(io.BytesIO(), pagesize=labels.rotated_page(stock)))
    )
    labels._draw(page, stock, row, [], kind, small)
    return page.sizes


DRIVE = {
    "asset_id": "RH-0117",
    "manufacturer": "Seagate",
    "model": "ST-225",
    "type": "storage",
    "specs": 'Capacity: 20MB | CHS: 615/4/17 | Form factor: 5.25"',
    "variant": "",
}
SCREEN = {
    "asset_id": "RH-0204",
    "manufacturer": "Commodore",
    "model": "1084S",
    "type": "display",
    "specs": 'Screen size: 14" | Panel: Trinitron | Resolution: 320x200 (CGA) | Refresh: 50 Hz, 60 Hz',
    "variant": "",
}


def same_word(one: str, other: str) -> bool:
    """Whether two surfaces wrote the same word, one of them possibly cut short.

    The two measure the same font file with different engines -- reportlab's
    metrics against Pillow's -- and they disagree by a fraction of a point. That is
    invisible everywhere except at the character a clip falls on, where it shows as
    "320x200" against "320x20…". Requiring those to match would be requiring two
    font engines to agree to the last decimal, which is not a promise worth making.
    """
    one, other = one.rstrip("…"), other.rstrip("…")
    return one.startswith(other) or other.startswith(one)


@pytest.mark.parametrize("media", sorted(labels.MEDIA))
@pytest.mark.parametrize("row", [DRIVE, SCREEN], ids=["drive", "screen"])
def test_both_surfaces_lay_out_the_same_label(media, row):
    """The point of writing the layout once: a label proofed as a PDF is the label
    that comes out of the thermal printer, saying the same things in the same order.

    Compared word by word rather than line by line. Where the lines break is the
    one place the two font engines' disagreement shows, and it cascades -- a line
    clipped a character earlier leaves a different word to start the next one. What
    the label *says* is the promise; where it wraps is typography.
    """
    page, dots = both_surfaces(media, row, labels.PART, small=media != "full-6x4")
    said, printed = " ".join(page).split(), " ".join(dots).split()
    assert len(said) == len(printed), f"{page} against {dots}"
    for one, other in zip(said, printed, strict=True):
        assert same_word(one, other), f"{page} against {dots}"


def test_a_taller_label_does_not_give_the_code_more_than_its_share():
    """The code is as big as it can be, because one that will not scan is worth
    nothing -- but a sticker is read by a person too, and a label saying only
    "Seaga…" has failed at the half of the job the code cannot do.

    Sizing the code by the label's height alone was right while every small label
    was a 51x19mm tape, where the height is what binds. On a 50x30mm Niimbot label
    it took more than half the width, with two thirds of the label left empty.
    """
    page, dots = both_surfaces("niimbot-50x30", DRIVE, labels.PART)
    words = ["PART", "RH-0117", "Seagate", "ST-225", "20MB", "CHS", "615/4/17", '5.25"']
    assert " ".join(page).split() == words
    assert " ".join(dots).split() == words


PROJECT = {
    "asset_id": "RH-J0Y7",
    "name": "Recap the PC1512",
    "status": "active",
    "specs": "",
    "variant": "",
}


def test_the_type_grows_with_the_label():
    """The sizes on a small label are the tape's, because they are what fits on a
    tape. Printed unchanged on a label half as tall again they left a third of it
    empty, which is a label that could have been read across the room and cannot."""
    tape = type_sizes("dymo-11355", DRIVE, labels.PART)
    taller = type_sizes("niimbot-50x30", DRIVE, labels.PART)
    # The body, which is the smallest thing set on a label. Not the tag: that is
    # sized to the width of its column, and a 50x30mm label has a narrower one than
    # a 51x19mm tape -- so the tag comes out a fraction smaller on the bigger label,
    # and asserting on the largest size would say the opposite of what this is about.
    assert min(taller) > min(tape)


@pytest.mark.parametrize("media", ["niimbot-50x30", "niimbot-40x30"])
def test_growing_the_type_does_not_outgrow_the_column(media):
    """A 40x30mm label is as tall as a 50x30mm one and a third narrower. Type sized
    by the height alone put "PC1512" in a column that could not hold it, where the
    only answer left is the clip -- so it came out as "PC15…" on a label with room
    to spare, which is the fault the growth was meant to fix, arriving the other
    way round."""
    page, dots = both_surfaces(media, PROJECT, labels.PROJECT)
    assert not [line for line in page if "…" in line], page
    assert not [line for line in dots if "…" in line], dots
