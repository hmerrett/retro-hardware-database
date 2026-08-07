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
"""
from __future__ import annotations

import re

from . import entry
from .models import ComputerDrive

# Display forms, so a row renders as it is stored.
KINDS = ["floppy", "Gotek", "optical", "SD", "CF", "tape"]
FORM_FACTORS = ['5.25"', '3.5"', '8"']
# The media designations that actually turn up on this hardware.
SIZES = ["160K", "180K", "320K", "360K", "720K", "1.2MB", "1.44MB", "2.88MB"]

# A size that only ever belongs to a floppy, so a segment naming one but no kind
# is a floppy -- which is how '2 x 5.25" 360K' was always meant to read.
_FLOPPY_SIZES = {s.lower() for s in SIZES}

# The bezel: the shade it was made in, and how far it has yellowed since. Both
# vocabularies live in entry.py, because storage parts record the same two things
# about the same plastic (see entry.BEZEL_COLOURS / entry.YELLOWING).
#
# What a person might type for each. The American spellings and the looser words
# are here so a typed drives field reads the same as the menus, and every label
# answers to itself.
_COLOUR_WORDS = {c["label"].lower(): c["label"] for c in entry.BEZEL_COLOURS} | {
    "gray": "Grey", "dark gray": "Dark grey", "light gray": "Light grey",
    "grey beige": "Grey-beige", "gray beige": "Grey-beige",
    "off white": "Off-white", "cream": "Off-white", "ivory": "Off-white",
}
_YELLOW_WORDS = {y["label"].lower(): y["label"] for y in entry.YELLOWING} | {
    "slightly yellowed": "Lightly yellowed", "lightly yellowing": "Lightly yellowed",
    "yellowing": "Yellowed", "yellow": "Yellowed",
    "very yellowed": "Heavily yellowed", "badly yellowed": "Heavily yellowed",
    "brown": "Browned", "browning": "Browned",
    "patchy yellowing": "Unevenly yellowed", "patchily yellowed": "Unevenly yellowed",
    "unevenly yellowing": "Unevenly yellowed", "patchy": "Unevenly yellowed",
}


def _phrase_re(words):
    """One alternation over every phrase, longest first -- so 'off-white' is not
    read as 'white' after a stray 'off-', nor 'heavily yellowed' as 'yellowed'
    after an adverb."""
    return re.compile(r"\b(" + "|".join(re.escape(w) for w in
                                        sorted(words, key=len, reverse=True))
                      + r")\b", re.I)


_COLOUR_RE = _phrase_re(_COLOUR_WORDS)
_YELLOW_RE = _phrase_re(_YELLOW_WORDS)


def _take(pattern, words, text):
    """(label, text without it) for the first phrase `pattern` finds."""
    m = pattern.search(text)
    if not m:
        return "", text
    return words[m.group(1).lower()], text[:m.start()] + " " + text[m.end():]

_KIND_WORDS = {"floppy": "floppy", "fdd": "floppy", "gotek": "Gotek",
               "optical": "optical", "cd-rom": "optical", "cdrom": "optical",
               "cd": "optical", "dvd": "optical", "sd": "SD", "sdcard": "SD",
               "cf": "CF", "compactflash": "CF", "tape": "tape"}
# Words that describe nothing once the kind is known.
_NOISE = {"drive", "drives", "emulator", "card", "x"}

_COUNT_RE = re.compile(r"^\s*(\d+)\s*(?:[x×]\s*|\s)", re.I)
# The inch mark, in every form it actually arrives in. A straight quote is what a
# keyboard gives; a phone or a Mac autocorrects it to a curly one, and ″ is the
# typographically correct prime. Six of the eight drive descriptions on file used
# the curly quote, and without it 3.5” read as the drive's *model* -- the number
# went into the name of the thing rather than into its form factor.
_FORM_RE = re.compile(r"""(\d\.?\d*)\s*(?:["”“″]|''|-?\s*inch\b|in\b)""", re.I)
_SIZE_RE = re.compile(r"\b(\d+(?:\.\d+)?)\s*(K|KB|MB|GB)\b", re.I)


def _canon_size(number, unit):
    unit = unit.upper()
    unit = "K" if unit in ("K", "KB") else unit
    number = number.rstrip(".")
    return f"{number}{unit}"


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
    # and 'heavily yellowed' are each one phrase, not a colour beside a stray word
    # that would end up in the model. Yellowing goes first, so 'brown' is read as
    # browning rather than left for the colour pass to puzzle over.
    yellowing, raw = _take(_YELLOW_RE, _YELLOW_WORDS, raw)
    colour, raw = _take(_COLOUR_RE, _COLOUR_WORDS, raw)

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
    if not (kind or size or form or model or colour or yellowing):
        return None
    return {"count": count, "kind": kind, "form_factor": form, "size": size,
            "model": model, "colour": colour, "yellowing": yellowing}


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
    """The canonical string: '2× 5.25" 360K floppy (beige, heavily yellowed)'.

    The bezel goes in brackets at the end -- the shade it was made in, then how far
    it has yellowed -- where it reads as the aside it is and where parsing takes it
    back off again."""
    out = []
    for d in drives:
        bits = [d.get("model", ""), d.get("form_factor", ""), d.get("size", ""),
                d.get("kind", "")]
        body = " ".join(b for b in bits if b)
        bezel = ", ".join(x.lower() for x in (d.get("colour"), d.get("yellowing"))
                          if x)
        if bezel:
            body = f"{body} ({bezel})".strip()
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
             "size": r.size, "model": r.model, "colour": r.colour or "",
             "yellowing": r.yellowing or ""} for r in rows]


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
                                 colour=d.get("colour", ""),
                                 yellowing=d.get("yellowing", "")))
        db.flush()
    if note is not None:
        computer.drives_note = note
    computer.drives = render(read(db, computer), computer.drives_note or "")
