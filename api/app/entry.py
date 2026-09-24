"""Guided-entry vocabularies and quick-entry helpers, ported from the flat-file
system's scripts/add.py and common.py so the web GUI matches the established
data-entry model exactly.

Everything here is pure (no DB, no HTTP): the GUI endpoints in main.py call these
to turn friendly input (port letters, slot codes, 'N x size' RAM) into the stored
'Key: value | Key: value' specs and computer fields.
"""

from __future__ import annotations

import re
from collections import Counter
from collections.abc import Iterable, Iterator, Mapping, Sequence
from typing import NotRequired, TypedDict, TypeVar

from markupsafe import Markup, escape

# --- type vocabulary -------------------------------------------------------

# A power supply is back in here, and it is worth saying why it left. The four in
# the flat-file register were mostly generic -- two rows reading "Generic power
# supply, Form factor: AT" -- and a type whose every member is generic is a type
# that earns nothing, so it went and took them with it. What is worth filing is a
# supply that is a documented model: a Delta DPS-300SB-1, a Kentex KTX-9006-81 with
# 1992 on the label and a machine it belongs to. Same rule as the catalogue's, and
# the label and the drawing for it were never taken out. It is not a step in the
# build walk, though: nobody builds a machine out by being asked for its PSU.
TYPE_ORDER = [
    "motherboard",
    "cpu",
    "ram",
    "video",
    "sound",
    "network",
    "io",
    "storage",
    "display",
    "psu",
    "cooler",
    "peripheral",
    "other",
]

TYPE_LABELS = {
    "motherboard": "Motherboard",
    "cpu": "CPU",
    "ram": "Memory",
    "video": "Video",
    "sound": "Sound",
    "network": "Network",
    "io": "I/O",
    "storage": "Storage",
    "display": "Display",
    "optical": "Optical drive",
    "floppy": "Floppy drive",
    "psu": "Power supply",
    "cooler": "Cooling",
    "peripheral": "Peripheral",
    "other": "Other",
}

# Expansion-card categories walked through when building out a machine.
CARD_STEPS = [
    ("video", "video card"),
    ("sound", "sound card"),
    ("network", "network card"),
    ("io", "I/O card"),
    ("other", "other expansion card"),
]

# Storage kinds that are their own tagged parts; the rest live on the computer's
# drives field.
PART_STORAGE_KINDS = ("Hard disk", "Tape")
# The one routed kind whose capacity is a media designation ('1.44MB') rather than
# a measured quantity, which is the vocabulary FLOPPY_SIZES holds and the only
# kind the capacity picker fits: an optical drive is not a 720K anything.
FLOPPY_KIND = "Floppy/Gotek"
# The kind that is described by what it does with a disc rather than by how big
# one is, and so has the two pickers below instead of a capacity.
OPTICAL_KIND = "Optical"
DISK_KIND = "Hard disk"
TAPE_KIND = "Tape"
# A card in a reader or an adapter: no bezel of its own, no disc, no spindle.
CARD_KIND = "SD/CF card"

# --- pick-list vocabularies ------------------------------------------------

CONDITIONS = ["Working", "Untested", "Partially working", "Faulty", "For parts/repair", "Restored"]
MOBO_FORM_FACTORS = ["AT", "Baby-AT", "ATX", "LPX", "NLX", "proprietary"]
CPU_FAMILIES = [
    "8088-class",
    "286-class",
    "386-class",
    "486-class",
    "Pentium-class",
    "Pentium Pro-class",
    "Pentium II/III-class",
    "Pentium 4-class",
    "Athlon-class",
    "Z80",
]
RAM_SLOT_TYPES = ["30-pin SIMM", "72-pin SIMM", "168-pin DIMM", "184-pin DIMM"]
CARD_INTERFACES = ["8-bit ISA", "16-bit ISA", "EISA", "MCA", "VLB", "PCI", "AGP", "PCIe x16", "USB"]
VIDEO_CONNECTORS = [
    "VGA",
    "DVI",
    "HDMI",
    "DisplayPort",
    "S-Video",
    "Composite",
    "Component",
    "MDA",
    "CGA",
    "EGA",
]
# Ordered as the radio group reads: the buses a drive is usually on, then the
# pre-IDE disk interfaces, the two floppy ribbons (a slimline drive takes a 26-pin
# flex cable, not the 34-pin header of a desktop drive), removable media, and last
# the early CD-ROMs that hung off a sound card rather than a disk controller.
STORAGE_INTERFACES = [
    "IDE",
    "SATA",
    "SCSI",
    "MFM",
    "RLL",
    "ESDI",
    "34-pin floppy",
    "26-pin floppy",
    "CF",
    "SD",
    "USB",
    "Proprietary",
]
STORAGE_KINDS = ["Hard disk", "SD/CF card", "Tape", "Optical", "Floppy/Gotek"]
STORAGE_PROTOCOLS = ["ATA", "ATAPI", "SATA", "XTA", "RLL", "MFM", "ESDI", "SCSI"]
PERIPHERAL_INTERFACES = ["USB", "PS/2", "Serial", "Parallel", "VGA", "DIN"]

# --- displays ---------------------------------------------------------------
# A screen is asked two questions about what makes the picture, not one, because
# they are two questions: what the technology is, and how that technology is
# arranged. A Trinitron is a CRT -- it is a CRT with an aperture grille instead of
# a shadow mask -- and folding the second answer into the first would mean the
# register could no longer answer "every CRT" once somebody filed one as a
# Trinitron. So the tube or panel construction is its own field, and "every CRT"
# and "every aperture grille" are both questions the collection can answer.
DISPLAY_TYPES = [
    "CRT",
    "LCD",
    "Plasma",
    "OLED",
    "Electroluminescent",
    "VFD",
    "LED matrix",
    "E-paper",
]

# How the tube or the panel is built. The CRT masks first, then the panel
# technologies, because that is the order the collection runs in. Trinitron and
# Diamondtron are named beside the thing they are -- they are Sony's and
# Mitsubishi's aperture grilles -- so that looking for either finds it, and so that
# a grille filed under a trade name is still a grille.
DISPLAY_PANELS = [
    "Shadow mask",
    "Aperture grille (Trinitron)",
    "Aperture grille (Diamondtron)",
    "Aperture grille",
    "Slot mask",
    "TN",
    "IPS",
    "VA",
    "DSTN (passive)",
    "STN (passive)",
]

