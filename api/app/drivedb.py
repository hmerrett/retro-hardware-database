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
from collections.abc import Iterable, Mapping, Sequence
from typing import TypedDict

from sqlalchemy.orm import Session

from . import entry
from .models import Computer, ComputerDrive


class Drive(TypedDict):
    """One fitted drive, in the same nine answers the row holds -- spelt out so
    that what builds one and what renders it are checked against each other, which
    a dict of mixed values is not."""

    count: int
    kind: str
    form_factor: str
    size: str
    media: str
    speed: str
    model: str
    colour: str
    yellowing: str


# Display forms, so a row renders as it is stored.
KINDS = ["floppy", "Gotek", "optical", "SD", "CF", "tape"]
# Both of these, and the four below, live in entry.py: a storage part is asked the
# same questions about the same drive, from the one table there (entry.STORAGE_ASKS),
# so a row on a machine and the same drive on the shelf cannot come to disagree.
FORM_FACTORS = entry.DRIVE_INCHES
SIZES = entry.FLOPPY_SIZES
# What an optical drive says instead of a capacity: the discs it takes and the
# rating on its front. Both vocabularies live in entry.py, because a storage part
# records the same two things about the same drive (see entry.OPTICAL_MEDIA /
# entry.OPTICAL_SPEEDS).
MEDIA = entry.OPTICAL_MEDIA
SPEEDS = entry.OPTICAL_SPEEDS

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
    "gray": "Grey",
    "dark gray": "Dark grey",
    "light gray": "Light grey",
    "grey beige": "Grey-beige",
    "gray beige": "Grey-beige",
    "off white": "Off-white",
    "cream": "Off-white",
    "ivory": "Off-white",
}
# What a person might write for each optical medium. Every spelling that drops the
# hyphens or the ±, because that is how they are typed, and "cd"/"dvd" alone for
# the drive nobody bothered to be precise about -- a bare "CD" drive is a reader,
# which is what CD-ROM says.
_MEDIA_WORDS = {m.lower(): m for m in entry.OPTICAL_MEDIA} | {
    "cd": "CD-ROM",
    "cdrom": "CD-ROM",
    "cd rom": "CD-ROM",
    "cdr": "CD-R",
    "cd r": "CD-R",
    "cdrw": "CD-RW",
    "cd rw": "CD-RW",
    "cdw": "CD-RW",
    "dvd": "DVD-ROM",
    "dvdrom": "DVD-ROM",
    "dvd rom": "DVD-ROM",
    "combo": "DVD/CD-RW combo",
    "dvd/cd-rw": "DVD/CD-RW combo",
    "dvdrw": "DVD±RW",
    "dvd-rw": "DVD±RW",
    "dvd+rw": "DVD±RW",
    "dvd rw": "DVD±RW",
    "dvdr": "DVD±RW",
    "dvd-r": "DVD±RW",
    "dvd+r": "DVD±RW",
    "dvd±r": "DVD±RW",
    "dvd rewriter": "DVD±RW",
    "dvd writer": "DVD±RW",
    "dvdram": "DVD-RAM",
    "dvd ram": "DVD-RAM",
    "bluray": "Blu-ray",
    "bd": "Blu-ray",
    "bd-rom": "Blu-ray",
}
_YELLOW_WORDS = {y["label"].lower(): y["label"] for y in entry.YELLOWING} | {
    "slightly yellowed": "Lightly yellowed",
    "lightly yellowing": "Lightly yellowed",
    "yellowing": "Yellowed",
    "yellow": "Yellowed",
    "very yellowed": "Heavily yellowed",
    "badly yellowed": "Heavily yellowed",
    "brown": "Browned",
    "browning": "Browned",
    "patchy yellowing": "Unevenly yellowed",
    "patchily yellowed": "Unevenly yellowed",
    "unevenly yellowing": "Unevenly yellowed",
    "patchy": "Unevenly yellowed",
}


