"""Print-ready labels, rendered in the api so the GUI's "print label" action can
hand back a file. A focused port of the flat-file make_labels.py: same 6x4in full
label and 51x19mm small label, same QR encoding <base_url>/items/<asset_id>/ so
the codes match every label already printed.

What a label says, and where on it that goes, is here. How a mark is actually made
is `surfaces.py`, and there are two: a PDF page and a bitmap of a printer's own
dots (ADR-0024). The layout is written once and runs on either, so the label that
comes out of a thermal printer is the label somebody proofed as a PDF.

`qr_svg` is here too, so the code on an item's page and the code on its label are
made by the same rule.
"""

from __future__ import annotations

import io
import os
from collections.abc import Mapping, Sequence
from typing import NamedTuple, TypedDict, cast

from reportlab.lib.units import inch, mm
from reportlab.pdfgen import canvas

from .entry import display_name, parse_specs, type_label
from .machines import ISSUE_KEY, REGION_KEY, STYLE_KEY
from .projects import status_label
from . import barcode, settings, typefaces
from .surfaces import BODY, HEAD, LABEL, PdfSurface, RasterSurface, Surface, blank, code

# The four kinds of thing a label can be for. This was an `is_computer` boolean
# while there were two, and stopped being able to be the day a project wanted a
# sticker: "not a computer" had quietly meant "a part", and a two-valued flag
# cannot hold a third answer without one of its two starting to lie. A location is
# the fourth (ADR-0034): the label on a box, scanned to see what is in it.
COMPUTER, PART, PROJECT, LOCATION = "computer", "part", "project", "location"

# Which codes a label carries (MANUAL §13, "QR code, barcode, both or none"): each
# label's own choice, read when it is drawn. None is a label of words alone, for a
# shelf edge, and the words have the room the code would have had.
QR, BARCODE, BOTH, NONE = "qr", "code128", "both", "none"
CODES = (QR, BARCODE, BOTH, NONE)

# The two labels (MANUAL §13, "Two labels, each set up for its job"). These say which
# of the two, not what each is called: the owner names them, in free text, so a print
# job and a URL say `small` or `full` and mean the first and the second.
LABELS = ("small", "full")

# What "what's on it" offers, in the words the settings page uses. A location's label
# is its own shape and reads none of them (ADR-0037).
DETAILS: tuple[tuple[str, str], ...] = (
    ("tag", "Tag"),
    ("name", "Name"),
    ("make", "Make and model"),
    ("specs", "Specifications"),
    ("serial", "Serial number"),
    ("kept", "Where it's kept"),
)
# The word up the end has a tick of its own beside the list rather than a place in
# it: it is not a line of the label, so there is no order for it to be in.
WORD = ("word", "Word up the end")

# The two faces a label can be set in (MANUAL §13, "The type on a label"): the label
# face, or the interface face of the look the site wears.
LABEL_FACE, LOOK_FACE = "label", "look"


class Setup(NamedTuple):
    """One of the two labels as Settings → Labels has it: what it is called, the code
    it carries, the stock its PDF is drawn on, the details it prints in the order it
    prints them, whether the word runs up the end, and the face it is set in."""

    key: str
    name: str
    codes: str
    stock: str
    details: tuple[str, ...]
    word: bool
    face: str


def order_of(key: str) -> list[str]:
    """Every detail one label offers, in the order its list is in, ticked or not."""
    return [k for k, _ in settings.order(f"label_{key}_details") if k != WORD[0]]


def setup(key: str) -> Setup:
    """One of the two labels, read from the settings and checked on the way out: a
    value this version does not know is read as the label started out, rather than
    drawn as a guess somebody discovers by peeling it off something."""
    first = key == LABELS[0]
    ticks = settings.order(f"label_{key}_details")
    codes = settings.value(f"label_{key}_codes")
    stock = settings.value(f"label_{key}_stock")
    face = settings.value(f"label_{key}_type")
    return Setup(
        key=key,
        name=settings.value(f"label_{key}_name"),
        codes=codes if codes in CODES else QR,
        stock=stock if stock in MEDIA else (SMALL if first else FULL),
        details=tuple(k for k, on in ticks if on and k != WORD[0]),
        word=dict(ticks).get(WORD[0], True),
        face=face if face in (LABEL_FACE, LOOK_FACE) else LABEL_FACE,
    )


def face_of(label: Setup) -> str:
    """The face a label's words are set in: the label face, or the interface face of
    the look the site wears (MANUAL §13, "The type on a label")."""
    if label.face != LOOK_FACE:
        return LABEL
    return typefaces.interface_face(settings.preset(), settings.typeface())


# The three answers in a catalogue machine's line that are not a chip, and so get a
# line of their own on a label (see computer_lines).
_MACHINE_KEYS = (ISSUE_KEY, STYLE_KEY, REGION_KEY)

# A register row as a label reads it: the model's columns as a dict (common.to_dict),
# sometimes with the typed spec pairs attached under "spec_pairs". A row read column
# by column holds each value as widely as a column can, which is why the reads below
# have to say which of them are text.
type Row = Mapping[str, object]


def _txt(row: Row, key: str) -> str:
    """One of a row's values as the label prints it, blank where there is none."""
    value = row.get(key)
    return "" if value is None else str(value)


class SmallGeometry(NamedTuple):
    """A small label's measurements, in points: the margins, the code's size, and
    the column the words are set in."""

    mx: float
    my: float
    qr: float
    tx: float
    tw: float


class Media(TypedDict):
    """One label stock: what it measures, and what prints it.

    Those are two facts, and `small: bool` was one answer trying to be both -- it
    could say 51x19mm or 6x4in and nothing else, which is not enough to say which
    of two 50mm Niimbot labels is on the printer, or how many dots that printer
    puts in a millimetre (ADR-0024).

    `dots` is the printable width of the head this stock belongs to, where the head
    is narrower than the stock -- a Niimbot B1 takes a 50mm label on a 48mm head --
    and 0 where the printer reaches the whole of it. Keeping it here rather than in
    each caller is what stops a label being laid out across 2mm of tape no printer
    can reach.
    """

    what: str
    # The same stock in as few words as will do, for a menu of printers: a list of
    # them is read to find one, and "dellski 51×19 mm" is what finding one needs.
    # `what` is the sentence, for the one place that is describing a stock rather
    # than naming it.
    short: str
    w_mm: float
    h_mm: float
    qr: str
    # The quarter-turn the PDF page is printed at: a 6x4 label goes through a
    # printer end-first on a 4x6 sheet. A fact about feeding paper, and so about
    # the PDF alone -- a bitmap is the label the way it is read, and has nothing to
    # turn.
    rotate: int
    # How far in from the ends of the tape the body keeps, where the medium has ends.
    safe_mm: float
    dpi: int
    dots: int


