"""Files kept beside the register -- drivers, manuals, ROM dumps, the utility disk
that came with a card -- and the names they are for.

The register's other tables hang off one asset id. These do not, on purpose. A
Trident 8900 driver is a fact about that card as a model, not about the particular
one on the shelf, and a collection holding three of them would otherwise carry the
same download three times and lose two of them the day two cards were disposed of.
So a file is tagged with the names it covers, and every item answering to one of
those names offers it -- a computer or a part, since the same disk often covers
both the card and the machine it shipped in.

What an item answers to is `keys_for`: its display name, its model, its maker and
model together, and its own asset id. That last one is how a file is pinned to a
single unit when it really is about that unit -- a receipt, a photograph of a repair
-- without needing a second mechanism for it.

Matching is containment on a folded form of the name: a tag matches an item when
the item's name has the tag inside it. That is what makes one tag cover a range --
"Creative Labs Sound Blaster" is on the AWE32, the 16 and the Pro, because each of
their names has it in -- while a tag that names one card exactly still lands on that
card alone. It goes one way only: the broader name reaches the narrower thing, never
the other way about, so a driver written for the AWE32 does not turn up on a plain
Sound Blaster.

The fold drops case and every space, because "Sound Blaster", "soundblaster" and
"SOUND  BLASTER" are one name written by three people.

This module owns the bytes too. The name on disk is generated and the uploaded name
is only ever data -- see `save`.
"""
from __future__ import annotations

import os
import re
import secrets
from datetime import datetime, timezone
from pathlib import Path

from sqlalchemy import literal, or_

from .entry import GIB, KIB, MIB
from .models import FileTag, StoredFile

FILES_DIR = Path(os.getenv("RHDB_FILES_DIR", "/app/files"))

# What one upload may weigh. A driver disk is a few hundred KiB and a CD image is
# not something to keep in a register, so this is generous rather than a guess at
# the largest useful file.
MAX_BYTES = 64 * 1024 * 1024

# Kept for the download's own name, and to give the stored copy a recognisable
# suffix. Anything else keeps its bytes and loses its extension -- the file is
# served as an attachment either way.
_SAFE_SUFFIX = re.compile(r"^\.[A-Za-z0-9]{1,8}$")


def fold(text) -> str:
    """The form several spellings of one name have in common: no spaces at all, no
    case. Every space rather than runs of them, because a name is as often written
    closed up as apart -- SoundBlaster, Sound Blaster -- and neither spelling is the
    wrong one to have typed."""
    return "".join((text or "").split()).lower()


def matches(name, tag) -> bool:
    """Whether a file tagged `tag` belongs to something called `name`. Containment,
    not equality, and in that direction only."""
    name_fold, tag_fold = fold(name), fold(tag)
    return bool(tag_fold) and tag_fold in name_fold


def keys_for(item) -> set[str]:
    """The folded names an item answers to. `item` is a dict of the record's own
    columns -- what to_dict gives -- so this works for a computer and a part alike.

    The display name is what the page calls it; the model and the maker-and-model
    are the two ways somebody would write the same card down; the asset id is how a
    file is pinned to one unit. Blanks are dropped rather than matching every item
    whose model nobody filled in."""
    maker = (item.get("manufacturer") or "").strip()
    model = (item.get("model") or "").strip()
    names = [item.get("name") or "", model, f"{maker} {model}".strip(),
             item.get("asset_id") or ""]
    return {fold(n) for n in names if fold(n)}


def _file_ids_for(db, keys):
    """The ids of files whose tags are inside any of these folded names.

    Two steps on purpose. LIKE narrows it in the database, so this does not read
    every tag on file to draw one page; then the same test is made again in Python,
    because a tag holding a % or an _ is a wildcard to LIKE and an ordinary
    character to everyone else. The database is the filter, Python is the
    authority."""
    if not keys:
        return set()
    hits = (db.query(FileTag.file_id, FileTag.fold)
            .filter(or_(*[literal(key).contains(FileTag.fold) for key in keys]))
            .all())
    return {fid for fid, tag_fold in hits
            if tag_fold and any(tag_fold in key for key in keys)}


def for_item(db, item):
    """Every file whose tags this item's names contain, newest first, each with its
    tags attached as `.tags`."""
    ids = _file_ids_for(db, keys_for(item))
    if not ids:
        return []
    rows = (db.query(StoredFile).filter(StoredFile.id.in_(ids))
            .order_by(StoredFile.created_at.desc(), StoredFile.id.desc()).all())
    return with_tags(db, rows)


