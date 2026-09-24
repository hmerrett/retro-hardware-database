"""Files kept beside the register -- drivers, manuals, ROM dumps, the utility disk
that came with a card, a receipt -- and what each one is for.

The register's other tables hang off one asset id. These do not: a driver disk is
as much about the fourth card of a model as about the first, and a receipt about
the one thing it is a receipt for. So a file is linked to the things it is for by
their asset ids, as many as it needs, by hand, and to nothing else (ADR-0028). An
item offers the files linked to it. There is no rule working out what a file
reaches, so renaming an item or correcting its model moves nothing.

The model survives in one role only, which is to suggest. The upload box on an
item offers its same-model siblings as one tick, and an item whose siblings have
files it lacks is offered them. Neither links anything until somebody says so --
the difference between this and the model links 0044 retired, which reached a
card nobody had looked at.

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
from collections.abc import Iterable, Mapping
from datetime import datetime, timezone
from pathlib import Path
from typing import NamedTuple

from sqlalchemy import func
from sqlalchemy.orm import Session
from starlette.datastructures import UploadFile

from . import entry, filekinds, machines, settings
from .entry import MIB
from .models import AssetVariant, Computer, FileAsset, Part, Project, StoredFile

FILES_DIR = Path(os.getenv("RHDB_FILES_DIR", "/app/files"))

# What one upload may weigh. A driver disk is a few hundred KiB and a CD image is
# not something to keep in a register, so this is generous rather than a guess at
# the largest useful file.
MAX_BYTES = 64 * 1024 * 1024

# Kept for the download's own name, and to give the stored copy a recognisable
# suffix. Anything else keeps its bytes and loses its extension -- the file is
# served as an attachment either way.
_SAFE_SUFFIX = re.compile(r"^\.[A-Za-z0-9]{1,8}$")

# How many links to units of one model a list shows one by one before it folds
# them into "5 × Polpo PicoGUS". Two identical boards read as two; five cards read
# as a row of chips nobody reads, and the file's own page lists them all anyway.
FOLD_AT = 3

NOTE_MAX = 255

_REGISTER: tuple[tuple[str, type[Computer] | type[Part]], ...] = (
    ("computers", Computer),
    ("parts", Part),
)


class Linked(NamedTuple):
    """One thing a file is linked to, as a page names it and links to it."""

    asset_id: str
    name: str
    page: str


class Chip(NamedTuple):
    """How a list shows what a file is linked to: one item, or several units of one
    model folded into one chip that leads to the file's page, where they are listed
    one by one."""

    label: str
    name: str
    page: str
    ids: tuple[str, ...]


def fold(text: str | None) -> str:
    """The form several spellings of one name have in common: no spaces at all, no
    case. Every space rather than runs of them, because a name is as often written
    closed up as apart -- SoundBlaster, Sound Blaster -- and neither spelling is the
    wrong one to have typed."""
    return "".join((text or "").split()).lower()


def named_key(maker: str | None, model: str | None) -> str:
    """A model the catalogue does not know, as a key: the maker and the model folded
    and joined. Joined with a character neither can contain once folded, so a maker
    of "Sound" and a model of "Blaster" cannot collide with a maker of
    "SoundBlaster" and no model at all."""
    return f"{fold(maker)}|{fold(model)}"


def _names(
    db: Session, asset_ids: Iterable[str], authed: bool = True
) -> dict[str, tuple[str, str]]:
    """{asset_id: (what it is called, its page)} for the machines, parts and
    projects among these ids that this reader may be told about.

    A private project is left out for a visitor, and so is its id: a file may be
    public while a project it is linked to is not, and the file's page must not be
    the way a visitor learns the project is there (ADR-0028)."""
    wanted = sorted(set(asset_ids))
    out: dict[str, tuple[str, str]] = {}
    if not wanted:
        return out
    projects = db.query(Project.asset_id, Project.name).filter(Project.asset_id.in_(wanted))
    if not authed:
        projects = projects.filter(Project.private.is_(False))
    for aid, name in projects:
        out[aid] = (name or aid, f"/projects/{aid}")
    for kind, cls in _REGISTER:
        for aid, name, maker, model in db.query(
            cls.asset_id, cls.name, cls.manufacturer, cls.model
        ).filter(cls.asset_id.in_(wanted)):
            out[aid] = (
                entry.display_name(
                    {"asset_id": aid, "name": name, "manufacturer": maker, "model": model}
                ),
                f"/{kind}/{aid}",
            )
    return out


def _chips(file_id: int, linked: list[Linked]) -> list[Chip]:
    """The links as a list shows them: one chip an item, except where FOLD_AT or
    more carry the same name, which become one."""
    by_name: dict[str, list[Linked]] = {}
    for link in linked:
        by_name.setdefault(link.name, []).append(link)
    out: list[Chip] = []
    for name, links in by_name.items():
        if len(links) >= FOLD_AT:
            ids = tuple(link.asset_id for link in links)
            out.append(Chip(f"{len(links)} ×", name, f"/files/{file_id}", ids))
        else:
            out += [Chip(link.asset_id, name, link.page, (link.asset_id,)) for link in links]
    return out


def with_links(db: Session, rows: Iterable[StoredFile], authed: bool = True) -> list[StoredFile]:
    """The same rows, each carrying what it is linked to and what it is: `.assets`
    the asset ids, `.linked` each with its name and page, `.chips` the way a list
    shows them, `.unlinked`, and `.what` from filekinds. A handful of queries for
    the whole page rather than a handful per file.

    For a visitor, `.linked` and `.chips` are what they may be told about -- a
    private project is not among them -- and `.assets` is the same list's ids."""
    rows = list(rows)
    if not rows:
        return []
    links: dict[int, list[str]] = {}
    for link in (
        db.query(FileAsset)
        .filter(FileAsset.file_id.in_([row.id for row in rows]))
        .order_by(FileAsset.asset_id)
    ):
        links.setdefault(link.file_id, []).append(link.asset_id)
    named = _names(db, (aid for aids in links.values() for aid in aids), authed)
    for row in rows:
        every = links.get(row.id, [])
        # The owner is shown an id with no row behind it, bare, since a link that
        # names nothing is worth seeing to be put right; a visitor is shown what
        # can be named and nothing else.
        row.linked = [
            Linked(aid, *named.get(aid, (aid, f"/items/{aid}")))
            for aid in every
            if authed or aid in named
        ]
        row.assets = [link.asset_id for link in row.linked]
        row.chips = _chips(row.id, row.linked)
        row.unlinked = not every
        row.what = filekinds.of(row.filename, row.size)
    return rows