# The stocks the register knows. A name rather than a size, because a size does not
# say what prints it; and a closed list rather than free measurements, because a
# guessed stock is discovered by peeling a label off something.
MEDIA: dict[str, Media] = {
    "full-6x4": {
        "what": "6×4 inch sheet",
        "short": "6×4 inch",
        "w_mm": 152.4,
        "h_mm": 101.6,
        "qr": "M",
        "rotate": 90,
        "safe_mm": 0,
        "dpi": 300,
        "dots": 0,
    },
    "dymo-11355": {
        "what": "51×19 mm multipurpose tape (DYMO LabelWriter)",
        "short": "51×19 mm",
        "w_mm": 51,
        "h_mm": 19,
        "qr": "M",
        "rotate": 90,
        "safe_mm": 3,
        "dpi": 300,
        "dots": 0,
    },
    "niimbot-50x30": {
        "what": "50×30 mm label (Niimbot B1, B21, B18)",
        "short": "50×30 mm",
        "w_mm": 50,
        "h_mm": 30,
        "qr": "M",
        "rotate": 0,
        "safe_mm": 1.5,
        "dpi": 203,
        "dots": 384,
    },
    "niimbot-40x30": {
        "what": "40×30 mm label (Niimbot B1, B21, B18)",
        "short": "40×30 mm",
        "w_mm": 40,
        "h_mm": 30,
        "qr": "M",
        "rotate": 0,
        "safe_mm": 1.5,
        "dpi": 203,
        "dots": 0,
    },
}

# What `small=True` and `small=False` have always meant. Every caller and every URL
# printed against keeps working by being these two names, and they are where the two
# labels' PDFs start out.
FULL, SMALL = "full-6x4", "dymo-11355"

# The least a stock has to measure both ways to be laid out as a full label: the
# full layout's own measures -- a code of up to 2.1in beside a column of words, in a
# frame -- want about four inches of it. The 6x4 sheet has that and nothing else the
# register knows comes near.
FULL_ROOM_MM = 100.0


def full_layout(media: Media) -> bool:
    """Whether a label on this stock is laid out as a full one. The stock decides the
    shape, whichever of the two labels is drawn on it (ADR-0037): the full label sent
    to a Niimbot comes out the size of the roll, not a 6x4 layout crushed onto 50mm."""
    return min(media["w_mm"], media["h_mm"]) >= FULL_ROOM_MM


def printable_mm(media: Media) -> float:
    """How much of the stock's width the head actually reaches."""
    if not media["dots"]:
        return media["w_mm"]
    return media["dots"] / media["dpi"] * 25.4


def layout_size(media: Media) -> tuple[float, float]:
    """The label as the layout sees it, in points: as wide as can be printed, and
    as tall as the stock."""
    return (printable_mm(media) * mm, media["h_mm"] * mm)


def size_dots(media: Media, dpi: int = 0) -> tuple[int, int]:
    """The bitmap's size for this stock, at the printer's resolution or another.

    `dots` is a count at the stock's own resolution, so asking for a different one
    scales it: the head does not grow, but the dots it is described in change.
    """
    dpi = dpi or media["dpi"]
    across = (
        round(media["dots"] * dpi / media["dpi"])
        if media["dots"]
        else round(media["w_mm"] * dpi / 25.4)
    )
    return (across, round(media["h_mm"] * dpi / 25.4))


BUILD_ROWS = [
    ("cpu", "CPU"),
    ("ram", "Memory"),
    ("video", "Video"),
    ("sound", "Sound"),
    ("storage", "Storage"),
    ("network", "Network"),
]
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
#
# A screen is the same sort of object: what identifies one across a room is how big
# it is and what makes the picture, joined on one line because "a 14-inch Trinitron"
# is one thing said and not two. The resolution follows, then what it will run at,
# and the interface last where the squeeze takes it -- a cable is the easiest thing
# to establish by looking at the back.
#
# The resolution and the refresh had a line between them, which was the joining rule
# applied where it does not hold: "320x200 (CGA)" and "50 Hz, 60 Hz" are two things
# said, not one, and together they are wider than the label. Joined they wrapped
# mid-figure -- "320x200 (CGA) 50" and then "Hz, 60 Hz" -- which reads as a fault in
# the label rather than as two facts.
SMALL_SPECS = {
    "storage": (
        (("Capacity", ""),),
        (("CHS", "CHS "),),
        (("Form factor", ""), ("Size", "")),
        (("Media", ""), ("Speed", "")),
    ),
    "display": (
        (("Screen size", ""), ("Panel", ""), ("Type", "")),
        (("Resolution", ""),),
        (("Refresh", ""),),
        (("Interface", ""),),
    ),
}


def _pairs_of(part: Row) -> list[tuple[str, str]]:
    """A part's (key, value) spec pairs: the ones the caller read from the typed
    tables if it attached them, else parsed from the rendered specs string."""
    pairs = part.get("spec_pairs")
    if pairs is None:
        return parse_specs(_txt(part, "specs"))
    # The caller attached these itself, out of specdb.pairs. A row read column by
    # column is a dict of values as wide as a column, and cannot say that one of
    # them is that list.
    return cast("list[tuple[str, str]]", pairs)


def base_url() -> str:
    """Where the QR codes point. From the environment, because it is a fact about
    this installation and nothing else -- a label is printed once and stuck on a
    machine for years, so a default belonging to some other site would be a wrong
    address that cannot be corrected without reprinting. Falls back to the address
    the app listens on, which is at least this installation."""
    return (os.getenv("RHDB_BASE_URL") or "http://localhost:8000").rstrip("/")


def item_url(asset_id: str) -> str:
    return f"{base_url()}/items/{asset_id}/"