def _phrase_re(words: Iterable[str], tail: str = "") -> re.Pattern[str]:
    """One alternation over every phrase, longest first -- so 'off-white' is not
    read as 'white' after a stray 'off-', nor 'heavily yellowed' as 'yellowed'
    after an adverb. `tail` is anything more the match has to satisfy."""
    return re.compile(
        r"\b("
        + "|".join(re.escape(w) for w in sorted(words, key=len, reverse=True))
        + r")\b"
        + tail,
        re.I,
    )


_COLOUR_RE = _phrase_re(_COLOUR_WORDS)
_YELLOW_RE = _phrase_re(_YELLOW_WORDS)
# A medium carrying on into "-something" is part of a longer name rather than the
# medium itself: a drive modelled "CD-120" is an optical drive, but those two
# letters are its model's and taking them would leave a bare "120" behind. The
# designations that have a hyphen of their own are matched whole before this can
# bite on them.
_MEDIA_RE = _phrase_re(_MEDIA_WORDS, tail=r"(?!-\w)")


def _take(pattern: re.Pattern[str], words: Mapping[str, str], text: str) -> tuple[str, str]:
    """(label, text without it) for the first phrase `pattern` finds."""
    m = pattern.search(text)
    if not m:
        return "", text
    return words[m.group(1).lower()], text[: m.start()] + " " + text[m.end() :]


_KIND_WORDS = {
    "floppy": "floppy",
    "fdd": "floppy",
    "gotek": "Gotek",
    "optical": "optical",
    "cd-rom": "optical",
    "cdrom": "optical",
    "cd": "optical",
    "dvd": "optical",
    "sd": "SD",
    "sdcard": "SD",
    "cf": "CF",
    "compactflash": "CF",
    "tape": "tape",
}
# Words that describe nothing once the kind is known.
_NOISE = {"drive", "drives", "emulator", "card", "x"}
_OPTICAL_WORDS = {w for w, k in _KIND_WORDS.items() if k == "optical"}


def _is_optical(text: str) -> bool:
    """Whether a segment describes an optical drive: it names a medium, or it says
    so outright. The only place a × rating can be, which is what keeps the "2 x" of
    '2 x 5.25" 360K' the two floppies it has always been."""
    return bool(_MEDIA_RE.search(text)) or any(
        word.strip(".,;()").lower() in _OPTICAL_WORDS for word in text.split()
    )


_COUNT_RE = re.compile(r"^\s*(\d+)\s*(?:[x×]\s*|\s)", re.I)
# The rating on the front. Not anchored like the count -- it turns up wherever the
# person writing it put it -- and no \b after the mark, because × is not a word
# character and would not have a boundary to sit against.
#
# One figure, or the run of them a writer quotes: "52x32x52x" and "4x 2x 20x" are
# one drive's write, rewrite and read speeds, and three of the four optical drives
# on file were written that way. Every figure has to carry the mark, so the "5" of
# a 5.25" bay standing after a rating is not read as another of them.
_FIGURE = r"\d+\s*[x×]"
_SPEED_RE = re.compile(rf"(?<![\w.])({_FIGURE}(?:\s*[/,]?\s*{_FIGURE})*)(?!\w)", re.I)
_DIGITS_RE = re.compile(r"\d+")


def _canon_speed(run: str) -> str:
    """A rating as it is written down here: '52x32x52x' and '4x 2x 20x' both become
    '52×/32×/52×', so the same drive reads the same however it was typed."""
    return "/".join(f"{n}×" for n in _DIGITS_RE.findall(run))


# The inch mark, in every form it actually arrives in. A straight quote is what a
# keyboard gives; a phone or a Mac autocorrects it to a curly one, and ″ is the
# typographically correct prime. Six of the eight drive descriptions on file used
# the curly quote, and without it 3.5” read as the drive's *model* -- the number
# went into the name of the thing rather than into its form factor.
_FORM_RE = re.compile(r"""(\d\.?\d*)\s*(?:["”“″]|''|-?\s*inch\b|in\b)""", re.I)
_SIZE_RE = re.compile(r"\b(\d+(?:\.\d+)?)\s*(KiB|MiB|GiB|K|KB|MB|GB)\b", re.I)

