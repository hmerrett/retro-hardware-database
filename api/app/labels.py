"""Print-ready label PDFs, rendered in the api so the GUI's "print label" action
can hand back a file to download. A focused port of the flat-file make_labels.py:
same 6x4in full label and 51x19mm small label, same QR encoding
<base_url>/items/<asset_id>/ so the codes match every label already printed.

Physical printing stays on the DYMO box; here we only generate the PDF.
"""
from __future__ import annotations

import io
import os
from pathlib import Path

import segno
from reportlab.lib.units import inch, mm
from reportlab.lib.utils import ImageReader
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont
from reportlab.pdfgen import canvas

from .entry import display_name, parse_specs, type_label
from .machines import ISSUE_KEY, REGION_KEY, STYLE_KEY

# The three answers in a catalogue machine's line that are not a chip, and so get a
# line of their own on a label (see computer_lines).
_MACHINE_KEYS = (ISSUE_KEY, STYLE_KEY, REGION_KEY)

FONT_PATH = Path(__file__).resolve().parent / "label_font.ttf"

# Label geometry, mirroring the flat-file config.yml defaults.
FULL = {"w": 6 * inch, "h": 4 * inch, "qr": "M", "rotate": 90}
SMALL = {"w": 51 * mm, "h": 19 * mm, "qr": "M", "rotate": 90, "safe_mm": 3}

BUILD_ROWS = [("cpu", "CPU"), ("ram", "Memory"), ("video", "Video"),
              ("sound", "Sound"), ("storage", "Storage"), ("network", "Network")]
# The one spec that stands for a whole part, where a machine's label has room for
# only a line each.
SPEC_PICK = {"ram": "Size", "storage": "Capacity"}
# The small label has no room for a spec list -- but a bare drive on a shelf is
# known by how big it is, and by the geometry you need before an old BIOS will talk
# to it, as much as by what is printed on the casing. Those get lines of their own,
# in this order: squeezed for height, the last is what goes.
#
# Each entry is one line, and a line may join more than one spec where the two are
# read as one thing: a floppy drive is "a 3.5-inch 1.44MB", never a 3.5-inch on one
# line and a 1.44MB on another -- and joined, they cannot be separated by the squeeze
# that drops the last line, which would leave the less useful half behind.
#
# Each carries the prefix it needs to be unmistakable at arm's length. A capacity
# and a form factor say their own units; a geometry is three numbers that could
# otherwise be anything.
#
# One table serves every sort of drive because the keys barely overlap: a disk has
# a Capacity and a CHS, a floppy has a Form factor and a Size, an optical drive has
# a Media, and each takes the lines the others leave empty.
#
# Speed is the one key two of them answer -- 7200 rpm on a disk, 48× on an optical
# drive -- and it goes last, beside the medium it belongs with, where the squeeze
# takes it first: it is the least of what identifies a drive at arm's length.
SMALL_SPECS = {"storage": ((("Capacity", ""),),
                           (("CHS", "CHS "),),
                           (("Form factor", ""), ("Size", "")),
                           (("Media", ""), ("Speed", "")))}


def _pairs_of(part):
    """A part's (key, value) spec pairs: the ones the caller read from the typed
    tables if it attached them, else parsed from the rendered specs string."""
    pairs = part.get("spec_pairs")
    return pairs if pairs is not None else parse_specs(part.get("specs", ""))

_font_ready = False


def base_url() -> str:
    return (os.getenv("RHDB_BASE_URL") or "https://db.2600.me").rstrip("/")


def item_url(asset_id: str) -> str:
    return f"{base_url()}/items/{asset_id}/"


def _fonts():
    """Register the display TTF once; fall back to Helvetica if it's missing."""
    global _font_ready
    if _font_ready:
        return ("LabelFont", "LabelFont")
    if FONT_PATH.exists():
        try:
            pdfmetrics.registerFont(TTFont("LabelFont", str(FONT_PATH)))
            _font_ready = True
            return ("LabelFont", "LabelFont")
        except Exception:
            pass
    return ("Helvetica-Bold", "Helvetica")


def _qr(data, error="M"):
    # micro=False, or segno picks a Micro QR whenever the data is short enough for
    # one -- and most readers, the scanner on the gallery included, decode standard
    # QR only. Any URL is comfortably too long to trigger it, so this is not load
    # bearing today; it is here so that encoding something short one day (a bare
    # asset tag is a Micro QR) cannot quietly print labels nothing will read.
    buf = io.BytesIO()
    segno.make(data, error=error.lower(), micro=False).save(
        buf, kind="png", scale=10, border=1)
    buf.seek(0)
    return ImageReader(buf)


def _wrap(c, text, font, size, max_w):
    words, lines, cur = text.split(), [], ""
    for w in words:
        trial = (cur + " " + w).strip()
        if not cur or c.stringWidth(trial, font, size) <= max_w:
            cur = trial
        else:
            lines.append(cur)
            cur = w
    if cur:
        lines.append(cur)
    return lines or [""]