def qr_svg(data: str, error: str = "M") -> str:
    """The same code as a label's, as SVG markup to drop straight into a page.

    Black on an opaque white ground rather than the page's own colours: half this
    site is read in the dark theme, and a pale code on a dark ground is one a phone
    camera has to be argued with. No width or height either -- the viewBox keeps it
    square and the stylesheet says how big.
    """
    buf = io.BytesIO()
    code(data, error).save(
        buf,
        kind="svg",
        scale=1,
        border=2,
        dark="#000",
        light="#fff",
        omitsize=True,
        xmldecl=False,
        nl=False,
        svgclass=None,
        lineclass=None,
    )
    return buf.getvalue().decode("utf-8")


def _wrap(s: Surface, text: str, font: str, size: float, max_w: float) -> list[str]:
    words, lines, cur = text.split(), [], ""
    for w in words:
        trial = (cur + " " + w).strip()
        if not cur or s.width_of(trial, font, size) <= max_w:
            cur = trial
        else:
            lines.append(cur)
            cur = w
    if cur:
        lines.append(cur)
    return lines or [""]


def _fit(s: Surface, text: str, font: str, start: float, min_size: float, max_w: float) -> float:
    size = start
    while size > min_size and s.width_of(text, font, size) > max_w:
        size -= 1
    return size


def _fit_lines(
    s: Surface,
    text: str,
    font: str,
    start: float,
    min_size: float,
    width: float,
    max_lines: int,
) -> float:
    size = start
    while size > min_size and len(_wrap(s, text, font, size, width)) > max_lines:
        size -= 0.5
    return size


def rotated_page(media: Media) -> tuple[float, float]:
    w, h = layout_size(media)
    return (h, w) if media["rotate"] in (90, 270) else (w, h)


def _apply_rotation(c: canvas.Canvas, W: float, H: float, rot: int) -> None:
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


def _catalogue_lines(asset: Row) -> list[str]:
    """An asset's catalogue identity as label lines, from its rendered variant.

    On a sealed machine the board issue and the ULA are what a label is for, since
    nothing inside it has a tag of its own to carry them; on a board lifted out of
    one they are what the board itself has to say, and the label is the only place a
    bare board in a box says which revision it is. The model, the board and the two
    answers that tell two machines apart get a line each; the chips share one line,
    each named by its socket, because a socket is often called what the label already
    calls something else -- a machine has a CPU field and a CPU socket, saying
    different true things -- and two lines both headed CPU read as a contradiction
    rather than as two facts."""
    lines, chips = [], []
    for key, value in parse_specs(_txt(asset, "variant")):
        if not key:
            lines.append(f"Machine: {value}")
        elif key in _MACHINE_KEYS:
            lines.append(f"{key}: {value}")
        else:
            chips.append(f"{key} {value}")
    if chips:
        lines.append("Chips: " + ", ".join(chips))
    return lines


def computer_lines(comp: Row, parts: Sequence[Row], form_factor: str = "") -> list[str]:
    """Label body for a machine. `form_factor` comes from the linked board's typed
    column (see main.gui_computer_label); it falls back to the rendered specs
    string only so a caller that has not looked it up still gets a label."""
    kids = sorted(
        (p for p in parts if p.get("computer_id") == comp["asset_id"]),
        key=lambda p: _txt(p, "type"),
    )
    # No "Type: Computer" first line any more: the word now runs up the end of the
    # label, and the bullet was saying it a second time in the most valuable line on
    # the label. A part keeps its Type line, which says what sort of part -- Storage,
    # Video -- and so completes the word at the end rather than repeating it.
    lines = []
    for p in kids:
        if form_factor:
            break
        if p.get("type") == "motherboard":
            form_factor = dict(_pairs_of(p)).get("Form factor", "")
    if comp.get("manufacturer"):
        lines.append(f"Manufacturer: {comp['manufacturer']}")
    if comp.get("year"):
        lines.append(f"Year: {comp['year']}")
    lines += _catalogue_lines(comp)
    if form_factor:
        lines.append(f"Form factor: {form_factor}")
    for label, key in (
        ("CPU", "cpu"),
        ("RAM", "installed_ram"),
        ("Drives", "drives"),
        ("Chassis", "chassis"),
        ("OS", "os"),
    ):
        if comp.get(key):
            lines.append(f"{label}: {comp[key]}")
    by_type: dict[str, list[Row]] = {}
    for p in kids:
        by_type.setdefault(_txt(p, "type"), []).append(p)
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


def small_body(
    asset: Row, kind: str, spec_pairs: list[tuple[str, str]] | None = None
) -> tuple[str, list[str]]:
    """(name, [spec lines]) for the small label's text below the asset id.

    Separate values rather than one sentence: each spec goes on a line of its own,
    so a shelf of drives reads down the capacities instead of finding each one at
    whatever point the name happened to stop wrapping. The list is empty for the
    types whose name already says what you want, and holds only what is recorded.

    A project's one line is its state. A sticker on a parcel is read months later
    with the parcel in your hand, and "in progress" against "done" is the whole of
    what you want to know before opening it.
    """
    name = display_name(asset)
    if kind == PROJECT:
        return name, [status_label(_txt(asset, "status"))]
    wanted = () if kind == COMPUTER else SMALL_SPECS.get(_txt(asset, "type"), ())
    if not wanted:
        return name, []
    if spec_pairs is None:
        spec_pairs = parse_specs(_txt(asset, "specs"))
    have = dict(spec_pairs)
    lines = []
    for group in wanted:
        said = [prefix + value for key, prefix in group if (value := (have.get(key) or "").strip())]
        if said:
            lines.append(" ".join(said))
    return name, lines


def part_lines(part: Row, spec_pairs: list[tuple[str, str]] | None = None) -> list[str]:
    lines = [f"Type: {type_label(_txt(part, 'type'))}"]
    for label, key in (("Manufacturer", "manufacturer"), ("Year", "year")):
        if part.get(key):
            lines.append(f"{label}: {part[key]}")
    # Before the specs, because on a board out of a sealed machine the model and the
    # revision are what the label is being read for, and the chipset row underneath
    # is likely to be empty.
    lines += _catalogue_lines(part)
    if spec_pairs is None:
        spec_pairs = parse_specs(_txt(part, "specs"))
    lines += [f"{k}: {v}" if k else v for k, v in spec_pairs]
    if part.get("computer_id"):
        lines.append(f"Installed in: {part['computer_id']}")
    if part.get("condition"):
        lines.append(f"Condition: {part['condition']}")
    return lines


