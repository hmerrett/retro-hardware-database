"""Shared foundations used across the app: the "still held" query filter, a few
small query helpers, the image-folder location and listing, and the collection
constants. Kept in one dependency-free place so the feature modules (stats,
search, photos) and main can all import them downward without a circular import.
"""
import hashlib
import os
from pathlib import Path

from sqlalchemy import case, func

from . import entry
from .models import Computer, Part, Project

# Container paths by default (the `images` volume); overridable so the app can be
# imported and run outside Docker for local development.
IMAGES_DIR = Path(os.getenv("RHDB_IMAGES_DIR", "/app/images"))
IMAGE_EXTS = (".jpg", ".jpeg", ".png", ".webp", ".gif")

# How many parts a maker needs before its record means anything. Below this a maker
# with one working card would top the table on a sample of one, which is not a
# fact about the maker.
RELIABILITY_MIN = 5
# Ways of attaching a disk that died with the 1980s, named rather than worked out:
# read by the /stats figure and by the /browse view behind it, so both mean the
# same four things.
LEGACY_DISK_BUSES = ("MFM", "RLL", "ESDI", "XTA")
# Not makers. These stand in the maker field for "we do not know" or "nobody in
# particular", and a league table of manufacturers should not have them in it.
NOT_A_MAKER = {"unknown", "generic", "various", "noname", "no name", "n/a", "-", "?"}


# Disposed items are records of things that have gone. A figure about the collection
# is about what is in it, so everything on /stats counts only what is still held.
# This is the filter, in one place, so "still here" means one thing.
def _held(query, model):
    return query.filter(model.disposed.is_(False))


def _all_years(db, held=True):
    """Every year recorded against anything still here, machines and parts together."""
    out = []
    for model in (Computer, Part):
        q = db.query(model.year).filter(model.year.isnot(None))
        out += [y for (y,) in (_held(q, model) if held else q)]
    return out


def _visible(query, authed):
    """A project query narrowed to what this reader may see."""
    return query if authed else query.filter(Project.private.is_(False))


def to_dict(obj):
    return {c.name: getattr(obj, c.name) for c in obj.__table__.columns}


def _maker_reliability(db):
    """(maker, parts, working, percent) per maker, best record first.

    Reliability here means one thing and only one: the share of that maker's parts
    whose condition is recorded as Working. Not "Restored" -- a part that had to be
    restored is evidence of the opposite -- and only parts still in the register,
    because a disposed one may have been sold in perfect order.

    Ties are settled by sample size: with equal records, the maker who earned it
    over more parts has made the better case."""
    rows = []
    for maker, n, working in (
            db.query(Part.manufacturer, func.count(Part.asset_id),
                     func.sum(case((Part.condition == "Working", 1), else_=0)))
            .filter(Part.manufacturer.isnot(None), Part.manufacturer != "",
                    Part.condition.isnot(None), Part.condition != "",
                    Part.disposed.is_(False))
            .group_by(Part.manufacturer)):
        if n < RELIABILITY_MIN or (maker or "").strip().lower() in NOT_A_MAKER:
            continue
        rows.append((maker, n, int(working or 0), round(100 * (working or 0) / n)))
    rows.sort(key=lambda r: (-r[3], -r[1], r[0]))
    return rows


def folder_images(kind):
    """(stem, filename) for every photo in one of the image folders, in a single
    pass. A page showing many assets reads the folder once and picks from the
    result rather than scanning it per row."""
    folder = IMAGES_DIR / kind
    if not folder.exists():
        return []
    return [(f.stem, f.name) for f in folder.iterdir()
            if f.suffix.lower() in IMAGE_EXTS]


def _stem_owner(stem, ids):
    """Whose photograph a filename is, or None. A photo is <asset_id>.<ext> or
    <asset_id>-<something>.<ext>, so the owner is the stem itself or the stem with
    its suffix taken off. The suffix comes off one hyphen at a time, so that
    RH-0001-back-left belongs to the machine exactly as RH-0001-2 does."""
    while stem:
        if stem in ids:
            return stem
        stem = stem.rpartition("-")[0]
    return None


def _photo_counts(ids_by_kind):
    """How many portraits each asset has, from one pass over each folder named.
    Keyed by kind, because a photograph belongs to the folder it is in. Only
    computers/ and parts/ are ever read, which is how a photograph on a history
    entry (filed under log/) stays out of this."""
    counts = {}
    for kind, ids in ids_by_kind.items():
        for stem, _name in folder_images(kind):
            aid = _stem_owner(stem, ids)
            if aid:
                counts[aid] = counts.get(aid, 0) + 1
    return counts


def _portraits(db):
    """(counts, missing): how many portraits each thing still here has, and the tags
    of the ones that have none. Held items only -- a disposed item cannot be
    photographed, so putting one on the "unphotographed" job list is handing
    somebody work they cannot do."""
    ids = {"computers": {a for (a,) in _held(db.query(Computer.asset_id), Computer)},
           "parts": {a for (a,) in _held(db.query(Part.asset_id), Part)}}
    counts = _photo_counts(ids)
    missing = {a for group in ids.values() for a in group if a not in counts}
    return counts, missing


def _big_total(kb):
    """A grand total in the unit a person would say it in. entry.fmt_kb keeps a
    non-round figure in MiB, which is right for one drive and unreadable for the
    sum of every drive there is."""
    if kb >= 1024 * 1024:
        return f"{kb / (1024 * 1024):.1f} {entry.GIB}"
    return entry.fmt_kb(kb, True)


# The three things an id in the register can name. One list, because every route
# that takes a bare asset id has to agree about this.
REGISTER = (("computers", Computer), ("parts", Part), ("projects", Project))


# --- static files and per-deployment branding ------------------------------
STATIC_DIR = Path(__file__).resolve().parent / "static"
# Where a deployment puts its own logo, icons and card, if it has any. What ships
# in static/ is a placeholder; a file dropped here under the same name is served
# instead of it. Read at start-up, like the rest of the configuration; nothing
# here is in git.
# Public origin used to build the absolute URLs that social-media link previews
# (Open Graph / Twitter cards) require; falls back to the request's own host.
PUBLIC_BASE_URL = os.getenv("RHDB_BASE_URL", "").rstrip("/")

BRANDING_DIR = Path(os.getenv("RHDB_BRANDING_DIR", "/app/branding"))


def branded(name: str) -> Path:
    """The deployment's own copy of a static file if it has one, else the shipped
    one. Names only -- never a path from a request, which the static mount checks
    for itself."""
    own = BRANDING_DIR / name
    return own if own.is_file() else STATIC_DIR / name


def _file_ver(path: Path) -> str:
    """Short content hash of a file, or '0' if it is not there. Used to name things
    after the artwork that went into them, so replacing the artwork misses every
    cache keyed on it -- the browser's favicon cache is famously sticky, and a
    watermark already composited into a served photo is stickier still."""
    try:
        return hashlib.md5(path.read_bytes()).hexdigest()[:8]
    except OSError:
        return "0"