def _fit(c, text, font, start, min_size, max_w):
    size = start
    while size > min_size and c.stringWidth(text, font, size) > max_w:
        size -= 1
    return size


def _fit_lines(c, text, font, start, min_size, width, max_lines):
    size = start
    while size > min_size and len(_wrap(c, text, font, size, width)) > max_lines:
        size -= 0.5
    return size


def rotated_page(spec):
    return (spec["h"], spec["w"]) if spec["rotate"] in (90, 270) else (spec["w"], spec["h"])


def _apply_rotation(c, W, H, rot):
    if rot == 90:
        c.translate(H, 0)
        c.rotate(90)
    elif rot == 270:
        c.translate(0, W)
        c.rotate(-90)
    elif rot == 180:
        c.translate(W, H)
        c.rotate(180)


# --- content ---------------------------------------------------------------

def computer_lines(comp, parts, form_factor=""):
    """Label body for a machine. `form_factor` comes from the linked board's typed
    column (see main.gui_computer_label); it falls back to the rendered specs
    string only so a caller that has not looked it up still gets a label."""
    kids = sorted((p for p in parts if p.get("computer_id") == comp["asset_id"]),
                  key=lambda p: p.get("type", ""))
    lines = ["Type: Computer"]
    for p in kids:
        if form_factor:
            break
        if p.get("type") == "motherboard":
            form_factor = dict(_pairs_of(p)).get("Form factor", "")
    if comp.get("manufacturer"):
        lines.append(f"Manufacturer: {comp['manufacturer']}")
    if comp.get("year"):
        lines.append(f"Year: {comp['year']}")
    # A catalogue machine's identity: on a sealed machine the board issue and the ULA
    # are what a label is for, since nothing inside it has a tag of its own to carry
    # them. The model, the board and the two answers that tell one of these apart get
    # a line each; the chips share one line, each named by its socket, because a
    # socket is often called what the label already calls something else -- a machine
    # has a CPU field and a CPU socket, saying different true things -- and two lines
    # both headed CPU read as a contradiction rather than as two facts.
    chips = []
    for key, value in parse_specs(comp.get("variant", "")):
        if not key:
            lines.append(f"Machine: {value}")
        elif key in _MACHINE_KEYS:
            lines.append(f"{key}: {value}")
        else:
            chips.append(f"{key} {value}")
    if chips:
        lines.append("Chips: " + ", ".join(chips))
    if form_factor:
        lines.append(f"Form factor: {form_factor}")
    for label, key in (("CPU", "cpu"), ("RAM", "installed_ram"),
                       ("Drives", "drives"), ("Chassis", "chassis"), ("OS", "os")):
        if comp.get(key):
            lines.append(f"{label}: {comp[key]}")
    by_type = {}
    for p in kids:
        by_type.setdefault(p.get("type", ""), []).append(p)
    for ptype, label in BUILD_ROWS:
        if ptype not in by_type:
            continue
        members = by_type[ptype]
        if ptype in SPEC_PICK:
            specs = dict(_pairs_of(members[0]))
            value = specs.get(SPEC_PICK[ptype]) or display_name(members[0])
        else:
            value = " + ".join(display_name(m) for m in members)
        lines.append(f"{label}: {value}")
    if comp.get("condition"):
        lines.append(f"Condition: {comp['condition']}")
    return lines


def small_body(asset, is_computer, spec_pairs=None):
    """(name, [spec lines]) for the small label's text below the asset id.

    Separate values rather than one sentence: each spec goes on a line of its own,
    so a shelf of drives reads down the capacities instead of finding each one at
    whatever point the name happened to stop wrapping. The list is empty for the
    types whose name already says what you want, and holds only what is recorded.
    """
    name = display_name(asset)
    wanted = () if is_computer else SMALL_SPECS.get(asset.get("type", ""), ())
    if not wanted:
        return name, []
    if spec_pairs is None:
        spec_pairs = parse_specs(asset.get("specs", ""))
    have = dict(spec_pairs)
    lines = []
    for group in wanted:
        said = [prefix + value for key, prefix in group
                if (value := (have.get(key) or "").strip())]
        if said:
            lines.append(" ".join(said))
    return name, lines


def part_lines(part, spec_pairs=None):
    lines = [f"Type: {type_label(part.get('type', ''))}"]
    for label, key in (("Manufacturer", "manufacturer"), ("Year", "year")):
        if part.get(key):
            lines.append(f"{label}: {part[key]}")
    if spec_pairs is None:
        spec_pairs = parse_specs(part.get("specs", ""))
    lines += [f"{k}: {v}" if k else v for k, v in spec_pairs]
    if part.get("computer_id"):
        lines.append(f"Installed in: {part['computer_id']}")
    if part.get("condition"):
        lines.append(f"Condition: {part['condition']}")
    return lines