# What comes out of it, which on this hardware is as often one colour as it is all
# of them. A green screen and an amber one are different objects to look at and
# different objects to want, and neither is "monochrome" to anybody who has owned
# one -- so the phosphor is named rather than the absence of colour.
DISPLAY_PICTURES = ["Colour", "Green", "Amber", "White", "Paper white", "Greyscale"]

# The shape of the picture, which for everything in this collection's period is
# one of the first two.
DISPLAY_ASPECTS = ["4:3", "5:4", "16:10", "16:9", "3:2"]

# How it attaches, oldest first: the digital TTL cables of an IBM monitor, the
# analogue VGA that replaced them and everything since, then the ways a home
# computer or a console put a picture on a screen. Comma-separated where a monitor
# has more than one socket, which by the DVI years most of them did.
DISPLAY_INTERFACES = [
    "VGA (HD-15)",
    "DVI-D",
    "DVI-I",
    "DVI-A",
    "HDMI",
    "DisplayPort",
    "9-pin TTL (MDA)",
    "9-pin TTL (CGA)",
    "9-pin TTL (EGA)",
    "13W3",
    "BNC",
    "SCART",
    "S-Video",
    "Composite",
    "Component",
    "RGB DIN",
    "RF",
]

# The sizes screens were actually sold in. A tube was sold by the size of the tube
# and a panel by the picture, which is why 14" and 15" both exist and why the
# laptop and industrial sizes are down at the bottom of the list.
DISPLAY_SIZES = [
    '9"',
    '12"',
    '14"',
    '15"',
    '17"',
    '19"',
    '20"',
    '21"',
    '22"',
    '24"',
    '5"',
    '7"',
    '10"',
    '13.3"',
]

# The modes a screen of this period is described by. A multisync tube does a range
# and says so in the custom box: what belongs here is the one figure a monitor is
# known by, which for a panel is the only one it has.
DISPLAY_RESOLUTIONS = [
    "640×480",
    "800×600",
    "1024×768",
    "1152×864",
    "1280×1024",
    "1400×1050",
    "1600×1200",
    "1920×1080",
    "1920×1200",
    "720×348 (Hercules)",
    "320×200 (CGA)",
]

# What a monitor will do at the resolution above, and like the line rate below it,
# usually more than one thing. 50 Hz is where the television-rate modes of a home
# computer sit and where anything driven at 15 kHz has to be met; 60 is where a
# panel sits and a tube flickers; 85 is where a tube stops flickering, and is the
# figure worth recording about one. A screen that does several is ticked several
# times, and a multiscan quoting a range (the AKF18's 47–90 Hz) says so in the box.
DISPLAY_REFRESH = ["50 Hz", "60 Hz", "70 Hz", "72 Hz", "75 Hz", "85 Hz", "100 Hz", "120 Hz"]

# The line rates a screen will lock to -- the horizontal figure to the vertical one
# above, and the answer that decides whether a machine can drive the screen at all
# rather than how well. A plain VGA monitor takes 31 kHz and nothing else, and a
# machine putting out the 15 kHz of a television gets a black screen off the best
# tube in the house.
#
# The answer comes in two shapes, which is why this is ticks with a box beside them.
# A screen that lists a few rates and nothing between them is ticked, and neither of
# its rates implies the other. A multiscan quotes a continuous range instead and
# types it in the box: the Acorn AKF18 is 15-38 kHz by its own user guide, which is
# every rate in this list up to the SVGA modes and not a set at all.
#
# Round figures in the list, because they are what the hardware is known by: the TV
# rate is 15.625 kHz in PAL and 15.734 in NTSC, and both are "a 15 kHz monitor" to
# anyone who has owned one.
DISPLAY_SYNCS = [
    "15 kHz",
    "24 kHz",
    "31 kHz",
    "35 kHz",
    "38 kHz",
    "48 kHz",
    "56 kHz",
    "64 kHz",
    "80 kHz",
]

# The pitches quoted on the box, finest first, because finer is the thing being
# claimed. A grille is measured horizontally and a mask diagonally, so the two are
# not quite comparable -- which is an argument for recording both this and the
# panel type, not for recording neither.
DISPLAY_PITCHES = [
    "0.20 mm",
    "0.22 mm",
    "0.24 mm",
    "0.25 mm",
    "0.26 mm",
    "0.27 mm",
    "0.28 mm",
    "0.31 mm",
    "0.39 mm",
]

# What a screen is asked, and with what. One table, on the pattern STORAGE_ASKS
# set: the form builds itself from it and the server reads every answer back
# through it, so a control on screen and a control read cannot come apart. Doing
# those two separately is what went wrong twice on the storage form.
#
#   key      the spec key the answer is recorded under
#   options  the list it is picked from; every one of these also takes "custom"
#   multi    several answers rather than one -- checkboxes instead of radios
#   max      how long a custom answer may be: the width of the column it lands in


class DisplayAsk(TypedDict):
    """One row of the table below, spelt out for the same reason StorageAsk is: what
    reads the table is checked against it rather than against `object`."""

    key: str
    label: str
    hint: str
    options: list[str]
    max: int
    placeholder: str
    multi: NotRequired[bool]