def _newest_first(db: Session, ids: Iterable[int] | None, authed: bool) -> list[StoredFile]:
    q = db.query(StoredFile)
    if ids is not None:
        wanted = sorted(set(ids))
        if not wanted:
            return []
        q = q.filter(StoredFile.id.in_(wanted))
    if not authed:
        q = q.filter(StoredFile.public.is_(True))
    rows = q.order_by(StoredFile.created_at.desc(), StoredFile.id.desc()).all()
    return with_links(db, rows, authed)


def for_item(db: Session, asset_id: str, authed: bool = True) -> list[StoredFile]:
    """The files linked to this item, newest first. A visitor is shown the published
    ones alone."""
    ids = [row[0] for row in db.query(FileAsset.file_id).filter(FileAsset.asset_id == asset_id)]
    return _newest_first(db, ids, authed)


def _identity(db: Session, item: Mapping[str, object]) -> tuple[str, str]:
    """(catalogue key, named key): the two ways an item says what model it is, either
    of which may be "". Both where it has both, since a Spectrum +2 is a catalogue
    machine and a Sinclair ZX Spectrum +2 at once."""
    # str(): the dict is a row read column by column, so every value in it is typed
    # as wide as a column can be; these three are text.
    asset_id = str(item.get("asset_id") or "").strip()
    catalogue = ""
    if asset_id:
        catalogue = (
            db.query(AssetVariant.model_key).filter(AssetVariant.asset_id == asset_id).scalar()
            or ""
        ).strip()
    maker, model = str(item.get("manufacturer") or ""), str(item.get("model") or "")
    return catalogue, (named_key(maker, model) if fold(maker) or fold(model) else "")