# --- drawing ---------------------------------------------------------------

def _render_full(c, W, H, asset_id, title, lines, url, hfont, bfont):
    margin = 0.22 * inch
    qr_size = min(H - 2 * margin, 2.1 * inch)
    qr_x = W - margin - qr_size
    text_w = qr_x - margin - 0.10 * inch
    bottom = margin + 0.16 * inch
    c.setLineWidth(1)
    c.setStrokeColorRGB(0.65, 0.65, 0.65)
    c.roundRect(0.10 * inch, 0.10 * inch, W - 0.20 * inch, H - 0.20 * inch, 8,
                stroke=1, fill=0)
    c.setFillColorRGB(0, 0, 0)
    aid_size = _fit(c, asset_id, hfont, 24, 12, text_w)
    y = H - margin - aid_size + 4
    c.setFont(hfont, aid_size)
    c.drawString(margin, y, asset_id)
    c.setFont(hfont, 12)
    for line in _wrap(c, title, hfont, 12, text_w)[:2]:
        y -= 16
        c.drawString(margin, y, line)
    y -= 5
    for raw in lines:
        for i, line in enumerate(_wrap(c, "• " + raw, bfont, 9, text_w)[:2]):
            if y - 12 < bottom:
                break
            y -= 12
            c.setFont(bfont, 9)
            c.drawString(margin if i == 0 else margin + 8, y,
                         line if i == 0 else "  " + line)
        if y - 12 < bottom:
            break
    qr_y = (H - qr_size) / 2 + 0.10 * inch
    c.drawImage(_qr(url), qr_x, qr_y, width=qr_size, height=qr_size,
                preserveAspectRatio=True, mask="auto")
    c.setFont(bfont, 7.5)
    c.drawCentredString(qr_x + qr_size / 2, qr_y - 11, "scan for details")


def _small_body_lines(c, title, tags, bfont, tw, avail):
    """(size, lines) for a small label's body: the name wrapped, then each spec on a
    line of its own.

    The type size is chosen against the height actually available with those lines
    already counted, so a long name shrinks the type rather than pushing a spec off
    the label -- on a drive the specs are what is being looked for. The name always
    keeps at least one line, and where even the floor will not fit, it is the name
    that is clipped and the last spec that is dropped.
    """
    size = 6.5
    while True:
        room = max(1, int(avail // (size + 1.5)))
        keep = list(tags[:max(0, room - 1)])
        for_name = max(1, room - len(keep))
        lines = _wrap(c, title, bfont, size, tw)
        if len(lines) <= for_name or size <= 4.5:
            return size, [*lines[:for_name], *keep]
        size -= 0.5


def _render_small(c, W, H, asset_id, title, url, hfont, bfont, safe=0.0, tags=()):
    my = 1.2 * mm
    mx = my + safe * mm
    c.setFillColorRGB(0, 0, 0)
    qr = H - 2 * my
    c.drawImage(_qr(url), mx, my, width=qr, height=qr, preserveAspectRatio=True,
                mask="auto")
    tx = mx + qr + 1.5 * mm
    tw = W - tx - mx
    aid_size = _fit(c, asset_id, hfont, 11, 5, tw)
    y = H - my - aid_size
    c.setFont(hfont, aid_size)
    c.drawString(tx, y, asset_id)
    bsize, lines = _small_body_lines(c, title, tags, bfont, tw, y - my)
    for line in lines:
        if y - (bsize + 1.5) < my:
            break
        y -= bsize + 1.5
        c.setFont(bfont, bsize)
        c.drawString(tx, y, line)


def render_pdf(asset, parts, is_computer, small=False, form_factor="",
               spec_pairs=None) -> bytes:
    """Render one label PDF and return its bytes. `asset` is the computer/part
    row (dict); `parts` is the full parts list (used for a computer's build).
    `form_factor` and `spec_pairs` come from the typed spec tables when the caller
    has them, so the label does not re-parse the specs string."""
    hfont, bfont = _fonts()
    spec = SMALL if small else FULL
    title = display_name(asset)
    url = item_url(asset["asset_id"])
    buf = io.BytesIO()
    c = canvas.Canvas(buf, pagesize=rotated_page(spec))
    c.saveState()
    _apply_rotation(c, spec["w"], spec["h"], spec["rotate"])
    if small:
        name, tags = small_body(asset, is_computer, spec_pairs)
        _render_small(c, spec["w"], spec["h"], asset["asset_id"], name, url,
                      hfont, bfont, spec.get("safe_mm", 0), tags=tags)
    else:
        lines = (computer_lines(asset, parts, form_factor) if is_computer
                 else part_lines(asset, spec_pairs))
        _render_full(c, spec["w"], spec["h"], asset["asset_id"], title, lines,
                     url, hfont, bfont)
    c.restoreState()
    c.showPage()
    c.save()
    return buf.getvalue()