def project_lines(project: Row) -> list[str]:
    """The full label's body for a project.

    Its own columns and nothing counted: how many jobs are left and how many things
    are still in the post are true this afternoon and false next week, and a label
    is printed once and then lives on a box for a year. What is put on it is what
    will still be true when it is read -- what the project is called, what state it
    was in, and the dates -- and the QR code is there for everything that moves."""
    lines = [f"Status: {status_label(_txt(project, 'status'))}"]
    for label, key in (
        ("Started", "started_at"),
        ("Wanted by", "target_date"),
        ("Finished", "finished_at"),
    ):
        if project.get(key):
            lines.append(f"{label}: {project[key]}")
    if project.get("summary"):
        lines.append(_txt(project, "summary"))
    return lines


def _make(asset: Row) -> list[str]:
    """Its make and model, for a thing with a name of its own to say them beside. A
    thing without one is already called by its make and model, and saying it twice
    would be the label repeating itself in the room it has least of."""
    made = " ".join(x for x in (_txt(asset, "manufacturer"), _txt(asset, "model")) if x)
    named = _txt(asset, "name").strip()
    return [made.strip()] if made.strip() and named and made.strip() != named else []


def _kept(asset: Row) -> str:
    """Where it is kept, as the path a location's label carries over its name."""
    return _txt(asset, "kept").upper()


def small_details(
    asset: Row, kind: str, label: Setup, spec_pairs: list[tuple[str, str]] | None = None
) -> list[str]:
    """A small label's lines: each of the label's details the thing has, in the
    label's order (MANUAL §13, "What's on it"). The first is the one printed largest.

    A detail the thing does not have is not there at all, rather than a blank line:
    a project has no serial number and is kept nowhere."""
    out: list[str] = []
    for detail in label.details:
        if detail == "tag":
            out.append(_txt(asset, "asset_id"))
        elif detail == "name":
            out.append(display_name(asset))
        elif detail == "make":
            out += _make(asset)
        elif detail == "specs":
            out += small_body(asset, kind, spec_pairs)[1]
        elif detail == "serial" and (serial := _txt(asset, "serial").strip()):
            out.append(f"S/N {serial}")
        elif detail == "kept" and (kept := _kept(asset)):
            out.append(kept)
    return [line for line in out if line.strip()]


# How a full label sets a line under its head: a name as a title, in bold, the way the
# name has always been set under the tag, and everything else listed under a bullet.
TITLE, LISTED = "title", "listed"


def full_details(
    asset: Row,
    kind: str,
    label: Setup,
    parts: Sequence[Row] = (),
    form_factor: str = "",
    spec_pairs: list[tuple[str, str]] | None = None,
) -> tuple[str, list[tuple[str, str]]]:
    """(head, body) for a full label: the first of the label's details the thing has,
    printed largest, then the rest in order, each a title or a listed line. A detail
    leading the label is set as itself; listed further down it says what it is."""
    entries: list[tuple[str, str, str]] = []
    for detail in label.details:
        if detail == "tag":
            tag = _txt(asset, "asset_id")
            entries.append((LISTED, tag, f"Tag: {tag}"))
        elif detail == "name":
            name = display_name(asset)
            entries.append((TITLE, name, name))
        elif detail == "make":
            entries += [(TITLE, made, made) for made in _make(asset)]
        elif detail == "specs":
            if kind == COMPUTER:
                lines = computer_lines(asset, parts, form_factor)
            elif kind == PROJECT:
                lines = project_lines(asset)
            else:
                lines = part_lines(asset, spec_pairs)
            entries += [(LISTED, line, line) for line in lines]
        elif detail == "serial" and (serial := _txt(asset, "serial").strip()):
            entries.append((LISTED, f"S/N {serial}", f"Serial number: {serial}"))
        elif detail == "kept" and (kept := _kept(asset)):
            entries.append((LISTED, kept, f"Kept in: {kept}"))
    entries = [e for e in entries if e[1].strip()]
    if not entries:
        return "", []
    return entries[0][1], [(style, listed) for style, _, listed in entries[1:]]


# --- drawing ---------------------------------------------------------------

# The word that says which of the three things a label is for, printed up one end
# of it. A tag on a shelf answers "which one is this?" and a code answers "tell me
# everything"; neither answers "what am I holding?", which is the question a
# stranger to the collection asks first and the question a box of mixed stickers
# raises every time. Up the end rather than in the body because it is not one of
# the facts -- it is what sort of thing the other facts are about -- and because
# the end of a label is the part of it still showing when the rest is face down.
#
# Black, like everything else on the label. It was grey, on the reasoning that a
# category is quieter than a fact -- which is true on a screen and false on a
# thermal printer, where there is no grey to print: the head is on or off, so grey
# comes out as a dither, and a dithered word at five and a half point is a smudge.
KIND_WORDS: dict[str | None, str] = {
    COMPUTER: "COMPUTER",
    PART: "PART",
    PROJECT: "PROJECT",
    LOCATION: "LOCATION",
}

# The most of a small label's width the QR code may take. A code that will not
# scan is worth nothing, so it gets as much as it can -- but a label is read by a
# person as well as by a phone, and a sticker on a parcel that says only "Seaga…"
# has failed at the half of the job the code cannot do.
#
# Settled by printing it. At 0.40 the code was small and there was white to the
# right of the words; at 0.52 the type shrank until "DK23DA-20F" clipped to
# "DK23DA-…", which is a part number nobody can look up.
QR_SHARE = 0.46

# And the words keep this much whatever that share works out to. A share alone is
# a rule about the label and not about what is written on it: the same 0.46 that
# suited a 50mm label left a 40mm one with ten millimetres for the words, which
# came out as "in progre…". A code is worth having as large as it can be, and not
# at the price of the line underneath it.
TEXT_MIN = 12 * mm

# The 51x19mm tape, which is the label every other small one is in proportion to.
TAPE_H = 19 * mm

# What the tag and the body are set at on that tape, which is what fits on it.
# Held as a size against a height rather than as two numbers, because a 50x30mm
# label set in the tape's type is a third of a label with nothing on it -- the
# words should grow with the room. Both are a ceiling and not the answer: the size
# used is the largest of them the width will take.
TAG_PT, BODY_PT = 11.0, 6.5

# The small label's own margins: the same at top and bottom on every stock, and the
# width of the strip the kind word stands in.
SMALL_MARGIN = 1.2 * mm
WORD_STRIP = 3.2 * mm


