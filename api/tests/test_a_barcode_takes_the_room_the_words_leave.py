"""A barcode is as tall as the words let it be (MANUAL §13, "QR code, barcode, both or
none"; ADR-0040).

The words are set as they would be with no bars there, and the bars rise from the
foot of the label to just under the last line: with nothing written, they run its
whole height. However much is written they keep the height they always had, and a
crowded label makes room as it always has. On a 6x4 sheet a barcode alone runs
across under the words rather than standing where the QR code would, and a label
whose words fill the sheet gives its last lines to it.

Where the bars go is noted rather than drawn, so that what is inked on the label is
what is written on it; and where a QR code goes, likewise.
"""

import pytest
from PIL import ImageOps
from reportlab.lib.units import inch

from app import barcode, labels, surfaces

FULL = labels.FULL
EVERY_STOCK = sorted(labels.MEDIA)
EVERY = ("tag", "name", "make", "specs", "serial", "kept")

# Names with tails on them, so that the last line over the bars has something to
# reach down with.
DRIVE = {
    "asset_id": "RH-K7Q2",
    "name": "Spare plugs",
    "manufacturer": "Seagate",
    "model": "ST-225",
    "type": "storage",
    "specs": 'Capacity: 20MB | CHS: 615/4/17 | Form factor: 5.25"',
    "serial": "3B4471",
    "kept": "Workshop / Drawer 4",
    "variant": "",
}
PLACE = {
    "asset_id": "RH-9J2X",
    "name": "Gaming rig",
    "kept": "Workshop / Rack 3 / Shelf 2",
    "kind": "Shelf",
    "notes": "",
}
# A drive whose specification fills a 6x4 sheet beside a QR code: eleven lines of it,
# then its serial number and where it is kept.
LONG = {
    **DRIVE,
    "specs": " | ".join(
        [
            "Capacity: 20MB",
            "CHS: 615/4/17",
            'Form factor: 5.25"',
            "Interface: ST-506",
            "Encoding: MFM",
            "Speed: 3600 rpm",
            "Seek: 65 ms",
            "Height: Full",
            "Jumpers: DS1",
        ]
    ),
}

# Labels with room to spare: the tag alone, a location's tag and name, a name alone.
ROOMY = [
    (labels.PART, DRIVE, ("tag",)),
    (labels.LOCATION, PLACE, ("tag", "name")),
    (labels.PART, DRIVE, ("name",)),
]


class Barless(surfaces.RasterSurface):
    """Draws the words and the word up the end, and notes where the bars, the QR code
    and each line of words go without drawing the codes."""

    def __init__(self, image, dpi, face):
        super().__init__(image, dpi, face)
        self.image, self.dpi = image, dpi
        self.bars: list[tuple[float, float, float, float]] = []
        self.qrs: list[tuple[float, float, float]] = []
        self.lines: list[tuple[float, float, str]] = []

    def barcode(self, x, y, w, h, data):
        self.bars.append((x, y, w, h))

    def qr(self, x, y, size, data, error="M"):
        self.qrs.append((x, y, size))

    def text(self, x, y, text, font, size):
        self.lines.append((y, size, text))
        super().text(x, y, text, font, size)


def setup(listed, codes, word=False, stock=labels.SMALL):
    return labels.Setup(
        "small", "Small label", codes, stock, tuple(listed), word, labels.LABEL_FACE
    )


def drawn(media, codes, listed, word=False, row=DRIVE, kind=labels.PART, face=surfaces.LABEL):
    stock = labels.MEDIA[media]
    surface = Barless(surfaces.blank(*labels.size_dots(stock)), stock["dpi"], face)
    labels._draw(surface, stock, row, [], kind, True, label=setup(listed, codes, word, media))
    return surface


def margin(media):
    return labels.FULL_MARGIN if media == FULL else labels.SMALL_MARGIN


def height(media):
    return labels.layout_size(labels.MEDIA[media])[1]


def ink_in(surface, box):
    """Whether anything is drawn inside `box`, (x, y, w, h) in points from the foot of
    the label, read off the label's own dots."""
    x, y, w, h = box
    scale = surface.dpi / 72
    image = surface.image
    crop = image.crop(
        (
            round(x * scale),
            image.height - round((y + h) * scale),
            round((x + w) * scale),
            image.height - round(y * scale),
        )
    )
    return ImageOps.invert(crop.convert("L")).getbbox() is not None


# --- with nothing written --------------------------------------------------------


@pytest.mark.parametrize("media", EVERY_STOCK)
def test_with_nothing_on_it_a_barcode_runs_the_labels_whole_height(media):
    """Nothing ticked, the word up the end included: the code alone, from the foot of
    the label to its top, inside its margins."""
    surface = drawn(media, labels.BARCODE, ())
    ((_, y, _, h),) = surface.bars
    assert y == pytest.approx(margin(media))
    assert y + h == pytest.approx(height(media) - margin(media))