DISPLAY_ASKS: list[DisplayAsk] = [
    {
        "key": "Type",
        "label": "Type",
        "hint": "what makes the picture",
        "options": DISPLAY_TYPES,
        "max": 64,
        "placeholder": "e.g. LCoS, DLP, Nixie",
    },
    {
        "key": "Panel",
        "label": "Tube or panel",
        "hint": "how it is built",
        "options": DISPLAY_PANELS,
        "max": 64,
        "placeholder": "e.g. Cromaclear, black matrix",
    },
    {
        "key": "Screen size",
        "label": "Screen size",
        "hint": "the diagonal, as it was sold",
        "options": DISPLAY_SIZES,
        "max": 32,
        "placeholder": 'e.g. 13.3", 16"',
    },
    {
        "key": "Aspect",
        "label": "Aspect ratio",
        "hint": "the shape of the picture",
        "options": DISPLAY_ASPECTS,
        "max": 16,
        "placeholder": "e.g. 5:3",
    },
    {
        "key": "Resolution",
        "label": "Resolution",
        "hint": "a panel's native one, or the most a tube will do",
        "options": DISPLAY_RESOLUTIONS,
        "max": 64,
        "placeholder": "e.g. 640×480 to 1280×1024",
    },
    # Ticked rather than chosen, for the reason the line rate is: a screen that
    # does 50 Hz for a television-rate mode and 85 for its best VGA one does both,
    # and the highest of them is not the useful half on its own -- whether a machine
    # putting out 50 Hz will be met is the question a record of it should answer.
    {
        "key": "Refresh",
        "label": "Refresh rate",
        "hint": "tick every rate it will do",
        "options": DISPLAY_REFRESH,
        "multi": True,
        "max": 255,
        "placeholder": "e.g. 47–90 Hz, 66 Hz",
    },
    # One of the two questions a screen may answer more than once. A tube that
    # locks to 15 kHz and to 31 kHz is two monitors in one case, and being made to
    # choose would mean recording the half that is less useful -- so the rates are
    # ticked. A multiscan that quotes a range (the AKF18's 15–38 kHz) types it in
    # the box instead of ticking every figure inside it.
    {
        "key": "Sync",
        "label": "Sync rate",
        "hint": "tick every line rate it will lock to",
        "options": DISPLAY_SYNCS,
        "multi": True,
        "max": 255,
        "placeholder": "e.g. 30–70 kHz, 15.625 kHz",
    },
    {
        "key": "Dot pitch",
        "label": "Dot pitch",
        "hint": "in millimetres",
        "options": DISPLAY_PITCHES,
        "max": 32,
        "placeholder": "e.g. 0.297 mm",
    },
    # The other, and the one most screens answer more than once: a monitor of the
    # DVI years has a VGA socket beside it, and a home-computer monitor takes
    # composite as well as RGB. Radios would make you choose which of a machine's
    # sockets to lie about, so these are checkboxes.
    {
        "key": "Interface",
        "label": "Interface",
        "hint": "tick every socket it has",
        "options": DISPLAY_INTERFACES,
        "multi": True,
        "max": 255,
        "placeholder": "e.g. 6-pin DIN, EGA/CGA switchable",
    },
    {
        "key": "Picture",
        "label": "Picture",
        "hint": "colour, or which phosphor a monochrome screen has",
        "options": DISPLAY_PICTURES,
        "max": 32,
        "placeholder": "e.g. Blue-white",
    },
]

# --- optical drives --------------------------------------------------------
# What an optical drive is known by: the discs it takes, and how fast it reads
# them. Neither is a capacity -- a CD-ROM drive is not a 650MB anything, it is a
# drive that takes CDs -- which is why these are their own two fields rather than
# the floppy capacity picker pointed at different words.
#
# Each medium names the most the drive does, on the understanding that a drive
# reads everything below it: a CD-RW writer reads pressed CD-ROMs, and saying so
# on every record would be noise. A drive that reads a disc it cannot write is
# named for what it reads (a DVD-ROM that burns CDs is the combo).
OPTICAL_MEDIA = [
    "CD-ROM",
    "CD-R",
    "CD-RW",
    "DVD-ROM",
    "DVD/CD-RW combo",
    "DVD±RW",
    "DVD-RAM",
    "Blu-ray",
]

# The × rating on the front of the drive, 1× being the 150 KB/s a CD player runs
# at. The list is the ratings that were actually sold; a drive quoting three
# figures (48×/24×/48× for write, rewrite and read) is typed into the custom box,
# because which of the three a single number means is a question this catalogue
# should not answer on the owner's behalf.
OPTICAL_SPEEDS = ["1×", "2×", "4×", "6×", "8×", "12×", "16×", "24×", "32×", "40×", "48×", "52×"]

# --- the rest of what a drive is asked --------------------------------------

# How wide the drive is, and how wide a bay it needs. Two questions with one
# vocabulary: a 3.5" drive normally sits in a 3.5" bay, but not when it is bracketed
# into a 5.25" one, and a floppy's own width is also the disk it takes.
DRIVE_INCHES = ['5.25"', '3.5"', '8"']

# The floppy capacities that actually turn up on this hardware. A designation rather
# than a measured quantity -- 1.44MB is 1475 KB only by convention, and nobody calls
# that disk a 1475 KB -- which is why it is its own key and never normalised.
FLOPPY_SIZES = ["160K", "180K", "320K", "360K", "720K", "1.2MB", "1.44MB", "2.88MB"]

# What a tape drive takes. The cartridge families a PC of this era was backed up
# onto, coarsest first; a drive quoting a length or a raw/compressed pair goes in
# the custom box.
TAPE_MEDIA = [
    "QIC-40",
    "QIC-80",
    "QIC-3010",
    "QIC-3020",
    "Travan TR-1",
    "Travan TR-2",
    "Travan TR-3",
    "Travan TR-4",
    "DC6150",
    "DDS/DAT",
    "DLT",
    "LTO",
]

# A spindle's speed, which is what "how fast" means for a disk -- the × ratings
# above are a reader's, and the two must not share a list. Anything off the shelf
# (4200, 5900, a quoted average) goes in the custom box.
DISK_SPEEDS = ["3600 rpm", "5400 rpm", "7200 rpm", "10000 rpm", "15000 rpm"]

_ALL_STORAGE_KINDS = (DISK_KIND, TAPE_KIND, OPTICAL_KIND, FLOPPY_KIND, CARD_KIND)

# What each kind of drive is asked, and with what. One table: the form builds itself
# from it and the server reads back through it, because keeping a form and the code
# behind it in step by hand is what went wrong twice here -- once a field on screen
# the server ignored, once a field the server read with nothing on screen to fill it.
#
#   key      the spec key the answer is recorded under
#   kinds    the kinds that are asked at all; every other kind hides it
#   options  the closed list it is picked from, per kind where that differs, or
#            None for a plain text box


class StorageAsk(TypedDict):
    """One row of the table below, spelt out so that what reads the table is checked
    against it: a dict of mixed values is `object` to a type checker, and `object`
    can be neither indexed nor lower-cased."""

    key: str
    kinds: tuple[str, ...]
    options: list[str] | dict[str, list[str]] | None
    label: str
    hint: str
    placeholder: NotRequired[str]
    required: NotRequired[bool]