def small_text_column(W: float, H: float, safe: float, worded: bool = True) -> SmallGeometry:
    """Where a small label's code and words go, given the size of the label.

    Worked out here rather than inside the renderer because it is asked twice: once
    to draw the label, and once by the suite, which checks that what the label says
    fits in the room there is. That check used to re-derive these numbers from the
    same constants, which is a second copy of the arithmetic and free to drift from
    the first without either of them noticing.
    """
    my = SMALL_MARGIN
    mx = my + safe * mm
    # What the words cost before any of them are written: the gap after the code,
    # the margin at the far end, and the strip the kind word stands in.
    spent = 1.5 * mm + mx + ((WORD_STRIP + 1.0 * mm) if worded else 0.0)
    qr = min(H - 2 * my, W * QR_SHARE, W - mx - spent - TEXT_MIN)
    tx = mx + qr + 1.5 * mm
    tw = W - tx - mx
    if worded:
        tw -= WORD_STRIP + 1.0 * mm
    return SmallGeometry(mx=mx, my=my, qr=qr, tx=tx, tw=tw)


def _two_lines(
    s: Surface, text: str, start: float, floor: float, width: float
) -> tuple[float, list[str]]:
    """A head too long for one line: two lines of it, as large as two will hold and
    never below `floor`, with the second cut short where even two will not do.

    For a name put first (MANUAL §13, "What's on it"). The tag has always been short
    enough to shrink until it fits; a name shrunk the same way ends up no larger
    than the words under it, and the first detail is the one printed largest."""
    size = start
    while size > floor and len(_wrap(s, text, HEAD, size, width)) > 2:
        size -= 1
    size = max(size, floor)
    lines = _wrap(s, text, HEAD, size, width)
    if len(lines) > 2:
        lines = [lines[0], _clip(s, " ".join(lines[1:]), HEAD, size, width)]
    return size, lines


def _render_full(
    s: Surface,
    W: float,
    H: float,
    head: str,
    body: Sequence[tuple[str, str]],
    url: str,
    error: str = "M",
    kind: str | None = None,
    over: str = "",
    codes: str = "qr",
    tag: str = "",
    breaks: bool = False,
) -> None:
    """A full label. `head` is what is printed largest -- the first of the label's
    details, or a location's name -- and `over` a line of small type above it: the
    path a location's label carries, which says where the box was when the label
    was printed. `body` is the rest, in order, each a title or a listed line.
    `codes` is which codes it carries and `tag` what a barcode holds. `breaks` lets
    a head that is a name take two lines rather than shrink (see `_two_lines`): a
    location's label keeps the shape it has always had, and does not.

    A barcode alone stands where the QR code would; with both, it runs under the
    words, which stop above it; with none, the words have the width."""
    data = tag or head
    margin = 0.22 * inch
    qr_size = min(H - 2 * margin, 2.1 * inch)
    qr_x = W - margin - qr_size
    # The strip the word stands in, taken off the left of the text rather than out
    # of the QR: the code has a size below which a phone stops seeing it, and the
    # body has lines it can afford to wrap one word earlier.
    word = KIND_WORDS.get(kind, "")
    strip = 0.30 * inch if word else 0.0
    text_x = margin + strip
    text_w = qr_x - text_x - 0.10 * inch
    if codes == NONE:
        # Nothing stands at the right-hand end, so the words run to the margin there.
        text_w = W - margin - text_x
    bottom = margin + 0.16 * inch
    if codes == BOTH:
        # The bars have the band's whole height. The tag that stood under them said
        # again what the largest line on the label says already (MANUAL §13).
        band_h = 0.5 * inch + 10
        used = s.barcode_width(text_w, data)
        s.barcode(text_x, bottom, used, band_h, data)
        bottom += band_h + 8
    s.frame(0.10 * inch, 0.10 * inch, W - 0.20 * inch, H - 0.20 * inch, 8)
    if word:
        s.vertical(margin, margin + strip, H / 2, word, HEAD, 13)
    aid_size = _fit(s, head, HEAD, 24, 12, text_w)
    heads = [head]
    # A head that can break, and that one line would shrink to the size of the bold
    # title under it, takes two lines instead and stays the largest thing there.
    if breaks and " " in head.strip() and aid_size < 14:
        aid_size, heads = _two_lines(s, head, 24, 14, text_w)
    y = H - margin - aid_size + 4
    if over:
        s.text(text_x, H - margin - 6, _tail(s, over, 9, text_w), BODY, 9)
        y -= 12
    for i, line in enumerate(heads):
        if i:
            y -= aid_size + 2
        s.text(text_x, y, _clip(s, line, HEAD, aid_size, text_w), HEAD, aid_size)
    # A title under the line before it, and a gap before the first of a run of
    # listed lines -- the shape the full label has always had, tag, name, list. Room
    # runs out from the bottom: the last of the label's details are the ones it loses.
    last = ""
    for style, raw in body:
        if style == TITLE:
            if y - 16 < bottom:
                break
            for line in _wrap(s, raw, HEAD, 12, text_w)[:2]:
                y -= 16
                s.text(text_x, y, line, HEAD, 12)
        else:
            if last != LISTED:
                y -= 5
            for i, line in enumerate(_wrap(s, "• " + raw, BODY, 9, text_w)[:2]):
                if y - 12 < bottom:
                    break
                y -= 12
                s.text(
                    text_x if i == 0 else text_x + 8, y, line if i == 0 else "  " + line, BODY, 9
                )
            if y - 12 < bottom:
                break
        last = style
    if codes == NONE:
        return
    if codes == BARCODE:
        bars_h = 0.9 * inch
        used = s.barcode_width(qr_size, data)
        bars_x = qr_x + (qr_size - used) / 2
        s.barcode(bars_x, (H - bars_h) / 2, used, bars_h, data)
        return
    qr_y = (H - qr_size) / 2 + 0.10 * inch
    s.qr(qr_x, qr_y, qr_size, url, error)
    s.text_centred(qr_x + qr_size / 2, qr_y - 11, "scan for details", BODY, 7.5)


def _tail(s: Surface, path: str, size: float, max_w: float) -> str:
    """A location's path in the room there is, losing its far end first.

    The near end is the useful one -- "SHELF 2" says where the box is, "WORKSHOP"
    only which building -- so a path too long for the label drops whole steps off
    the front, saying so, before a step is cut in the middle."""
    if s.width_of(path, BODY, size) <= max_w:
        return path
    steps = path.split(" / ")
    while len(steps) > 1:
        steps = steps[1:]
        shorter = "… / " + " / ".join(steps)
        if s.width_of(shorter, BODY, size) <= max_w:
            return shorter
    return _clip(s, steps[0], BODY, size, max_w)


