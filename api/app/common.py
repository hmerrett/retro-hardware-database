"""Shared foundations used across the app: the "still held" query filter, a few
small query helpers, the image-folder location and listing, and the collection
constants. Kept in one dependency-free place so the feature modules (stats,
search, photos) and main can all import them downward without a circular import.
"""

import hashlib
import os
from collections.abc import Container, Mapping
from pathlib import Path
from typing import TypeVar


# Whether a project is one of the private ones, asked as a query rather than as a
# column filter. This replaced PRIVATE_COLUMNS, which kept two columns of an
# otherwise public record back from a visitor; a project is private as a whole or
# not at all, so what is hidden is the row, and hiding a row is done where rows are
# chosen rather than where their fields are read.
#
# Five places, and it is only private with all five shut: the list leaves them out,
# the project's own page refuses them, the search and the suggestion list drop them,
# the sitemap does not name them, and the panel on an item's page does not say the
# item is wanted for one. Miss any one and the other four are decoration.

from sqlalchemy import case, func
from sqlalchemy.orm import Query, Session

from . import entry
from .db import Base
from .models import Computer, Part, Project

# The rows a query hands back, kept as it passes through the filters below.
_Row = TypeVar("_Row")

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

# Columns a visitor is never shown, by name, so that keeping one back is a decision
# recorded in one place rather than a habit of remembering (ADR-0018).
#
# The set exists because search._haystack reads *every* column off the model -- that
# is what makes "search any field" true rather than nearly true -- so a new column
# joins what a stranger can search by merely existing. A boolean reads as "True",
# and a search for "true" would hand back every row carrying it, off a page that
# shows no such thing. Hiding a column in the template is half the job; this is the
# other half, and it is the half nobody remembers.
#
# Never shown, and so a frozenset: a column kept back only while a preference says
# so does not belong in here, because the answer would depend on when the set was
# read. Those are added on top of this one, per reader, by search._hidden_columns
# (ADR-0027) -- which is the question this set is one answer to.
OWNER_ONLY = frozenset({"for_sale"})


# Disposed items are records of things that have gone. A figure about the collection
# is about what is in it, so everything on /stats counts only what is still held.
# This is the filter, in one place, so "still here" means one thing.
def _held(query: Query[_Row], model: type[Computer] | type[Part]) -> Query[_Row]:
    return query.filter(model.disposed.is_(False))


def _all_years(db: Session, held: bool = True) -> list[int]:
    """Every year recorded against anything still here, machines and parts together."""
    out: list[int] = []
    for model in (Computer, Part):
        q = db.query(model.year).filter(model.year.isnot(None))
        # The query has already dropped the years nobody recorded; saying so again
        # here is what makes the list one of years rather than of maybe-years.
        out += [y for (y,) in (_held(q, model) if held else q) if y is not None]
    return out


def _visible(query: Query[_Row], authed: bool) -> Query[_Row]:
    """A project query narrowed to what this reader may see."""
    return query if authed else query.filter(Project.private.is_(False))


def to_dict(obj: Base) -> dict[str, object]:
    return {c.name: getattr(obj, c.name) for c in obj.__table__.columns}


def _maker_reliability(db: Session) -> list[tuple[str | None, int, int, int]]:
    """(maker, parts, working, percent) per maker, best record first.

    Reliability here means one thing and only one: the share of that maker's parts
    whose condition is recorded as Working. Not "Restored" -- a part that had to be
    restored is evidence of the opposite -- and only parts still in the register,
    because a disposed one may have been sold in perfect order.

    Ties are settled by sample size: with equal records, the maker who earned it
    over more parts has made the better case."""
    rows: list[tuple[str | None, int, int, int]] = []
    for maker, n, working in (
        db.query(
            Part.manufacturer,
            func.count(Part.asset_id),
            func.sum(case((Part.condition == "Working", 1), else_=0)),
        )
        .filter(
            Part.manufacturer.isnot(None),
            Part.manufacturer != "",
            Part.condition.isnot(None),
            Part.condition != "",
            Part.disposed.is_(False),
        )
        .group_by(Part.manufacturer)
    ):
        if n < RELIABILITY_MIN or (maker or "").strip().lower() in NOT_A_MAKER:
            continue
        rows.append((maker, n, int(working or 0), round(100 * (working or 0) / n)))
    rows.sort(key=lambda r: (-r[3], -r[1], r[0]))
    return rows


