"""A machine's fitted removable-media drives: rows in, canonical string out.

The same split as specstruct/specdb and ramdb: the computer_drive rows are the
source of truth and computers.drives is a rendered cache of them, kept for
display, search, labels and the wire format.

Parsing here reads what a person typed ('2 x 5.25" 360K', '1x GOTEK') and stores
the structure. That is the specstruct.parse job, not the mistake ramdb removed:
what must never happen is parsing our own rendered output back into storage.
Anything a segment does not yield goes to drives_note verbatim.

    write(db, computer, drives, note)   rows -> table, and refresh the string
    read(db, computer)                  table -> [dict]
    from_string(text)                   typed text -> ([dict], leftover note)
    swatch(colour)                      a colour's entry in COLOURS, or None
"""
from __future__ import annotations

import re

from .models import ComputerDrive

# Display forms, so a row renders as it is stored.
KINDS = ["floppy", "Gotek", "optical", "SD", "CF", "tape"]
FORM_FACTORS = ['5.25"', '3.5"', '8"']
# The media designations that actually turn up on this hardware.
SIZES = ["160K", "180K", "320K", "360K", "720K", "1.2MB", "1.44MB", "2.88MB"]

# A size that only ever belongs to a floppy, so a segment naming one but no kind
# is a floppy -- which is how '2 x 5.25" 360K' was always meant to read.
_FLOPPY_SIZES = {s.lower() for s in SIZES}

# The colour of the bezel, as it looks now rather than as it was made: half of
# what tells two otherwise identical drives apart in a box of spares, and the
# thing to check against the machine before fitting one. The hex is a swatch to
# hold a real bezel up to, not a measurement -- `hex2` makes a two-tone swatch for
# a drive that has yellowed unevenly.
#
# It is one field, deliberately: a bezel has one colour to record, and "beige, but
# now heavily yellowed" is a story for the drives note, not two columns to keep in
# step. The factory shades come first because that is where every bezel started.
COLOURS = [
    {"label": "Black", "group": "As it was made", "hex": "#1a1b1d",
     "note": "black plastic or a painted bezel"},
    {"label": "Dark grey", "group": "As it was made", "hex": "#4b4f55",
     "note": "a grey that reads darker than the case around it"},
    {"label": "Grey", "group": "As it was made", "hex": "#8b9097",
     "note": "mid grey, with no warmth in it"},
    {"label": "Light grey", "group": "As it was made", "hex": "#c3c7cc",
     "note": "pale grey, cooler than beige"},
    {"label": "White", "group": "As it was made", "hex": "#f6f6f4",
     "note": "a true white, no cream in it"},
    {"label": "Off-white", "group": "As it was made", "hex": "#ece8dc",
     "note": "white with a little cream, as made rather than as aged"},
    {"label": "Beige", "group": "As it was made", "hex": "#dad0b8",
     "note": "the classic PC beige"},
    {"label": "Warm beige", "group": "As it was made", "hex": "#cebb9a",
     "note": "beige with more brown in it"},
    {"label": "Grey-beige", "group": "As it was made", "hex": "#c8c5b5",
     "note": "beige with the warmth taken out"},
    {"label": "Lightly yellowed", "group": "Yellowed with age", "hex": "#e2d3a6",
     "note": "just off its original shade; tells beside a clean part"},
    {"label": "Yellowed", "group": "Yellowed with age", "hex": "#d5bd7d",
     "note": "plainly yellow, evenly across the bezel"},
    {"label": "Heavily yellowed", "group": "Yellowed with age", "hex": "#c2a457",
     "note": "deep yellow going to tan"},
    {"label": "Browned", "group": "Yellowed with age", "hex": "#a2834b",
     "note": "past yellow into brown; UV, heat or years of smoke"},
    {"label": "Unevenly yellowed", "group": "Yellowed with age", "hex": "#dad0b8",
     "hex2": "#c2a457",
     "note": "patchy, or one side only -- a sun-facing edge, or the shadow of a "
             "bracket"},
]
COLOUR_LABELS = [c["label"] for c in COLOURS]
COLOUR_GROUPS = list(dict.fromkeys(c["group"] for c in COLOURS))

# What a person might type for one of them. The American spellings and the looser
# words are here so a typed drives field reads the same as the menu, and every
# label answers to itself.
_COLOUR_WORDS = {c["label"].lower(): c["label"] for c in COLOURS} | {
    "gray": "Grey", "dark gray": "Dark grey", "light gray": "Light grey",
    "grey beige": "Grey-beige", "gray beige": "Grey-beige",
    "off white": "Off-white", "cream": "Off-white", "ivory": "Off-white",
    "slightly yellowed": "Lightly yellowed", "yellowing": "Yellowed",
    "very yellowed": "Heavily yellowed", "badly yellowed": "Heavily yellowed",
    "brown": "Browned", "patchy yellowing": "Unevenly yellowed",
    "unevenly yellowing": "Unevenly yellowed", "patchy": "Unevenly yellowed",
}
# Longest first, so 'off-white' is not read as 'white' with a stray 'off-', and
# 'heavily yellowed' not as 'yellowed' after an adverb.
_COLOUR_RE = re.compile(
    r"\b(" + "|".join(re.escape(w) for w in
                      sorted(_COLOUR_WORDS, key=len, reverse=True)) + r")\b", re.I)