def _clip(s: Surface, text: str, font: str, size: float, max_w: float) -> str:
    """`text` cut down until it fits, with an ellipsis to say it was.

    The last resort, for a run with no space in it to break at -- a resolution, a
    part number. Losing the end of a spec is bad; drawing it off the side of the
    label is worse, because there it is lost with nothing to say so, and on the way
    out it crosses whatever else is printed there."""
    if s.width_of(text, font, size) <= max_w:
        return text
    while text and s.width_of(text + "…", font, size) > max_w:
        text = text[:-1]
    return (text.rstrip() + "…") if text.strip() else ""


def _small_body_lines(
    s: Surface, title: str, tags: Sequence[str], tw: float, avail: float, start: float = BODY_PT
) -> tuple[float, list[str]]:
    """(size, lines) for a small label's body: the name, then the specs, each
    wrapped to the width there actually is.

    The type size is chosen against the height available with every line counted,
    so a long name shrinks the type rather than pushing a spec off the label -- on a
    drive the specs are what is being looked for. The name always keeps at least one
    line, and where even the floor will not fit, it is the name that is clipped and
    the last spec that is dropped.

    The specs are wrapped and not taken on trust, which they used to be. Only the
    name was ever measured, on the assumption that a spec line is short -- true of
    "3.5\" 1.44MB" and false of a monitor's "320x200 (CGA) 50 Hz, 60 Hz", which is
    wider than the label. An unmeasured line does not stop at the edge: it is drawn
    straight past it, through whatever else is printed on the way, and off into the
    part of the page the printer will never reach.
    """
    # The height says how big the type may be; the width says how big it can
    # actually be. A 40x30mm label is as tall as a 50x30mm one and a third
    # narrower, and type sized by the height alone put "PC1512" in a column that
    # could not hold it -- where the only answer left is the clip, so it came out
    # as "PC15…" on a label with room to spare. So the start comes down until the
    # longest run that cannot be broken fits, and never below the tape's own size:
    # going lower than that is the loop's job, and it has the whole label in view.
    longest = max((w for line in (title, *tags) for w in line.split()), key=len, default="")
    if longest:
        # Down to the floor, not down to the tape's size. Stopping at the tape's
        # size meant a narrow label with big type had nowhere left to go but the
        # clip, and "in progre…" is worse than the same words a point smaller --
        # the clip is for a run that cannot be made to fit at any size, not for one
        # that could have been if anybody had tried.
        start = _fit(s, longest, BODY, start, 4.5, tw)
    size = start
    while True:
        room = max(1, int(avail // (size + 1.5)))
        spec_lines = [ln for t in tags for ln in _wrap(s, t, BODY, size, tw)]
        keep = spec_lines[: max(0, room - 1)]
        for_name = max(1, room - len(keep))
        lines = _wrap(s, title, BODY, size, tw)
        if len(lines) <= for_name or size <= 4.5:
            out = [*lines[:for_name], *keep]
            # At the floor a single unbreakable run can still be too wide, and this
            # is the only place left to deal with it.
            return size, [_clip(s, x, BODY, size, tw) for x in out]
        size -= 0.5


# The barcode's band on a small label: a share of the height, with a floor below
# which a scanner's line misses the bars. The bars have all of it. Nothing is
# printed under them (MANUAL §13): the tag is already the largest line on an item's
# label and the line under the name on a location's, and the seven characters again
# under the bars were room the bars could use.
BAR_SHARE, BAR_MIN = 0.36, 4.5 * mm

# A QR code smaller than this is one a phone has to be argued with. With both codes
# on a small label the barcode goes under the words beside the code while the code
# can keep this much; where it cannot, the barcode runs the width of the label under
# everything instead, with the code above it. A label too short even for that -- the
# 51x19mm tape -- carries the barcode alone, which was the owner's answer to which of
# the two that tape should keep.
QR_MIN = 12 * mm


def _bars_of(data: str) -> float:
    """How much of a barcode's width is bars, the white either side being the rest."""
    whole = barcode.width(data)
    return (whole - 2 * barcode.QUIET) / whole


def _render_small(
    s: Surface,
    W: float,
    H: float,
    asset_id: str,
    title: str,
    url: str,
    safe: float = 0.0,
    error: str = "M",
    tags: Sequence[str] = (),
    kind: str | None = None,
    over: str = "",
    codes: str = "qr",
    tag: str = "",
    breaks: bool = False,
) -> None:
    # `asset_id` is the line printed largest and `over` a line of small type above
    # it, as on the full label: a location's label is its name, with its path over.
    # `tag` is what a barcode holds, which is the asset tag however the label is
    # headed; `codes` which codes the label carries (MANUAL §13); and `breaks` lets
    # a head that is a name take two lines rather than shrink, which a location's
    # label, keeping the shape it has always had, does not.
    #
    # The code is as tall as the label allows, but never so wide that the words
    # have nowhere to go. On a 51x19mm tape the height is what binds and this
    # changes nothing; on a 50x30mm Niimbot label it is not, and a code as tall as
    # that label takes more than half its width -- which came out as "Seagate
    # ST-225" clipped to "Seaga…" on a label two thirds empty.
    #
    # The strip the kind word stands in is taken out of the text column, so a long
    # name wraps a word sooner. The alternative was shrinking the code, and one
    # that will not scan is worth less than a name that takes an extra line.
    data = tag or asset_id
    word = KIND_WORDS.get(kind, "")
    mx, my, qr, tx, tw = small_text_column(W, H, safe, bool(word))
    grow = H / TAPE_H
    bars = max(BAR_MIN, (H - 2 * my) * BAR_SHARE) if codes in (BARCODE, BOTH) else 0.0
    band = bars + 1.0 if bars else 0.0
    strip_w = (WORD_STRIP + 1.0 * mm) if word else 0.0
    across = False
    if codes == BOTH:
        short = s.barcode_min(data) - tw
        above = H - 2 * my - band - 1.0 * mm
        if short > 0 and qr - short >= QR_MIN:
            # Under the words beside the code, the code giving up what the bars need.
            qr -= short
            tx -= short
            tw += short
        elif short > 0 and above >= QR_MIN:
            # Or across the label under everything, with the code above it.
            across = True
            qr = min(qr, above)
            tx = mx + qr + 1.5 * mm
            tw = W - tx - mx - strip_w
        elif short > 0:
            # Or, on a label too short for both, the barcode alone.
            codes = BARCODE
    # A barcode on its own runs the width of the label, under the words and the kind
    # word both, because width is what bars are made of: on a 40mm label at 203 dpi
    # the text column alone gives each bar one dot, which is a barcode in name only.
    if codes == BARCODE:
        across = True
        tw += tx - mx
        tx = mx
        qr = 0.0
    # And with no code at all, the words have the room the code would have had.
    if codes == NONE:
        tw += tx - mx
        tx = mx
        qr = 0.0
    if qr:
        # What the code will not use, the words get. A code is drawn at a whole
        # number of dots to the square, so a box sized to the nearest anything leaves
        # up to a square's worth per square unused -- which on a 50x30mm label was
        # four millimetres of white around a code that looked as though it had been
        # given room and not taken it. Printing that as a margin is the one use for
        # it that helps nobody.
        drawn = s.qr_size(qr, url, error)
        tx -= qr - drawn
        tw += qr - drawn
        qr = drawn
        # Centred in what height there is: on a squarer label a code sitting on the
        # bottom margin leaves a hole above it that reads as a mistake rather than
        # as a margin. On a tape there is no spare height and this is exactly that
        # margin. Above the bars, when they run across under it.
        low = my + (band if across else 0.0)
        s.qr(mx, low + (H - my - low - qr) / 2, qr, url, error)
    if bars:
        if across:
            # The white a scanner needs either side of the bars may stand in the
            # allowance kept at the tape's ends, since it prints nothing, and only the
            # bars keep inside it: on the 51x19mm tape, a fourth dot to every bar.
            used = s.barcode_width(W - 2 * my, data)
            if used * _bars_of(data) > W - 2 * mx:
                used = s.barcode_width(W - 2 * mx, data)
            left = (W - used) / 2
        else:
            used = s.barcode_width(tw, data)
            left = tx + (tw - used) / 2
        s.barcode(left, my, used, bars, data)
    if word:
        strip = WORD_STRIP
        # A millimetre further in than the text stops. `safe_mm` is the allowance
        # the body keeps from the ends of the tape, and it is enough for a line of
        # words that can afford to lose a hair off a descender; a single word set
        # across the tape cannot, since half a letter missing makes the word
        # unreadable rather than merely tight. So this keeps its own margin, wider.
        # Centred in the height above the bars when they run under it.
        edge = mx + 1.0 * mm
        middle = (H + (band if across else 0.0)) / 2
        s.vertical(W - edge - strip, W - edge, middle, word, HEAD, 5.0)
    # The words stand above the bars, wherever the bars are.
    floor = my + band
    aid_size = _fit(s, asset_id, HEAD, TAG_PT * grow, 5, tw)
    heads = [asset_id]
    # A head that can break, and that one line would shrink to the size of the words
    # under it, takes two lines instead and stays the largest thing on the label.
    least = BODY_PT * grow + 1.0
    if breaks and " " in asset_id.strip() and aid_size < least:
        aid_size, heads = _two_lines(s, asset_id, TAG_PT * grow, least, tw)
    head_h = aid_size * len(heads) + 1.0 * (len(heads) - 1)
    top = H - my
    over_size = BODY_PT * grow * 0.85 if over else 0.0
    above = over_size + 1.0 if over else 0.0
    if title or tags:
        bsize, lines = _small_body_lines(
            s, title, tags, tw, top - above - head_h - floor, BODY_PT * grow
        )
    else:
        bsize, lines = BODY_PT * grow, []
    # Centred down the label rather than hung from the top. What is written is as
    # tall as it is; where the label is taller than that, the difference is a margin
    # and belongs at both ends. Hung from the top it reads as a label somebody
    # started and left, which is what a 50x30mm one looked like.
    written = above + head_h + len(lines) * (bsize + 1.5)
    top -= max(0.0, (H - my - floor - written) / 2)
    if over:
        s.text(tx, top - over_size, _tail(s, over, over_size, tw), BODY, over_size)
        top -= above
    y = top
    for i, line in enumerate(heads):
        y -= aid_size + (1.0 if i else 0.0)
        s.text(tx, y, _clip(s, line, HEAD, aid_size, tw), HEAD, aid_size)
    for line in lines:
        if y - (bsize + 1.5) < floor:
            break
        y -= bsize + 1.5
        s.text(tx, y, line, BODY, bsize)


def _draw(
    surface: Surface,
    media: Media,
    asset: Row,
    parts: Sequence[Row],
    kind: str,
    small: bool,
    form_factor: str = "",
    spec_pairs: list[tuple[str, str]] | None = None,
    codes: str | None = None,
    label: Setup | None = None,
) -> None:
    """One label, on whichever surface it was given.

    `small` says which of the two labels it is, the first or the second, and the
    stock decides its shape (ADR-0037). `label` is that label's settings where the
    caller has already read them, and `codes` overrides its codes.

    The only thing either renderer does that the other does not is get the surface
    ready -- a page to draw on, or a bitmap of the right number of dots. What goes
    on it is decided once, here."""
    label = label or setup(LABELS[0] if small else LABELS[1])
    if codes:
        label = label._replace(codes=codes)
    W, H = layout_size(media)
    _draw_at(
        surface,
        W,
        H,
        media["safe_mm"],
        media["qr"],
        asset,
        parts,
        kind,
        label,
        full_layout(media),
        form_factor,
        spec_pairs,
    )


def _draw_at(
    surface: Surface,
    W: float,
    H: float,
    safe: float,
    error: str,
    asset: Row,
    parts: Sequence[Row],
    kind: str,
    label: Setup,
    full: bool,
    form_factor: str = "",
    spec_pairs: list[tuple[str, str]] | None = None,
) -> None:
    """One label at a size, rather than on a stock: what a sheet of them draws
    into each of its cells, and what `_draw` draws onto a stock. `full` is whether
    it is laid out as a full label, which the stock decides."""
    codes = label.codes
    asset_id = _txt(asset, "asset_id")
    url = item_url(asset_id)
    if kind == LOCATION:
        # The name largest, the path over it, and the tag under: what is on the
        # shelf, where the shelf was when this was printed, and what to type. Its own
        # shape whatever the label's list says (MANUAL §13); its code is the label's.
        name, path = _txt(asset, "name") or asset_id, _txt(asset, "path").upper()
        if not full:
            _render_small(
                surface,
                W,
                H,
                name,
                asset_id,
                url,
                safe,
                error,
                kind=kind,
                over=path,
                codes=codes,
                tag=asset_id,
            )
            return
        lines = [x for x in (_txt(asset, "kind"), _txt(asset, "notes")) if x]
        _render_full(
            surface,
            W,
            H,
            name,
            [(TITLE, asset_id), *((LISTED, line) for line in lines)],
            url,
            error,
            kind=kind,
            over=path,
            codes=codes,
            tag=asset_id,
        )
        return
    # The word up the end has a tick of its own (MANUAL §13, "What's on it").
    worded = kind if label.word else None
    if not full:
        said = small_details(asset, kind, label, spec_pairs)
        _render_small(
            surface,
            W,
            H,
            said[0] if said else "",
            said[1] if len(said) > 1 else "",
            url,
            safe,
            error,
            tags=said[2:],
            kind=worded,
            codes=codes,
            tag=asset_id,
            breaks=True,
        )
        return
    head, body = full_details(asset, kind, label, parts, form_factor, spec_pairs)
    _render_full(
        surface, W, H, head, body, url, error, kind=worded, codes=codes, tag=asset_id, breaks=True
    )


def render_pdf(
    asset: Row,
    parts: Sequence[Row],
    kind: str,
    small: bool = False,
    media: Media | None = None,
    form_factor: str = "",
    spec_pairs: list[tuple[str, str]] | None = None,
) -> bytes:
    """Render one label PDF and return its bytes. `asset` is the computer, part or
    project row (dict) and `kind` says which; `parts` is the full parts list (used
    for a computer's build). `form_factor` and `spec_pairs` come from the typed
    spec tables when the caller has them, so the label does not re-parse the specs
    string.

    A project's label is made here beside the other two rather than somewhere of
    its own, because the whole of what a label is -- an asset id, a name, and a QR
    code back to /items/<id> -- is true of a project exactly as it is of a machine.
    What differs is the few lines of body text, which is what `kind` picks.

    `small` says which of the two labels it is. Its PDF is drawn on the label's own
    stock, unless the caller names one."""
    label = setup(LABELS[0] if small else LABELS[1])
    spec = media or MEDIA[label.stock]
    buf = io.BytesIO()
    c = canvas.Canvas(buf, pagesize=rotated_page(spec))
    c.saveState()
    _apply_rotation(c, *layout_size(spec), spec["rotate"])
    surface = PdfSurface(c, face_of(label), spec["dpi"])
    _draw(surface, spec, asset, parts, kind, small, form_factor, spec_pairs, label=label)
    c.restoreState()
    c.showPage()
    c.save()
    return buf.getvalue()


def render_png(
    asset: Row,
    parts: Sequence[Row],
    kind: str,
    media: Media,
    dpi: int = 0,
    small: bool = True,
    form_factor: str = "",
    spec_pairs: list[tuple[str, str]] | None = None,
) -> bytes:
    """The same label as a bitmap of the printer's own dots, one bit deep.

    No page rotation: a PDF is turned because a 6x4 label is fed into a printer
    end-first on a 4x6 sheet, and a bitmap is not fed anywhere -- it is the label
    as it will be read, and the printer is the thing that knows which way the tape
    goes through it.

    The default is the first label, because this exists for the printers that take a
    bitmap and every one of those is a small-label printer -- but a 6x4 stock
    rasterises the same way, for a print server that would rather be handed dots
    than a page. Either label is drawn on the stock it is given: the printer's.
    """
    label = setup(LABELS[0] if small else LABELS[1])
    image = blank(*size_dots(media, dpi))
    surface = RasterSurface(image, dpi or media["dpi"], face_of(label))
    _draw(surface, media, asset, parts, kind, small, form_factor, spec_pairs, label=label)
    buf = io.BytesIO()
    image.save(buf, format="PNG", optimize=True)
    return buf.getvalue()


# A sheet of labels: A4, three across and seven down, at 63.5 x 38.1 mm -- the size of
# the commonest stock of sheet labels -- with the margins and the pitch that stock is
# cut to (MANUAL §13, "A location has one too").
SHEET_W, SHEET_H = 210 * mm, 297 * mm
SHEET_COLS, SHEET_ROWS = 3, 7
CELL_W, CELL_H = 63.5 * mm, 38.1 * mm
SHEET_LEFT, SHEET_TOP = 7.21 * mm, 15.15 * mm
PITCH_X, PITCH_Y = 66.04 * mm, 38.1 * mm


def render_many(rows: Sequence[tuple[Row, str]], sheet: bool = False) -> bytes:
    """Many of the first label in one PDF: one to a page on its stock, for a label
    printer, or laid out on A4 sheets for a printer with a tray, each set up as the
    first label is. `rows` are (row, kind) as `render_pdf` takes them one at a time."""
    buf = io.BytesIO()
    label = setup(LABELS[0])
    face = face_of(label)
    if sheet:
        c = canvas.Canvas(buf, pagesize=(SHEET_W, SHEET_H))
        per = SHEET_COLS * SHEET_ROWS
        for n, (row, kind) in enumerate(rows):
            if n and n % per == 0:
                c.showPage()
            at = n % per
            x = SHEET_LEFT + (at % SHEET_COLS) * PITCH_X
            y = SHEET_H - SHEET_TOP - (at // SHEET_COLS + 1) * PITCH_Y
            c.saveState()
            c.translate(x, y)
            # An office printer's, whatever it is: 600 and 1200 dpi both lay their dots
            # on a 300 dpi grid, so a bar of whole 300 dpi dots is whole in theirs too.
            sheet_surface = PdfSurface(c, face, 300)
            _draw_at(sheet_surface, CELL_W, CELL_H, 1.5, "M", row, [], kind, label, False)
            c.restoreState()
        c.showPage()
    else:
        spec = MEDIA[label.stock]
        c = canvas.Canvas(buf, pagesize=rotated_page(spec))
        for row, kind in rows:
            c.saveState()
            _apply_rotation(c, *layout_size(spec), spec["rotate"])
            _draw(PdfSurface(c, face, spec["dpi"]), spec, row, [], kind, True, label=label)
            c.restoreState()
            c.showPage()
    c.save()
    return buf.getvalue()
