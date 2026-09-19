"""The two things a label can be drawn on: a PDF page, and a bitmap of dots.

A label's layout -- where the code goes, how wide the text column is, which type
size fits, what gets clipped -- is the label's own business and has nothing to do
with the file it ends up in. That logic lives in `labels.py` and talks to one of
the surfaces here, which is the whole of what it knows about how a mark is made
(ADR-0024).

Both surfaces take the same coordinates: **points, origin bottom-left, y upwards**,
which is reportlab's convention and so costs the PDF nothing. The raster surface
converts, because the alternative -- a second set of numbers, in dots, kept in step
with the first by hand -- is how the two labels come to disagree about where the
name goes.

Two fonts, named by what they are for rather than by what they are called: the
display face if it is there, and whatever the surface can fall back on if it is
not.
"""

from __future__ import annotations

import io
from pathlib import Path
from typing import Protocol

import segno
from PIL import Image, ImageDraw, ImageFont
from reportlab.lib.utils import ImageReader
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont
from reportlab.pdfgen import canvas

FONT_PATH = Path(__file__).resolve().parent / "label_font.ttf"

# The two roles a label's type plays. What answers to them is the surface's to
# decide: the PDF registers the display face and names it, the raster opens the
# same file at a size in pixels, and where the file is missing they fall back to
# different things because they have different things to fall back on.
HEAD, BODY = "head", "body"

# What Pillow will draw with. Two classes rather than one: the display face is a
# TrueType font, and the fallback where that file has gone missing is Pillow's own
# bitmap one, which is not a subclass of it.
type Face = ImageFont.FreeTypeFont | ImageFont.ImageFont

# A point in dots, at the resolution a PDF is described in. Both surfaces measure
# in points; this is what the raster one multiplies by.
POINT_DPI = 72.0


class Surface(Protocol):
    """What a label's layout needs of the thing it is drawn on.

    Everything is in points with the origin at the bottom left. `text` puts a
    string's baseline at (x, y); nothing here knows about pages, dots or files.
    """

    def width_of(self, text: str, font: str, size: float) -> float: ...

    def ascent(self, font: str, size: float) -> float: ...

    def text(self, x: float, y: float, text: str, font: str, size: float) -> None: ...

    def text_centred(self, x: float, y: float, text: str, font: str, size: float) -> None: ...

    def vertical(
        self, x0: float, x1: float, y: float, text: str, font: str, size: float
    ) -> None: ...

    def qr(self, x: float, y: float, size: float, data: str, error: str = "M") -> None: ...

    def frame(self, x: float, y: float, w: float, h: float, radius: float) -> None: ...


def code(data: str, error: str) -> segno.QRCode:
    # micro=False, or segno picks a Micro QR whenever the data is short enough for
    # one -- and most readers, the scanner on the gallery included, decode standard
    # QR only. Any URL is comfortably too long to trigger it, so this is not load
    # bearing today; it is here so that encoding something short one day (a bare
    # asset tag is a Micro QR) cannot quietly print labels nothing will read.
    return segno.make(data, error=error.lower(), micro=False)


