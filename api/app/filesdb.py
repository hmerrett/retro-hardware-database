"""Files kept beside the register -- drivers, manuals, ROM dumps, the utility disk
that came with a card -- and what each one is for.

The register's other tables hang off one asset id. These do not, on purpose: a
Trident TVGA8900 driver is a fact about that card as a model, not about the
particular one on the shelf, and a collection holding three of them would
otherwise carry the same download three times and lose two of them the day two
cards were disposed of.

So a file is attached to what it is for, by hand, in one of two ways. To an
**asset id** -- this one unit -- for a receipt, a photograph of a repair, a ROM
read off one board. To a **model** -- every item of it, owned now or acquired
next year -- for a driver, a manual, a disk. A model is named by machines.yaml's
key where the catalogue knows the machine and by the maker and model as written
where it does not, and an item with both answers to both (ADR-0020).

Matching is equality on the stored key. It used to be containment on the item's
name, which is what let one tag cover a range -- and what let a tag of "16" or
"Pro" cover far more than a range, moved a file the day somebody corrected a
maker, and left a privacy gate resting on a recomputation. ADR-0006 has the whole
of that argument, including what it got right; 0039 is the migration that ran the
old matcher one last time and wrote down what it found.

Tags stay, demoted: a tag says what a file *is* -- a manual, a driver, a ROM dump
-- and no longer decides what it applies to.

A file is also either published or not, and starts unpublished. The register is a
public catalogue, but this box takes receipts as readily as driver disks, so who
may see one is asked here rather than left to the auth rules: `authed=False` is a
visitor, and a visitor is shown the published ones alone. The download route asks
the same question of the same column -- a listing that hides a file and a URL that
still hands it over is not privacy (ADR-0009).

This module owns the bytes too. The name on disk is generated and the uploaded name
is only ever data -- see `save`.
"""

from __future__ import annotations

import os
import re
import secrets
from datetime import datetime, timezone
from pathlib import Path

from sqlalchemy import and_, or_

from . import machines
from .entry import GIB, KIB, MIB
from .models import AssetVariant, FileAsset, FileModel, FileTag, StoredFile

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


CATALOGUE, NAMED = "catalogue", "named"


def named_key(maker, model) -> str:
    """The handle for a model the catalogue does not know: the maker and the model
    folded and joined. Joined with a character neither can contain once folded, so
    a maker of "Sound" and a model of "Blaster" cannot collide with a maker of
    "SoundBlaster" and no model at all."""
    return f"{fold(maker)}|{fold(model)}"


def model_ids_for(db, item) -> list[tuple[str, str, str]]:
    """The models an item answers to, as (kind, key, label).

    Both where it has both: a Spectrum +2 is a catalogue machine *and* a Sinclair
    ZX Spectrum +2, and identifying a machine in the catalogue after a file was
    attached to it by name must not take the file away."""
    out = []
    asset_id = (item.get("asset_id") or "").strip()
    if asset_id:
        key = (
            db.query(AssetVariant.model_key).filter(AssetVariant.asset_id == asset_id).scalar()
            or ""
        ).strip()
        if key:
            known = machines.model(key)
            out.append((CATALOGUE, key, (known or {}).get("model") or key))
    maker = (item.get("manufacturer") or "").strip()
    model = (item.get("model") or "").strip()
    if fold(maker) or fold(model):
        out.append(
            (NAMED, named_key(maker, model), " ".join(word for word in (maker, model) if word))
        )
    return out


def _file_ids_for(db, item) -> set[int]:
    """The ids of the files attached to this item or to a model it answers to."""
    asset_id = (item.get("asset_id") or "").strip()
    ids = set()
    if asset_id:
        ids |= {
            row[0]
            for row in db.query(FileAsset.file_id).filter(FileAsset.asset_id == asset_id).all()
        }
    models = model_ids_for(db, item)
    if models:
        ids |= {
            row[0]
            for row in db.query(FileModel.file_id)
            .filter(
                or_(
                    *[
                        and_(FileModel.kind == kind, FileModel.model_key == key)
                        for kind, key, _ in models
                    ]
                )
            )
            .all()
        }
    return ids


def for_item(db, item, authed=True):
    """Every file attached to this item or to a model it answers to, newest first,
    each with its tags attached as `.tags`. A visitor is shown the published ones
    alone."""
    ids = _file_ids_for(db, item)
    if not ids:
        return []
    q = db.query(StoredFile).filter(StoredFile.id.in_(ids))
    if not authed:
        q = q.filter(StoredFile.public.is_(True))
    rows = q.order_by(StoredFile.created_at.desc(), StoredFile.id.desc()).all()
    return with_links(db, with_tags(db, rows))


def attach_asset(db, file_id: int, asset_id: str) -> bool:
    """Attach a file to one unit. True when it was not already, so the caller can
    say what it did without asking twice."""
    asset_id = (asset_id or "").strip()
    if not asset_id:
        return False
    if (
        db.query(FileAsset)
        .filter(FileAsset.file_id == file_id, FileAsset.asset_id == asset_id)
        .first()
    ):
        return False
    db.add(FileAsset(file_id=file_id, asset_id=asset_id))
    db.flush()
    return True