# The IEC spellings, by what someone might type them as. A size in a drive segment
# is what is written on the drive -- a 1.44MB floppy, a 4GB card -- and neither is
# a figure this end did the 1024 arithmetic for, so the unit is kept the way it was
# given rather than converted. What this settles is only the capitalisation, so
# "4gib" and "4GIB" are the one drive.
_IEC_SIZE_UNITS = {"KIB": "KiB", "MIB": "MiB", "GIB": "GiB"}


def _canon_size(number: str, unit: str) -> str:
    upper = unit.upper()
    unit = _IEC_SIZE_UNITS.get(upper) or ("K" if upper in ("K", "KB") else upper)
    number = number.rstrip(".")
    return f"{number}{unit}"


def parse_segment(text: str | None) -> Drive | None:
    """One typed drive ('2 x 5.25" 360K') as a dict, or None if nothing is left
    to say. Unrecognised words become the model, which is where a make belongs."""
    raw = " ".join((text or "").split())
    if not raw:
        return None
    # The rating first, and only where the segment is an optical drive's. A count
    # and a rating are both written "N×" and position cannot separate them: a person
    # types what is printed on the front of the drive first, and "48× CD-ROM" is one
    # drive, not forty-eight. So in a segment that is an optical drive's, a figure
    # carrying the mark is a rating -- render() writes such a segment's count as a
    # bare number for exactly that reason, and nothing else in the register is
    # measured in ×.
    speed = ""
    if _is_optical(raw):
        m = _SPEED_RE.search(raw)
        if m:
            speed = _canon_speed(m.group(1))
            raw = raw[: m.start()] + " " + raw[m.end() :]

    count = 1
    m = _COUNT_RE.match(raw)
    if m:
        count, raw = int(m.group(1)), raw[m.end() :]

    form = ""
    m = _FORM_RE.search(raw)
    if m and m.group(1) in ("5.25", "3.5", "8", "5", "3"):
        form = {"5": '5.25"', "3": '3.5"'}.get(m.group(1), f'{m.group(1)}"')
        raw = raw[: m.start()] + " " + raw[m.end() :]

    size = ""
    m = _SIZE_RE.search(raw)
    if m:
        size = _canon_size(m.group(1), m.group(2))
        raw = raw[: m.start()] + " " + raw[m.end() :]

    # Taken out whole, before the words are looked at one at a time: 'light grey'
    # and 'heavily yellowed' are each one phrase, not a colour beside a stray word
    # that would end up in the model. Yellowing goes first, so 'brown' is read as
    # browning rather than left for the colour pass to puzzle over.
    yellowing, raw = _take(_YELLOW_RE, _YELLOW_WORDS, raw)
    colour, raw = _take(_COLOUR_RE, _COLOUR_WORDS, raw)
    # Taken whole for the same reason: "CD-RW" is one designation, and read a word
    # at a time it would be a kind ("cd") beside a stray "rw" bound for the model.
    media, raw = _take(_MEDIA_RE, _MEDIA_WORDS, raw)

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
    # A named medium is only ever an optical drive's, and says so more surely than
    # the bare "cd" the kind list knows -- which the medium has just taken out of
    # the text on its way past.
    if not kind and media:
        kind = "optical"
    if not kind and (size.lower() in _FLOPPY_SIZES or form in FORM_FACTORS):
        kind = "floppy"
    model = " ".join(rest).strip(" -,;")
    if not (kind or size or form or model or colour or yellowing or media or speed):
        return None
    return {
        "count": count,
        "kind": kind,
        "form_factor": form,
        "size": size,
        "media": media,
        "speed": speed,
        "model": model,
        "colour": colour,
        "yellowing": yellowing,
    }