STORAGE_ASKS: list[StorageAsk] = [
    {
        "key": "Interface",
        "kinds": _ALL_STORAGE_KINDS,
        "options": STORAGE_INTERFACES,
        "required": True,
        "label": "Interface",
        "hint": "how it attaches",
        "placeholder": "e.g. QIC-02, Panasonic/Matsushita",
    },
    {
        "key": "Protocol",
        "kinds": (DISK_KIND, TAPE_KIND, OPTICAL_KIND, CARD_KIND),
        "options": STORAGE_PROTOCOLS,
        "label": "Protocol",
        "hint": "the command set it speaks",
        "placeholder": "e.g. ATA-3, Fast SCSI-2",
    },
    {
        "key": "Form factor",
        "kinds": (DISK_KIND, TAPE_KIND, OPTICAL_KIND, FLOPPY_KIND),
        "options": DRIVE_INCHES,
        "label": "Bay size",
        "hint": "the bay it fits",
        "placeholder": 'e.g. 3" (Amstrad CF-2), 2.5"',
    },
    {
        "key": "Media",
        "kinds": (OPTICAL_KIND, TAPE_KIND, FLOPPY_KIND),
        "options": {OPTICAL_KIND: OPTICAL_MEDIA, TAPE_KIND: TAPE_MEDIA, FLOPPY_KIND: DRIVE_INCHES},
        "label": "Media",
        "hint": "what it takes",
        "placeholder": "e.g. HD DVD, magneto-optical, AIT",
    },
    {
        "key": "Size",
        "kinds": (FLOPPY_KIND,),
        "options": FLOPPY_SIZES,
        "label": "Capacity",
        "hint": "what the disk is called, not a measured size",
        "placeholder": "e.g. 21MB Floptical, 120MB LS-120",
    },
    {
        "key": "Capacity",
        "kinds": (DISK_KIND, TAPE_KIND, OPTICAL_KIND, CARD_KIND),
        "options": None,
        "label": "Capacity",
        "hint": "e.g. 540 MiB",
    },
    {
        "key": "Speed",
        "kinds": (OPTICAL_KIND, DISK_KIND),
        "options": {OPTICAL_KIND: OPTICAL_SPEEDS, DISK_KIND: DISK_SPEEDS},
        "label": "Speed",
        "hint": "the rating on the front, or the spindle",
        "placeholder": "e.g. 48×/24×/48× (write/rewrite/read), 4200 rpm",
    },
    {
        "key": "CHS",
        "kinds": (DISK_KIND, CARD_KIND),
        "options": None,
        "label": "CHS geometry",
        "hint": "cylinders/heads/sectors, e.g. 1024/16/63",
    },
    {
        "key": "Role",
        "kinds": _ALL_STORAGE_KINDS,
        "options": None,
        "label": "Role",
        "hint": "what it was for",
    },
]

# The two that are not spec text at all: the bezel is a pair of colour menus, and
# the disk image is a column on the part. Same question of which kinds are asked.
BEZEL_KINDS = (DISK_KIND, TAPE_KIND, OPTICAL_KIND, FLOPPY_KIND)
DISK_IMAGE_KINDS = (DISK_KIND,)


def storage_asks(kind: str) -> list[StorageAsk]:
    """The asks that apply to one kind, each with the options that kind picks from
    (a per-kind vocabulary resolved, and None left as None for a text box)."""
    out: list[StorageAsk] = []
    for ask in STORAGE_ASKS:
        if kind not in ask["kinds"]:
            continue
        options = ask["options"]
        if isinstance(options, dict):
            options = options.get(kind)
        out.append(ask | {"options": options})
    return out


# --- bezel colour and yellowing --------------------------------------------
# Two things, recorded separately: the shade a drive was made in, and how far it
# has yellowed since. They are not one field because they answer different
# questions -- "what did this machine's drives look like new" and "how bad is this
# one" -- and because a beige drive that has gone yellow is still a beige drive.
# Either can be recorded without the other: an unrestored find often shows only
# how yellow it is, and a pristine spare only what shade it is.
#
# Shared by a machine's drive rows (drivedb), by storage parts and by displays (the
# Colour and Yellowing specs), so a drive fitted in a machine and the same drive on
# the shelf are described in the same words -- and so is the monitor sat on top of
# it, which is the same plastic, made in the same beige, gone the same colour.


class BezelColour(TypedDict):
    label: str
    # What to draw it as, and what a yellowed shade is mixed from.
    hex: str
    note: str


BEZEL_COLOURS: list[BezelColour] = [
    {"label": "Black", "hex": "#1a1b1d", "note": "black plastic or a painted bezel"},
    {
        "label": "Dark grey",
        "hex": "#4b4f55",
        "note": "a grey that reads darker than the case around it",
    },
    {"label": "Grey", "hex": "#8b9097", "note": "mid grey, with no warmth in it"},
    {"label": "Light grey", "hex": "#c3c7cc", "note": "pale grey, cooler than beige"},
    {"label": "White", "hex": "#f6f6f4", "note": "a true white, no cream in it"},
    {
        "label": "Off-white",
        "hex": "#ece8dc",
        "note": "white with a little cream, as made rather than as aged",
    },
    {"label": "Beige", "hex": "#dad0b8", "note": "the classic PC beige"},
    {"label": "Warm beige", "hex": "#cebb9a", "note": "beige with more brown in it"},
    {"label": "Grey-beige", "hex": "#c8c5b5", "note": "beige with the warmth taken out"},
]

# How far it has gone. `weight` is how much of `tint` to mix into the original
# shade to draw it -- a rendering, not data, so these numbers can be adjusted
# without touching a single record. Blank means it has not yellowed, or nobody has
# looked yet: the same blank every other unrecorded field uses.


class Yellowing(TypedDict):
    label: str
    weight: float
    # The far end of an uneven one, which is drawn as a gradient between the two.
    weight2: NotRequired[float]
    tint: str
    note: str


YELLOWING: list[Yellowing] = [
    {
        "label": "Lightly yellowed",
        "weight": 0.20,
        "tint": "#c49a44",
        "note": "just off its original shade; tells beside a clean part",
    },
    {
        "label": "Yellowed",
        "weight": 0.38,
        "tint": "#bd8f34",
        "note": "plainly yellow, evenly across the bezel",
    },
    {
        "label": "Heavily yellowed",
        "weight": 0.58,
        "tint": "#b3822c",
        "note": "deep yellow going to tan",
    },
    {
        "label": "Browned",
        "weight": 0.78,
        "tint": "#8a6a35",
        "note": "past yellow into brown; UV, heat or years of smoke",
    },
    {
        "label": "Unevenly yellowed",
        "weight": 0.15,
        "weight2": 0.55,
        "tint": "#bd8f34",
        "note": "patchy, or one side only -- a sun-facing edge, or the shadow of a bracket",
    },
]
BEZEL_COLOUR_LABELS = [c["label"] for c in BEZEL_COLOURS]
YELLOWING_LABELS = [y["label"] for y in YELLOWING]

# What to draw a yellowing level on when the original shade was never recorded:
# some pale plastic, which is what almost every yellowed bezel started as.
ASSUMED_BEZEL = "#ded7c6"