def whole_dots(space: int, data: str, error: str = "M") -> int:
    """How many dots one square of this code gets, in `space` dots of room.

    The largest whole number that fits, and never less than one. Whole, because a
    code scaled to whatever was left over has squares a dot wider than their
    neighbours: at eight dots to the millimetre that is a quarter of a square, and
    a phone reads the result as a picture of a QR code rather than as a code.

    The border is counted in, at the one-square quiet zone segno draws by default,
    because a code with its margin eaten is one a reader has to be argued with.
    """
    across = int(code(data, error).symbol_size(scale=1, border=1)[0])
    return max(1, space // across)


class PdfSurface:
    """A label on a reportlab canvas, which is what it has always been."""

    def __init__(self, c: canvas.Canvas) -> None:
        self._c = c
        self._fonts = _pdf_fonts()

    def _font(self, font: str) -> str:
        return self._fonts[font]

    def width_of(self, text: str, font: str, size: float) -> float:
        return float(self._c.stringWidth(text, self._font(font), size))

    def ascent(self, font: str, size: float) -> float:
        return float(pdfmetrics.getAscent(self._font(font))) / 1000.0 * size

    def text(self, x: float, y: float, text: str, font: str, size: float) -> None:
        self._c.setFont(self._font(font), size)
        self._c.drawString(x, y, text)

    def text_centred(self, x: float, y: float, text: str, font: str, size: float) -> None:
        self._c.setFont(self._font(font), size)
        self._c.drawCentredString(x, y, text)

    def vertical(self, x0: float, x1: float, y: float, text: str, font: str, size: float) -> None:
        """One word running bottom to top, centred in the strip between x0 and x1.

        Rotated -90 and not +90. The page is already turned a quarter of the way
        round (see labels.rotated_page: a 6x4 label prints on a 4x6 sheet), and
        turning the word the same way again stands it the right way up but pointing
        the other way down the label, which on paper is upside down against
        everything beside it. The two rotations have to disagree for the word to
        agree with the body.

        Centred by measuring rather than by an offset picked to look right: the
        glyphs stand to one side of the baseline, so which side and how far both
        change with the type size, and a hand-tuned number is one that silently
        stops being centred the moment anybody changes the size.
        """
        ascent = self.ascent(font, size)
        self._c.saveState()
        self._c.translate(x0 + (x1 - x0 - ascent) / 2, y)
        self._c.rotate(-90)
        self.text_centred(0, 0, text, font, size)
        self._c.restoreState()

    def qr(self, x: float, y: float, size: float, data: str, error: str = "M") -> None:
        buf = io.BytesIO()
        code(data, error).save(buf, kind="png", scale=10, border=1)
        buf.seek(0)
        self._c.drawImage(
            ImageReader(buf), x, y, width=size, height=size, preserveAspectRatio=True, mask="auto"
        )

    def frame(self, x: float, y: float, w: float, h: float, radius: float) -> None:
        self._c.setLineWidth(1)
        self._c.setStrokeColorRGB(0.65, 0.65, 0.65)
        self._c.roundRect(x, y, w, h, radius, stroke=1, fill=0)
        self._c.setFillColorRGB(0, 0, 0)


class RasterSurface:
    """A label as the dots a print head burns.

    One bit deep, because that is what the head is: on or off, with no grey to
    print. A greyscale image scaled down here would be dithered by the printer,
    and a dithered code is unreadable.

    `dpi` is the printer's, and the only place the two coordinate systems meet:
    a point is `dpi/72` dots, and y is measured from the bottom here as it is in a
    PDF, so the layout does not have to know which surface it has.
    """

    def __init__(self, image: Image.Image, dpi: float) -> None:
        self._image = image
        self._draw = ImageDraw.Draw(image)
        self._dpi = dpi
        self._scale = dpi / POINT_DPI
        self._cache: dict[tuple[str, int], Face] = {}

    def _font(self, font: str, size: float) -> Face:
        """The face at a size in dots, kept: a label picks its type size by asking
        how wide a string is at one size after another, so the same few faces are
        opened dozens of times in the drawing of one small label."""
        dots = max(1, round(size * self._scale))
        key = (font, dots)
        if key not in self._cache:
            self._cache[key] = _raster_font(dots)
        return self._cache[key]

    def _xy(self, x: float, y: float) -> tuple[float, float]:
        """A point in the layout's coordinates as one in the image's: dots, and
        measured down from the top."""
        return (x * self._scale, self._image.height - y * self._scale)

    def width_of(self, text: str, font: str, size: float) -> float:
        return float(self._font(font, size).getlength(text)) / self._scale

    def ascent(self, font: str, size: float) -> float:
        face = self._font(font, size)
        if isinstance(face, ImageFont.FreeTypeFont):
            return float(face.getmetrics()[0]) / self._scale
        # Pillow's own bitmap face has no metrics to be asked for. Its glyphs sit
        # inside the size it was opened at, which is near enough for the one thing
        # an ascent is used for -- centring a word across a strip.
        return size

    def text(self, x: float, y: float, text: str, font: str, size: float) -> None:
        # anchor="ls": the left end of the baseline, which is what (x, y) means to
        # every caller here and to reportlab's drawString.
        self._draw.text(self._xy(x, y), text, font=self._font(font, size), fill=0, anchor="ls")

    def text_centred(self, x: float, y: float, text: str, font: str, size: float) -> None:
        self._draw.text(self._xy(x, y), text, font=self._font(font, size), fill=0, anchor="ms")

    def vertical(self, x0: float, x1: float, y: float, text: str, font: str, size: float) -> None:
        """The same word up the same end, drawn by turning a picture of it.

        There is no page rotation to disagree with here -- the image is the label
        as it will be read -- so the word is simply turned to read bottom to top,
        and centred in the strip by its own bounding box rather than by its
        baseline, which after a quarter turn is an edge rather than a middle.
        """
        face = self._font(font, size)
        left, top, right, bottom = (round(v) for v in face.getbbox(text))
        block = Image.new("1", (max(1, right - left), max(1, bottom - top)), 1)
        ImageDraw.Draw(block).text((-left, -top), text, font=face, fill=0)
        turned = block.rotate(90, expand=True)
        x = (x0 + x1) / 2 * self._scale - turned.width / 2
        cy = self._image.height - y * self._scale - turned.height / 2
        self._image.paste(turned, (round(x), round(cy)))

    def qr(self, x: float, y: float, size: float, data: str, error: str = "M") -> None:
        """The code at a whole number of dots to the square, centred on what it was
        given -- see `whole_dots` on why it is never merely fitted."""
        space = round(size * self._scale)
        scale = whole_dots(space, data, error)
        buf = io.BytesIO()
        code(data, error).save(buf, kind="png", scale=scale, border=1)
        buf.seek(0)
        drawn = Image.open(buf).convert("1")
        left, top = self._xy(x, y + size)
        self._image.paste(
            drawn,
            (round(left + (space - drawn.width) / 2), round(top + (space - drawn.height) / 2)),
        )

    def frame(self, x: float, y: float, w: float, h: float, radius: float) -> None:
        """Black, where the PDF draws a grey hairline. There is no grey on a
        thermal head, and the dither it would come out as is worse than a border
        heavier than it was drawn."""
        left, bottom = self._xy(x, y)
        right, top = self._xy(x + w, y + h)
        self._draw.rounded_rectangle(
            [left, top, right, bottom], radius=radius * self._scale, outline=0, width=1
        )


_pdf_ready = False


def _pdf_fonts() -> dict[str, str]:
    """Register the display TTF with reportlab once; fall back to Helvetica if it
    is missing."""
    global _pdf_ready
    if not _pdf_ready and FONT_PATH.exists():
        try:
            pdfmetrics.registerFont(TTFont("LabelFont", str(FONT_PATH)))
            _pdf_ready = True
        except Exception:
            pass
    if _pdf_ready:
        return {HEAD: "LabelFont", BODY: "LabelFont"}
    return {HEAD: "Helvetica-Bold", BODY: "Helvetica"}


def _raster_font(dots: int) -> Face:
    """The display face at a size in dots, or Pillow's own where it is missing.

    The fallback is a different shape of answer from the PDF's: there is no
    Helvetica to ask for here, only whatever Pillow was built with, and a label
    drawn in it will not look like the PDF of the same label. That is the point at
    which the font file has gone missing from the image, which is a deployment
    fault and not a rendering one.
    """
    if FONT_PATH.exists():
        try:
            return ImageFont.truetype(str(FONT_PATH), dots)
        except OSError:
            pass
    return ImageFont.load_default(size=dots)


def blank(width: int, height: int) -> Image.Image:
    """A label's worth of unburnt dots. White is 1 in a one-bit image, and every
    mark made on it is 0."""
    return Image.new("1", (max(1, width), max(1, height)), 1)