def from_string(text: str | None) -> tuple[list[Drive], str]:
    """A typed drives field as ([drive dict], note). A segment that yields
    nothing keeps its text in the note rather than being dropped."""
    drives: list[Drive] = []
    leftover: list[str] = []
    for seg in (text or "").split(";"):
        if not seg.strip():
            continue
        d = parse_segment(seg)
        if d:
            drives.append(d)
        else:
            leftover.append(seg.strip())
    return drives, "; ".join(leftover)


def render(drives: Iterable[Drive], note: str = "") -> str:
    """The canonical string: '2× 5.25" 360K floppy (beige, heavily yellowed)', or
    '5.25" 48× CD-RW optical' for the drive that takes discs rather than disks.

    The bezel goes in brackets at the end -- the shade it was made in, then how far
    it has yellowed -- where it reads as the aside it is and where parsing takes it
    back off again.

    The speed sits in front of the medium, which is where it is said out loud: a
    48× CD-RW, never a CD-RW at 48×. Being in the middle of the segment is also
    what keeps it clear of the count at the front, so a rendered row reads back as
    the row it was rendered from."""
    out = []
    for d in drives:
        bits = [
            d.get("model", ""),
            d.get("form_factor", ""),
            d.get("size", ""),
            d.get("speed", ""),
            d.get("media", ""),
            d.get("kind", ""),
        ]
        body = " ".join(b for b in bits if b)
        bezel = ", ".join(x.lower() for x in (d.get("colour"), d.get("yellowing")) if x)
        if bezel:
            body = f"{body} ({bezel})".strip()
        n = d.get("count") or 1
        if n > 1:
            # In a segment where the × belongs to a rating, the count goes without
            # one -- otherwise two unrated CD-RW drives would render "2× CD-RW
            # optical" and read back as one 2× drive. A bare number at the front is
            # a count and nothing else. The question is put to the parser's own
            # test, so the two cannot come to disagree about which segments those
            # are.
            body = f"{n} {body}" if _is_optical(body) else f"{n}× {body}"
        out.append(body)
    if note:
        out.append(note)
    return "; ".join(x for x in out if x)


def read(db: Session, computer: Computer) -> list[Drive]:
    """A machine's drives as dicts, in the order they were entered."""
    rows = (
        db.query(ComputerDrive)
        .filter(ComputerDrive.computer_id == computer.asset_id)
        .order_by(ComputerDrive.id)
        .all()
    )
    return [
        {
            "count": r.count or 1,
            "kind": r.kind,
            "form_factor": r.form_factor,
            "size": r.size,
            "media": r.media or "",
            "speed": r.speed or "",
            "model": r.model,
            "colour": r.colour or "",
            "yellowing": r.yellowing or "",
        }
        for r in rows
    ]


def write(
    db: Session,
    computer: Computer,
    drives: Sequence[Drive] | None = None,
    note: str | None = None,
) -> None:
    """Store a machine's drives and refresh the rendered string. drives=None
    leaves the rows alone, so a caller that only has a note does not wipe them."""
    aid = computer.asset_id
    if drives is not None:
        db.query(ComputerDrive).filter(ComputerDrive.computer_id == aid).delete(
            synchronize_session=False
        )
        for d in drives:
            db.add(
                ComputerDrive(
                    computer_id=aid,
                    count=d.get("count") or 1,
                    kind=d.get("kind", ""),
                    form_factor=d.get("form_factor", ""),
                    size=d.get("size", ""),
                    media=d.get("media", ""),
                    speed=d.get("speed", ""),
                    model=d.get("model", ""),
                    colour=d.get("colour", ""),
                    yellowing=d.get("yellowing", ""),
                )
            )
        db.flush()
    if note is not None:
        computer.drives_note = note
    computer.drives = render(read(db, computer), computer.drives_note or "")