def bezel_colour(label: str | None) -> BezelColour | None:
    """The BEZEL_COLOURS entry for a recorded shade, or None for one from outside
    the vocabulary -- which is shown as its own words and no swatch."""
    return _by_label(BEZEL_COLOURS, label)


def yellowing_level(label: str | None) -> Yellowing | None:
    """The YELLOWING entry for a recorded level, or None."""
    return _by_label(YELLOWING, label)


# One lookup for both vocabularies, and the answer keeps the vocabulary's own shape:
# a restricted variable rather than a common base, because the two tables have
# nothing in common but the label they are found by.
_Vocab = TypeVar("_Vocab", BezelColour, Yellowing)


def _by_label(vocab: Sequence[_Vocab], label: str | None) -> _Vocab | None:
    want = (label or "").strip().lower()
    return next((v for v in vocab if v["label"].lower() == want), None) if want else None


def _mix(base: str, tint: str, weight: float) -> str:
    """`base` hex moved `weight` of the way towards `tint` hex."""
    pairs = [(int(base[i : i + 2], 16), int(tint[i : i + 2], 16)) for i in (1, 3, 5)]
    return "#" + "".join(f"{round(b + (t - b) * weight):02x}" for b, t in pairs)


def bezel_css(colour: str | None = "", yellowing: str | None = "") -> str:
    """A CSS background for a bezel as made and as it has aged, or '' if neither is
    recorded. Uneven yellowing comes back as a two-tone gradient, which is the only
    honest way to draw one shade in two states.

    The maths lives here, once: the chart, the swatch beside a form row and the
    swatch on an item page all read the same value, so none of them can disagree
    about what 'heavily yellowed beige' looks like."""
    col = bezel_colour(colour)
    lvl = yellowing_level(yellowing)
    if not col and not lvl:
        return ""
    base = col["hex"] if col else ASSUMED_BEZEL
    if not lvl:
        return base
    if lvl.get("weight2"):
        light = _mix(base, lvl["tint"], lvl["weight"])
        heavy = _mix(base, lvl["tint"], lvl["weight2"])
        return f"linear-gradient(115deg, {light} 46%, {heavy} 54%)"
    return _mix(base, lvl["tint"], lvl["weight"])


def bezel_slug(label: str | None) -> str:
    """A vocabulary label as the part of a class name it becomes."""
    return re.sub(r"[^a-z0-9]+", "-", (label or "").strip().lower()).strip("-")


def bezel_class(colour: str | None = "", yellowing: str | None = "") -> str:
    """The class that paints a swatch for a bezel as made and as it has aged, or ''
    where there is no colour to give.

    A class rather than the CSS itself, because the content policy allows no style
    attribute in the markup (ADR-0022). The mixing still happens once, here: the
    rules these names refer to are generated from bezel_css into the stylesheet at
    /style/data.css, so the chart, the swatch beside a menu and the swatch on an
    item page cannot disagree any more than they did before."""
    if not bezel_css(colour, yellowing):
        return ""
    return f"bz-{bezel_slug(colour) or 'x'}-{bezel_slug(yellowing) or 'x'}"


def bezel_pairs() -> Iterator[tuple[str, str, str]]:
    """Every colour/yellowing pair that has a swatch, as (colour, level, css)."""
    for colour in ["", *BEZEL_COLOUR_LABELS]:
        for level in ["", *YELLOWING_LABELS]:
            css = bezel_css(colour, level)
            if css:
                yield colour, level, css


def bezel_swatch_map() -> dict[str, str]:
    """Every colour/yellowing pair as its swatch class, keyed 'colour|yellowing'.

    The browser repaints the swatch beside a menu by swapping the class from this
    rather than doing the mixing again in JavaScript, so there is one
    implementation of it."""
    return {f"{colour}|{level}": bezel_class(colour, level) for colour, level, _ in bezel_pairs()}


# --- specs parsing / merging -----------------------------------------------


def parse_specs(specs: str | None) -> list[tuple[str, str]]:
    """Turn 'CPU: x | RAM: y' into [('CPU','x'), ('RAM','y')]."""
    out = []
    for chunk in (specs or "").split("|"):
        chunk = chunk.strip()
        if not chunk:
            continue
        if ":" in chunk:
            k, v = chunk.split(":", 1)
            out.append((k.strip(), v.strip()))
        else:
            out.append(("", chunk))
    return out


def merge_spec(specs: str, key: str, value: str) -> str:
    """Set/replace 'key: value' inside a 'a: b | c: d' specs string."""
    pairs, replaced, out = parse_specs(specs), False, []
    for k, v in pairs:
        if k.lower() == key.lower():
            out.append((key, value))
            replaced = True
        else:
            out.append((k, v))
    if not replaced:
        out.append((key, value))
    return " | ".join(f"{k}: {v}" if k else v for k, v in out)


def build_specs(pairs: Iterable[tuple[str, str | None]]) -> str:
    """Assemble ordered (key, value) pairs into a specs string, dropping blanks."""
    specs = ""
    for key, value in pairs:
        value = (value or "").strip()
        if value:
            specs = merge_spec(specs, key, value)
    return specs


# --- amounts / RAM ---------------------------------------------------------

# What the register says, and what it reads.
#
# Every amount in here is binary and always has been: a K is 1024 bytes, an M is
# 1024 of those, and the arithmetic below has never done anything else. What was
# written on the page said KB and MB, which are the decimal units, so the label
# disagreed with the sum behind it. These are the IEC units that mean what the
# register actually counts, and saying them is the whole of the change -- no figure
# moves.
#
# The old spellings stay readable (KB, MB, and the bare K of a "360K" floppy), and
# have to: every specs string, memory total and drive already stored says KB, and
# is parsed back on the next save. They are read and never written.
KIB, MIB, GIB, TIB = "KiB", "MiB", "GiB", "TiB"

_KB_UNITS = {
    "": 1024,
    "k": 1,
    "kb": 1,
    "ki": 1,
    "kib": 1,
    "m": 1024,
    "mb": 1024,
    "mi": 1024,
    "mib": 1024,
    "g": 1024 * 1024,
    "gb": 1024 * 1024,
    "gi": 1024 * 1024,
    "gib": 1024 * 1024,
    "t": 1024 * 1024 * 1024,
    "tb": 1024 * 1024 * 1024,
    "ti": 1024 * 1024 * 1024,
    "tib": 1024 * 1024 * 1024,
}