def folder_images(kind: str) -> list[tuple[str, str]]:
    """(stem, filename) for every photo in one of the image folders, in a single
    pass. A page showing many assets reads the folder once and picks from the
    result rather than scanning it per row."""
    folder = IMAGES_DIR / kind
    if not folder.exists():
        return []
    return [(f.stem, f.name) for f in folder.iterdir() if f.suffix.lower() in IMAGE_EXTS]


def _stem_owner(stem: str, ids: Container[str]) -> str | None:
    """Whose photograph a filename is, or None. A photo is <asset_id>.<ext> or
    <asset_id>-<something>.<ext>, so the owner is the stem itself or the stem with
    its suffix taken off. The suffix comes off one hyphen at a time, so that
    RH-0001-back-left belongs to the machine exactly as RH-0001-2 does."""
    while stem:
        if stem in ids:
            return stem
        stem = stem.rpartition("-")[0]
    return None


def _photo_counts(ids_by_kind: Mapping[str, set[str]]) -> dict[str, int]:
    """How many portraits each asset has, from one pass over each folder named.
    Keyed by kind, because a photograph belongs to the folder it is in. Only
    computers/ and parts/ are ever read, which is how a photograph on a history
    entry (filed under log/) stays out of this."""
    counts: dict[str, int] = {}
    for kind, ids in ids_by_kind.items():
        for stem, _name in folder_images(kind):
            aid = _stem_owner(stem, ids)
            if aid:
                counts[aid] = counts.get(aid, 0) + 1
    return counts


def _portraits(db: Session) -> tuple[dict[str, int], set[str]]:
    """(counts, missing): how many portraits each thing still here has, and the tags
    of the ones that have none. Held items only -- a disposed item cannot be
    photographed, so putting one on the "unphotographed" job list is handing
    somebody work they cannot do."""
    ids = {
        "computers": {a for (a,) in _held(db.query(Computer.asset_id), Computer)},
        "parts": {a for (a,) in _held(db.query(Part.asset_id), Part)},
    }
    counts = _photo_counts(ids)
    missing = {a for group in ids.values() for a in group if a not in counts}
    return counts, missing


def _big_total(kb: int) -> str:
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
        return _text_ver(path.read_bytes())
    except OSError:
        return "0"


def _text_ver(content: str | bytes) -> str:
    """The same stamp for something built rather than read from disk -- the
    generated stylesheet, which has no file to hash."""
    if isinstance(content, str):
        content = content.encode()
    return hashlib.md5(content).hexdigest()[:8]


# What the app will load, which is only ever itself. Here rather than beside the
# middleware that sends it because the error page sends it too: a 500 is caught
# outside every middleware, so that one page has to state the policy itself.
#
# What the app will load, which is only ever itself. `img_url` yields `/images/...`,
# a reference photograph is fetched into that volume server-side rather than hot-
# linked, and the QR decoder is vendored under /static/vendor -- so `'self'`
# throughout is a description of the code and not an aspiration for it.
#
# `form-action`, `frame-ancestors` and `base-uri` are stated because they do not
# fall back to `default-src`: left out they are simply absent, which reads like a
# tight policy and is not one.
#
# `style-src` is now `'self'` as well: the 69 style attributes and the two <style>
# blocks the token was there for have gone into app.css as classes, and the two
# whose values were data into the generated stylesheet at /style/data.css
# (ADR-0022). A test walks the rendered pages for a style attribute rather than
# trusting this comment.
CONTENT_SECURITY_POLICY = "; ".join(
    (
        "default-src 'self'",
        "script-src 'self'",
        "style-src 'self'",
        "img-src 'self'",
        "font-src 'self'",
        "connect-src 'self'",
        "form-action 'self'",
        "frame-ancestors 'self'",
        "base-uri 'none'",
        "object-src 'none'",
    )
)