_KIND_WORDS = {"floppy": "floppy", "fdd": "floppy", "gotek": "Gotek",
               "optical": "optical", "cd-rom": "optical", "cdrom": "optical",
               "cd": "optical", "dvd": "optical", "sd": "SD", "sdcard": "SD",
               "cf": "CF", "compactflash": "CF", "tape": "tape"}
# Words that describe nothing once the kind is known.
_NOISE = {"drive", "drives", "emulator", "card", "x"}

_COUNT_RE = re.compile(r"^\s*(\d+)\s*(?:[x×]\s*|\s)", re.I)
_FORM_RE = re.compile(r"""(\d\.?\d*)\s*(?:"|''|-?\s*inch\b|in\b)""", re.I)
_SIZE_RE = re.compile(r"\b(\d+(?:\.\d+)?)\s*(K|KB|MB|GB)\b", re.I)


def _canon_size(number, unit):
    unit = unit.upper()
    unit = "K" if unit in ("K", "KB") else unit
    number = number.rstrip(".")
    return f"{number}{unit}"


def swatch(colour):
    """The COLOURS entry for a recorded colour, or None for one from before the
    menu (or from nowhere), which is shown as its own words and no swatch."""
    if not colour:
        return None
    want = colour.strip().lower()
    return next((c for c in COLOURS if c["label"].lower() == want), None)


def parse_segment(text):
    """One typed drive ('2 x 5.25" 360K') as a dict, or None if nothing is left
    to say. Unrecognised words become the model, which is where a make belongs."""
    raw = " ".join((text or "").split())
    if not raw:
        return None
    count = 1
    m = _COUNT_RE.match(raw)
    if m:
        count, raw = int(m.group(1)), raw[m.end():]

    form = ""
    m = _FORM_RE.search(raw)
    if m and m.group(1) in ("5.25", "3.5", "8", "5", "3"):
        form = {"5": '5.25"', "3": '3.5"'}.get(m.group(1), f'{m.group(1)}"')
        raw = raw[:m.start()] + " " + raw[m.end():]

    size = ""
    m = _SIZE_RE.search(raw)
    if m:
        size = _canon_size(m.group(1), m.group(2))
        raw = raw[:m.start()] + " " + raw[m.end():]

    # Taken out whole, before the words are looked at one at a time: 'light grey'
    # and 'heavily yellowed' are each one colour, not a colour beside a stray word
    # that would end up in the model.
    colour = ""
    m = _COLOUR_RE.search(raw)
    if m:
        colour = _COLOUR_WORDS[m.group(1).lower()]
        raw = raw[:m.start()] + " " + raw[m.end():]

    kind, rest = "", []
    for word in raw.replace("(", " ").replace(")", " ").split():
        key = word.strip(".,;").lower()
        if key in _KIND_WORDS:
            # An emulator is a Gotek even when the word 'floppy' is next to it.
            if not kind or _KIND_WORDS[key] == "Gotek":
                kind = _KIND_WORDS[key]
        elif key in _NOISE or not key:
            continue
        else:
            rest.append(word)
    if not kind and (size.lower() in _FLOPPY_SIZES or form in FORM_FACTORS):
        kind = "floppy"
    model = " ".join(rest).strip(" -,;")
    if not (kind or size or form or model or colour):
        return None
    return {"count": count, "kind": kind, "form_factor": form, "size": size,
            "model": model, "colour": colour}


def from_string(text):
    """A typed drives field as ([drive dict], note). A segment that yields
    nothing keeps its text in the note rather than being dropped."""
    drives, leftover = [], []
    for seg in (text or "").split(";"):
        if not seg.strip():
            continue
        d = parse_segment(seg)
        if d:
            drives.append(d)
        else:
            leftover.append(seg.strip())
    return drives, "; ".join(leftover)


def render(drives, note=""):
    """The canonical string: '2× 5.25" 360K floppy (beige)'.

    The colour goes in brackets at the end, where it reads as the aside it is and
    where parsing takes it back off again."""
    out = []
    for d in drives:
        bits = [d.get("model", ""), d.get("form_factor", ""), d.get("size", ""),
                d.get("kind", "")]
        body = " ".join(b for b in bits if b)
        if d.get("colour"):
            body = f"{body} ({d['colour'].lower()})".strip()
        n = d.get("count") or 1
        out.append(f"{n}× {body}" if n > 1 else body)
    if note:
        out.append(note)
    return "; ".join(x for x in out if x)


def read(db, computer):
    """A machine's drives as dicts, in the order they were entered."""
    rows = (db.query(ComputerDrive)
            .filter(ComputerDrive.computer_id == computer.asset_id)
            .order_by(ComputerDrive.id).all())
    return [{"count": r.count or 1, "kind": r.kind, "form_factor": r.form_factor,
             "size": r.size, "model": r.model, "colour": r.colour or ""}
            for r in rows]


def write(db, computer, drives=None, note=None):
    """Store a machine's drives and refresh the rendered string. drives=None
    leaves the rows alone, so a caller that only has a note does not wipe them."""
    aid = computer.asset_id
    if drives is not None:
        db.query(ComputerDrive).filter(
            ComputerDrive.computer_id == aid).delete(synchronize_session=False)
        for d in drives:
            db.add(ComputerDrive(computer_id=aid, count=d.get("count") or 1,
                                 kind=d.get("kind", ""),
                                 form_factor=d.get("form_factor", ""),
                                 size=d.get("size", ""),
                                 model=d.get("model", ""),
                                 colour=d.get("colour", "")))
        db.flush()
    if note is not None:
        computer.drives_note = note
    computer.drives = render(read(db, computer), computer.drives_note or "")