def to_kb(text: str | None) -> int | None:
    """'2MiB'->2048, '512KiB'->512, '2'->2048 (bare number assumed MiB). The older
    KB/MB spellings read the same, because that is what is already on file. None if
    unparseable."""
    m = re.match(r"^\s*([\d.]+)\s*([a-zA-Z]*)\s*$", text or "")
    if not m:
        return None
    unit = m.group(2).lower()
    if unit not in _KB_UNITS:
        return None
    try:
        return round(float(m.group(1)) * _KB_UNITS[unit])
    except ValueError:
        return None


def normalise_amount(spec_key: str, amt: str) -> str:
    """Memory amounts (Size/Memory) normalise to KiB; others kept as typed."""
    if spec_key in ("Size", "Memory"):
        kb = to_kb(amt)
        if kb is not None:
            return f"{kb} {KIB}"
    return amt


def fmt_kb(kb: int | None, display: bool = False) -> str:
    """A KiB count in the unit a person would use. The one place that decides this,
    for spec columns, a machine's memory total and the figures on the stats page.

    Quantities are stored as plain KiB integers so they sort and compare in SQL;
    which unit to say them in is a rendering question, answered here.

    A whole number of MiB stays in MiB rather than climbing to GiB, because for this
    hardware the difference is meaningful: 2096128 KiB is the 2047 MiB BIOS limit,
    not "2 GiB".

    Everything the default returns parses back to exactly the number of KiB it was
    given, which is what the edit form and the stored specs string need -- both are
    read back and parsed on the next save. `display` is for text that is only ever
    read (a page, a label, a RAM total): there an amount that cannot be said
    exactly is rounded to three significant figures, "37.9 MiB" rather than the
    strictly-true-but-useless "38828 KiB".
    """
    if not kb:
        return ""
    if kb % (1024 * 1024) == 0:
        return f"{kb // (1024 * 1024)} {GIB}"
    if kb % 1024 == 0:
        return f"{kb // 1024} {MIB}"
    # The largest unit whose short decimal form still parses back to exactly this
    # many KiB, so "1.2GiB" comes back as "1.2 GiB" rather than "1228.8 MiB". Two
    # places as well as one, which is what lets a floppy's 1475 KiB be the 1.44 MiB
    # everyone calls it while still being reversible.
    for unit, mult in ((GIB, 1024 * 1024), (MIB, 1024)):
        if kb < mult:
            continue
        for places in (1, 2):
            text = f"{kb / mult:.{places}f}"
            if round(float(text) * mult) == kb:
                return f"{text} {unit}"
    return _round_kb(kb) if display else f"{kb} {KIB}"


def _round_kb(kb: int) -> str:
    """A KiB count at three significant figures in the largest unit it fills, for
    text that is read and never parsed back. 1475 KiB is the 1.44 MiB of a floppy;
    38828 KiB is a 37.9 MiB drive. Neither parses back to the KiB it came from,
    which is why this is not what the form or the specs string is given."""
    for unit, mult in ((GIB, 1024 * 1024), (MIB, 1024)):
        if kb < mult:
            continue
        val = kb / mult
        # Three significant figures, without %g's habit of turning 1000 into 1e+03.
        text = f"{val:.0f}" if val >= 100 else f"{val:.1f}" if val >= 10 else f"{val:.2f}"
        if "." in text:
            text = text.rstrip("0").rstrip(".")
        return f"{text} {unit}"
    return f"{kb} {KIB}"


# Common DRAM chips for machines with RAM soldered/socketed directly on the board
# (not on SIMMs/modules). Each is (part number, KiB per chip, organisation).
#
# The 4532 and the 41464 are here for the home machines rather than the PCs: the
# 4532 is the half-good 4164 that eight of make up a 48K Spectrum's upper bank, and
# the 41464 is what a C64C or a 6128 has two or four of where a breadbin had eight
# 4164s. Neither ever turns up in a PC, and both are the whole answer to "how much
# memory has this got" on the machines that do use them.
RAM_CHIPS = [
    ("4116", 2, "16K×1"),
    ("4532", 4, "32K×1"),
    ("4164", 8, "64K×1"),
    ("4416", 8, "16K×4"),
    ("4464", 32, "64K×4"),
    ("41464", 32, "64K×4"),
    ("41256", 32, "256K×1"),
    ("44256", 128, "256K×4"),
    ("411000", 128, "1M×1"),
    ("514256", 128, "256K×4"),
]
RAM_CHIP_KB = {pn: kb for pn, kb, _ in RAM_CHIPS}
RAM_CHIP_ORG = {pn: org for pn, _kb, org in RAM_CHIPS}


def _chip_width(org: str | None) -> int:
    """Data-bits-per-chip from an organisation string: '256K×1' -> 1, '64K×4' -> 4."""
    m = re.search(r"[×x](\d+)\s*$", org or "")
    return int(m.group(1)) if m else 1


def _chip_depth(org: str | None) -> str:
    """The addressable depth from an organisation string: '64K×4' -> '64K'. Chips of
    the same depth are what make up a bank together, whatever their width."""
    return (org or "").split("×")[0].split("x")[0].strip()


def chip_capacity(counts: Iterable[tuple[str, int | None]]) -> tuple[int, bool]:
    """Usable KiB and whether parity is fitted, from [(chip, n), ...].

    A bank is made of chips of the same depth, and is nine bits wide where the
    ninth is parity. Chips are therefore grouped by depth and the group's total
    width decides: 18 bits at 64K deep is two banks of 8 data bits plus 2 parity,
    so 128 KiB of the 144 KiB fitted is usable.

    Grouping matters because a bank's data and parity are often different chips --
    an Amstrad PC1640 carries 4x 4464 for data with 2x 4164 alongside for their
    parity, and counting those two as data overstates the machine by 16 KiB.
    """
    groups: dict[str, tuple[int, int]] = {}
    for pn, n in counts:
        if not n:
            continue
        org = RAM_CHIP_ORG.get(pn, "")
        depth = _chip_depth(org)
        bits, kb = groups.get(depth, (0, 0))
        groups[depth] = (bits + n * _chip_width(org), kb + n * RAM_CHIP_KB.get(pn, 0))
    total_kb, parity = 0, False
    for bits, kb in groups.values():
        if bits % 9 == 0:
            total_kb += kb * 8 // 9
            parity = True
        else:
            total_kb += kb
    return total_kb, parity


def format_ram_chips(counts: Iterable[tuple[str, int | None]]) -> str:
    """[(chip, n), ...] -> '9× 41256 (256 KiB + parity)' with the usable total."""
    counts = [(pn, n) for pn, n in counts if n]
    if not counts:
        return ""
    total_kb, parity = chip_capacity(counts)
    chips = ", ".join(f"{n}× {pn}" for pn, n in counts)
    return f"{chips} ({fmt_kb(total_kb, display=True)}{' + parity' if parity else ''})"