def model_name(db: Session, item: Mapping[str, object]) -> str:
    """What an item's model is called, for "the other 4 Polpo PicoGUS": the maker and
    model as written, or the catalogue's name for the machine where there are none."""
    written = " ".join(
        str(part).strip() for part in (item.get("manufacturer"), item.get("model")) if part
    ).strip()
    if written:
        return written
    known = machines.model(_identity(db, item)[0])
    return str(known["model"]) if known else ""


def siblings(db: Session, item: Mapping[str, object], held: bool = False) -> list[Linked]:
    """The other machines and parts of this item's model, by asset id -- the same
    catalogue key, or the same maker and model folded -- and only those still held
    when `held` says so. A project has no model, and so no siblings."""
    own = str(item.get("asset_id") or "").strip().upper()
    catalogue, named = _identity(db, item)
    if not catalogue and not named:
        return []
    found: set[str] = set()
    if catalogue:
        found |= {
            aid
            for (aid,) in db.query(AssetVariant.asset_id).filter(
                AssetVariant.model_key == catalogue
            )
        }
    if named:
        maker, model = named.split("|", 1)
        for _kind, cls in _REGISTER:
            # The database narrows by the folded spelling it can compute, with the
            # spaces taken out and the case ignored, and the fold decides: it also
            # takes out the tabs and newlines REPLACE does not know about.
            for aid, m, d in db.query(cls.asset_id, cls.manufacturer, cls.model).filter(
                func.lower(func.replace(func.coalesce(cls.manufacturer, ""), " ", "")) == maker,
                func.lower(func.replace(func.coalesce(cls.model, ""), " ", "")) == model,
            ):
                if named_key(m, d) == named:
                    found.add(aid)
    found.discard(own)
    if not found:
        return []
    kept: set[str] = set()
    for _kind, cls in _REGISTER:
        q = db.query(cls.asset_id).filter(cls.asset_id.in_(sorted(found)))
        if held:
            q = q.filter(cls.disposed.is_(False))
        kept |= {aid for (aid,) in q}
    named_ids = _names(db, kept)
    return [Linked(aid, *named_ids[aid]) for aid in sorted(kept) if aid in named_ids]


def offered(db: Session, item: Mapping[str, object]) -> list[StoredFile]:
    """The files linked to this item's same-model siblings, held or not, that are not
    linked to this item: what a new unit is offered, and only ever offered. For the
    owner alone, so there is no visitor's version of the question."""
    others = [link.asset_id for link in siblings(db, item)]
    if not others:
        return []
    own = str(item.get("asset_id") or "").strip().upper()
    theirs = {row[0] for row in db.query(FileAsset.file_id).filter(FileAsset.asset_id.in_(others))}
    mine = {row[0] for row in db.query(FileAsset.file_id).filter(FileAsset.asset_id == own)}
    return _newest_first(db, theirs - mine, authed=True)


def panel(db: Session, item: Mapping[str, object], authed: bool) -> dict[str, object]:
    """What the Files panel on a machine's, a part's or a project's page is drawn
    from: the files linked to it, and, for the owner, the siblings the upload box
    offers, what their model is called, the files those siblings have that this one
    has not, and whether the upload's Public tick starts ticked.

    It starts ticked where the owner has said new files are public (ADR-0029),
    except on a private project: a file uploaded there is as likely to be the
    receipt the project is private for, and a default that published it would be
    the one place the preference could disclose something nobody chose to."""
    asset_id = str(item.get("asset_id") or "")
    return {
        "files": for_item(db, asset_id, authed),
        "file_siblings": siblings(db, item, held=True) if authed else [],
        "file_model": model_name(db, item) if authed else "",
        "file_offer": offered(db, item) if authed else [],
        "file_public_default": authed and settings.on("files_public") and not item.get("private"),
    }


def link(db: Session, file_id: int, asset_id: str | None) -> bool:
    """Link a file to one more thing. True when it was not already, so the caller
    can say what it did without asking twice."""
    asset_id = (asset_id or "").strip().upper()
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


