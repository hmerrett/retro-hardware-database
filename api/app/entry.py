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

# --- type vocabulary -------------------------------------------------------

TYPE_ORDER = [
    "motherboard", "cpu", "ram", "video", "sound", "network", "io",
    "storage", "cooler", "peripheral", "other",
]

TYPE_LABELS = {
    "motherboard": "Motherboard", "cpu": "CPU", "ram": "Memory", "video": "Video",
    "sound": "Sound", "network": "Network", "io": "I/O", "storage": "Storage",
    "optical": "Optical drive", "floppy": "Floppy drive", "psu": "Power supply",
    "cooler": "Cooling", "peripheral": "Peripheral", "other": "Other",
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
# a measured quantity, which is the vocabulary drivedb.SIZES holds and the only
# kind the capacity picker fits: an optical drive is not a 720K anything.
FLOPPY_KIND = "Floppy/Gotek"
# The kind that is described by what it does with a disc rather than by how big
# one is, and so has the two pickers below instead of a capacity.
OPTICAL_KIND = "Optical"

# --- pick-list vocabularies ------------------------------------------------

CONDITIONS = ["Working", "Untested", "Partially working", "Faulty",
              "For parts/repair", "Restored"]
MOBO_FORM_FACTORS = ["AT", "Baby-AT", "ATX", "LPX", "NLX", "proprietary"]
CPU_FAMILIES = ["8088-class", "286-class", "386-class", "486-class",
                "Pentium-class", "Pentium Pro-class", "Pentium II/III-class",
                "Pentium 4-class", "Athlon-class", "Z80"]
RAM_SLOT_TYPES = ["30-pin SIMM", "72-pin SIMM", "168-pin DIMM", "184-pin DIMM"]
CARD_INTERFACES = ["8-bit ISA", "16-bit ISA", "EISA", "MCA", "VLB",
                   "PCI", "AGP", "PCIe x16", "USB"]
VIDEO_CONNECTORS = ["VGA", "DVI", "HDMI", "DisplayPort", "S-Video", "Composite",
                    "Component", "MDA", "CGA", "EGA"]
# Ordered as the radio group reads: the buses a drive is usually on, then the
# pre-IDE disk interfaces, the two floppy ribbons (a slimline drive takes a 26-pin
# flex cable, not the 34-pin header of a desktop drive), removable media, and last
# the early CD-ROMs that hung off a sound card rather than a disk controller.
STORAGE_INTERFACES = ["IDE", "SATA", "SCSI", "MFM", "RLL", "ESDI",
                      "34-pin floppy", "26-pin floppy", "CF", "SD", "USB",
                      "Proprietary"]
STORAGE_KINDS = ["Hard disk", "SD/CF card", "Tape", "Optical", "Floppy/Gotek"]
STORAGE_PROTOCOLS = ["ATA", "ATAPI", "SATA", "XTA", "RLL", "MFM", "ESDI", "SCSI"]
PERIPHERAL_INTERFACES = ["USB", "PS/2", "Serial", "Parallel", "VGA", "DIN"]

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
OPTICAL_MEDIA = ["CD-ROM", "CD-R", "CD-RW", "DVD-ROM", "DVD/CD-RW combo",
                 "DVD±RW", "DVD-RAM", "Blu-ray"]

# The × rating on the front of the drive, 1× being the 150 KB/s a CD player runs
# at. The list is the ratings that were actually sold; a drive quoting three
# figures (48×/24×/48× for write, rewrite and read) is typed into the custom box,
# because which of the three a single number means is a question this catalogue
# should not answer on the owner's behalf.
OPTICAL_SPEEDS = ["1×", "2×", "4×", "6×", "8×", "12×", "16×", "24×", "32×",
                  "40×", "48×", "52×"]

# --- bezel colour and yellowing --------------------------------------------
# Two things, recorded separately: the shade a drive was made in, and how far it
# has yellowed since. They are not one field because they answer different
# questions -- "what did this machine's drives look like new" and "how bad is this
# one" -- and because a beige drive that has gone yellow is still a beige drive.
# Either can be recorded without the other: an unrestored find often shows only
# how yellow it is, and a pristine spare only what shade it is.
#
# Shared by a machine's drive rows (drivedb) and by storage parts (the Colour and
# Yellowing specs), so a drive fitted in a machine and the same drive on the shelf
# are described in the same words.
BEZEL_COLOURS = [
    {"label": "Black", "hex": "#1a1b1d",
     "note": "black plastic or a painted bezel"},
    {"label": "Dark grey", "hex": "#4b4f55",
     "note": "a grey that reads darker than the case around it"},
    {"label": "Grey", "hex": "#8b9097", "note": "mid grey, with no warmth in it"},
    {"label": "Light grey", "hex": "#c3c7cc", "note": "pale grey, cooler than beige"},
    {"label": "White", "hex": "#f6f6f4", "note": "a true white, no cream in it"},
    {"label": "Off-white", "hex": "#ece8dc",
     "note": "white with a little cream, as made rather than as aged"},
    {"label": "Beige", "hex": "#dad0b8", "note": "the classic PC beige"},
    {"label": "Warm beige", "hex": "#cebb9a", "note": "beige with more brown in it"},
    {"label": "Grey-beige", "hex": "#c8c5b5",
     "note": "beige with the warmth taken out"},
]

# How far it has gone. `weight` is how much of `tint` to mix into the original
# shade to draw it -- a rendering, not data, so these numbers can be adjusted
# without touching a single record. Blank means it has not yellowed, or nobody has
# looked yet: the same blank every other unrecorded field uses.
YELLOWING = [
    {"label": "Lightly yellowed", "weight": 0.20, "tint": "#c49a44",
     "note": "just off its original shade; tells beside a clean part"},
    {"label": "Yellowed", "weight": 0.38, "tint": "#bd8f34",
     "note": "plainly yellow, evenly across the bezel"},
    {"label": "Heavily yellowed", "weight": 0.58, "tint": "#b3822c",
     "note": "deep yellow going to tan"},
    {"label": "Browned", "weight": 0.78, "tint": "#8a6a35",
     "note": "past yellow into brown; UV, heat or years of smoke"},
    {"label": "Unevenly yellowed", "weight": 0.15, "weight2": 0.55,
     "tint": "#bd8f34",
     "note": "patchy, or one side only -- a sun-facing edge, or the shadow of a "
             "bracket"},
]
BEZEL_COLOUR_LABELS = [c["label"] for c in BEZEL_COLOURS]
YELLOWING_LABELS = [y["label"] for y in YELLOWING]

# What to draw a yellowing level on when the original shade was never recorded:
# some pale plastic, which is what almost every yellowed bezel started as.
ASSUMED_BEZEL = "#ded7c6"


def bezel_colour(label):
    """The BEZEL_COLOURS entry for a recorded shade, or None for one from outside
    the vocabulary -- which is shown as its own words and no swatch."""
    return _by_label(BEZEL_COLOURS, label)


def yellowing_level(label):
    """The YELLOWING entry for a recorded level, or None."""
    return _by_label(YELLOWING, label)


def _by_label(vocab, label):
    want = (label or "").strip().lower()
    return next((v for v in vocab if v["label"].lower() == want), None) if want else None


def _mix(base, tint, weight):
    """`base` hex moved `weight` of the way towards `tint` hex."""
    pairs = [(int(base[i:i + 2], 16), int(tint[i:i + 2], 16)) for i in (1, 3, 5)]
    return "#" + "".join(f"{round(b + (t - b) * weight):02x}" for b, t in pairs)


def bezel_css(colour="", yellowing=""):
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


def bezel_swatch_map():
    """Every colour/yellowing pair as its CSS background, keyed 'colour|yellowing'.

    The browser repaints the swatch beside a menu from this rather than doing the
    mixing again in JavaScript, so there is one implementation of it."""
    out = {}
    for colour in ["", *BEZEL_COLOUR_LABELS]:
        for level in ["", *YELLOWING_LABELS]:
            css = bezel_css(colour, level)
            if css:
                out[f"{colour}|{level}"] = css
    return out

# --- specs parsing / merging -----------------------------------------------

def parse_specs(specs: str) -> list[tuple[str, str]]:
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


def build_specs(pairs) -> str:
    """Assemble ordered (key, value) pairs into a specs string, dropping blanks."""
    specs = ""
    for key, value in pairs:
        value = (value or "").strip()
        if value:
            specs = merge_spec(specs, key, value)
    return specs


# --- amounts / RAM ---------------------------------------------------------

_KB_UNITS = {"": 1024, "k": 1, "kb": 1, "m": 1024, "mb": 1024,
             "g": 1024 * 1024, "gb": 1024 * 1024,
             "t": 1024 * 1024 * 1024, "tb": 1024 * 1024 * 1024}


def to_kb(text: str):
    """'2MB'->2048, '512KB'->512, '2'->2048 (bare number assumed MB). None if
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
    """Memory amounts (Size/Memory) normalise to KB; others kept as typed."""
    if spec_key in ("Size", "Memory"):
        kb = to_kb(amt)
        if kb is not None:
            return f"{kb} KB"
    return amt


def fmt_kb(kb, display: bool = False) -> str:
    """A KB count in the unit a person would use. The one place that decides this,
    for spec columns, a machine's memory total and the figures on the stats page.

    Quantities are stored as plain KB integers so they sort and compare in SQL;
    which unit to say them in is a rendering question, answered here.

    A whole number of MB stays in MB rather than climbing to GB, because for this
    hardware the difference is meaningful: 2096128 KB is the 2047 MB BIOS limit,
    not "2 GB".

    Everything the default returns parses back to exactly the number of KB it was
    given, which is what the edit form and the stored specs string need -- both are
    read back and parsed on the next save. `display` is for text that is only ever
    read (a page, a label, a RAM total): there an amount that cannot be said
    exactly is rounded to three significant figures, "37.9 MB" rather than the
    strictly-true-but-useless "38828 KB".
    """
    if not kb:
        return ""
    if kb % (1024 * 1024) == 0:
        return f"{kb // (1024 * 1024)} GB"
    if kb % 1024 == 0:
        return f"{kb // 1024} MB"
    # The largest unit whose short decimal form still parses back to exactly this
    # many KB, so "1.2GB" comes back as "1.2 GB" rather than "1228.8 MB". Two
    # places as well as one, which is what lets a floppy's 1475 KB be the 1.44 MB
    # everyone calls it while still being reversible.
    for unit, mult in (("GB", 1024 * 1024), ("MB", 1024)):
        if kb < mult:
            continue
        for places in (1, 2):
            text = f"{kb / mult:.{places}f}"
            if round(float(text) * mult) == kb:
                return f"{text} {unit}"
    return _round_kb(kb) if display else f"{kb} KB"


def _round_kb(kb) -> str:
    """A KB count at three significant figures in the largest unit it fills, for
    text that is read and never parsed back. 1475 KB is the 1.44 MB of a floppy;
    38828 KB is a 37.9 MB drive. Neither parses back to the KB it came from, which
    is why this is not what the form or the specs string is given."""
    for unit, mult in (("GB", 1024 * 1024), ("MB", 1024)):
        if kb < mult:
            continue
        val = kb / mult
        # Three significant figures, without %g's habit of turning 1000 into 1e+03.
        text = f"{val:.0f}" if val >= 100 else f"{val:.1f}" if val >= 10 else f"{val:.2f}"
        if "." in text:
            text = text.rstrip("0").rstrip(".")
        return f"{text} {unit}"
    return f"{kb} KB"


# Common DRAM chips for machines with RAM soldered/socketed directly on the board
# (not on SIMMs/modules). Each is (part number, KB per chip, organisation).
RAM_CHIPS = [
    ("4116", 2, "16K×1"), ("4164", 8, "64K×1"), ("4416", 8, "16K×4"),
    ("4464", 32, "64K×4"), ("41256", 32, "256K×1"), ("44256", 128, "256K×4"),
    ("411000", 128, "1M×1"), ("514256", 128, "256K×4"),
]
RAM_CHIP_KB = {pn: kb for pn, kb, _ in RAM_CHIPS}
RAM_CHIP_ORG = {pn: org for pn, _kb, org in RAM_CHIPS}


def _chip_width(org):
    """Data-bits-per-chip from an organisation string: '256K×1' -> 1, '64K×4' -> 4."""
    m = re.search(r"[×x](\d+)\s*$", org or "")
    return int(m.group(1)) if m else 1


def _chip_depth(org):
    """The addressable depth from an organisation string: '64K×4' -> '64K'. Chips of
    the same depth are what make up a bank together, whatever their width."""
    return (org or "").split("×")[0].split("x")[0].strip()


def chip_capacity(counts):
    """Usable KB and whether parity is fitted, from [(chip, n), ...].

    A bank is made of chips of the same depth, and is nine bits wide where the
    ninth is parity. Chips are therefore grouped by depth and the group's total
    width decides: 18 bits at 64K deep is two banks of 8 data bits plus 2 parity,
    so 128 KB of the 144 KB fitted is usable.

    Grouping matters because a bank's data and parity are often different chips --
    an Amstrad PC1640 carries 4x 4464 for data with 2x 4164 alongside for their
    parity, and counting those two as data overstates the machine by 16 KB.
    """
    groups = {}
    for pn, n in counts:
        if not n:
            continue
        org = RAM_CHIP_ORG.get(pn, "")
        depth = _chip_depth(org)
        bits, kb = groups.get(depth, (0, 0))
        groups[depth] = (bits + n * _chip_width(org),
                         kb + n * RAM_CHIP_KB.get(pn, 0))
    total_kb, parity = 0, False
    for bits, kb in groups.values():
        if bits % 9 == 0:
            total_kb += kb * 8 // 9
            parity = True
        else:
            total_kb += kb
    return total_kb, parity


def format_ram_chips(counts):
    """[(chip, n), ...] -> '9× 41256 (256 KB + parity)' with the usable total."""
    counts = [(pn, n) for pn, n in counts if n]
    if not counts:
        return ""
    total_kb, parity = chip_capacity(counts)
    chips = ", ".join(f"{n}× {pn}" for pn, n in counts)
    return f"{chips} ({fmt_kb(total_kb, display=True)}{' + parity' if parity else ''})"


# Common memory modules for machines with RAM on SIMMs / SIPPs rather than
# soldered chips. Each is (slug for the form field, KB per module, label).
RAM_MODULES = [
    ("30p256k", 256, "256KB 30-pin"), ("30p1m", 1024, "1MB 30-pin"),
    ("30p4m", 4096, "4MB 30-pin"),
    ("sipp256k", 256, "256KB SIPP"), ("sipp1m", 1024, "1MB SIPP"),
    ("sipp4m", 4096, "4MB SIPP"),
    ("72p1m", 1024, "1MB 72-pin"), ("72p2m", 2048, "2MB 72-pin"),
    ("72p4m", 4096, "4MB 72-pin"), ("72p8m", 8192, "8MB 72-pin"),
    ("72p16m", 16384, "16MB 72-pin"), ("72p32m", 32768, "32MB 72-pin"),
]
RAM_MODULE_KB = {s: kb for s, kb, _ in RAM_MODULES}
RAM_MODULE_LABEL = {s: lbl for s, _kb, lbl in RAM_MODULES}


def format_ram_modules(counts):
    """[(slug, n), ...] -> '4× 1MB 30-pin, 2× 4MB 72-pin (12 MB)' with the total."""
    counts = [(s, n) for s, n in counts if n]
    if not counts:
        return ""
    total_kb = sum(n * RAM_MODULE_KB.get(s, 0) for s, n in counts)
    mods = ", ".join(f"{n}× {RAM_MODULE_LABEL[s]}" for s, n in counts)
    return f"{mods} ({fmt_kb(total_kb, display=True)})"


def ram_total_kb(modules, chips) -> int:
    """Usable KB fitted, from [(slug, n)] modules and [(chip, n)] chips. Parity
    chips are not capacity, so chip_capacity discounts them."""
    return (sum(n * RAM_MODULE_KB.get(slug, 0) for slug, n in modules if n)
            + chip_capacity(chips)[0])


def render_installed_ram(modules, chips, total_kb=None, note="") -> str:
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

PORT_CODES = [("I", "IDE"), ("C", "SCSI"), ("A", "SATA"), ("M", "MFM"),
              ("R", "RLL"), ("F", "Floppy"), ("S", "Serial"), ("P", "Parallel"),
              ("G", "Game"), ("K", "PS/2 keyboard"), ("O", "PS/2 mouse"),
              ("D", "DIN keyboard"), ("U", "USB")]

PORT_LEGEND = " ".join(f"{ltr}={name}" for ltr, name in PORT_CODES)
PORT_NAMES = [name for _, name in PORT_CODES]


def format_counts(items) -> str:
    """[(name, n), ...] -> 'n× name, ...' (the canonical count-list rendering)."""
    return ", ".join(f"{n}× {name}" if n and n > 1 else name for name, n in items)


_PORT_ITEM_RE = re.compile(r"^(?:(\d+)\s*[×x]\s*)?(.+)$")


def parse_port_list(value: str):
    """[(port, count), ...] if `value` is already an expanded port list such as
    'IDE, Floppy, 2× Serial' -- that is, every comma-separated item names a known
    port. None if it is not, which means it should be read as letter codes."""
    items = [tok.strip() for tok in (value or "").split(",") if tok.strip()]
    if not items:
        return None
    out = []
    for tok in items:
        m = _PORT_ITEM_RE.match(tok)
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
    counts = Counter()
    for tok in re.split(r"[\s,]+", (raw or "").strip()):
        if not tok:
            continue
        m = re.match(r"^(.+?)\s*[:*xX]\s*(\d+)$", tok)
        key, n = (m.group(1), int(m.group(2))) if m else (tok, 1)
        name = alias.get(key.upper())
        if name:
            counts[name] += n
    return ", ".join(f"{counts[name]}× {name}" if counts[name] > 1 else name
                     for name in SLOT_NAMES if counts.get(name))


# --- shared display helpers ------------------------------------------------

SHOUT_ACRONYMS = {
    "SCSI", "SATA", "PATA", "EISA", "ESDI", "VESA", "SVGA", "WXGA", "ATAPI",
    "BIOS", "UEFI", "DRAM", "SRAM", "SDRAM", "VRAM", "SIMM", "DIMM", "RIMM",
    "SIPP", "COAST", "CMOS", "MIDI", "EPROM", "EEPROM", "PROM", "MCGA",
    "PLCC", "NTSC", "SECAM", "WLAN", "ASIC",
}


def deshout(text: str) -> str:
    """De-shout a value word by word: a purely-uppercase token 5+ long that isn't
    a known acronym becomes Capitalised; short tokens, acronyms and part numbers
    are left alone."""
    out = []
    for tok in re.split(r"(\s+)", text or ""):
        core = tok.strip(".,:;()[]{}/\\\"'")
        if (core.isalpha() and core.isupper() and len(core) >= 5
                and core not in SHOUT_ACRONYMS):
            i = tok.find(core)
            tok = tok[:i] + core[0] + core[1:].lower() + tok[i + len(core):]
        out.append(tok)
    return "".join(out)


def display_name(row) -> str:
    if row.get("name"):
        return row["name"]
    joined = " ".join(p for p in (row.get("manufacturer", ""),
                                  row.get("model", "")) if p).strip()
    return joined or row.get("asset_id", "")


def type_label(t: str) -> str:
    return TYPE_LABELS.get(t, (t or "other").title())


def type_sort_key(t: str) -> int:
    try:
        return TYPE_ORDER.index(t)
    except ValueError:
        return len(TYPE_ORDER)


# Placeholder icon (served from /static/placeholders/) shown when an item has no
# photo -- same set as the old public site.
PLACEHOLDER = {
    "computer": "computer", "motherboard": "board", "cpu": "chip", "ram": "ram",
    "video": "card", "sound": "card", "network": "card", "io": "card",
    "storage": "drive", "optical": "disc", "floppy": "floppy", "psu": "psu",
    "cooler": "fan", "peripheral": "keyboard", "other": "box",
}


def placeholder_for(kind_or_type: str) -> str:
    return "placeholders/" + PLACEHOLDER.get(kind_or_type, "box") + ".svg"