# Common memory modules for machines with RAM on SIMMs / SIPPs rather than
# soldered chips. Each is (slug for the form field, KiB per module, label).
RAM_MODULES = [
    ("30p256k", 256, "256KiB 30-pin"),
    ("30p1m", 1024, "1MiB 30-pin"),
    ("30p4m", 4096, "4MiB 30-pin"),
    ("sipp256k", 256, "256KiB SIPP"),
    ("sipp1m", 1024, "1MiB SIPP"),
    ("sipp4m", 4096, "4MiB SIPP"),
    ("72p1m", 1024, "1MiB 72-pin"),
    ("72p2m", 2048, "2MiB 72-pin"),
    ("72p4m", 4096, "4MiB 72-pin"),
    ("72p8m", 8192, "8MiB 72-pin"),
    ("72p16m", 16384, "16MiB 72-pin"),
    ("72p32m", 32768, "32MiB 72-pin"),
]
RAM_MODULE_KB = {s: kb for s, kb, _ in RAM_MODULES}
RAM_MODULE_LABEL = {s: lbl for s, _kb, lbl in RAM_MODULES}


def format_ram_modules(counts: Iterable[tuple[str, int | None]]) -> str:
    """[(slug, n), ...] -> '4× 1MiB 30-pin, 2× 4MiB 72-pin (12 MiB)' with the total."""
    counts = [(s, n) for s, n in counts if n]
    if not counts:
        return ""
    total_kb = sum(n * RAM_MODULE_KB.get(s, 0) for s, n in counts if n)
    mods = ", ".join(f"{n}× {RAM_MODULE_LABEL[s]}" for s, n in counts)
    return f"{mods} ({fmt_kb(total_kb, display=True)})"


def ram_total_kb(
    modules: Iterable[tuple[str, int | None]], chips: Iterable[tuple[str, int | None]]
) -> int:
    """Usable KiB fitted, from [(slug, n)] modules and [(chip, n)] chips. Parity
    chips are not capacity, so chip_capacity discounts them."""
    return sum(n * RAM_MODULE_KB.get(slug, 0) for slug, n in modules if n) + chip_capacity(chips)[0]


def render_installed_ram(
    modules: Iterable[tuple[str, int | None]],
    chips: Iterable[tuple[str, int | None]],
    total_kb: int | None = None,
    note: str = "",
) -> str:
    """A machine's installed RAM for display: the module and chip lists each with
    their own subtotal, or a bare total where there is no breakdown, plus any
    free text that is neither."""
    mods = format_ram_modules(modules)
    chips_txt = format_ram_chips(chips)
    out = []
    if not (mods or chips_txt) and total_kb:
        out.append(fmt_kb(total_kb, display=True))
    out += [x for x in (mods, chips_txt) if x]
    if note:
        out.append(note)
    return "; ".join(out)


# --- quick-entry: ports (io cards + motherboard onboard I/O) ---------------

PORT_CODES = [
    ("I", "IDE"),
    ("C", "SCSI"),
    ("A", "SATA"),
    ("M", "MFM"),
    ("R", "RLL"),
    ("F", "Floppy"),
    ("S", "Serial"),
    ("P", "Parallel"),
    ("G", "Game"),
    ("K", "PS/2 keyboard"),
    ("O", "PS/2 mouse"),
    ("D", "DIN keyboard"),
    ("U", "USB"),
]

PORT_NAMES = [name for _, name in PORT_CODES]


def format_counts(items: Iterable[tuple[str, int | None]]) -> str:
    """[(name, n), ...] -> 'n× name, ...' (the canonical count-list rendering)."""
    return ", ".join(f"{n}× {name}" if n and n > 1 else name for name, n in items)


_PORT_ITEM_RE = re.compile(r"^(?:(\d+)\s*[×x]\s*)?(.+)$")


def parse_port_list(value: str | None) -> list[tuple[str, int]] | None:
    """[(port, count), ...] if `value` is already an expanded port list such as
    'IDE, Floppy, 2× Serial' -- that is, every comma-separated item names a known
    port. None if it is not, which means it should be read as letter codes."""
    items = [tok.strip() for tok in (value or "").split(",") if tok.strip()]
    if not items:
        return None
    out = []
    for tok in items:
        m = _PORT_ITEM_RE.match(tok)
        # "." stops at a line break, so an item with one inside it matches nothing.
        if m is None:
            return None
        name = m.group(2).strip()
        if name not in PORT_NAMES:
            return None
        out.append((name, int(m.group(1)) if m.group(1) else 1))
    return out


def expand_ports(code: str) -> str:
    """'IFSSP' -> 'IDE, Floppy, 2x Serial, Parallel'. Order-independent; repeated
    letters become a count; unknown letters are ignored.

    Input that is already an expanded list is normalised rather than re-read as
    letters -- otherwise round-tripping the edit form would count the letters of
    the port names themselves ('IDE, Floppy, ...' has four A's, inventing
    '4x SATA') and corrupt the value on every save.
    """
    expanded = parse_port_list(code)
    if expanded is not None:
        return format_counts(expanded)
    counts = Counter(c for c in (code or "").upper() if c.isalpha())
    out = []
    for letter, name in PORT_CODES:
        n = counts.get(letter, 0)
        if n:
            out.append(f"{n}× {name}" if n > 1 else name)
    return ", ".join(out)


# --- quick-entry: expansion slots (motherboard) ----------------------------

SLOT_TYPES = [
    ("8-bit ISA", ("8I", "I8", "8ISA", "8")),
    ("16-bit ISA", ("16I", "I16", "16ISA", "16")),
    ("EISA", ("E", "EISA")),
    ("MCA", ("M", "MCA")),
    ("VLB", ("V", "VL", "VLB")),
    ("PCI", ("P", "PCI")),
    ("AGP", ("A", "AGP")),
    ("PCIe x16", ("PCIE16", "X16")),
]
SLOT_NAMES = [name for name, _ in SLOT_TYPES]