def with_tags(db, rows):
    """The same rows, each carrying its tags in one extra query rather than one
    per file."""
    rows = list(rows)
    if not rows:
        return []
    tags: dict[int, list[str]] = {}
    for row in (db.query(FileTag)
                .filter(FileTag.file_id.in_([r.id for r in rows]))
                .order_by(FileTag.id).all()):
        tags.setdefault(row.file_id, []).append(row.tag)
    for row in rows:
        row.tags = tags.get(row.id, [])
    return rows


def all_files(db, tag=""):
    """Everything on file, newest first -- or, given a name, what something called
    that would be offered. The same rule the item pages use, so following a tag
    from a page shows what that page shows and not a narrower list."""
    q = db.query(StoredFile)
    if fold(tag):
        ids = _file_ids_for(db, {fold(tag)})
        if not ids:
            return []
        q = q.filter(StoredFile.id.in_(ids))
    return with_tags(db, q.order_by(StoredFile.created_at.desc(),
                                    StoredFile.id.desc()).all())


def parse_tags(text) -> list[str]:
    """The tags box as a list: one name per line or separated by commas, blanks
    dropped and each name kept once, in the order they were written."""
    out, seen = [], set()
    for raw in re.split(r"[,\n]", text or ""):
        name = " ".join(raw.split())
        if name and fold(name) not in seen and len(name) <= 120:
            seen.add(fold(name))
            out.append(name)
    return out


def set_tags(db, stored: StoredFile, tags):
    """Replace a file's tags with these. Replace rather than add, because the box
    on the page shows all of them and what it shows is what a save means."""
    db.query(FileTag).filter(FileTag.file_id == stored.id).delete(
        synchronize_session=False)
    for tag in parse_tags("\n".join(tags) if not isinstance(tags, str) else tags):
        db.add(FileTag(file_id=stored.id, tag=tag, fold=fold(tag)))
    db.flush()


def save(db, upload, tags, note=""):
    """Store an upload and file it under `tags`. Returns the row, or None for an
    empty upload; raises ValueError if it is over MAX_BYTES.

    The name on disk is generated and the uploaded name is only ever data. A
    filename is the one part of an upload chosen entirely by whoever sent it, and
    the moment it is used as a path it decides where the bytes land."""
    name = Path(upload.filename or "").name
    if not name:
        return None
    suffix = Path(name).suffix
    if not _SAFE_SUFFIX.match(suffix):
        suffix = ""
    FILES_DIR.mkdir(parents=True, exist_ok=True)
    stored = f"{secrets.token_hex(16)}{suffix.lower()}"
    dest = FILES_DIR / stored
    size = 0
    with dest.open("wb") as out:
        while chunk := upload.file.read(1024 * 1024):
            size += len(chunk)
            if size > MAX_BYTES:
                out.close()
                dest.unlink(missing_ok=True)
                raise ValueError(f"{name} is over {MAX_BYTES // (1024 * 1024)} {MIB}")
            out.write(chunk)
    if not size:
        dest.unlink(missing_ok=True)
        return None
    row = StoredFile(stored=stored, filename=name[:255], size=size,
                     note=(note or "").strip()[:255],
                     created_at=datetime.now(timezone.utc).replace(tzinfo=None))
    db.add(row)
    db.flush()
    set_tags(db, row, tags)
    return row


def path_of(stored: StoredFile) -> Path:
    return FILES_DIR / stored.stored


def remove(db, stored: StoredFile):
    """Forget a file, bytes and all. The tags go with it (the foreign key
    cascades), and the row is gone whether or not the file was still on disk --
    a record pointing at nothing is worse than no record."""
    path_of(stored).unlink(missing_ok=True)
    db.query(FileTag).filter(FileTag.file_id == stored.id).delete(
        synchronize_session=False)
    db.delete(stored)


def human_size(n) -> str:
    """A size as it would be said out loud, which is what a download link wants."""
    n = int(n or 0)
    if n < 1024:
        return f"{n} B"
    for unit, scale in ((KIB, 1024), (MIB, 1024 ** 2), (GIB, 1024 ** 3)):
        if n < scale * 1024 or unit == GIB:
            size = n / scale
            return f"{size:.0f} {unit}" if size >= 10 else f"{size:.1f} {unit}"
    return f"{n} B"