@pytest.mark.parametrize("media", ["dymo-99012", "dymo-99015", FULL])
def test_beside_a_qr_code_the_bars_run_the_whole_height_too(media):
    """With both codes, on a label wide enough for the bars to stand beside the QR code
    rather than under it, nothing ticked leaves them the whole height beside it."""
    surface = drawn(media, labels.BOTH, ())
    ((qx, _, size),) = surface.qrs
    ((x, y, w, h),) = surface.bars
    assert x + w <= qx or x >= qx + size, "beside the code, not under it"
    assert y == pytest.approx(margin(media))
    assert y + h == pytest.approx(height(media) - margin(media))


# --- with words ------------------------------------------------------------------


@pytest.mark.parametrize("media", EVERY_STOCK)
@pytest.mark.parametrize("kind, row, listed", ROOMY)
def test_the_bars_rise_to_just_under_the_last_line(media, kind, row, listed):
    """Between the last line's baseline and the top of the bars there is less than
    that line is tall: no room for another line, and none the bars could have had."""
    surface = drawn(media, labels.BARCODE, listed, row=row, kind=kind)
    ((_, y, _, h),) = surface.bars
    last, size, _ = min(surface.lines)
    assert 0 < last - (y + h) <= size


@pytest.mark.parametrize("face", sorted(surfaces.FACES))
@pytest.mark.parametrize("codes", [labels.BARCODE, labels.BOTH])
@pytest.mark.parametrize("media", EVERY_STOCK)
def test_nothing_written_reaches_into_bars_that_rise_to_meet_it(media, codes, face):
    """The whole of the last line stands above them, tails and all, and so does the word
    up the end, which on a label the bars run across stands above them too."""
    for kind, row, listed in [*ROOMY, (labels.PART, DRIVE, ())]:
        surface = drawn(media, codes, listed, word=True, row=row, kind=kind, face=face)
        ((x, y, w, h),) = surface.bars
        assert not ink_in(surface, (x, y, w, h)), f"{kind} {listed}: ink in the bars"


@pytest.mark.parametrize("codes", [labels.BARCODE, labels.BOTH])
@pytest.mark.parametrize("media", EVERY_STOCK)
def test_however_much_is_written_the_bars_keep_the_height_they_always_had(media, codes):
    """A little over a third of a small label's height, and on a 6x4 sheet 0.9 inches for
    a barcode alone and as high up the label as they always reached with both codes."""
    for row, listed in [(DRIVE, ()), (DRIVE, ("tag",)), (DRIVE, EVERY), (LONG, EVERY)]:
        surface = drawn(media, codes, listed, word=True, row=row)
        ((_, y, _, h),) = surface.bars
        if media != FULL:
            least = max(labels.BAR_MIN, (height(media) - 2 * margin(media)) * labels.BAR_SHARE)
            assert h >= least - 1e-6, listed
        elif codes == labels.BARCODE:
            assert h >= 0.9 * inch - 1e-6, listed
        else:
            assert y + h >= margin(media) + 0.66 * inch + 10 - 1e-6, listed


@pytest.mark.parametrize("media", EVERY_STOCK)
def test_with_both_codes_the_qr_code_keeps_its_size(media):
    """The bars have only the height the QR code leaves them: the code is the same size
    with nothing written as with every detail, and bars running under it stay under
    it."""
    sizes = set()
    for listed in [(), EVERY]:
        surface = drawn(media, labels.BOTH, listed, word=True)
        if not surface.qrs:
            continue  # the 51x19 mm tape, which carries the barcode alone
        ((qx, qy, size),) = surface.qrs
        ((x, y, w, h),) = surface.bars
        sizes.add(round(size, 6))
        if x < qx + size and qx < x + w:
            assert y + h <= qy + 1e-6, f"{listed}: the bars reach into the code"
    assert len(sizes) <= 1


# --- on a 6x4 sheet --------------------------------------------------------------


def test_on_a_6x4_sheet_a_barcode_alone_runs_across_under_the_words():
    """As wide as the sheet allows inside its margins, under every line written on it,
    and no QR code."""
    stock = labels.MEDIA[FULL]
    surface = drawn(FULL, labels.BARCODE, ("tag", "name", "specs"), word=True)
    assert not surface.qrs
    ((_, y, w, h),) = surface.bars
    W, _ = labels.layout_size(stock)
    room = W - 2 * labels.FULL_MARGIN
    another_dot = barcode.width(DRIVE["asset_id"]) * 72 / stock["dpi"]
    assert w <= room < w + another_dot
    assert min(line for line, _, _ in surface.lines) > y + h


def test_a_6x4_label_that_fills_the_sheet_gives_its_last_lines_to_a_barcode_alone():
    """Beside a QR code the whole of it fits; with the bars running across under it, the
    last of its specification goes and so do the details after it -- and the label
    says so, which is what the settings page puts under its picture."""
    stock = labels.MEDIA[FULL]
    qr = labels.fit(LONG, [], labels.PART, stock, setup(EVERY, labels.QR, True, FULL))
    assert qr == labels.Fit((), ())
    bars = labels.fit(LONG, [], labels.PART, stock, setup(EVERY, labels.BARCODE, True, FULL))
    assert bars == labels.Fit(("serial", "kept"), ("specs",))