def expand_slots(raw: str) -> str:
    """'8I:2 16I:6 VLB' -> '2x 8-bit ISA, 6x 16-bit ISA, VLB'. Tokens are 'key',
    'key:n', 'key*n' or 'keyxn'; order-independent; unknown tokens ignored."""
    alias = {c.upper(): name for name, codes in SLOT_TYPES for c in codes}
    counts: Counter[str] = Counter()
    for tok in re.split(r"[\s,]+", (raw or "").strip()):
        if not tok:
            continue
        m = re.match(r"^(.+?)\s*[:*xX]\s*(\d+)$", tok)
        key, n = (m.group(1), int(m.group(2))) if m else (tok, 1)
        name = alias.get(key.upper())
        if name:
            counts[name] += n
    return ", ".join(
        f"{counts[name]}× {name}" if counts[name] > 1 else name
        for name in SLOT_NAMES
        if counts.get(name)
    )


# --- shared display helpers ------------------------------------------------

SHOUT_ACRONYMS = {
    "SCSI",
    "SATA",
    "PATA",
    "EISA",
    "ESDI",
    "VESA",
    "SVGA",
    "WXGA",
    "ATAPI",
    "BIOS",
    "UEFI",
    "DRAM",
    "SRAM",
    "SDRAM",
    "VRAM",
    "SIMM",
    "DIMM",
    "RIMM",
    "SIPP",
    "COAST",
    "CMOS",
    "MIDI",
    "EPROM",
    "EEPROM",
    "PROM",
    "MCGA",
    "PLCC",
    "NTSC",
    "SECAM",
    "WLAN",
    "ASIC",
}


def deshout(text: str) -> str:
    """De-shout a value word by word: a purely-uppercase token 5+ long that isn't
    a known acronym becomes Capitalised; short tokens, acronyms and part numbers
    are left alone."""
    out = []
    for tok in re.split(r"(\s+)", text or ""):
        core = tok.strip(".,:;()[]{}/\\\"'")
        if core.isalpha() and core.isupper() and len(core) >= 5 and core not in SHOUT_ACRONYMS:
            i = tok.find(core)
            tok = tok[:i] + core[0] + core[1:].lower() + tok[i + len(core) :]
        out.append(tok)
    return "".join(out)


def display_name(row: Mapping[str, object]) -> str:
    """What one register row is called. Given a row read column by column (to_dict),
    so what it holds is typed as widely as a column can be; these four are text."""
    if row.get("name"):
        return str(row["name"])
    joined = " ".join(
        str(p) for p in (row.get("manufacturer", ""), row.get("model", "")) if p
    ).strip()
    return joined or str(row.get("asset_id", ""))


def type_label(t: str | None) -> str:
    return TYPE_LABELS.get(t or "", (t or "other").title())


def type_sort_key(t: str) -> int:
    try:
        return TYPE_ORDER.index(t)
    except ValueError:
        return len(TYPE_ORDER)


# Placeholder icon (served from /static/placeholders/) shown when an item has no
# photo -- same set as the old public site.
PLACEHOLDER = {
    "computer": "computer",
    "motherboard": "board",
    "cpu": "chip",
    "ram": "ram",
    "video": "card",
    "sound": "card",
    "network": "card",
    "io": "card",
    "storage": "drive",
    "optical": "disc",
    "floppy": "floppy",
    "psu": "psu",
    "display": "monitor",
    "cooler": "fan",
    "peripheral": "keyboard",
    "other": "box",
}


def placeholder_for(kind_or_type: str) -> str:
    return "placeholders/" + PLACEHOLDER.get(kind_or_type, "box") + ".svg"


# --- links in what people wrote --------------------------------------------
# A URL typed into a note, a summary or a history entry is a URL you meant to
# follow, and until this it was text to be selected and pasted. The register is
# full of them: where a board came from, the forum thread that identified a chip,
# the FTP archive a ROM dump is out of.
#
# What counts as one is deliberately narrow. Anything with a scheme in front of it
# is unambiguous -- http, https, ftp, ftps, sftp, mailto -- and beyond those only
# two shapes are taken, both of them shapes nobody writes by accident: a host
# beginning www., and an address with an @ and a dotted domain after it. Bare
# hostnames are not, because half the part numbers in here have a domain's shape
# and none of them is one: config.sys, 1.44MB, 74LS00.rev2.
#
# Only these schemes, and never whatever a text box happens to say before a colon:
# javascript: is a scheme too, and this text arrives from a form.
_LINK_RE = re.compile(
    r"""
    (?<![\w@.-])                                # not mid-word, nor an address's tail
    (?:
        (?:https?|ftps?|sftp)://[^\s<>"']+      # said outright
      | mailto:[^\s<>"']+
      | www\.[^\s<>"']+                         # the shorthand everybody writes
      | [\w.+%-]+@[\w-]+(?:\.[\w-]+)+           # an email address
    )
""",
    re.VERBOSE | re.IGNORECASE,
)

# Punctuation that ends the sentence rather than the URL. A closing bracket is the
# URL's own as long as one opened inside it, which is what tells
# "http://x/Amiga_(computer)" from "(see http://x/p)" -- and, a bracket at a time,
# tells both of them from "(see http://x/Amiga_(computer))".
_LINK_TAIL = ".,;:!?'\"”’)]}>"


def _link_end(url: str) -> str:
    while url and url[-1] in _LINK_TAIL:
        if url[-1] == ")" and url.count("(") >= url.count(")"):
            break
        url = url[:-1]
    return url


def linked(text: object) -> Markup:
    """What was written, with every link in it clickable and nothing else changed.

    Returns markup, so it escapes as it goes: the text came out of a form and is
    never allowed to arrive as markup of its own. Anything that is not a string --
    a year, a date, the None of an empty column -- is read as what it prints as,
    since the details tables hand this whole rows at a time.

    An off-site link opens in a tab of its own, as the reference link on an item's
    page always has: the register is a thing you are working through, and following
    a note out of it should not lose your place in it.
    """
    s = "" if text is None else str(text)
    out, at = [], 0
    for m in _LINK_RE.finditer(s):
        url = _link_end(m.group(0))
        if not url:
            continue
        out.append(escape(s[at : m.start()]))
        low = url.lower()
        if low.startswith("www."):
            # http, not https: a host that has TLS redirects to it, and one that
            # never got round to it is simply unreachable the other way about --
            # and the hosts written down in here are museum pieces as often as not.
            href, tab = "http://" + url, True
        elif low.startswith("mailto:"):
            href, tab = url, False
        elif "://" in url:
            href, tab = url, True
        else:
            href, tab = "mailto:" + url, False
        out.append(
            Markup(
                '<a class="url" href="{}" target="_blank" rel="noopener noreferrer">{}</a>'
                if tab
                else '<a class="url" href="{}">{}</a>'
            ).format(href, url)
        )
        at = m.start() + len(url)
    out.append(escape(s[at:]))
    return Markup("").join(out)
