"""What a file is, read from its name and its size: the drawing it gets on a list,
the list that finds it, and the size it is given as.

None of this decides anything. Where a file appears is what it is linked to, and
who may see it is a tick somebody made (ADR-0028, ADR-0009); this is only how it is
drawn. It is worked out on every page rather than stored, so a better answer for an
extension is a change here and nowhere else, and nothing already on file has to be
rewritten to get it.

A disk image is the one kind whose size says something its name does not. An .img
is a floppy as often as not, and the size says which floppy: 1,474,560 bytes is a
3½″ 1.44M disk and 368,640 a 5¼″ 360K one. So an image of a floppy is drawn as that
floppy and given the capacity printed on the disk -- which is what somebody writing
it back needs to know -- rather than "1.4 MiB", which nobody ever wrote on one.
"""

from __future__ import annotations

from pathlib import PurePosixPath
from typing import NamedTuple

from .entry import GIB, KIB, MIB

# The lists a file can be found under, in the order the page offers them, and what
# each is called there. Lower case because they are tabs (interface-text), apart
# from the acronym, which keeps its capitals wherever it falls.
GROUPS: dict[str, str] = {
    "document": "documents",
    "disk": "disk images",
    "rom": "ROMs",
    "picture": "pictures",
    "archive": "archives",
    "program": "programs",
    "sound": "sounds",
    "other": "other",
}

# Each drawing, and the list it belongs to. The five disks are one list: somebody
# looking for the image of a disk is not yet asking which sort of disk it was.
DRAWINGS: dict[str, str] = {
    "floppy35": "disk",
    "floppy525": "disk",
    "harddisk": "disk",
    "cd": "disk",
    "tape": "disk",
    "rom": "rom",
    "document": "document",
    "picture": "picture",
    "archive": "archive",
    "program": "program",
    "sound": "sound",
    "other": "other",
}

_EXTENSIONS: dict[str, str] = {}
for _drawing, _names in (
    # The images of a floppy that carry no size of their own worth reading: flux
    # captures, copy-protection formats, and the machines whose disks were one size.
    ("floppy35", "adf st msa d81 dsk hfe scp ipf imd td0 dmk fdi"),
    ("floppy525", "d64 d71 g64 nib woz ssd dsd"),
    ("harddisk", "vhd vhdx hdf hdi hdd vmdk qcow2"),
    ("cd", "iso cue ccd mdf mds nrg cdi gdi chd toast"),
    ("tape", "tap tzx tsx cas uef cdt t64 csw"),
    ("rom", "rom hex jed srec s19 ihx"),
    ("document", "pdf djvu djv txt doc docx rtf odt wri htm html md nfo diz ps"),
    ("picture", "jpg jpeg png gif tif tiff bmp pcx iff lbm heic webp svg"),
    ("archive", "zip 7z rar lha lzh arj arc zoo tar gz tgz bz2 xz sit sea hqx cab cpt lzx dms"),
    ("program", "exe com bat cmd sys prg bas app sh"),
    ("sound", "wav mid midi voc mod s3m xm mp3 flac ogg aif aiff"),
):
    for _name in _names.split():
        _EXTENSIONS[_name] = _drawing

# A raw image of a PC floppy, under any of the names one goes by. What it is is
# decided by how big it is.
_BY_SIZE = frozenset({"img", "ima", "vfd", "flp"})

# The floppies a raw image can be, by the exact number of bytes on one, and what is
# printed on the disk. Exact, because an image is a copy of every sector: one byte
# either way is a file that happens to be near a floppy's size, not a floppy.
_FLOPPIES: dict[int, tuple[str, str]] = {
    160 * 1024: ("floppy525", "5¼″ 160K"),
    180 * 1024: ("floppy525", "5¼″ 180K"),
    320 * 1024: ("floppy525", "5¼″ 320K"),
    360 * 1024: ("floppy525", "5¼″ 360K"),
    1200 * 1024: ("floppy525", "5¼″ 1.2M"),
    720 * 1024: ("floppy35", "3½″ 720K"),
    1440 * 1024: ("floppy35", "3½″ 1.44M"),
    1680 * 1024: ("floppy35", "3½″ 1.68M"),
    2880 * 1024: ("floppy35", "3½″ 2.88M"),
}
# An Amiga disk is its own format, and its size means one thing.
_AMIGA = {880 * 1024: "3½″ 880K", 1760 * 1024: "3½″ 1.76M"}

# Above this a raw image is not a floppy of any size ever made, so it is a disk.
_LARGEST_FLOPPY = 3 * 1024 * 1024
# A .bin is a ROM dump or a CD image, and only the size tells them apart: the
# largest ROM chip anyone will have read is well under this, and a CD image well
# over it.
_LARGEST_ROM = 4 * 1024 * 1024


# What each drawing is called in a sentence, for the line under a file's name on
# its own page.
NOUNS: dict[str, str] = {
    "floppy35": "floppy image",
    "floppy525": "floppy image",
    "harddisk": "hard disk image",
    "cd": "CD image",
    "tape": "tape image",
    "rom": "ROM image",
    "document": "document",
    "picture": "picture",
    "archive": "archive",
    "program": "program",
    "sound": "sound",
    "other": "file",
}


class What(NamedTuple):
    """What a file is, for drawing it: the picture, the list it is found under, its
    size as it would be said, the extension to print under the picture, what to
    call it in a sentence, and whether the page offers to show it rather than save
    it -- which only its name decides here, and its bytes decide when it is asked
    for (filesdb.is_pdf, ADR-0030)."""

    drawing: str
    group: str
    size: str
    extension: str
    noun: str
    viewable: bool


def human_size(n: int | None) -> str:
    """A size as it would be said out loud, which is what a download link wants."""
    n = int(n or 0)
    if n < 1024:
        return f"{n} B"
    for unit, scale in ((KIB, 1024), (MIB, 1024**2), (GIB, 1024**3)):
        if n < scale * 1024 or unit == GIB:
            size = n / scale
            return f"{size:.0f} {unit}" if size >= 10 else f"{size:.1f} {unit}"
    return f"{n} B"


def extension(filename: str | None) -> str:
    """The end of a file's name, lower case and without its dot: "" for none."""
    return PurePosixPath(filename or "").suffix.lower().lstrip(".")


def of(filename: str | None, size: int | None) -> What:
    """What this file is, from its name and how big it is."""
    ext = extension(filename)
    n = int(size or 0)
    said = human_size(n)
    if ext in _BY_SIZE:
        if n in _FLOPPIES:
            drawing, said = _FLOPPIES[n]
        else:
            drawing = "floppy35" if n < _LARGEST_FLOPPY else "harddisk"
    elif ext == "adf":
        drawing, said = "floppy35", _AMIGA.get(n, said)
    elif ext == "bin":
        drawing = "rom" if n < _LARGEST_ROM else "cd"
    else:
        drawing = _EXTENSIONS.get(ext, "other")
    return What(drawing, DRAWINGS[drawing], said, ext, NOUNS[drawing], ext == "pdf")