def unlink(db: Session, file_id: int, asset_id: str) -> None:
    db.query(FileAsset).filter(
        FileAsset.file_id == file_id, FileAsset.asset_id == asset_id.strip().upper()
    ).delete(synchronize_session=False)
    db.flush()


def forget_asset(db: Session, asset_id: str) -> None:
    """Drop the links to an item being deleted. The bytes stay: a file with no
    links left is unlinked, which the files page says out loud rather than treating
    as rubbish (ADR-0006)."""
    db.query(FileAsset).filter(FileAsset.asset_id == asset_id).delete(synchronize_session=False)
    db.flush()


def _matches(row: StoredFile, needle: str) -> bool:
    """Whether a folded search term is in a file's name, its note, or the asset id
    or name of anything it is linked to."""
    return any(
        needle in fold(text)
        for text in (
            row.filename,
            row.note,
            *(link.asset_id for link in row.linked),
            *(link.name for link in row.linked),
        )
    )


# The two lists that are the owner's alone: the files that want attention.
SHOWS = ("unlinked", "private")


def all_files(
    db: Session, authed: bool = True, group: str = "", q: str = "", show: str = ""
) -> list[StoredFile]:
    """Everything on file, newest first, each with what it is linked to -- narrowed
    to one kind (`group`, a key of filekinds.GROUPS), to a search, or, for the
    owner, to the files linked to nothing or kept back from visitors.

    `authed` is asked here too, because an unpublished file left in this list would
    be one a visitor could read the name of."""
    rows = _newest_first(db, None, authed)
    if group in filekinds.GROUPS:
        rows = [row for row in rows if row.what.group == group]
    if fold(q):
        rows = [row for row in rows if _matches(row, fold(q))]
    if authed and show == "unlinked":
        rows = [row for row in rows if row.unlinked]
    if authed and show == "private":
        rows = [row for row in rows if not row.public]
    return rows


def groups(rows: Iterable[StoredFile]) -> list[tuple[str, str, int]]:
    """The kinds these files come in, as (key, label, how many), in the order the
    page offers them -- only the ones there are files of, since a filter that finds
    nothing is a question the page need not ask."""
    counts: dict[str, int] = {}
    for row in rows:
        counts[row.what.group] = counts.get(row.what.group, 0) + 1
    return [(key, label, counts[key]) for key, label in filekinds.GROUPS.items() if key in counts]


def save(
    db: Session, upload: UploadFile, note: str = "", public: bool = False
) -> StoredFile | None:
    """Store an upload. Returns the row, or None for an empty upload; raises
    ValueError if it is over MAX_BYTES.

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
        note=(note or "").strip()[:NOTE_MAX],
        public=bool(public),
        created_at=datetime.now(timezone.utc).replace(tzinfo=None),
    )
    db.add(row)
    db.flush()
    return row


def path_of(stored: StoredFile) -> Path:
    return FILES_DIR / stored.stored


# Where a PDF's header must be found. The format lets a little come before it, and
# the readers everyone uses look this far in, so this does too.
_PDF_HEADER_WITHIN = 1024


def is_pdf(stored: StoredFile) -> bool:
    """Whether this file may be shown by the browser as a PDF: named one, and one by
    its own first bytes. The name alone is what an uploader chose; the bytes are
    what the browser will be handed (ADR-0030)."""
    if filekinds.extension(stored.filename) != "pdf":
        return False
    try:
        with path_of(stored).open("rb") as fh:
            head = fh.read(_PDF_HEADER_WITHIN)
    except OSError:
        return False
    return b"%PDF-" in head


def remove(db: Session, stored: StoredFile) -> None:
    """Forget a file, bytes and all. Its links go with it, and the row is gone
    whether or not the file was still on disk -- a record pointing at nothing is
    worse than no record."""
    path_of(stored).unlink(missing_ok=True)
    db.query(FileAsset).filter(FileAsset.file_id == stored.id).delete(synchronize_session=False)
    db.delete(stored)