def attach_model(db, file_id: int, kind: str, key: str, label: str = "") -> bool:
    """Attach a file to a model. `label` is what to print; `key` is what matches."""
    if kind not in (CATALOGUE, NAMED) or not (key or "").strip():
        return False
    if (
        db.query(FileModel)
        .filter(FileModel.file_id == file_id, FileModel.kind == kind, FileModel.model_key == key)
        .first()
    ):
        return False
    db.add(FileModel(file_id=file_id, kind=kind, model_key=key, label=label or key))
    db.flush()
    return True


def detach_asset(db, file_id: int, asset_id: str) -> None:
    db.query(FileAsset).filter(FileAsset.file_id == file_id, FileAsset.asset_id == asset_id).delete(
        synchronize_session=False
    )
    db.flush()


def detach_model(db, file_id: int, kind: str, key: str) -> None:
    db.query(FileModel).filter(
        FileModel.file_id == file_id, FileModel.kind == kind, FileModel.model_key == key
    ).delete(synchronize_session=False)
    db.flush()


def forget_asset(db, asset_id: str) -> None:
    """Drop the links to an item being deleted. The bytes stay: a file with no
    links left is unfiled, which the files page says out loud rather than treating
    as rubbish (ADR-0006)."""
    db.query(FileAsset).filter(FileAsset.asset_id == asset_id).delete(synchronize_session=False)
    db.flush()


def with_links(db, rows):
    """The same rows, each carrying what it is attached to: `.assets` is a list of
    asset ids and `.models` a list of (kind, key, label). Two queries for the whole
    page rather than two per file, the way `with_tags` works."""
    rows = list(rows)
    if not rows:
        return []
    ids = [row.id for row in rows]
    assets: dict[int, list[str]] = {}
    for link in (
        db.query(FileAsset).filter(FileAsset.file_id.in_(ids)).order_by(FileAsset.asset_id).all()
    ):
        assets.setdefault(link.file_id, []).append(link.asset_id)
    models: dict[int, list[tuple[str, str, str]]] = {}
    for link in (
        db.query(FileModel).filter(FileModel.file_id.in_(ids)).order_by(FileModel.label).all()
    ):
        models.setdefault(link.file_id, []).append((link.kind, link.model_key, link.label))
    for row in rows:
        row.assets = assets.get(row.id, [])
        row.models = models.get(row.id, [])
        # The pairs on their own, for a page asking "is this one of them?" of each
        # of an item's models in turn.
        row.model_pairs = {(kind, key) for kind, key, _ in row.models}
        row.unfiled = not row.assets and not row.models
    return rows


def with_tags(db, rows):
    """The same rows, each carrying its tags in one extra query rather than one
    per file."""
    rows = list(rows)
    if not rows:
        return []
    tags: dict[int, list[str]] = {}
    for row in (
        db.query(FileTag)
        .filter(FileTag.file_id.in_([r.id for r in rows]))
        .order_by(FileTag.id)
        .all()
    ):
        tags.setdefault(row.file_id, []).append(row.tag)
    for row in rows:
        row.tags = tags.get(row.id, [])
    return rows


def all_files(db, tag="", authed=True):
    """Everything on file, newest first, each with its tags and what it is attached
    to -- or, given a tag, the files carrying that tag.

    The tag filter is equality on the fold now, not containment on a name: a tag
    says what a file is, so following one asks for the manuals rather than for
    whatever a machine of that name would be offered. `authed` is asked here too,
    because an unpublished file left in this list would be reachable from the chip
    on the very page it was kept off."""
    q = db.query(StoredFile)
    if not authed:
        q = q.filter(StoredFile.public.is_(True))
    if fold(tag):
        ids = {row[0] for row in db.query(FileTag.file_id).filter(FileTag.fold == fold(tag)).all()}
        if not ids:
            return []
        q = q.filter(StoredFile.id.in_(ids))
    rows = q.order_by(StoredFile.created_at.desc(), StoredFile.id.desc()).all()
    return with_links(db, with_tags(db, rows))


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
    db.query(FileTag).filter(FileTag.file_id == stored.id).delete(synchronize_session=False)
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
    row = StoredFile(
        stored=stored,
        filename=name[:255],
        size=size,
        note=(note or "").strip()[:255],
        created_at=datetime.now(timezone.utc).replace(tzinfo=None),
    )
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
    db.query(FileTag).filter(FileTag.file_id == stored.id).delete(synchronize_session=False)
    db.delete(stored)


def human_size(n) -> str:
    """A size as it would be said out loud, which is what a download link wants."""
    n = int(n or 0)
    if n < 1024:
        return f"{n} B"
    for unit, scale in ((KIB, 1024), (MIB, 1024**2), (GIB, 1024**3)):
        if n < scale * 1024 or unit == GIB:
            size = n / scale
            return f"{size:.0f} {unit}" if size >= 10 else f"{size:.1f} {unit}"
    return f"{n} B"
