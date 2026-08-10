"""Retro Hardware Database — FastAPI backend.

Two surfaces over the same MariaDB:
  * JSON API under /api  (used by scripts, the MCP wrapper, and the GUI)
  * a bespoke server-rendered GUI that mirrors the flat-file add.py workflow:
    the guided build walk (computer -> link/create motherboard -> parts by
    category), storage-kind routing, CPU/RAM as computer fields, photo upload,
    a disposed toggle, print-label PDFs, and a searchable/filterable index.

Interactive API docs live at /docs (OpenAPI).
"""
import base64
import hashlib
import os
import random
import secrets
import shutil
from collections import Counter
from datetime import UTC, date, datetime
from pathlib import Path
import json
from urllib.parse import quote, urlparse
from xml.sax.saxutils import escape

from fastapi import (Depends, FastAPI, File, HTTPException, Query, Request,
                     UploadFile)
from fastapi.responses import FileResponse, HTMLResponse, RedirectResponse, Response
from itsdangerous import BadSignature, SignatureExpired, URLSafeTimedSerializer
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from sqlalchemy import case, func
from sqlalchemy.orm import Session

from . import drivedb, enrich, entry, labels, ramdb, specdb, specstruct
from .db import get_db
from .ids import next_asset_id
from .models import (Computer, ComputerDrive, ComputerRamChip,
                     ComputerRamModule, LogEntry, Part, PartPort, PartSlot,
                     StorageSpec)
from .schemas import ComputerIn, ComputerOut, PartIn, PartOut
import contextlib

# Schema is owned by Alembic now (entrypoint.sh runs `alembic upgrade head` on
# start); no create_all here.

app = FastAPI(title="Retro Hardware Database API", version="0.3.0")
templates = Jinja2Templates(directory=str(Path(__file__).resolve().parent / "templates"))
templates.env.globals.update(
    display_name=entry.display_name, type_label=entry.type_label,
    bezel_css=entry.bezel_css,
    today=lambda: date.today().isoformat())

AUTH_USER = os.getenv("RHDB_AUTH_USER", "")
AUTH_PASS = os.getenv("RHDB_AUTH_PASSWORD", "")
AUTH_ENABLED = bool(AUTH_USER and AUTH_PASS)
templates.env.globals["auth_enabled"] = AUTH_ENABLED

# Public origin used to build the absolute URLs that social-media link previews
# (Open Graph / Twitter cards) require; falls back to the request's own host.
PUBLIC_BASE_URL = os.getenv("RHDB_BASE_URL", "").rstrip("/")


def _abs_url(request: Request, path: str) -> str:
    base = PUBLIC_BASE_URL or str(request.base_url).rstrip("/")
    return base + path


def _dot(*parts) -> str:
    return " · ".join(str(p) for p in parts if p)


def _image_size(image_rel: str):
    """(width, height) of a stored image, or None. Lets link previews (Discord
    especially) render the large image immediately without a probe fetch."""
    try:
        from PIL import Image, ImageOps
        with Image.open(IMAGES_DIR / image_rel) as im:
            # As served, which is upright: a photo lying on its side in the file
            # would otherwise be announced to a preview the wrong way round.
            return ImageOps.exif_transpose(im).size
    except Exception:
        return None


# The share card for a page with no photograph of its own: the logo on its own
# cream, opaque and at the 1.91:1 those slots want (tools/make_icons.py makes it).
# Several of the sites that show these composite a transparent PNG onto black,
# which is why this one is not transparent.
SITE_CARD = ("/static/og-image.png", 1200, 630)


def _og(request: Request, title: str, description: str = "", image_rel: str | None = None):
    """Open Graph / Twitter-card context for a page's social-share preview."""
    og = {"title": title, "url": _abs_url(request, request.url.path),
          "description": " ".join((description or "").split())[:280]}
    if image_rel:
        og["image"] = _abs_url(request, img_url(image_rel))
        og["image_alt"] = title
        size = _image_size(image_rel)
        if size:
            og["image_w"], og["image_h"] = size
    else:
        # An item with no photo, the gallery, the figures: the site's own card, so a
        # shared link is never the bare text preview it used to be.
        path, og["image_w"], og["image_h"] = SITE_CARD
        og["image"] = _abs_url(request, f"{path}?v={SITE_CARD_VER}")
        og["image_alt"] = "2600.me — the Retro Hardware Database"
    return og


def _jsonld(og, asset_id, brand, category):
    """schema.org Product data for an item, so search engines can show a richer
    result. Built from the same values as the social-share card."""
    d = {"@context": "https://schema.org", "@type": "Product",
         "name": og["title"], "sku": asset_id, "category": category}
    if og.get("description"):
        d["description"] = og["description"]
    if og.get("image"):
        d["image"] = og["image"]
    if og.get("url"):
        d["url"] = og["url"]
    if brand:
        d["brand"] = {"@type": "Brand", "name": brand}
    return d

# Signed-cookie session for the browser (the API/tools keep using HTTP Basic).
SECRET_KEY = (os.getenv("RHDB_SECRET_KEY")
              or hashlib.sha256(f"{AUTH_USER}:{AUTH_PASS}:rhdb".encode()).hexdigest())
COOKIE = "rhdb_session"
SESSION_MAX_AGE = 60 * 60 * 24 * 30
_signer = URLSafeTimedSerializer(SECRET_KEY, salt="rhdb-session")


def _check_basic(request: Request) -> bool:
    header = request.headers.get("authorization", "")
    if not header.startswith("Basic "):
        return False
    try:
        u, _, p = base64.b64decode(header[6:]).decode("utf-8").partition(":")
        return (secrets.compare_digest(u, AUTH_USER)
                and secrets.compare_digest(p, AUTH_PASS))
    except Exception:
        return False


def _check_cookie(request: Request) -> bool:
    token = request.cookies.get(COOKIE)
    if not token:
        return False
    try:
        _signer.loads(token, max_age=SESSION_MAX_AGE)
        return True
    except (BadSignature, SignatureExpired):
        return False


def _is_api_path(path: str) -> bool:
    return path.startswith(("/api", "/docs")) or path == "/openapi.json"


def _is_public_read(request: Request) -> bool:
    """Anonymous visitors get read-only GETs: the gallery, item pages, photos and
    static assets. Editing GETs (new/edit forms, delete confirmations, labels),
    the JSON API and /docs stay private, and every write (POST/PATCH/DELETE)
    requires login."""
    if request.method != "GET":
        return False
    path = request.url.path
    if path in ("/", "/stats", "/browse", "/suggest", "/robots.txt", "/sitemap.xml",
                "/favicon.ico",
                "/apple-touch-icon.png", "/apple-touch-icon-precomposed.png"):
        return True
    if path.startswith(("/images/", "/static/")):
        return True
    if path.startswith("/items/"):
        return True
    if path.startswith(("/computers/", "/parts/")):
        return not (path.endswith(("/new", "/delete"))
                    or "/edit" in path or "/label.pdf" in path)
    return False


@app.middleware("http")
async def auth_gate(request: Request, call_next):
    """Public read-only browsing; login required to edit. Browsers use a session
    cookie (login page + logout); the API and tools use HTTP Basic."""
    path = request.url.path
    api_path = _is_api_path(path)
    # Browser paths trust the session cookie only, so logout is reliable; the API
    # and docs also accept HTTP Basic for the MCP server and command-line tools.
    request.state.authed = (not AUTH_ENABLED or _check_cookie(request)
                            or (api_path and _check_basic(request)))
    if path in ("/login", "/logout"):
        return await call_next(request)
    if not request.state.authed and not _is_public_read(request):
        if api_path:
            return Response("Authentication required", status_code=401, headers={
                "WWW-Authenticate": 'Basic realm="Retro Hardware Database"'})
        return RedirectResponse(f"/login?next={quote(path)}", status_code=303)
    return await call_next(request)


def _safe_next(nxt: str) -> str:
    return nxt if nxt.startswith("/") and not nxt.startswith("//") else "/"


@app.get("/login", response_class=HTMLResponse, include_in_schema=False)
def gui_login(request: Request, next: str = "/"):
    if request.state.authed:
        return RedirectResponse(_safe_next(next), status_code=303)
    return templates.TemplateResponse(request, "login.html",
                                      {"next": _safe_next(next), "error": False,
                                       "noindex": True})


@app.post("/login", include_in_schema=False)
async def gui_do_login(request: Request):
    form = await request.form()
    nxt = _safe_next(form.get("next", "/") or "/")
    ok = (AUTH_ENABLED
          and secrets.compare_digest(form.get("username", ""), AUTH_USER)
          and secrets.compare_digest(form.get("password", ""), AUTH_PASS))
    if not ok:
        return templates.TemplateResponse(request, "login.html",
                                          {"next": nxt, "error": True, "noindex": True},
                                          status_code=401)
    resp = RedirectResponse(nxt, status_code=303)
    resp.set_cookie(COOKIE, _signer.dumps("ok"), max_age=SESSION_MAX_AGE,
                    httponly=True, samesite="lax",
                    secure=request.headers.get("x-forwarded-proto") == "https")
    return resp


@app.post("/logout", include_in_schema=False)
def gui_logout():
    resp = RedirectResponse("/", status_code=303)
    resp.delete_cookie(COOKIE)
    return resp


COMPUTER_FIELDS = [c.name for c in Computer.__table__.columns if c.name != "asset_id"]
PART_FIELDS = [c.name for c in Part.__table__.columns if c.name != "asset_id"]

# These are rendered from the memory and drive child tables, so the form loop must
# not write them, and the change log need not repeat the derived total.
DERIVED_FIELDS = {"installed_ram", "installed_ram_kb", "drives", "drives_note"}
COMPUTER_DIFF_FIELDS = [f for f in COMPUTER_FIELDS if f != "installed_ram_kb"]

# Container paths by default (the `images` volume and the goaccess report mount);
# overridable so the app can be imported and run outside Docker for local
# development, which the hardcoded absolute paths used to make impossible.
IMAGES_DIR = Path(os.getenv("RHDB_IMAGES_DIR", "/app/images"))
IMAGE_EXTS = (".jpg", ".jpeg", ".png", ".webp", ".gif")

# GoAccess writes a self-contained traffic report here (read-only mount from the
# shared volume). The route is login-only via the auth gate above.
STATS_DIR = Path(os.getenv("RHDB_STATS_DIR", "/app/stats"))


@app.get("/traffic", response_class=HTMLResponse, include_in_schema=False)
def gui_traffic():
    report = STATS_DIR / "index.html"
    if not report.exists():
        return HTMLResponse(
            "<p style='font-family:system-ui;margin:2rem'>No traffic report yet "
            "&mdash; it is generated from the access log every minute, so check "
            "back shortly.</p>")
    return HTMLResponse(report.read_text(encoding="utf-8"))


def _all_years(db):
    """Every year recorded against anything, machines and parts together."""
    years = [y for (y,) in db.query(Computer.year).filter(Computer.year.isnot(None))]
    return years + [y for (y,) in db.query(Part.year).filter(Part.year.isnot(None))]


# --- the pointless department -----------------------------------------------
# Figures that answer nothing anyone needs to know, which is the point of them. A
# page of totals says how big the collection is; these say what it is like.

# How many parts a maker needs before its record means anything. Below this a maker
# with one working card would top the table on a sample of one, which is not a
# fact about the maker. The caption on the page says the threshold, because a
# ranking whose entry condition is hidden is a ranking that flatters itself.
RELIABILITY_MIN = 5
# Not makers. These stand in the maker field for "we do not know" or "nobody in
# particular", and a league table of manufacturers should not have them in it.
NOT_A_MAKER = {"unknown", "generic", "various", "noname", "no name", "n/a", "-", "?"}


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


def _photo_counts(db, asset_ids):
    """How many photographs each asset has, from one pass over the two folders.

    A photo is <asset_id>.<ext> or <asset_id>-<something>.<ext>, so the stem is the
    tag itself or the tag with a suffix -- and the tags are matched against the
    register rather than guessed at with a regex, because an asset id is whatever
    ids.py says it is and not a shape this function should be repeating."""
    counts = {}
    for kind in ("computers", "parts"):
        for stem, _name in folder_images(kind):
            aid = stem if stem in asset_ids else stem.rsplit("-", 1)[0]
            if aid in asset_ids:
                counts[aid] = counts.get(aid, 0) + 1
    return counts


def _curios(db, st, this_year):
    """The shuffled half of /stats: every figure that has something to say today.

    Each is skipped rather than shown empty, so the pool is what the collection can
    currently answer -- a register with no acquisition dates simply never offers the
    ones about waiting. The page draws a handful at random from what comes back."""
    out = []

    def add(k, v, s, href=None):
        out.append({"k": k, "v": v, "s": s, "href": href})

    def named(obj):
        return entry.display_name(to_dict(obj))

    rel = _maker_reliability(db)
    if len(rel) >= 2:
        best, worst = rel[0], rel[-1]
        add("Most reliable maker", best[0],
            f"{best[2]} of {best[1]} parts working",
            f"/browse?f=maker&v={quote(best[0])}")
        add("Least reliable maker", worst[0],
            f"{worst[2]} of {worst[1]} parts working",
            f"/browse?f=maker&v={quote(worst[0])}")

    # The long wait: made one year, arrived another. Computers and parts together,
    # because the record is the same record either way.
    waits = []
    for model in (Computer, Part):
        for obj in (db.query(model)
                    .filter(model.year.isnot(None), model.acquired_date.isnot(None))):
            waits.append((obj.acquired_date.year - obj.year, obj))
    waits = [w for w in waits if w[0] > 0]
    if waits:
        gap, obj = max(waits, key=lambda w: w[0])
        kind = "computers" if isinstance(obj, Computer) else "parts"
        add("Longest wait", f"{gap} years",
            f"{named(obj)}, made {obj.year}, arrived {obj.acquired_date.year}",
            f"/{kind}/{obj.asset_id}")

    # Every floppy in every machine, as though each had a disk in it. Pure whimsy,
    # and it says so: the drives are real, the disks are hypothetical.
    #
    # Floppies and Goteks only. The same column holds an optical drive's size and a
    # card reader's, and a 4GB CF card among the 1.44s swamps the total: the first
    # draft of this said 7189 MB, of which 7000 was two memory cards.
    floppy_kb, floppy_n = 0, 0
    for size, count in db.query(ComputerDrive.size, ComputerDrive.count).filter(
            ComputerDrive.size != "",
            ComputerDrive.kind.in_(("floppy", "Gotek"))):
        kb = entry.to_kb(size)
        if kb:
            floppy_kb += kb * (count or 1)
            floppy_n += count or 1
    # Three drives is where adding them up starts being a joke rather than a sum;
    # below that "if all 2 drives had a disk in them" is just arithmetic.
    if floppy_kb and floppy_n >= 3:
        add("Every floppy at once", f"{round(floppy_kb / 1024)} MB",
            f"if all {floppy_n} drives had a disk in them",
            "/browse?f=drives")

    eventful = (db.query(LogEntry.asset_id, func.count(LogEntry.id))
                .group_by(LogEntry.asset_id)
                .order_by(func.count(LogEntry.id).desc()).first())
    if eventful:
        obj = db.get(Computer, eventful[0]) or db.get(Part, eventful[0])
        if obj:
            kind = "computers" if isinstance(obj, Computer) else "parts"
            add("Most written about", named(obj),
                f"{eventful[1]} entries in its history",
                f"/{kind}/{obj.asset_id}")

    lonely = [t for t, n, _v in st["types"] if n == 1]
    if lonely:
        # One is a thing; several is a count. "1 — categories with a single example:
        # Peripheral" says the same word twice and names it in the small print.
        add("One of a kind",
            entry.type_label(lonely[0]) if len(lonely) == 1 else str(len(lonely)),
            "the only one in the register" if len(lonely) == 1 else
            "categories with a single example: "
            + ", ".join(entry.type_label(t) for t in lonely[:3]),
            f"/browse?f=type&v={quote(lonely[0])}")

    ids = {a for (a,) in db.query(Computer.asset_id)} | {
        a for (a,) in db.query(Part.asset_id)}
    shots = _photo_counts(db, ids)
    if shots:
        aid, n = max(shots.items(), key=lambda kv: (kv[1], kv[0]))
        obj = db.get(Computer, aid) or db.get(Part, aid)
        if obj and n > 1:
            kind = "computers" if isinstance(obj, Computer) else "parts"
            add("Most photographed", named(obj), f"{n} pictures of it",
                f"/{kind}/{obj.asset_id}")
    bare = len(ids) - len(shots)
    if bare:
        add("Never photographed", str(bare),
            f"{round(100 * bare / len(ids))}% of the register, waiting for a camera",
            "/browse?f=nophotos")

    makers = db.query(func.count(func.distinct(Part.manufacturer))).filter(
        Part.manufacturer.isnot(None), Part.manufacturer != "").scalar() or 0
    if makers:
        add("Names on the parts", str(makers), "distinct makers in the register",
            "/browse?f=parts")

    # Counted in Python rather than grouped by YEAR(): the app runs on SQLite for
    # local development as well as on MariaDB, and that function is not portable.
    # At this size it is a few dozen dates either way.
    arrivals = Counter(d.year for (d,) in db.query(Part.acquired_date)
                       .filter(Part.acquired_date.isnot(None)))
    if arrivals:
        year, n = max(arrivals.items(), key=lambda kv: (kv[1], kv[0]))
        if n > 1:
            add("Busiest year for buying", str(year), f"{n} parts arrived",
                "/browse?f=held")

    source = (db.query(Part.source, func.count(Part.asset_id))
              .filter(Part.source.isnot(None), Part.source != "")
              .group_by(Part.source)
              .order_by(func.count(Part.asset_id).desc()).first())
    if source and source[1] > 1:
        add("Where things come from", source[0], f"{source[1]} parts from there",
            f"/browse?f=source&v={quote(source[0])}")

    caps = [(kb, pid) for pid, kb in db.query(StorageSpec.part_id,
                                              StorageSpec.capacity_kb)
            .filter(StorageSpec.capacity_kb.isnot(None), StorageSpec.capacity_kb > 0)]
    if len(caps) >= 2:
        big, small = max(caps), min(caps)
        add("Biggest and smallest disk",
            f"{entry.fmt_kb(big[0], True)} / {entry.fmt_kb(small[0], True)}",
            f"a factor of {round(big[0] / small[0]):,} between them",
            "/browse?f=storage")

    chips = (db.query(ComputerRamChip.computer_id, func.sum(ComputerRamChip.count))
             .group_by(ComputerRamChip.computer_id)
             .order_by(func.sum(ComputerRamChip.count).desc()).first())
    if chips:
        machine = db.get(Computer, chips[0])
        if machine:
            add("Most memory chips", named(machine),
                f"{int(chips[1])} of them in one machine",
                f"/computers/{machine.asset_id}")

    longest, holder, holder_kind = 0, None, ""
    for model, kind in ((Computer, "computers"), (Part, "parts")):
        for obj in db.query(model):
            name = named(obj)
            if len(name) > longest:
                longest, holder, holder_kind = len(name), obj, kind
    if holder and longest > 20:
        add("Longest name in the register", f"{longest} characters", named(holder),
            f"/{holder_kind}/{holder.asset_id}")

    # Not when this year is also the busiest: two tiles saying "48 parts, 2026" in
    # one draw is the shuffle looking like it is broken.
    if arrivals.get(this_year) and max(arrivals, key=arrivals.get) != this_year:
        add(f"Arrived in {this_year}", str(arrivals[this_year]),
            "parts so far this year", "/browse?f=held")

    return out


def _collection_stats(db):
    """Figures about the collection for the public /stats page. Everything here is
    counted from the typed columns and child tables rather than parsed out of
    strings, which is the whole point of their being typed.

    The ranked lists carry three fields per row -- label, count, and the value to
    query on -- so that a bar on the page can link to the items behind it. Usually
    the label is the value; for part types the label is prettified and the raw type
    key is what /browse needs."""
    n_computers = db.query(func.count(Computer.asset_id)).scalar() or 0
    n_parts = db.query(func.count(Part.asset_id)).scalar() or 0

    def ranked(query, limit=None):
        rows = [(k, n, k) for k, n in query if (k or "").strip()]
        rows.sort(key=lambda r: (-r[1], r[0]))
        return rows[:limit] if limit else rows

    makers = ranked(db.query(Part.manufacturer, func.count(Part.asset_id))
                    .group_by(Part.manufacturer), 8)
    types = ranked(db.query(Part.type, func.count(Part.asset_id))
                   .group_by(Part.type))
    buses = ranked(db.query(PartSlot.bus, func.sum(PartSlot.count))
                   .group_by(PartSlot.bus), 6)
    ports = ranked(db.query(PartPort.port, func.sum(PartPort.count))
                   .group_by(PartPort.port), 6)
    conditions = ranked(db.query(Part.condition, func.count(Part.asset_id))
                        .group_by(Part.condition))

    years = _all_years(db)
    ram = [kb for (kb,) in db.query(Computer.installed_ram_kb)
           .filter(Computer.installed_ram_kb.isnot(None))]
    common_ram = sorted(((entry.fmt_kb(kb), ram.count(kb), kb) for kb in set(ram)),
                        key=lambda r: (-r[1], r[0]))
    # Ties share the honour: two sizes fitted to three machines each are both "the
    # usual amount". Sorted by count, so the ties are the rows at the front.
    top_ram = [r for r in common_ram if r[1] == common_ram[0][1]][:3] if common_ram else []

    fitted_kb = sum(ram)
    stored_kb = db.query(func.sum(StorageSpec.capacity_kb)).scalar() or 0
    slots = db.query(func.sum(PartSlot.count)).scalar() or 0
    boards = db.query(func.count(func.distinct(PartSlot.part_id))).scalar() or 0
    chips = db.query(func.sum(ComputerRamChip.count)).scalar() or 0
    drives = db.query(func.sum(ComputerDrive.count)).scalar() or 0
    gotek = db.query(func.count(ComputerDrive.id)).filter(
        ComputerDrive.kind == "Gotek").scalar() or 0
    working = db.query(func.count(Part.asset_id)).filter(
        Part.condition == "Working").scalar() or 0
    disposed = ((db.query(func.count(Part.asset_id)).filter(Part.disposed).scalar() or 0)
                + (db.query(func.count(Computer.asset_id))
                   .filter(Computer.disposed).scalar() or 0))

    fullest = (db.query(Part.computer_id, func.count(Part.asset_id))
               .filter(Part.computer_id.isnot(None))
               .group_by(Part.computer_id)
               .order_by(func.count(Part.asset_id).desc()).first())
    fullest_machine = db.get(Computer, fullest[0]) if fullest else None

    oldest_held = (db.query(Part).filter(Part.acquired_date.isnot(None))
                   .order_by(Part.acquired_date).first())
    photos = sum(len(folder_images(k)) for k in ("computers", "parts"))
    # Most parts are spares on a shelf, so "parts per machine" over the whole
    # register would say 19 and mean nothing. Only the fitted ones divide.
    fitted = db.query(func.count(Part.asset_id)).filter(
        Part.computer_id.isnot(None)).scalar() or 0

    return {
        "n_computers": n_computers, "n_parts": n_parts,
        "n_total": n_computers + n_parts,
        "makers": makers, "types": types, "buses": buses, "ports": ports,
        "types_labelled": [(entry.type_label(t), n, t) for t, n, _ in types],
        "conditions": conditions,
        "top_maker": makers[0] if makers else None,
        "top_type": types[0] if types else None,
        "top_ram": top_ram, "top_ram_kb": [r[2] for r in top_ram],
        "mean_year": round(sum(years) / len(years)) if years else None,
        "oldest_year": min(years) if years else None,
        "newest_year": max(years) if years else None,
        "fitted_kb": fitted_kb, "stored_kb": stored_kb,
        "slots": slots, "boards": boards, "chips": chips,
        "drives": drives, "gotek": gotek,
        "working": working, "disposed": disposed, "photos": photos,
        "fullest": (fullest_machine, fullest[1]) if fullest_machine else None,
        "oldest_held": oldest_held,
        "fitted": fitted, "spares": n_parts - fitted,
        # Guarded because an empty register is a real state -- a fresh install --
        # and a stats page that divides by zero on day one is no use to anyone.
        "fitted_per_machine": (round(fitted / n_computers, 1) if n_computers else None),
        "working_pct": (round(100 * working / n_parts) if n_parts else None),
        "slots_per_board": (round(slots / boards, 1) if boards else None),
    }


# How many of the shuffled figures a visit gets. Six fills two rows on a wide
# screen and still leaves the page's fixed figures as the page, rather than a
# preamble to a slot machine.
CURIOS_SHOWN = 6


@app.get("/stats", response_class=HTMLResponse, include_in_schema=False)
def gui_stats(request: Request, db: Session = Depends(get_db)):
    this_year = date.today().year
    st = _collection_stats(db)
    # A different handful each time the page is looked at. The pool is only the
    # figures that have something to say today, so the sample is never padded with
    # blanks; sample() rather than shuffle() because it also handles a pool smaller
    # than the handful, which is what a young register has.
    pool = _curios(db, st, this_year)
    st["curios"] = random.sample(pool, min(CURIOS_SHOWN, len(pool)))
    st["n_curios"] = len(pool)
    rel = _maker_reliability(db)
    # Shaped for the rank macro here rather than in the template: (label, bar, the
    # value /browse needs). The macro takes rows, not a data model.
    st["reliability_rank"] = [(maker, pct, maker) for maker, _n, _w, pct in rel]
    st["reliability_min"] = RELIABILITY_MIN
    # The description a crawler or a chat window sees is the collection, not
    # whichever six figures this particular render drew.
    blurb = (f"{st['n_total']} things in the register: {st['n_computers']} machines "
             f"and {st['n_parts']} parts, averaging {st['mean_year']}.")
    return templates.TemplateResponse(request, "stats.html", {
        "st": st, "this_year": this_year,
        "og": _og(request, "The collection by numbers", blurb)})


@app.get("/robots.txt", include_in_schema=False)
def robots_txt(request: Request):
    base = PUBLIC_BASE_URL or str(request.base_url).rstrip("/")
    body = (
        "User-agent: *\n"
        "Allow: /\n"
        "Disallow: /api\n"
        "Disallow: /docs\n"
        "Disallow: /openapi.json\n"
        "Disallow: /login\n"
        "Disallow: /logout\n"
        "Disallow: /traffic\n"
        # Filtered slices of the gallery: the items in them are indexed already.
        "Disallow: /browse\n"
        # What the search bar reads while you type: JSON about pages already indexed.
        "Disallow: /suggest\n"
        "Disallow: /computers/new\n"
        "Disallow: /parts/new\n"
        "Disallow: /*/edit\n"
        f"Sitemap: {base}/sitemap.xml\n")
    return Response(body, media_type="text/plain")


@app.get("/sitemap.xml", include_in_schema=False)
def sitemap_xml(request: Request, db: Session = Depends(get_db)):
    base = PUBLIC_BASE_URL or str(request.base_url).rstrip("/")
    # Newest change per asset, for <lastmod>.
    last = dict(db.query(
        LogEntry.asset_id, func.max(LogEntry.created_at)).group_by(LogEntry.asset_id))
    urls = [(f"{base}/", None), (f"{base}/stats", None)]
    for c in db.query(Computer.asset_id).order_by(Computer.asset_id):
        urls.append((f"{base}/computers/{c.asset_id}", last.get(c.asset_id)))
    for p in db.query(Part.asset_id).order_by(Part.asset_id):
        urls.append((f"{base}/parts/{p.asset_id}", last.get(p.asset_id)))
    lines = ['<?xml version="1.0" encoding="UTF-8"?>',
             '<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">']
    for loc, ts in urls:
        lines.append("  <url>")
        lines.append(f"    <loc>{escape(loc)}</loc>")
        if ts:
            lines.append(f"    <lastmod>{ts.strftime('%Y-%m-%d')}</lastmod>")
        lines.append("  </url>")
    lines.append("</urlset>")
    return Response("\n".join(lines), media_type="application/xml")


STATIC_DIR = Path(__file__).resolve().parent / "static"


def _file_ver(path: Path) -> str:
    """Short content hash of a file, or '0' if it is not there. Used to name things
    after the artwork that went into them, so replacing the artwork misses every
    cache keyed on it -- the browser's favicon cache is famously sticky, and a
    watermark already composited into a served photo is stickier still."""
    try:
        return hashlib.md5(path.read_bytes()).hexdigest()[:8]
    except OSError:
        return "0"


templates.env.globals["icon_ver"] = _file_ver(STATIC_DIR / "favicon.ico")
# Social sites cache a card hard, so its URL carries the artwork's hash too.
SITE_CARD_VER = _file_ver(STATIC_DIR / SITE_CARD[0].removeprefix("/static/"))
_ICON_CACHE = {"Cache-Control": "public, max-age=86400"}


# Browsers and crawlers request these at the domain root regardless of markup.
@app.get("/favicon.ico", include_in_schema=False)
def favicon():
    return FileResponse(STATIC_DIR / "favicon.ico", headers=_ICON_CACHE)


@app.get("/apple-touch-icon.png", include_in_schema=False)
@app.get("/apple-touch-icon-precomposed.png", include_in_schema=False)
def apple_touch_icon():
    return FileResponse(STATIC_DIR / "apple-touch-icon.png", headers=_ICON_CACHE)


for sub in ("computers", "parts"):
    (IMAGES_DIR / sub).mkdir(parents=True, exist_ok=True)
app.mount("/static", StaticFiles(directory=str(STATIC_DIR)), name="static")

# Our own photos are served with a small RHDB watermark composited in a corner,
# so shared/saved copies carry attribution. Originals on disk are never altered;
# the watermarked version is cached next to a mtime check. Reference (not-ours)
# images and favicons are served untouched. Toggle with RHDB_WATERMARK=0.
WATERMARK = os.getenv("RHDB_WATERMARK", "1").lower() not in ("0", "false", "no", "off")
# The logo at its own proportions (tools/make_icons.py writes it), not the squared
# app icon: a mark letterbox-padded inside a square would sit on the photo smaller
# than the numbers below ask for. Falls back to the square icon if it is missing.
WM_SRC = STATIC_DIR / "logo-512.png"
if not WM_SRC.exists():
    WM_SRC = STATIC_DIR / "icon-512.png"

# A proportion of the photo's short edge, so the mark stays legible on a 5712px
# photo and unobtrusive on a small one, with a floor for the very small.
WM_SCALE = 0.216
WM_MIN_PX = 41
WM_OPACITY = 0.55
WM_MARGIN = 0.03
# Bumped when the compositing itself changes rather than the numbers above, so the
# cache misses and every copy is rebuilt. 2: EXIF orientation is baked in, which
# every photo cached before it was is missing.
WM_BUILD = 2

# The cache lives under a directory named after those numbers, and after the mark
# itself. A cached copy is otherwise only rebuilt when its source photo changes, so
# changing the size here left every existing watermark at the old one until its
# photo was next edited -- twice now. Naming the directory after what went into it
# means a change simply misses the old cache instead of needing anyone to remember;
# the artwork's hash is in there because a new site icon is a new watermark, and
# every photo already served carries the old one.
WM_CACHE = (IMAGES_DIR / ".wm"
            / f"s{WM_SCALE}-m{WM_MIN_PX}-o{WM_OPACITY}-b{WM_BUILD}-i{_file_ver(WM_SRC)}")

if WATERMARK:
    WM_CACHE.mkdir(parents=True, exist_ok=True)
    for stale in WM_CACHE.parent.iterdir():
        if stale.is_dir() and stale != WM_CACHE:
            shutil.rmtree(stale, ignore_errors=True)


def _make_watermark(src_path: Path, dst_path: Path):
    from PIL import Image, ImageOps
    # Bake in EXIF orientation, exactly as editing a photo does. This copy is
    # re-encoded without the EXIF block, so a photo whose pixels lie on their side
    # and say so only in that block would be served -- and shown -- on its side.
    # Worse than looking wrong: a crop dragged on that view was being mapped onto
    # the upright original, so it kept a different region of the photo altogether.
    with Image.open(src_path) as src:
        base = ImageOps.exif_transpose(src).convert("RGBA")
    w, h = base.size
    mark = Image.open(WM_SRC).convert("RGBA")
    target = max(WM_MIN_PX, int(min(w, h) * WM_SCALE))
    mark.thumbnail((target, target), Image.LANCZOS)
    mark.putalpha(mark.getchannel("A").point(lambda a: int(a * WM_OPACITY)))
    margin = max(6, int(min(w, h) * WM_MARGIN))
    layer = Image.new("RGBA", base.size, (0, 0, 0, 0))
    layer.paste(mark, (w - mark.width - margin, h - mark.height - margin), mark)
    out = Image.alpha_composite(base, layer)
    dst_path.parent.mkdir(parents=True, exist_ok=True)
    if dst_path.suffix.lower() in (".jpg", ".jpeg"):
        out.convert("RGB").save(dst_path, "JPEG", quality=88)
    else:
        out.save(dst_path)


def _watermarked_file(rel: str) -> Path:
    """Path to the cached watermarked copy of an image, regenerated if stale.
    Falls back to the original on any compositing error."""
    src = IMAGES_DIR / rel
    dst = WM_CACHE / rel
    try:
        if not dst.exists() or dst.stat().st_mtime < src.stat().st_mtime:
            _make_watermark(src, dst)
        return dst
    except Exception:
        return src


def _wm_forget(rel: str):
    """Drop an image's cached watermark (on delete / rename) so it regenerates."""
    with contextlib.suppress(OSError):
        (WM_CACHE / rel).unlink(missing_ok=True)


def _is_own_photo(rel: str) -> bool:
    ext = Path(rel).suffix.lower()
    return (WATERMARK and ext in IMAGE_EXTS
            and (rel.startswith(("computers/", "parts/")))
            and not is_reference(rel))


@app.get("/images/{path:path}", include_in_schema=False)
def serve_image(path: str):
    # Reject traversal, dotfiles/dotdirs (e.g. the .wm cache) and non-images.
    if any(seg.startswith(".") for seg in path.split("/")):
        raise HTTPException(404)
    full = (IMAGES_DIR / path).resolve()
    if not str(full).startswith(str(IMAGES_DIR.resolve()) + os.sep) or not full.is_file():
        raise HTTPException(404)
    if full.suffix.lower() not in IMAGE_EXTS:
        raise HTTPException(404)
    served = _watermarked_file(path) if _is_own_photo(path) else full
    return FileResponse(served, headers={"Cache-Control": "public, max-age=3600"})


def get_or_404(db, model, aid):
    obj = db.get(model, (aid or "").upper())
    if not obj:
        raise HTTPException(404, f"{model.__tablename__} {aid} not found")
    return obj


def to_dict(obj):
    return {c.name: getattr(obj, c.name) for c in obj.__table__.columns}


def _now():
    """Naive UTC, matching the column and every row already in it. utcnow() is
    deprecated, and an aware value here would be inconsistent with the history
    written before this."""
    return datetime.now(UTC).replace(tzinfo=None)


def add_log(db, asset_id, message, kind="change"):
    """Record a dated history entry for an asset. The caller commits."""
    if not message:
        return
    db.add(LogEntry(asset_id=asset_id, created_at=_now(),
                    kind=kind, message=message))


def item_log(db, asset_id):
    return (db.query(LogEntry).filter(LogEntry.asset_id == asset_id)
            .order_by(LogEntry.created_at.desc(), LogEntry.id.desc()).all())


def log_stamp(created_at, authed):
    """A history line's date, with the clock time only for whoever is signed in.
    Editing wants the minute -- it is how you tell apart two corrections to the same
    photo -- but a visitor is reading about the machine, and the time of day says
    more about the owner's evenings than about the hardware."""
    if not created_at:
        return ""
    return created_at.strftime("%Y-%m-%d %H:%M" if authed else "%Y-%m-%d")


templates.env.globals["log_stamp"] = log_stamp


def _short(v, limit=80):
    v = "" if v is None else str(v).strip()
    if not v:
        return "(empty)"
    return v if len(v) <= limit else v[:limit - 1] + "…"


def _disposal_log(obj, with_machine=None):
    """The history line for a disposal: when, and why if a reason was given."""
    when = obj.disposed_at.isoformat() if obj.disposed_at else "date unknown"
    who = f" with {with_machine}" if with_machine else ""
    return f"marked disposed{who} ({when})" + (f": {obj.disposed_note}"
                                               if obj.disposed_note else "")


def _parts_in_computer(db, aid):
    """Everything inside a machine: the parts installed in it, and then whatever
    is mounted on those in turn. A disk on a controller card carries the card's
    id rather than the machine's, so following computer_id alone would miss it."""
    found, seen = [], set()
    ids, first = [aid], True
    while ids:
        q = db.query(Part).filter(Part.computer_id == aid) if first \
            else db.query(Part).filter(Part.parent_id.in_(ids))
        rows = [p for p in q.order_by(Part.asset_id).all() if p.asset_id not in seen]
        seen.update(p.asset_id for p in rows)
        found.extend(rows)
        ids, first = [p.asset_id for p in rows], False
    return found


def _dispose_contents(db, c):
    """A machine goes to the tip with what is in it. A part already disposed keeps
    the record it has -- it did not go with this machine -- and so is left alone,
    which is also what lets a restore tell the two apart."""
    n = 0
    for p in _parts_in_computer(db, c.asset_id):
        if p.disposed:
            continue
        p.disposed, p.disposed_at = True, c.disposed_at
        p.disposed_note = c.disposed_note
        add_log(db, p.asset_id, _disposal_log(p, c.asset_id))
        n += 1
    return n


def _restore_contents(db, c, was_at, was_note):
    """The other half of the cascade: the parts that went out with this machine --
    still in it, and still carrying its disposal record -- come back with it."""
    n = 0
    for p in _parts_in_computer(db, c.asset_id):
        if not (p.disposed and p.disposed_at == was_at
                and (p.disposed_note or "") == (was_note or "")):
            continue
        p.disposed, p.disposed_at, p.disposed_note = False, None, ""
        add_log(db, p.asset_id, f"restored with {c.asset_id}")
        n += 1
    return n


def _and_parts(n, went="went with it"):
    """The tail of a machine's history line when the cascade touched anything."""
    return f"\n{n} part{'' if n == 1 else 's'} in it {went}" if n else ""


def _parse_date(raw):
    """A date from a form field. ISO is what <input type="date"> submits; the
    day-first form is accepted too because it is what gets typed by hand.
    Anything else, including blank, means not recorded."""
    v = (raw or "").strip()
    for fmt in ("%Y-%m-%d", "%d/%m/%Y", "%d/%m/%y"):
        try:
            return datetime.strptime(v, fmt).date()
        except ValueError:
            pass
    return None


def _coerce(field, raw):
    """A form string as the column's type: blank means not recorded."""
    if field == "year":
        v = (raw or "").strip()
        return int(v) if v.isdigit() else None
    if field in ("acquired_date", "disposed_at"):
        return _parse_date(raw)
    if field == "disposed":
        return (raw or "").strip() not in ("", "0", "false")
    return raw or ""


def _field_diffs(old, new, keys, semantic_specs=False):
    """A one-change-per-line diff of old vs new field values, for the change log.
    specs is broken down per spec key; re-canonicalising an unchanged specs
    string produces no diff."""
    lines = []
    for k in keys:
        ov, nv = old.get(k) or "", new.get(k) or ""
        if semantic_specs and k == "specs":
            o, n = dict(entry.parse_specs(ov)), dict(entry.parse_specs(nv))
            for sk in [x for x in n if x not in o or o[x] != n[x]]:
                lines.append(f"{sk or 'spec'}: {_short(o.get(sk))} → {_short(n[sk])}")
            for sk in [x for x in o if x not in n]:
                lines.append(f"{sk or 'spec'}: {_short(o[sk])} → (removed)")
        elif ov != nv:
            lines.append(f"{k}: {_short(ov)} → {_short(nv)}")
    return "\n".join(lines)


# --- JSON API: computers ---------------------------------------------------

def _drives_from_api(db, computer, text):
    """drives over the wire is what a person would type, ';'-separated, and is
    parsed into rows the way the specs string is -- anything a segment does not
    yield is kept verbatim in drives_note."""
    drives, note = drivedb.from_string(text)
    drivedb.write(db, computer, drives, note)


def _ram_from_api(db, computer, text):
    """installed_ram over the wire is a plain amount ('640KB') or free text, never
    a module breakdown -- that has its own grids in the GUI. A caller sending one
    replaces any note and total but leaves the fitted modules and chips alone."""
    total_kb, note = ramdb.from_string(text)
    ramdb.write(db, computer, note=note, total_kb=total_kb)


@app.get("/api/computers", response_model=list[ComputerOut], tags=["computers"])
def api_list_computers(db: Session = Depends(get_db)):
    return db.query(Computer).order_by(Computer.asset_id).all()


@app.post("/api/computers", response_model=ComputerOut, tags=["computers"])
def api_create_computer(data: ComputerIn, db: Session = Depends(get_db)):
    fields = data.model_dump()
    ram = fields.pop("installed_ram", "")
    drives = fields.pop("drives", "")
    obj = Computer(asset_id=next_asset_id(db), **fields)
    db.add(obj)
    db.flush()
    _ram_from_api(db, obj, ram)
    _drives_from_api(db, obj, drives)
    add_log(db, obj.asset_id, "created", "created")
    db.commit()
    db.refresh(obj)
    return obj


@app.get("/api/computers/{aid}", response_model=ComputerOut, tags=["computers"])
def api_get_computer(aid: str, db: Session = Depends(get_db)):
    return get_or_404(db, Computer, aid)


@app.patch("/api/computers/{aid}", response_model=ComputerOut, tags=["computers"])
def api_update_computer(aid: str, data: ComputerIn, db: Session = Depends(get_db)):
    obj = get_or_404(db, Computer, aid)
    fields = data.model_dump(exclude_unset=True)
    ram = fields.pop("installed_ram", None)
    drives = fields.pop("drives", None)
    derived = ("installed_ram", "drives")
    old = {k: getattr(obj, k) for k in fields} | {k: getattr(obj, k) for k in derived}
    for k, v in fields.items():
        setattr(obj, k, v)
    if ram is not None:
        _ram_from_api(db, obj, ram)
    if drives is not None:
        _drives_from_api(db, obj, drives)
    new = {k: getattr(obj, k) for k in fields} | {k: getattr(obj, k) for k in derived}
    diff = _field_diffs(old, new, list(fields) + list(derived))
    # The contents follow the machine whichever door the change came in by, so
    # that the API and the GUI cannot leave the register in different states.
    n = 0
    if "disposed" in fields and bool(old["disposed"]) != bool(obj.disposed):
        if obj.disposed:
            n = _dispose_contents(db, obj)
        else:
            # A patch that clears the flag need not clear the date and note as
            # well, so the record to match the parts against is whichever of the
            # two the request left behind.
            n = _restore_contents(
                db, obj,
                old["disposed_at"] if "disposed_at" in fields else obj.disposed_at,
                old["disposed_note"] if "disposed_note" in fields else obj.disposed_note)
    if diff or n:
        add_log(db, aid, (diff + _and_parts(
            n, "went with it" if obj.disposed else "came back too")).strip())
    db.commit()
    db.refresh(obj)
    return obj


@app.delete("/api/computers/{aid}", tags=["computers"])
def api_delete_computer(aid: str, db: Session = Depends(get_db)):
    """Delete a computer. The parts inside it are unlinked, not deleted; its
    photos, drive/memory rows and history go with it (see delete_computer). The
    API deletes any computer -- the disposed-only rule and the confirmation are
    the GUI's, where a delete is a click rather than a deliberate request."""
    obj = get_or_404(db, Computer, aid)
    return {"deleted": aid, "photos": len(delete_computer(db, obj))}


# --- JSON API: parts -------------------------------------------------------

@app.get("/api/parts", response_model=list[PartOut], tags=["parts"])
def api_list_parts(computer_id: str | None = None, type: str | None = None,
                   db: Session = Depends(get_db)):
    q = db.query(Part)
    if computer_id is not None:
        q = q.filter(Part.computer_id.is_(None) if computer_id == ""
                     else Part.computer_id == computer_id)
    if type is not None:
        q = q.filter(Part.type == type)
    return q.order_by(Part.asset_id).all()


def _check_links(db, fields):
    """A part's links must point at something that exists. The foreign keys
    refuse a bad one anyway; this says which id was wrong."""
    cid = fields.get("computer_id")
    if cid and not db.get(Computer, cid):
        raise HTTPException(404, f"no computer {cid}")
    pid = fields.get("parent_id")
    if pid and not db.get(Part, pid):
        raise HTTPException(404, f"no part {pid}")


@app.post("/api/parts", response_model=PartOut, tags=["parts"])
def api_create_part(data: PartIn, db: Session = Depends(get_db)):
    _check_links(db, data.model_dump())
    obj = Part(asset_id=next_asset_id(db), **data.model_dump())
    db.add(obj)
    db.flush()
    specdb.write(db, obj)
    add_log(db, obj.asset_id, "created", "created")
    db.commit()
    db.refresh(obj)
    return obj


@app.get("/api/parts/{aid}", response_model=PartOut, tags=["parts"])
def api_get_part(aid: str, db: Session = Depends(get_db)):
    return get_or_404(db, Part, aid)


@app.patch("/api/parts/{aid}", response_model=PartOut, tags=["parts"])
def api_update_part(aid: str, data: PartIn, db: Session = Depends(get_db)):
    obj = get_or_404(db, Part, aid)
    fields = data.model_dump(exclude_unset=True)
    _check_links(db, fields)
    old = {k: getattr(obj, k) for k in fields}
    for k, v in fields.items():
        setattr(obj, k, v)
    specdb.write(db, obj)
    new = {k: getattr(obj, k) for k in fields}
    diff = _field_diffs(old, new, list(fields), semantic_specs=True)
    if diff:
        add_log(db, aid, diff)
    db.commit()
    db.refresh(obj)
    return obj


@app.delete("/api/parts/{aid}", tags=["parts"])
def api_delete_part(aid: str, db: Session = Depends(get_db)):
    """Delete a part, with its typed spec rows, photos and history. Anything
    mounted on it is unlinked, not deleted."""
    obj = get_or_404(db, Part, aid)
    return {"deleted": aid, "photos": len(delete_part(db, obj))}


@app.get("/api/items/{aid}/log", tags=["log"])
def api_item_log(aid: str, db: Session = Depends(get_db)):
    return [{"created_at": e.created_at.isoformat() if e.created_at else None,
             "kind": e.kind, "message": e.message} for e in item_log(db, aid)]


def folder_images(kind):
    """(stem, filename) for every photo in one of the image folders, in a single
    pass. A page showing many assets reads the folder once and picks from the
    result rather than scanning it per row."""
    folder = IMAGES_DIR / kind
    if not folder.exists():
        return []
    return [(f.stem, f.name) for f in folder.iterdir()
            if f.suffix.lower() in IMAGE_EXTS]


def pick_images(kind, asset_id, listing):
    """An asset's photos from a folder listing: <asset_id>.<ext> first, then -2,
    -3, ..., then any other suffix alphabetically."""
    primary, extras = [], []
    for stem, name in listing:
        if stem == asset_id:
            primary.append(f"{kind}/{name}")
        elif stem.startswith(asset_id + "-"):
            extras.append((stem, name))

    def sort_key(item):
        suffix = item[0][len(asset_id) + 1:]
        return (0, int(suffix), "") if suffix.isdigit() else (1, 0, suffix.lower())

    return primary + [f"{kind}/{name}" for _stem, name in sorted(extras, key=sort_key)]


def detect_images(kind, asset_id):
    """Ordered photos for one asset."""
    return pick_images(kind, asset_id, folder_images(kind))


def _photo_target(kind, asset_id, ext):
    """Path for a new photo: <asset_id>.<ext> for the first (the primary), then
    the next free -N suffix so an item can carry several."""
    folder = IMAGES_DIR / kind
    folder.mkdir(parents=True, exist_ok=True)
    existing = detect_images(kind, asset_id)
    if not any(Path(p).stem == asset_id for p in existing):
        name = f"{asset_id}{ext}"
    else:
        n = 2
        while any(Path(p).stem == f"{asset_id}-{n}" for p in existing):
            n += 1
        name = f"{asset_id}-{n}{ext}"
    return folder / name, f"{kind}/{name}"


def _save_photo(kind, asset_id, upload: UploadFile):
    ext = Path(upload.filename or "").suffix.lower() or ".jpg"
    if ext not in IMAGE_EXTS:
        raise HTTPException(400, f"unsupported image type: {ext}")
    path, rel = _photo_target(kind, asset_id, ext)
    with open(path, "wb") as f:
        shutil.copyfileobj(upload.file, f)
    return rel


def _chosen_photos(form):
    """The photos picked on a create form, every one of them checked before any is
    written. The item is committed before its photos are stored, so its asset id is
    settled first: a file rejected half way would otherwise leave photos filed
    under an id the item never kept, which the next thing created would inherit."""
    # A form value is either text or an upload, and the upload is Starlette's own
    # class -- not the FastAPI subclass the typed routes are annotated with, so it
    # is the text case that is worth excluding here.
    ups = [u for u in form.getlist("photos")
           if not isinstance(u, str) and (u.filename or "").strip()]
    for up in ups:
        ext = Path(up.filename or "").suffix.lower() or ".jpg"
        if ext not in IMAGE_EXTS:
            raise HTTPException(400, f"unsupported image type: {ext}")
    return ups


def _attach_photos(db, obj, kind, uploads):
    """Store photos against an item that has only just been created. Nothing can
    upload while a create form is still being filled in -- there is no asset id to
    file a photo under yet -- so they come with the form and are written here."""
    first = None
    for up in uploads:
        rel = _save_photo(kind, obj.asset_id, up)
        if first is None:
            first = rel
    if first and not obj.image:
        obj.image = first
    if uploads:
        add_log(db, obj.asset_id, f"added {len(uploads)} photo(s)")


def _fetch_reference_photo(kind, asset_id, url):
    """Pull a photo from the item's reference URL (Wikipedia API or og:image),
    store it, and return its relative path (or None if nothing was found)."""
    data = enrich.fetch_jpeg(url)
    if not data:
        return None
    path, rel = _photo_target(kind, asset_id, ".jpg")
    path.write_bytes(data)
    # A fetched photo is from the reference source, not necessarily this unit;
    # record the source so we can show its favicon.
    _mark_reference(rel, True, "Photo from the reference source, may not be this exact unit", url)
    return rel


# A photo can be flagged as a reference / stock image (not a photo of the actual
# unit) with a small ".ref" sidecar file next to it. The sidecar holds JSON with
# an optional note and the source URL it was crawled from; from that source we
# cache the site's favicon and show it in the photo's corner. No schema change,
# and the marker travels with the image.
FAVICON_DIR = IMAGES_DIR / "favicons"
_DEFAULT_REF_NOTE = "Illustrative image, not this exact unit"


def _ref_sidecar(rel):
    p = IMAGES_DIR / rel
    return p.with_name(p.name + ".ref")


def is_reference(rel):
    return bool(rel) and _ref_sidecar(rel).exists()


def _read_ref(rel):
    """{'note':.., 'source':..} for a reference image, or None if not flagged.
    Tolerates the pre-JSON format where the sidecar held a bare note string."""
    try:
        raw = _ref_sidecar(rel).read_text(encoding="utf-8").strip()
    except OSError:
        return None
    if raw.startswith("{"):
        try:
            d = json.loads(raw)
            return {"note": d.get("note", ""), "source": d.get("source", "")}
        except ValueError:
            pass
    return {"note": raw, "source": ""}


def _favicon_rel(source):
    """Relative path of the cached favicon for a source URL's host, if present."""
    host = urlparse(source or "").hostname or ""
    if host and (FAVICON_DIR / f"{host}.png").exists():
        return f"favicons/{host}.png"
    return ""


def reference_marks(kind, asset_id):
    """{rel: {'note':.., 'icon':..}} for the item's flagged reference photos."""
    out = {}
    for rel in detect_images(kind, asset_id):
        info = _read_ref(rel)
        if info is not None:
            out[rel] = {"note": info["note"] or _DEFAULT_REF_NOTE,
                        "icon": _favicon_rel(info["source"])}
    return out


def _favicon_for_rel(rel):
    """Cached source favicon path for a single image rel, or '' (for index cards)."""
    info = _read_ref(rel) if rel else None
    return _favicon_rel(info["source"]) if info else ""


def img_url(rel):
    """/images URL for a photo with a cache-busting ?v= stamp from its mtime, so
    the browser refetches after an edit or watermark change rather than showing a
    stale cached copy. Reflects the reference-marker sidecar too (its toggle
    changes whether the served image is watermarked)."""
    if not rel:
        return ""
    ts = 0
    for p in (IMAGES_DIR / rel, _ref_sidecar(rel)):
        with contextlib.suppress(OSError):
            ts = max(ts, int(p.stat().st_mtime))
    return f"/images/{rel}?v={ts}" if ts else f"/images/{rel}"


templates.env.globals["img_url"] = img_url


def _cache_favicon(source):
    """Fetch and cache the source site's favicon; return its rel path or ''."""
    host = urlparse(source or "").hostname or ""
    if not host:
        return ""
    dest = FAVICON_DIR / f"{host}.png"
    if dest.exists():
        return f"favicons/{host}.png"
    data = enrich.fetch_favicon(source)
    if not data:
        return ""
    FAVICON_DIR.mkdir(parents=True, exist_ok=True)
    dest.write_bytes(data)
    return f"favicons/{host}.png"


def _mark_reference(rel, on, note="", source=""):
    sc = _ref_sidecar(rel)
    if on:
        sc.write_text(json.dumps({"note": note or _DEFAULT_REF_NOTE, "source": source}),
                      encoding="utf-8")
        if source:
            _cache_favicon(source)
    elif sc.exists():
        sc.unlink()
    _wm_forget(rel)  # reference state changed: rebuild (or drop) the watermark


def _move_with_sidecar(src: Path, dst: Path):
    """Rename an image, carrying its reference-marker sidecar along with it, and
    dropping stale watermark caches for both names."""
    src.rename(dst)
    sc = src.with_name(src.name + ".ref")
    if sc.exists():
        sc.rename(dst.with_name(dst.name + ".ref"))
    for p in (src, dst):
        with contextlib.suppress(ValueError):
            _wm_forget(str(p.relative_to(IMAGES_DIR)))


def _set_primary_photo(kind, asset_id, rel):
    """Promote one of an item's photos to the primary (the <asset_id>.<ext>
    file shown in the gallery and as the main photo). The current primary is
    demoted to the next free extra slot. Returns the new primary's path."""
    if rel not in detect_images(kind, asset_id):
        raise HTTPException(404, "no such photo for this item")
    folder = IMAGES_DIR / kind
    chosen = folder / Path(rel).name
    if chosen.stem == asset_id:
        return rel
    for f in list(folder.iterdir()):
        if f.is_file() and f.suffix.lower() in IMAGE_EXTS and f.stem == asset_id:
            n = 2
            while (folder / f"{asset_id}-{n}{f.suffix}").exists():
                n += 1
            _move_with_sidecar(f, folder / f"{asset_id}-{n}{f.suffix}")
            break
    new_primary = folder / f"{asset_id}{chosen.suffix}"
    _move_with_sidecar(chosen, new_primary)
    return f"{kind}/{new_primary.name}"


def _delete_image(kind, asset_id, rel):
    """Delete a photo (and its reference sidecar). If it was the primary, the
    next remaining photo is promoted. Returns (was_primary, new_primary_rel)."""
    if rel not in detect_images(kind, asset_id):
        raise HTTPException(404, "no such photo for this item")
    p = IMAGES_DIR / rel
    was_primary = p.stem == asset_id
    sc = _ref_sidecar(rel)
    if sc.exists():
        sc.unlink()
    p.unlink()
    _wm_forget(rel)
    new_primary = ""
    if was_primary:
        remaining = detect_images(kind, asset_id)
        if remaining:
            new_primary = _set_primary_photo(kind, asset_id, remaining[0])
    return was_primary, new_primary


# --- deleting a record for good ---------------------------------------------
# Disposal says an item has left the collection and keeps its record; this is the
# other thing, for when the record itself should not exist -- a duplicate, a
# mistake, something scrapped that was never worth a line. Only a disposed item
# can be deleted through the GUI, so the ordinary way to lose something is still
# the reversible one.
#
# Everything pointing at the asset is cleared before its own row goes, rather
# than leaving it to the foreign keys. Three reasons: what another item's history
# should say about losing its link is a judgement no cascade can make; the
# confirmation page can only promise what this code actually does; and the
# cascades are MariaDB's, while the tests run on SQLite, where they hold only
# while a PRAGMA does.

def _purge_photos(rels):
    """Delete photo files, each with its reference sidecar and cached watermark.
    Called after the rows are safely gone -- a file cannot be rolled back."""
    for rel in rels:
        with contextlib.suppress(OSError):
            _ref_sidecar(rel).unlink(missing_ok=True)
        with contextlib.suppress(OSError):
            (IMAGES_DIR / rel).unlink(missing_ok=True)
        _wm_forget(rel)


def _clear_part_rows(db, part, also_going=()):
    """Everything in the database belonging to one part, and the links other parts
    hold to it. Returns its photos, for the caller to delete once the transaction
    is safe. `also_going` names assets being deleted in the same breath, which are
    not told they have lost a link they are about to stop having."""
    aid = part.asset_id
    for child in db.query(Part).filter(Part.parent_id == aid).all():
        if child.asset_id in also_going:
            continue
        child.parent_id = None
        add_log(db, child.asset_id, f"came off {aid}, which was deleted")
    for model in specdb.SPEC_TABLES:
        db.query(model).filter(model.part_id == aid).delete(synchronize_session=False)
    db.query(LogEntry).filter(LogEntry.asset_id == aid).delete(synchronize_session=False)
    photos = detect_images("parts", aid)
    db.delete(part)
    return photos


def _clear_computer_rows(db, c, with_parts=()):
    """The same for a computer: its drive and memory rows, its history, and either
    the parts inside it or the link they hold to it. `with_parts` is the parts to
    delete along with it; the rest are unlinked and kept."""
    aid = c.asset_id
    going = {p.asset_id for p in with_parts}
    photos = []
    # The same walk disposal uses, so that what a delete calls "in the machine" is
    # what disposal called it: a disk on a controller card carries the card's id,
    # not the machine's. A kept part only needs the link it holds to the machine
    # cleared here -- one held to a part that is going is cleared by that part.
    for p in _parts_in_computer(db, aid):
        if p.asset_id in going:
            photos += _clear_part_rows(db, p, also_going=going)
        elif p.computer_id == aid:
            p.computer_id = None
            add_log(db, p.asset_id, f"came out of {aid}, which was deleted")
    for model in (ComputerDrive, ComputerRamModule, ComputerRamChip):
        db.query(model).filter(model.computer_id == aid).delete(synchronize_session=False)
    db.query(LogEntry).filter(LogEntry.asset_id == aid).delete(synchronize_session=False)
    photos += detect_images("computers", aid)
    db.delete(c)
    return photos


def delete_part(db, part):
    """Delete a part and commit. Returns the photos that went with it."""
    photos = _clear_part_rows(db, part)
    db.commit()  # the rows first: if this raises, the photos are still there
    _purge_photos(photos)
    return photos


def delete_computer(db, c, with_parts=()):
    photos = _clear_computer_rows(db, c, with_parts)
    db.commit()
    _purge_photos(photos)
    return photos


def _edit_image(kind, asset_id, rel, fn):
    """Apply fn(PIL.Image)->PIL.Image to a photo in place (originals are not
    kept), baking in EXIF orientation, then invalidate its watermark cache."""
    if rel not in detect_images(kind, asset_id):
        raise HTTPException(404, "no such photo for this item")
    from PIL import Image, ImageOps
    src = IMAGES_DIR / rel
    with Image.open(src) as im:
        out = fn(ImageOps.exif_transpose(im))
        kwargs = {}
        if src.suffix.lower() in (".jpg", ".jpeg"):
            out = out.convert("RGB")
            kwargs = {"quality": 90}
        out.save(src, **kwargs)
    _wm_forget(rel)


def _rotate_op(direction):
    from PIL import Image
    turn = Image.Transpose.ROTATE_270 if direction == "cw" else Image.Transpose.ROTATE_90
    return lambda im: im.transpose(turn)


def _crop_op(x, y, w, h):
    """Crop to a box given as fractions (0..1) of the image's width/height."""
    def crop(im):
        iw, ih = im.size
        left, top = max(0, round(x * iw)), max(0, round(y * ih))
        right, bottom = min(iw, round((x + w) * iw)), min(ih, round((y + h) * ih))
        # Ignore a too-small or degenerate selection.
        if right - left < 8 or bottom - top < 8:
            return im
        return im.crop((left, top, right, bottom))
    return crop


def _photo_edit_redirect(kind, aid, image):
    """The photo editor used to be its own page. Rotating and cropping now live in
    the big view on the item page, so there is one crop implementation rather than
    two; this keeps any link or bookmark to the old page working."""
    return RedirectResponse(f"/{kind}/{aid}?photo={quote(image or '')}", status_code=303)


def _do_photo_rotate(db, model, kind, aid, form):
    get_or_404(db, model, aid)
    _edit_image(kind, aid, form.get("image", ""), _rotate_op(form.get("dir", "cw")))
    add_log(db, aid, "rotated a photo")
    db.commit()


def _do_photo_crop(db, model, kind, aid, form):
    get_or_404(db, model, aid)
    try:
        x, y, w, h = (float(form.get(k, "")) for k in ("x", "y", "w", "h"))
    except ValueError as err:
        raise HTTPException(400, "bad crop box") from err
    _edit_image(kind, aid, form.get("image", ""), _crop_op(x, y, w, h))
    add_log(db, aid, "cropped a photo")
    db.commit()


# --- QR target: one stable /items/<id> URL for either kind ------------------

@app.get("/items/{aid}", include_in_schema=False)
def gui_item(aid: str, db: Session = Depends(get_db)):
    """The URL printed on labels: resolve an asset id to its page whether it's a
    computer or a part. Keeps the same /items/<id> scheme the old QR codes used."""
    aid = aid.upper()
    if db.get(Computer, aid):
        return RedirectResponse(f"/computers/{aid}", status_code=307)
    if db.get(Part, aid):
        return RedirectResponse(f"/parts/{aid}", status_code=307)
    raise HTTPException(404, f"no asset {aid}")


def _register_order(db):
    """Every asset in register order, as (asset_id, kind, display name).

    Two small column queries: no photos are looked at, because this is only wanted
    for the prev/next buttons on an item page. It is the fallback order -- arrive
    from the gallery and the browser hands over the order it was actually showing,
    filtered and sorted as you left it (see base.html)."""
    rows = []
    for kind, cls in (("computers", Computer), ("parts", Part)):
        for aid, name, maker, model in db.query(cls.asset_id, cls.name,
                                                cls.manufacturer, cls.model):
            rows.append((aid, kind, entry.display_name(
                {"asset_id": aid, "name": name, "manufacturer": maker,
                 "model": model})))
    rows.sort()
    return rows


def _item_nav(db, aid):
    """{prev, next} for an item page: the assets either side of this one."""
    order = _register_order(db)
    here = next((n for n, row in enumerate(order) if row[0] == aid), None)
    if here is None:
        return {}

    def at(n):
        if not 0 <= n < len(order):
            return None
        a, kind, name = order[n]
        return {"url": f"/{kind}/{a}", "name": name, "aid": a}

    return {"prev": at(here - 1), "next": at(here + 1)}


# --- GUI: index ------------------------------------------------------------

def _catalogue_rows(db, precise_times=True):
    """Every computer and part as one list of card rows. The gallery and /browse
    render the same grid from this; they differ only in which rows survive.

    The recency sort keys ride on the cards as data attributes, so anonymously they
    carry the date alone, like the history does (`precise_times=False`). The rows
    come back newest-change-first regardless, which is what keeps a day's worth of
    edits in order once the browser sorts on dates that are all equal."""
    computers = db.query(Computer).order_by(Computer.asset_id).all()
    parts = db.query(Part).order_by(Part.asset_id).all()
    counts = {}
    for p in parts:
        if p.computer_id:
            counts[p.computer_id] = counts.get(p.computer_id, 0) + 1
    comp_ids = {c.asset_id for c in computers}

    # Newest/oldest log timestamp per asset, for the updated / added sorts.
    ts = {}
    for aid, latest, first in db.query(
            LogEntry.asset_id, func.max(LogEntry.created_at),
            func.min(LogEntry.created_at)).group_by(LogEntry.asset_id):
        ts[aid] = (latest, first)

    def stamp(when):
        if not when:
            return ""
        return when.isoformat() if precise_times else when.strftime("%Y-%m-%d")

    def stamps(aid):
        latest, first = ts.get(aid, (None, None))
        return (stamp(latest), stamp(first))

    # Both folders read once for the whole page: scanning per row was the bulk of
    # this route's time (0.38s of 0.50s across 293 assets).
    listings = {kind: folder_images(kind) for kind in ("computers", "parts")}

    def primary_image(kind, aid):
        imgs = pick_images(kind, aid, listings[kind])
        return imgs[0] if imgs else ""

    # One query for every storage part's Kind, rather than re-parsing each specs
    # string (or a lookup per row) just to choose an icon.
    kinds = specdb.storage_kinds(db)

    rows = []
    for c in computers:
        rows.append({
            "obj": c, "kind": "computer", "cat": "computer",
            "cat_label": "Computer", "parent": "", "year": c.year or "",
            "name": entry.display_name(to_dict(c)),
            "image": (cpi := primary_image("computers", c.asset_id)),
            "ref_photo": is_reference(cpi), "ref_icon": _favicon_for_rel(cpi),
            "placeholder": entry.placeholder_for("computer"),
            "updated": stamps(c.asset_id)[0], "added": stamps(c.asset_id)[1],
            "maker": (c.manufacturer or "").lower(),
            "acquired": str(c.acquired_date or ""), "catsort": 0,
            "sub": f"{counts.get(c.asset_id, 0)} part(s)",
            "search": " ".join([c.asset_id, c.name or "", c.manufacturer or "",
                                 c.model or "", c.os or "", c.cpu or "",
                                 c.chassis or "", c.installed_ram or "",
                                 c.drives or "", str(c.year or ""),
                                 c.condition or "", c.source or "",
                                 str(c.acquired_date or ""),
                                 c.disposed_note or ""]).lower(),
        })
    for p in parts:
        ptype = p.type or "other"
        rows.append({
            "obj": p, "kind": "part", "cat": ptype,
            "cat_label": entry.type_label(ptype), "year": p.year or "",
            "parent": p.computer_id if p.computer_id in comp_ids else "",
            "name": entry.display_name(to_dict(p)),
            "image": (ppi := primary_image("parts", p.asset_id)),
            "ref_photo": is_reference(ppi), "ref_icon": _favicon_for_rel(ppi),
            "placeholder": (_storage_placeholder(kinds.get(p.asset_id))
                            if ptype == "storage"
                            else entry.placeholder_for(ptype)),
            "updated": stamps(p.asset_id)[0], "added": stamps(p.asset_id)[1],
            "maker": (p.manufacturer or "").lower(),
            "acquired": str(p.acquired_date or ""),
            "catsort": entry.type_sort_key(ptype) + 1,
            "sub": (p.computer_id if p.computer_id else "standalone"),
            "search": " ".join([p.asset_id, p.name or "", p.manufacturer or "",
                                 p.model or "", p.specs or "", p.type or "",
                                 entry.type_label(ptype), str(p.year or ""),
                                 p.condition or "", p.source or "",
                                 str(p.acquired_date or ""), p.disk_image or "",
                                 p.computer_id or "", p.disposed_note or ""]).lower(),
        })
    # Newest change first. The browser re-sorts on load anyway, but its sort is
    # stable, so this is the order items updated on the same day keep -- the whole
    # of what the dropped clock time used to settle.
    rows.sort(key=lambda r: ts.get(r["obj"].asset_id, (datetime.min,))[0] or datetime.min,
              reverse=True)
    return rows


def _storage_placeholder(kind):
    """Which drive icon a storage part wears, read from its Kind spec: a floppy, a
    disc and a disk are all "storage" and none of them look alike."""
    kind = (kind or "").lower()
    if "optical" in kind:
        return entry.placeholder_for("optical")
    if "floppy" in kind or "gotek" in kind:
        return entry.placeholder_for("floppy")
    return entry.placeholder_for("storage")


def _cats_for(rows):
    """Options for the toolbar's category menu: only the kinds actually present, so
    a filtered page does not offer to filter down to nothing."""
    cats = [("computer", "Computers")] if any(r["kind"] == "computer" for r in rows) else []
    present = {r["cat"] for r in rows if r["kind"] == "part"}
    for t in sorted(present, key=entry.type_sort_key):
        cats.append((t, entry.type_label(t)))
    return cats


def _grid_page(request, rows, **extra):
    """Render the card grid. Counts come from the rows on the page rather than from
    the register, so a filtered view describes itself honestly."""
    n_computers = sum(1 for r in rows if r["kind"] == "computer")
    return templates.TemplateResponse(request, "index.html", {
        "rows": rows, "cats": _cats_for(rows),
        "n_computers": n_computers, "n_parts": len(rows) - n_computers, **extra})


def search_terms(query):
    """A query as the list of things that must all appear. Bare words are words;
    "a quoted run" is one term, so a phrase can be asked for exactly."""
    terms = []
    for i, chunk in enumerate((query or "").lower().split('"')):
        if i % 2:
            if chunk.strip():
                terms.append(chunk.strip())
        else:
            terms.extend(chunk.split())
    return terms


def _haystack(db, obj, history):
    """Everything written about one item, as one lowercase string: every text
    column, its rendered specs or memory and drives, and its history. This is what
    makes a search over "any field" true rather than nearly true."""
    fields = [str(getattr(obj, c.name) or "") for c in obj.__table__.columns]
    fields += history.get(obj.asset_id, [])
    if isinstance(obj, Part):
        fields.append(entry.type_label(obj.type or "other"))
    # Joined by newline, not by space: with a space, a quoted phrase could match
    # across the seam between two fields -- a part whose model is "Etherlink" and
    # whose name begins "III" would answer to "etherlink iii", which it is not.
    return "\n".join(fields).lower()


def _history_by_asset(db):
    out = {}
    for aid, message in db.query(LogEntry.asset_id, LogEntry.message):
        out.setdefault(aid, []).append(message or "")
    return out


def _search(db, rows, query):
    """The rows whose text contains every term. Done in Python over the rows the
    page already loaded: at this size it is a few hundred string searches, and it
    matches exactly what a reader would call a match rather than what SQL collation
    would."""
    terms = search_terms(query)
    if not terms:
        return rows
    history = _history_by_asset(db)
    kept = []
    for r in rows:
        hay = _haystack(db, r["obj"], history)
        if all(t in hay for t in terms):
            kept.append(r)
    return kept


# --- GUI: what the search bar offers while you are still typing --------------

SUGGEST_LIMIT = 10


def _suggest_tier(obj, name, raw):
    """Which band of the list an item belongs in, lowest first: what was typed is
    its asset tag, or the start of one, or the start of its name, or somewhere in
    what identifies it -- or else it matched on a spec or a history entry, which
    is a real hit but not one to put at the top of a list of ten."""
    aid = (obj.asset_id or "").lower()
    if aid == raw:
        return 0
    if aid.startswith(raw):
        return 1
    if name.lower().startswith(raw):
        return 2
    ident = " ".join([obj.asset_id or "", name, obj.manufacturer or "",
                      obj.model or ""]).lower()
    return 3 if raw in ident else 4


def _suggest(db, query, limit=SUGGEST_LIMIT):
    """The first few items a query matches, and how many it matches in all.

    Deliberately the same match the search bar itself performs -- every field of
    every item plus its history -- so the list is a preview of the answer Enter
    gives rather than a second, narrower search that disagrees with it. What the
    list adds is an order: a whole-page result can arrive in catalogue order
    because you read it, but ten rows under a half-typed word are being aimed at,
    so the ones that answer to what was typed come first."""
    terms = search_terms(query)
    if not terms:
        return [], 0
    history = _history_by_asset(db)
    latest = dict(db.query(LogEntry.asset_id, func.max(LogEntry.created_at))
                    .group_by(LogEntry.asset_id).all())
    raw = " ".join((query or "").lower().split())

    hits = []
    for obj, kind in ([(c, "computer") for c in db.query(Computer).all()]
                      + [(p, "part") for p in db.query(Part).all()]):
        if not all(t in _haystack(db, obj, history) for t in terms):
            continue
        name = entry.display_name(to_dict(obj))
        hits.append({"obj": obj, "kind": kind, "name": name,
                     "tier": _suggest_tier(obj, name, raw)})
    # Two stable sorts rather than one compound key: the second keeps the order of
    # the first within each band, which is how recency settles a tie without the
    # arithmetic of negating a timestamp that may be missing.
    hits.sort(key=lambda h: latest.get(h["obj"].asset_id) or datetime.min,
              reverse=True)
    hits.sort(key=lambda h: (h["tier"], bool(h["obj"].disposed)))

    shown = hits[:limit]
    listings, kinds = {}, None
    out = []
    for h in shown:
        obj, folder = h["obj"], "computers" if h["kind"] == "computer" else "parts"
        if folder not in listings:
            listings[folder] = folder_images(folder)
        imgs = pick_images(folder, obj.asset_id, listings[folder])
        if h["kind"] == "computer":
            cat, icon = "Computer", entry.placeholder_for("computer")
        else:
            cat = entry.type_label(obj.type or "other")
            icon = entry.placeholder_for(obj.type or "other")
            if (obj.type or "") == "storage":
                # One query, and only when a drive is actually on the list, to tell
                # a floppy from a disc from a disk as the gallery's cards do.
                if kinds is None:
                    kinds = specdb.storage_kinds(db)
                icon = _storage_placeholder(kinds.get(obj.asset_id))
        out.append({
            "url": f"/{folder}/{obj.asset_id}", "aid": obj.asset_id,
            "name": h["name"], "cat": cat, "year": obj.year or "",
            "disposed": bool(obj.disposed),
            "img": img_url(imgs[0]) if imgs else "",
            "icon": f"/static/{icon}",
        })
    return out, len(hits)


@app.get("/suggest", include_in_schema=False)
def gui_suggest(q: str = "", db: Session = Depends(get_db)):
    items, total = _suggest(db, q)
    return {"q": q, "items": items, "total": total}


@app.get("/", response_class=HTMLResponse, include_in_schema=False)
def gui_index(request: Request, q: str = "", db: Session = Depends(get_db)):
    rows = _catalogue_rows(db, precise_times=request.state.authed)
    total = len(rows)
    if q.strip():
        rows = _search(db, rows, q)
    n_computers = sum(1 for r in rows if r["kind"] == "computer")
    return _grid_page(
        request, rows, q=q, searched=bool(q.strip()), total=total,
        og=_og(request, "Retro Hardware Database",
               f"{n_computers} computers and {len(rows) - n_computers} parts "
               "in the collection."))


# --- GUI: browse, the items behind a figure on /stats -----------------------

def _tagged(query):
    """A row test for the asset ids a single-column query returns. Asset ids are
    unique across the whole register, so the kind needs no separate check."""
    ids = {aid for (aid,) in query}
    return lambda r: r["obj"].asset_id in ids


def _browse_view(db, key: str, val: str):
    """What /browse?f=<key> means: a heading, a line saying what is on the page, an
    optional link back to the thing it is about, and a test each catalogue row
    passes or fails.

    There is one entry per figure on /stats, which is the point: every number there
    is clickable and lands here on exactly the items it counted. Where a figure adds
    up quantities rather than counting assets -- slots, chips, drives -- the note
    says whose they are, because the count on this page is of items, not of slots.
    Returns None for an unknown view, which the caller turns into a 404."""
    if key == "all":
        return ("Everything in the register", "computers and parts together",
                None, lambda r: True)
    if key == "computers":
        return ("Computers", "every whole machine in the register", None,
                lambda r: r["kind"] == "computer")
    if key == "parts":
        return ("Parts", "everything tagged in its own right rather than as a machine",
                None, lambda r: r["kind"] == "part")
    if key == "photos":
        return ("Photographed", "items with at least one photograph on file", None,
                lambda r: bool(r["image"]))
    if key == "nophotos":
        return ("Not photographed yet", "everything still waiting for a camera",
                None, lambda r: not r["image"])
    if key == "source":
        return (f"Came from {val}", "as recorded in the source field", None,
                lambda r: (r["obj"].source or "") == val)
    if key == "maker":
        return (f"Parts made by {val}", "as recorded in the maker field", None,
                lambda r: r["kind"] == "part" and (r["obj"].manufacturer or "") == val)
    if key == "type":
        return (entry.type_label(val), "every one of them in the register", None,
                lambda r: r["kind"] == "part" and r["cat"] == val)
    if key == "condition":
        return (f"Parts recorded as {val}", "condition as it was last checked", None,
                lambda r: r["kind"] == "part" and (r["obj"].condition or "") == val)
    if key == "year":
        return ("Items with a year", "what the average year is worked out from", None,
                lambda r: bool(r["obj"].year))
    if key == "extremes":
        years = _all_years(db)
        ends = {min(years), max(years)} if years else set()
        return ("The oldest and the newest", "the two ends of the range", None,
                lambda r: r["obj"].year in ends)
    if key == "ram":
        sizes = sorted({int(x) for x in val.split(",") if x.strip().isdigit()})
        return (("Machines with " + " or ".join(entry.fmt_kb(kb) for kb in sizes)
                 + " fitted") if sizes else "Machines by memory fitted",
                "read from the typed memory column, not from the text", None,
                lambda r: r["kind"] == "computer" and r["obj"].installed_ram_kb in sizes)
    if key == "ramfitted":
        return ("Machines with their memory recorded",
                "the machines the memory total is added up from", None,
                lambda r: r["kind"] == "computer"
                and r["obj"].installed_ram_kb is not None)
    if key == "storage":
        return ("Storage with a capacity recorded",
                "the parts the storage total is added up from", None,
                _tagged(db.query(StorageSpec.part_id)
                        .filter(StorageSpec.capacity_kb.isnot(None))))
    if key == "slots":
        return ("Boards with expansion slots", "the boards those slots are on", None,
                _tagged(db.query(PartSlot.part_id).distinct()))
    if key == "bus":
        return (f"Boards with {val} slots", "the boards those slots are on", None,
                _tagged(db.query(PartSlot.part_id).filter(PartSlot.bus == val)))
    if key == "port":
        return (f"Fitted with a {val} port", "the cards and boards those ports are on",
                None, _tagged(db.query(PartPort.part_id).filter(PartPort.port == val)))
    if key == "chips":
        return ("Machines with memory chips on the board",
                "the machines those chips are soldered or socketed into", None,
                _tagged(db.query(ComputerRamChip.computer_id).distinct()))
    if key == "drives":
        return ("Machines with a drive fitted", "the machines those drives are in",
                None, _tagged(db.query(ComputerDrive.computer_id).distinct()))
    if key == "gotek":
        return ("Machines with a Gotek", "a floppy emulator standing in for a drive",
                None, _tagged(db.query(ComputerDrive.computer_id)
                              .filter(ComputerDrive.kind == "Gotek").distinct()))
    if key == "fitted":
        return ("Parts fitted in a machine", "installed rather than sitting on a shelf",
                None, lambda r: r["kind"] == "part" and bool(r["obj"].computer_id))
    if key == "spares":
        return ("Spares on the shelf", "parts not fitted in anything", None,
                lambda r: r["kind"] == "part" and not r["obj"].computer_id)
    if key == "disposed":
        return ("No longer in the collection", "binned, sold or donated", None,
                lambda r: bool(r["obj"].disposed))
    if key == "held":
        return ("Items with an acquisition date",
                "when each of these arrived, as recorded", None,
                lambda r: r["obj"].acquired_date is not None)
    if key == "in":
        machine = db.get(Computer, (val or "").upper())
        if machine is None:
            return None
        name = entry.display_name(to_dict(machine))
        return (f"Parts fitted in {name}", "everything installed in this machine",
                (f"/computers/{machine.asset_id}", name),
                lambda r: r["kind"] == "part"
                and r["obj"].computer_id == machine.asset_id)
    return None


@app.get("/browse", response_class=HTMLResponse, include_in_schema=False)
def gui_browse(request: Request, f: str = "", v: str = "",
               db: Session = Depends(get_db)):
    """The items behind one figure on /stats, in the same grid as the gallery."""
    view = _browse_view(db, f, v)
    if view is None:
        raise HTTPException(404, f"no such view: {f or '(none)'}")
    heading, note, crumb, keep = view
    rows = [r for r in _catalogue_rows(db, precise_times=request.state.authed)
            if keep(r)]
    return _grid_page(
        request, rows, heading=heading, note=note, crumb=crumb,
        # The figures on /stats count disposed items too, so this page has to show
        # them by default or it would seem to contradict the number clicked on.
        show_disposed=True,
        page_title=f"{heading} — Retro Hardware Database",
        # A filtered slice of the gallery is not a page search engines want; the
        # items themselves are already indexed one by one.
        noindex=True, og=_og(request, heading, note))


# --- GUI: computers --------------------------------------------------------

def _grid_counts(form, prefix, items):
    """[(key, n), ...] for the count-grid inputs '<prefix>:<key>' that hold a
    positive integer."""
    out = []
    for key, *_ in items:
        raw = (form.get(f"{prefix}:{key}", "") or "").strip()
        if raw.isdigit() and int(raw) > 0:
            out.append((key, int(raw)))
    return out


def _ram_from_form(form):
    """A computer's memory as the form gives it: the SIMM/SIPP module grid, the
    direct-DRAM-chip grid, and the free-text box read as a total or kept as a
    note. Nothing is parsed back out of a rendered string."""
    mods = _grid_counts(form, "rammod", entry.RAM_MODULES)
    chips = _grid_counts(form, "ramchip", entry.RAM_CHIPS)
    total_kb, note = ramdb.from_string(form.get("installed_ram", ""))
    return mods, chips, note, total_kb


MAX_DRIVE_ROWS = 8


def _drives_from_form(form):
    """[drive dict] from the numbered drive rows, skipping the empty ones -- so
    clearing a row's fields is how a drive is removed."""
    out = []
    for i in range(MAX_DRIVE_ROWS):
        row = {k: (form.get(f"drive{i}_{k}", "") or "").strip()
               for k in ("kind", "form_factor", "size", "media", "speed",
                         "model", "colour", "yellowing")}
        if not any(row.values()):
            continue
        count = (form.get(f"drive{i}_count", "") or "").strip()
        row["count"] = int(count) if count.isdigit() and int(count) > 0 else 1
        out.append(row)
    return out


def _computer_form_ctx(c, title, db=None):
    mods, chips = ramdb.read(db, c) if (c is not None and db is not None) else ([], [])
    free = c.installed_ram_note if c else ""
    if c is not None and not (mods or chips) and not free and c.installed_ram_kb:
        free = entry.fmt_kb(c.installed_ram_kb)
    drives = drivedb.read(db, c) if (c is not None and db is not None) else []
    blanks = max(2, MAX_DRIVE_ROWS - len(drives))
    return {"c": c, "conditions": entry.CONDITIONS, "title": title,
            "ram_modules": entry.RAM_MODULES, "ram_mod_counts": dict(mods),
            "ram_chips": entry.RAM_CHIPS, "ram_counts": dict(chips),
            "ram_free": free, "drives": drives + [{}] * blanks,
            "drive_kinds": drivedb.KINDS, "drive_forms": drivedb.FORM_FACTORS,
            "drive_sizes": drivedb.SIZES, "drive_media": drivedb.MEDIA,
            "drive_speeds": drivedb.SPEEDS, **_bezel_ctx()}


def _bezel_ctx():
    """The bezel vocabularies and their swatches, for any form that records one:
    a machine's drive rows and a storage part both do."""
    return {"bezel_colours": entry.BEZEL_COLOURS, "yellowing": entry.YELLOWING,
            "bezel_colour_labels": entry.BEZEL_COLOUR_LABELS,
            "yellowing_labels": entry.YELLOWING_LABELS,
            "bezel_swatches": entry.bezel_swatch_map()}


@app.get("/computers/new", response_class=HTMLResponse, include_in_schema=False)
def gui_new_computer(request: Request):
    return templates.TemplateResponse(request, "computer_form.html",
                                      _computer_form_ctx(None, "New computer"))


@app.post("/computers/new", include_in_schema=False)
async def gui_create_computer(request: Request, db: Session = Depends(get_db)):
    form = await request.form()
    photos = _chosen_photos(form)
    data = {k: _coerce(k, form[k]) for k in COMPUTER_FIELDS if k in form}
    data.pop("installed_ram", None)
    data.pop("drives", None)
    for f in ("manufacturer", "model"):
        if f in data:
            data[f] = entry.deshout(data[f])
    obj = Computer(asset_id=next_asset_id(db), **data)
    db.add(obj)
    db.flush()
    ramdb.write(db, obj, *_ram_from_form(form))
    drivedb.write(db, obj, _drives_from_form(form),
                  (form.get("drives_note", "") or "").strip())
    add_log(db, obj.asset_id, "created", "created")
    db.commit()
    if photos:
        _attach_photos(db, obj, "computers", photos)
        db.commit()
    # Land on the build walk so the next step (motherboard) is front and centre.
    return RedirectResponse(f"/computers/{obj.asset_id}?build=1", status_code=303)


@app.get("/computers/{aid}", response_class=HTMLResponse, include_in_schema=False)
def gui_computer(aid: str, request: Request, build: int = 0, imgerr: int = 0,
                 db: Session = Depends(get_db)):
    c = get_or_404(db, Computer, aid)
    parts = db.query(Part).filter(Part.computer_id == aid).all()
    parts.sort(key=lambda p: (entry.type_sort_key(p.type or ""),
                              entry.display_name(to_dict(p))))
    motherboard = next((p for p in parts if p.type == "motherboard"), None)
    # Unlinked boards that could be linked to this machine.
    free_boards, link_candidates = [], []
    if request.state.authed:
        free_boards = (db.query(Part)
                       .filter(Part.type == "motherboard",
                               Part.computer_id.is_(None))
                       .order_by(Part.asset_id).all())
        link_candidates = (db.query(Part)
                           .filter(Part.type != "motherboard",
                                   Part.computer_id.is_(None),
                                   Part.parent_id.is_(None))
                           .order_by(Part.type, Part.asset_id).all())
    images = detect_images("computers", aid)
    blurb = c.summary or _dot(" ".join(x for x in (c.manufacturer, c.model, str(c.year or "")) if x),
                              c.cpu, c.condition)
    # Form factor is a property of the board, shown on the machine -- which is
    # what the part form promises ("the computer's form factor is taken from
    # here"). Read it from the typed column rather than re-parsing the string.
    form_factor = (specdb.scalars(db, motherboard).get("form_factor", "")
                   if motherboard else "")
    return templates.TemplateResponse(request, "computer.html", {
        "c": c, "parts": [p for p in parts if p is not motherboard],
        "motherboard": motherboard, "form_factor": form_factor,
        "free_boards": free_boards,
        "link_candidates": link_candidates, "images": images,
        "ref_marks": reference_marks("computers", aid),
        "card_steps": entry.CARD_STEPS, "build": bool(build), "imgerr": bool(imgerr),
        "log": item_log(db, aid), "nav": _item_nav(db, aid),
        "og": (og := _og(request, entry.display_name(to_dict(c)), blurb,
                         images[0] if images else None)),
        "jsonld": _jsonld(og, c.asset_id, c.manufacturer, "Vintage computer")})


@app.get("/computers/{aid}/edit", response_class=HTMLResponse, include_in_schema=False)
def gui_edit_computer(aid: str, request: Request, db: Session = Depends(get_db)):
    c = get_or_404(db, Computer, aid)
    return templates.TemplateResponse(request, "computer_form.html",
                                      _computer_form_ctx(c, f"Edit {aid}", db))


@app.post("/computers/{aid}/edit", include_in_schema=False)
async def gui_save_computer(aid: str, request: Request, db: Session = Depends(get_db)):
    c = get_or_404(db, Computer, aid)
    form = await request.form()
    old = {k: getattr(c, k) for k in COMPUTER_FIELDS}
    for k in COMPUTER_FIELDS:
        if k not in form:
            continue
        if k in DERIVED_FIELDS:
            continue
        v = _coerce(k, form[k])
        if k in ("manufacturer", "model"):
            v = entry.deshout(v)
        setattr(c, k, v)
    mods, chips, note, total_kb = _ram_from_form(form)
    ramdb.write(db, c, mods, chips, note, total_kb)
    drivedb.write(db, c, _drives_from_form(form),
                  (form.get("drives_note", "") or "").strip())
    diff = _field_diffs(old, {k: getattr(c, k) for k in COMPUTER_FIELDS},
                        COMPUTER_DIFF_FIELDS)
    if diff:
        add_log(db, aid, diff)
    db.commit()
    return RedirectResponse(f"/computers/{aid}", status_code=303)


@app.post("/computers/{aid}/link-motherboard", include_in_schema=False)
async def gui_link_motherboard(aid: str, request: Request,
                               db: Session = Depends(get_db)):
    get_or_404(db, Computer, aid)
    form = await request.form()
    pid = form.get("part_id", "")
    board = get_or_404(db, Part, pid)
    if board.type != "motherboard":
        raise HTTPException(400, f"{pid} is not a motherboard")
    board.computer_id = aid
    add_log(db, aid, f"linked motherboard {board.asset_id}")
    add_log(db, board.asset_id, f"linked to computer {aid}")
    db.commit()
    return RedirectResponse(f"/computers/{aid}?build=1", status_code=303)


@app.post("/computers/{aid}/link-part", include_in_schema=False)
async def gui_link_part(aid: str, request: Request, db: Session = Depends(get_db)):
    """Install an existing standalone part into this computer."""
    get_or_404(db, Computer, aid)
    form = await request.form()
    part = get_or_404(db, Part, form.get("part_id", ""))
    part.computer_id = aid
    part.parent_id = None
    add_log(db, aid, f"linked part {part.asset_id}")
    add_log(db, part.asset_id, f"installed in {aid}")
    db.commit()
    return RedirectResponse(f"/computers/{aid}", status_code=303)


# --- the GUI's delete, with its safety net ----------------------------------

def _require_disposed(obj, kind):
    """Only a disposed item can be deleted from the GUI. Disposal is reversible
    and deletion is not, so the reversible step is made a precondition of the
    other: whatever is about to go has already been marked as gone once, on
    purpose, on an earlier day."""
    if not obj.disposed:
        raise HTTPException(
            400, f"{obj.asset_id} is still in the collection. Mark it disposed "
                 f"first -- only a disposed {kind} can be deleted.")


def _confirms_url(text, kind, aid) -> bool:
    """The safety net: the item's own URL, pasted in. Nothing about this asks the
    database a question it does not already know the answer to -- the point is to
    make deleting the wrong thing take a deliberate act, so that a delete cannot
    be a stray click on a page somebody landed on by accident.

    What the address bar holds is accepted from any host, with any query or
    fragment, and so is the bare path, because all three are the same act of
    fetching the thing's identity. The asset id itself has to be right."""
    path = urlparse((text or "").strip()).path.rstrip("/")
    return path.upper() == f"/{kind}/{aid}".upper()


def _log_count(db, asset_ids):
    if not asset_ids:
        return 0
    return (db.query(func.count(LogEntry.id))
            .filter(LogEntry.asset_id.in_(asset_ids)).scalar() or 0)


def _delete_ctx(request, db, kind, obj, error="", with_parts=False):
    """What deleting this would take with it, for the confirmation page. Read with
    the same queries the deletion itself runs, so the page cannot promise one
    thing and the button do another.

    The item's own figures and the contents' are kept apart rather than summed
    against the tick, so both are on the page whichever way the tick is set and
    neither needs a script to keep them honest."""
    aid = obj.asset_id
    inside = children = []
    if kind == "computers":
        inside = _parts_in_computer(db, aid)
    else:
        children = (db.query(Part).filter(Part.parent_id == aid)
                    .order_by(Part.asset_id).all())
    # A part inside the machine that is not itself disposed is not deleted even
    # when the box is ticked: it is still in the collection, and the rule here is
    # that only what has already been marked as gone can go.
    deletable = [p for p in inside if p.disposed]
    return {"kind": kind, "obj": obj, "aid": aid,
            "name": entry.display_name(to_dict(obj)),
            "url": _abs_url(request, f"/{kind}/{aid}"),
            "photos": detect_images(kind, aid),
            "logs": _log_count(db, [aid]),
            "inside": inside, "deletable": deletable,
            "kept": [p for p in inside if not p.disposed],
            "parts_photos": sum(len(detect_images("parts", p.asset_id))
                                for p in deletable),
            "parts_logs": _log_count(db, [p.asset_id for p in deletable]),
            "children": children, "with_parts": with_parts, "error": error,
            "noindex": True}


@app.post("/computers/{aid}/dispose", include_in_schema=False)
async def gui_dispose_computer(aid: str, request: Request,
                               db: Session = Depends(get_db)):
    c = get_or_404(db, Computer, aid)
    form = await request.form()
    c.disposed = True
    c.disposed_at = _parse_date(form.get("date", "")) or date.today()
    c.disposed_note = form.get("note", "") or ""
    # What was in the machine went out with the machine, on the same date and for
    # the same reason -- recording it any other way would leave the register
    # claiming we still hold parts that are in the same skip as their host.
    n = _dispose_contents(db, c)
    add_log(db, aid, _disposal_log(c) + _and_parts(n))
    db.commit()
    return RedirectResponse(f"/computers/{aid}", status_code=303)


@app.post("/computers/{aid}/restore", include_in_schema=False)
def gui_restore_computer(aid: str, db: Session = Depends(get_db)):
    c = get_or_404(db, Computer, aid)
    was_at, was_note = c.disposed_at, c.disposed_note
    c.disposed = False
    c.disposed_at = None
    c.disposed_note = ""
    n = _restore_contents(db, c, was_at, was_note)
    add_log(db, aid, "restored" + _and_parts(n, "came back too"))
    db.commit()
    return RedirectResponse(f"/computers/{aid}", status_code=303)


@app.get("/computers/{aid}/delete", response_class=HTMLResponse, include_in_schema=False)
def gui_delete_computer_form(aid: str, request: Request, db: Session = Depends(get_db)):
    c = get_or_404(db, Computer, aid)
    _require_disposed(c, "computer")
    return templates.TemplateResponse(request, "delete.html",
                                      _delete_ctx(request, db, "computers", c))


@app.post("/computers/{aid}/delete", include_in_schema=False)
async def gui_delete_computer(aid: str, request: Request,
                              db: Session = Depends(get_db)):
    c = get_or_404(db, Computer, aid)
    _require_disposed(c, "computer")
    form = await request.form()
    with_parts = bool(form.get("with_parts"))
    if not _confirms_url(form.get("confirm", ""), "computers", c.asset_id):
        # Back to the page rather than an error: a paste that went wrong is the
        # ordinary way to arrive here, and the tick keeps whatever it was set to.
        return templates.TemplateResponse(
            request, "delete.html",
            _delete_ctx(request, db, "computers", c, with_parts=with_parts,
                        error="That is not this item's URL. Nothing was deleted."),
            status_code=400)
    ctx = _delete_ctx(request, db, "computers", c, with_parts=with_parts)
    delete_computer(db, c, with_parts=ctx["deletable"] if with_parts else ())
    return RedirectResponse("/", status_code=303)


@app.post("/computers/{aid}/note", include_in_schema=False)
async def gui_computer_note(aid: str, request: Request, db: Session = Depends(get_db)):
    get_or_404(db, Computer, aid)
    form = await request.form()
    add_log(db, aid, (form.get("message", "") or "").strip(), kind="note")
    db.commit()
    return RedirectResponse(f"/computers/{aid}", status_code=303)


@app.post("/computers/{aid}/photo", include_in_schema=False)
async def gui_computer_photo(aid: str, photos: list[UploadFile] = File(...),
                             db: Session = Depends(get_db)):
    c = get_or_404(db, Computer, aid)
    first = None
    n = 0
    for up in photos:
        if (up.filename or "").strip():
            rel = _save_photo("computers", aid, up)
            n += 1
            if first is None:
                first = rel
    if first and not c.image:
        c.image = first
    if n:
        add_log(db, aid, f"added {n} photo(s)")
    db.commit()
    return RedirectResponse(f"/computers/{aid}", status_code=303)


@app.post("/computers/{aid}/fetch-image", include_in_schema=False)
def gui_computer_fetch_image(aid: str, db: Session = Depends(get_db)):
    c = get_or_404(db, Computer, aid)
    rel = _fetch_reference_photo("computers", aid, c.url or "") if c.url else None
    if rel:
        if not c.image:
            c.image = rel
        add_log(db, aid, "fetched a photo from the reference")
        db.commit()
    return RedirectResponse(f"/computers/{aid}" + ("" if rel else "?imgerr=1"),
                            status_code=303)


@app.post("/computers/{aid}/primary-photo", include_in_schema=False)
async def gui_computer_primary(aid: str, request: Request,
                               db: Session = Depends(get_db)):
    c = get_or_404(db, Computer, aid)
    form = await request.form()
    c.image = _set_primary_photo("computers", aid, form.get("image", ""))
    add_log(db, aid, "changed the default photo")
    db.commit()
    return RedirectResponse(f"/computers/{aid}", status_code=303)


@app.post("/computers/{aid}/photo-delete", include_in_schema=False)
async def gui_computer_photo_delete(aid: str, request: Request,
                                    db: Session = Depends(get_db)):
    c = get_or_404(db, Computer, aid)
    form = await request.form()
    was_primary, new_primary = _delete_image("computers", aid, form.get("image", ""))
    if was_primary:
        c.image = new_primary or ""
    add_log(db, aid, "deleted a photo")
    db.commit()
    return RedirectResponse(f"/computers/{aid}", status_code=303)


@app.post("/computers/{aid}/photo-reference", include_in_schema=False)
async def gui_computer_photo_reference(aid: str, request: Request,
                                       db: Session = Depends(get_db)):
    c = get_or_404(db, Computer, aid)
    form = await request.form()
    rel = form.get("image", "")
    if rel not in detect_images("computers", aid):
        raise HTTPException(404, "no such photo for this item")
    on = form.get("set", "1") == "1"
    _mark_reference(rel, on, (form.get("note", "") or "").strip(), c.url or "")
    add_log(db, aid, "flagged a photo as a reference image" if on
            else "unflagged a reference photo")
    db.commit()
    return RedirectResponse(f"/computers/{aid}", status_code=303)


@app.get("/computers/{aid}/edit-photo", response_class=HTMLResponse, include_in_schema=False)
def gui_computer_edit_photo(aid: str, image: str = ""):
    return _photo_edit_redirect("computers", aid, image)


@app.post("/computers/{aid}/photo-rotate", include_in_schema=False)
async def gui_computer_photo_rotate(aid: str, request: Request,
                                    db: Session = Depends(get_db)):
    form = await request.form()
    _do_photo_rotate(db, Computer, "computers", aid, form)
    return RedirectResponse(_safe_next(form.get("next") or f"/computers/{aid}"),
                            status_code=303)


@app.post("/computers/{aid}/photo-crop", include_in_schema=False)
async def gui_computer_photo_crop(aid: str, request: Request,
                                  db: Session = Depends(get_db)):
    form = await request.form()
    _do_photo_crop(db, Computer, "computers", aid, form)
    return RedirectResponse(_safe_next(form.get("next") or f"/computers/{aid}"),
                            status_code=303)


@app.get("/computers/{aid}/label.pdf", include_in_schema=False)
def gui_computer_label(aid: str, small: int = 0, db: Session = Depends(get_db)):
    c = get_or_404(db, Computer, aid)
    installed = db.query(Part).filter(Part.computer_id == aid).all()
    board = next((p for p in installed if p.type == "motherboard"), None)
    rows = []
    for p in installed:
        d = to_dict(p)
        d["spec_pairs"] = specdb.pairs(db, p, display=True)
        rows.append(d)
    pdf = labels.render_pdf(
        to_dict(c), rows, is_computer=True, small=bool(small),
        form_factor=(specdb.scalars(db, board).get("form_factor", "")
                     if board else ""))
    return Response(pdf, media_type="application/pdf", headers={
        "Content-Disposition": f'inline; filename="{aid}{"-small" if small else ""}.pdf"'})


# --- GUI: parts (guided, typed entry) --------------------------------------

def _known_makes(db):
    """The manufacturers and (make, model) pairs already recorded, for the new-part
    form's pick lists and for spotting that a part being entered is a second of
    something already here. One representative asset id per pair, so the form can
    offer to start from it."""
    makes = [m for (m,) in db.query(Part.manufacturer).distinct()
             .order_by(Part.manufacturer) if (m or "").strip()]
    pairs = (db.query(Part.manufacturer, Part.model, Part.type,
                      func.max(Part.asset_id))
             .filter(Part.manufacturer != "", Part.model != "")
             .group_by(Part.manufacturer, Part.model, Part.type).all())
    known = [{"m": mk, "d": md, "t": t, "id": aid} for mk, md, t, aid in pairs]
    models = sorted({p["d"] for p in known})
    return makes, models, known


def _part_form_ctx(db, obj, ptype, computer_id, parent_id="", action=None):
    # Existing values come from the typed tables, not from re-parsing the string.
    mb_slots, mb_ram, mb_ports, mb_cpufams = {}, {}, {}, []
    spec_keys = {}
    if obj:
        st = specdb.read(db, obj)
        # The form's text inputs are keyed by display name, and want the same
        # rendering the item page shows ('256 KB', not 256).
        spec_keys = {k: v for k, v in specstruct.pairs(obj.type or "other", st) if k}
        if (obj.type or "") == "motherboard":
            mb_slots = dict(st.slots)
            mb_ram = dict(st.ram_slots)
            mb_ports = dict(st.ports)
            mb_cpufams = [x.strip() for x
                          in (st.scalars.get("cpu_family") or "").split(",")
                          if x.strip()]
    # A stored CPU family that is not in the pick list (older rows say '486'
    # where the vocabulary says '486-class') still needs a checkbox, or saving the
    # form would silently drop it.
    cpu_families = list(entry.CPU_FAMILIES)
    cpu_families += [f for f in mb_cpufams if f not in cpu_families]
    makes, models, known = _known_makes(db)
    return {
        "p": obj, "ptype": ptype, "computer_id": computer_id, "parent_id": parent_id,
        "spec_keys": spec_keys,
        "action": action or (f"/parts/{obj.asset_id}/edit" if obj else "/parts/new"),
        "makes": makes, "models": models, "known": known,
        "conditions": entry.CONDITIONS,
        "vocab": {
            "form_factors": entry.MOBO_FORM_FACTORS, "cpu_families": cpu_families,
            "ram_slots": entry.RAM_SLOT_TYPES, "card_interfaces": entry.CARD_INTERFACES,
            "video_connectors": entry.VIDEO_CONNECTORS,
            "storage_interfaces": entry.STORAGE_INTERFACES,
            "storage_kinds": entry.STORAGE_KINDS, "storage_protocols": entry.STORAGE_PROTOCOLS,
            "peripheral_interfaces": entry.PERIPHERAL_INTERFACES,
        },
        # What the routed-drive block's two pickers offer, and the kind whose
        # capacities those are. Column widths so a typed "custom" answer cannot be
        # longer than the drive row it may end up in.
        "drive_forms": drivedb.FORM_FACTORS, "drive_sizes": drivedb.SIZES,
        "drive_media": drivedb.MEDIA, "drive_speeds": drivedb.SPEEDS,
        "floppy_kind": entry.FLOPPY_KIND, "optical_kind": entry.OPTICAL_KIND,
        "drive_form_max": ComputerDrive.form_factor.type.length,
        "drive_size_max": ComputerDrive.size.type.length,
        "drive_media_max": ComputerDrive.media.type.length,
        "drive_speed_max": ComputerDrive.speed.type.length,
        **_bezel_ctx(),
        "slot_names": entry.SLOT_NAMES, "port_names": entry.PORT_NAMES,
        "mb_slots": mb_slots, "mb_ram": mb_ram, "mb_ports": mb_ports,
        "mb_cpufams": mb_cpufams,
        "port_legend": entry.PORT_LEGEND,
        "type_labels": entry.TYPE_LABELS, "type_order": entry.TYPE_ORDER,
    }


@app.get("/parts/new", response_class=HTMLResponse, include_in_schema=False)
def gui_new_part(request: Request, type: str = "other", computer_id: str = "",
                 parent_id: str = "", db: Session = Depends(get_db),
                 source: str = Query("", alias="from")):
    """The new-part form. `from` starts it filled in from an existing part -- the
    same fields duplicating one copies, so a second of something already recorded
    is a couple of clicks rather than retyping its specs. Nothing is saved until
    the form is submitted, so it can be edited first, which is the difference
    between this and the duplicate button."""
    src = db.get(Part, source.upper()) if source else None
    if src is None:
        ctx = _part_form_ctx(db, None, type, computer_id, parent_id)
        ctx["title"] = f"New {entry.type_label(type)}"
        return templates.TemplateResponse(request, "part_form.html", ctx)

    ptype = src.type or type
    ctx = _part_form_ctx(db, src, ptype, computer_id, parent_id, action="/parts/new")
    # A transient Part, never added to the session: the descriptive fields of the
    # source with everything belonging to that particular object left out.
    ctx["p"] = Part(**{k: getattr(src, k) for k in PART_FIELDS
                       if k not in DUP_EXCLUDE})
    ctx["title"] = f"New {entry.type_label(ptype)}"
    ctx["from_part"] = src.asset_id
    return templates.TemplateResponse(request, "part_form.html", ctx)


def _counts_from_form(form, prefix, names):
    """Read a grid of per-name number inputs (name='<prefix>:<n>') into
    [(name, count), ...], skipping zeros/blanks."""
    out = []
    for name in names:
        raw = (form.get(f"{prefix}:{name}", "") or "").strip()
        try:
            n = int(raw)
        except ValueError:
            n = 0
        if n > 0:
            out.append((name, n))
    return out


def _append_unmanaged(specs, extra, managed):
    """Carry across the spec values the form does not manage. Keyed ones merge by
    key; keyless ones (bare values from the old CSV import, e.g. 'ES1869F') are
    appended verbatim -- they have no key to merge on and used to be dropped."""
    keyless = []
    for k, v in extra:
        if not k:
            keyless.append(v)
        elif k not in managed:
            specs = entry.merge_spec(specs, k, v)
    for v in keyless:
        specs = f"{specs} | {v}" if specs else v
    return specs


def _assemble_motherboard_specs(form, extra=()):
    """Build a motherboard's specs from the structured grids (slot/RAM/port
    counts and CPU-family checkboxes) plus the plain text fields."""
    pairs = [("Chipset", (form.get("spec_chipset", "") or "").strip()),
             ("CPU family", ", ".join(form.getlist("cpufam"))),
             ("Form factor", (form.get("spec_form_factor", "") or "").strip()),
             ("RAM slots", entry.format_counts(
                 _counts_from_form(form, "ram", entry.RAM_SLOT_TYPES))),
             ("Onboard RAM", (form.get("spec_onboard_ram", "") or "").strip()),
             ("Slots", entry.format_counts(
                 _counts_from_form(form, "slot", entry.SLOT_NAMES))),
             ("Cache", (form.get("spec_cache", "") or "").strip()),
             ("BIOS", (form.get("spec_bios", "") or "").strip()),
             ("Onboard video", (form.get("spec_onboard_video", "") or "").strip()),
             ("Ports", entry.format_counts(
                 _counts_from_form(form, "port", entry.PORT_NAMES)))]
    return _append_unmanaged(entry.build_specs(pairs), extra,
                             [k for k, _ in pairs])


def _assemble_specs(ptype, form, extra=()):
    """Build a part's specs string from the typed form fields, running the same
    quick-entry expanders the guided flow has always used. `extra` carries the
    (key, value) pairs the form does not manage -- read from part_attribute, which
    is where anything unrecognised or unparseable already lives -- so editing a
    part never silently drops them."""
    if ptype == "motherboard":
        return _assemble_motherboard_specs(form, extra)
    managed = {
        "motherboard": ["Chipset", "CPU family", "Form factor", "RAM slots",
                        "Onboard RAM", "Slots", "Cache", "BIOS",
                        "Onboard video", "Ports"],
        "cpu": ["Socket", "Speed", "FSB", "Cores", "Cache"],
        "ram": ["Type", "Size", "Speed"],
        "video": ["Chip", "Interface", "Connector", "Memory", "Type"],
        "sound": ["Chip", "Interface", "FM", "Ports"],
        "network": ["Chip", "Interface", "Connector"],
        "io": ["Chip", "Interface", "Ports"],
        "storage": ["Kind", "Description", "Form factor", "Size", "Interface",
                    "Protocol", "Capacity", "CHS", "Media", "Speed", "Role",
                    "Colour", "Yellowing"],
    }.get(ptype)
    # 'other' / 'peripheral' keep a free-text specs box (no data loss).
    if managed is None:
        return " ".join((form.get("specs", "") or "").split())
    # One managed key whose box is not named for it: the drive description is
    # typed into the same field that feeds a machine's drive row, so it is named
    # for that job. Routed to a machine it becomes the row and never reaches
    # here; kept as a part, this is what stops it being dropped on the floor.
    fields = {"Description": "drive_desc"}
    specs = ""
    for key in managed:
        # spec_ prefix keeps these clear of the part's own columns (a RAM
        # 'Type' spec vs the part type, etc.).
        field = fields.get(key) or (
            "spec_" + key.lower().replace(" ", "_").replace("/", "_"))
        raw = None
        if ptype == "storage" and key in DRIVE_PICKS:
            # Picked from a radio group with a box beside it, not typed into one
            # input, and read only for the kinds the group is offered for. Where it
            # is offered its answer stands, blank included -- that is how a value is
            # taken back off -- and where it is not, the plain field below it is
            # what the form was asking with, so that is what is read.
            raw = _picked_drive(form, key)
        if raw is None:
            raw = (form.get(field, "") or "").strip()
        if not raw:
            continue
        if key == "Ports":
            raw = entry.expand_ports(raw)
        elif key == "Slots":
            raw = entry.expand_slots(raw)
        elif key in ("Size", "Memory") and ptype != "storage":
            # A memory amount is a quantity, and normalises to KB so it sorts and
            # compares. A drive's size is a media designation and must not: 1.44MB
            # is 1475 KB only by convention, and nobody calls that disk a 1475 KB.
            raw = entry.normalise_amount(key, raw)
        specs = entry.merge_spec(specs, key, raw)
    return _append_unmanaged(specs, extra, managed)


# The routed-drive block's pick-or-type groups: the spec key each fills, the form
# field it is named for, the drive row column it becomes, and the kind it is
# offered for (None for any drive that lives on the drives field). A form factor
# fits every such drive -- an optical drive is 5.25" as surely as a floppy is 3.5"
# -- while the capacities on offer are floppy media designations and fit a floppy.
# An optical drive answers the other two instead: what it does with a disc, and how
# fast, which is what that drive is known by where a capacity is what a floppy is
# known by.
DRIVE_PICKS = {
    "Form factor": ("drive_form", "form_factor", None),
    "Size": ("drive_size", "size", entry.FLOPPY_KIND),
    "Media": ("drive_media", "media", entry.OPTICAL_KIND),
    "Speed": ("drive_speed", "speed", entry.OPTICAL_KIND),
}


def _picked_drive(form, key):
    """What one of those groups chose: one of the standard answers, or whatever was
    typed beside "custom" for the hardware the list does not name (a 3" Amstrad, a
    Floptical). Blank when nothing was picked, which leaves the description to say
    it.

    None -- not blank -- for a kind the group is not offered for, which is the
    difference between "asked, and the answer is nothing" and "never asked". A
    radio left checked from a kind since changed must not be saved against a drive
    it never described; but Media and Speed are also a hard disk's own typed spec
    fields, and those must not be thrown away by a picker that was not on screen.
    """
    field, _col, only = DRIVE_PICKS[key]
    kind = form.get("kind", "") or ""
    if kind in entry.PART_STORAGE_KINDS or (only and kind != only):
        return None
    picked = (form.get(field, "") or "").strip()
    if picked == "custom":
        return " ".join((form.get(field + "_custom", "") or "").split())
    return picked


def _apply_drive_picks(form, rows):
    """Put what the pickers chose on drives just read from a typed description.

    A picker is a deliberate answer, so it wins over the same thing said in the
    text; a blank one leaves what the text said. Two drives typed at once get the
    same answers, which is the only reading a single set of pickers can have.

    And the kind, where the description named none. drivedb infers "floppy" from a
    size or a form factor only a floppy has, but it infers it while reading the
    text -- so a description like "Sony MPF920", which names neither, used to leave
    a row with no kind, and picking the size rather than typing it does not reach
    that rule. The menu that routed the drive here has already said which kind it
    is, so let it answer: read through drivedb's own vocabulary rather than a
    second mapping of the same words, and only where the text did not say.
    """
    picks = {col: _picked_drive(form, key) or ""
             for key, (_f, col, _only) in DRIVE_PICKS.items()}
    picks["colour"] = form.get("drive_colour", "") or ""
    picks["yellowing"] = form.get("drive_yellowing", "") or ""
    # The make and model, from the fields that ask for them. A routed drive never
    # becomes a Part, so what was typed under Identity used to be dropped on the
    # floor and the description was the only way to name the thing -- survivable
    # while the description was always on screen, not now that a floppy the pickers
    # have described does without one. Filled in where the description named
    # nothing, not over the top of it: what is left of a description after the
    # pickers have taken their share is the words they could not say (a "SS/DD"),
    # and those are the last thing to overwrite.
    named = " ".join(
        x for x in (entry.deshout((form.get("manufacturer", "") or "").strip()),
                    entry.deshout((form.get("model", "") or "").strip())) if x)
    # The first word of the menu's label: "Floppy/Gotek" and "SD/CF card" are pairs
    # of alternatives that drivedb reads as neither, and a Gotek names itself.
    menu = (form.get("kind", "") or "").split("/")[0]
    from_menu = (drivedb.parse_segment(menu) or {}).get("kind", "")
    for row in rows:
        for col, picked in picks.items():
            row[col] = picked.strip() or row.get(col, "")
        row["kind"] = row.get("kind", "") or from_menu
        row["model"] = row.get("model", "") or named


async def _part_from_form(form, ptype, extra=()):
    data = {"type": ptype,
            "computer_id": form.get("computer_id", "") or None,
            "parent_id": form.get("parent_id", "") or None}
    for f in ("manufacturer", "model", "name", "year", "condition", "source",
              "acquired_date", "url", "summary", "notes", "disk_image"):
        data[f] = _coerce(f, form.get(f, ""))
    for f in ("manufacturer", "model"):
        data[f] = entry.deshout(data[f])
    data["specs"] = _assemble_specs(ptype, form, extra)
    return data


@app.post("/parts/new", include_in_schema=False)
async def gui_create_part(request: Request, db: Session = Depends(get_db)):
    form = await request.form()
    photos = _chosen_photos(form)
    ptype = form.get("type", "other") or "other"
    computer_id = form.get("computer_id", "") or ""
    # Storage routing: floppy / optical / SD-CF live on the computer's drives
    # field; only hard disks and tape become their own tagged parts.
    if ptype == "storage":
        kind = form.get("kind", "") or ""
        if kind and kind not in entry.PART_STORAGE_KINDS:
            # With nothing typed, the kind names the drive -- but the menu's label
            # is a pair of alternatives ("Floppy/Gotek", "SD/CF card") that the
            # parser reads as neither, and files as a model. Hand it the first
            # word, which is a word it knows. Picking only a capacity and typing
            # no description is an ordinary gesture now the picker exists.
            desc = (form.get("drive_desc", "") or "").strip() or kind.split("/")[0]
            if computer_id:
                c = get_or_404(db, Computer, computer_id)
                # Append a row, not text: drives is rendered from the rows, so
                # anything written straight to it would vanish on the next save.
                added = drivedb.from_string(desc)[0]
                _apply_drive_picks(form, added)
                drivedb.write(db, c, drivedb.read(db, c) + added)
                # The canonical rendering rather than what was typed, so the history
                # names the bezel that was picked from the menus as well.
                add_log(db, computer_id,
                        f"added drive: {drivedb.render(added) or desc}")
                # This drive is a field on the machine rather than an asset of its
                # own, so it has no tag of its own to file a photo under: any that
                # were chosen belong to the machine the drive went into.
                if photos:
                    _attach_photos(db, c, "computers", photos)
                db.commit()
                return RedirectResponse(f"/computers/{computer_id}?build=1",
                                        status_code=303)
    data = await _part_from_form(form, ptype)
    if ptype == "storage":
        data["specs"] = entry.merge_spec(data["specs"], "Kind",
                                         form.get("kind", "") or "")
        # A routed kind with no machine to route to becomes a part after all, so a
        # bezel picked on that path comes with it rather than being dropped on the
        # floor -- the part's own menus were not on screen to say otherwise.
        for key, routed, own in (("Colour", "drive_colour", "spec_colour"),
                                 ("Yellowing", "drive_yellowing", "spec_yellowing")):
            picked = (form.get(routed, "") or "").strip()
            if picked and not (form.get(own, "") or "").strip():
                data["specs"] = entry.merge_spec(data["specs"], key, picked)
    obj = Part(asset_id=next_asset_id(db), **data)
    db.add(obj)
    db.flush()
    specdb.write(db, obj)
    add_log(db, obj.asset_id, "created", "created")
    db.commit()
    if photos:
        _attach_photos(db, obj, "parts", photos)
        db.commit()
    parent_id = form.get("parent_id", "") or ""
    dest = (f"/computers/{computer_id}?build=1" if computer_id
            else f"/parts/{parent_id}" if parent_id
            else f"/parts/{obj.asset_id}")
    return RedirectResponse(dest, status_code=303)


@app.get("/parts/{aid}", response_class=HTMLResponse, include_in_schema=False)
def gui_part(aid: str, request: Request, imgerr: int = 0,
             db: Session = Depends(get_db)):
    p = get_or_404(db, Part, aid)
    parent = db.get(Computer, p.computer_id) if p.computer_id else None
    host = db.get(Part, p.parent_id) if p.parent_id else None
    children = (db.query(Part).filter(Part.parent_id == aid)
                .order_by(Part.asset_id).all())
    candidates, computers = [], []
    if request.state.authed:
        candidates = (db.query(Part)
                      .filter(Part.type == "storage", Part.asset_id != aid,
                              Part.parent_id.is_(None))
                      .order_by(Part.asset_id).all())
        if not p.computer_id and not p.parent_id:
            computers = db.query(Computer).order_by(Computer.asset_id).all()
    images = detect_images("parts", aid)
    spec_pairs = specdb.pairs(db, p, display=True)
    # The preview text and the structured data are read rather than parsed, so they
    # say the figures the page says -- not the stored string's exact-to-the-KB ones.
    blurb = p.summary or _dot(entry.type_label(p.type),
                              " ".join(x for x in (p.manufacturer, p.model, str(p.year or "")) if x),
                              specstruct.join(spec_pairs))
    return templates.TemplateResponse(request, "part.html", {
        "p": p, "parent": parent, "host": host, "children": children,
        "candidates": candidates, "computers": computers,
        "images": images, "ref_marks": reference_marks("parts", aid),
        "spec_pairs": spec_pairs, "imgerr": bool(imgerr),
        "log": item_log(db, aid), "nav": _item_nav(db, aid),
        "og": (og := _og(request, entry.display_name(to_dict(p)), blurb,
                         images[0] if images else None)),
        "jsonld": _jsonld(og, p.asset_id, p.manufacturer,
                          entry.type_label(p.type) or "Computer part")})


@app.get("/parts/{aid}/edit", response_class=HTMLResponse, include_in_schema=False)
def gui_edit_part(aid: str, request: Request, db: Session = Depends(get_db)):
    p = get_or_404(db, Part, aid)
    ctx = _part_form_ctx(db, p, p.type or "other", p.computer_id or "",
                         p.parent_id or "")
    ctx["title"] = f"Edit {aid}"
    return templates.TemplateResponse(request, "part_form.html", ctx)


@app.post("/parts/{aid}/edit", include_in_schema=False)
async def gui_save_part(aid: str, request: Request, db: Session = Depends(get_db)):
    p = get_or_404(db, Part, aid)
    form = await request.form()
    ptype = form.get("type", p.type) or "other"
    # Unmanaged keys live in part_attribute; carry them across the edit.
    data = await _part_from_form(form, ptype, specdb.read(db, p).attributes)
    if ptype == "storage" and (form.get("kind", "") or ""):
        data["specs"] = entry.merge_spec(data["specs"], "Kind", form.get("kind"))
    old = {k: getattr(p, k) for k in data}
    for k, v in data.items():
        setattr(p, k, v)
    specdb.write(db, p)
    diff = _field_diffs(old, {k: getattr(p, k) for k in data}, list(data), semantic_specs=True)
    if diff:
        add_log(db, aid, diff)
    db.commit()
    return RedirectResponse(f"/parts/{aid}", status_code=303)


# A duplicate is a second identical unit, so it copies what describes the model --
# the fields, the specs, a machine's fitted memory and drives -- and nothing that
# belongs to the original object: its photos, its disposal, its provenance
# (source / acquired date / notes), and where it sits. A second card is a second
# card, not another card in the same slot, so the copy starts unplaced.
DUP_EXCLUDE = {"image", "disposed", "disposed_at", "disposed_note", "source",
               "acquired_date", "notes", "computer_id", "parent_id"}


@app.post("/parts/{aid}/duplicate", include_in_schema=False)
def gui_duplicate_part(aid: str, db: Session = Depends(get_db)):
    src = get_or_404(db, Part, aid)
    data = {k: getattr(src, k) for k in PART_FIELDS if k not in DUP_EXCLUDE}
    obj = Part(asset_id=next_asset_id(db), **data)
    db.add(obj)
    db.flush()
    specdb.write(db, obj)
    add_log(db, obj.asset_id, f"created as a duplicate of {aid}", kind="created")
    add_log(db, aid, f"duplicated to {obj.asset_id}", kind="duplicate")
    db.commit()
    return RedirectResponse(f"/parts/{obj.asset_id}", status_code=303)


@app.post("/computers/{aid}/duplicate", include_in_schema=False)
def gui_duplicate_computer(aid: str, db: Session = Depends(get_db)):
    """A second machine of the same model. Its memory and drives come across --
    they describe the build -- but its parts do not: those are tagged objects
    fitted to the original, and the copy starts as an empty chassis to fill."""
    src = get_or_404(db, Computer, aid)
    data = {k: getattr(src, k) for k in COMPUTER_FIELDS
            if k not in DUP_EXCLUDE and k not in DERIVED_FIELDS}
    obj = Computer(asset_id=next_asset_id(db), **data)
    db.add(obj)
    db.flush()
    mods, chips = ramdb.read(db, src)
    ramdb.write(db, obj, mods, chips, src.installed_ram_note or "",
                src.installed_ram_kb)
    drivedb.write(db, obj, drivedb.read(db, src), src.drives_note or "")
    add_log(db, obj.asset_id, f"created as a duplicate of {aid}", kind="created")
    add_log(db, aid, f"duplicated to {obj.asset_id}", kind="duplicate")
    db.commit()
    return RedirectResponse(f"/computers/{obj.asset_id}", status_code=303)


@app.post("/parts/{aid}/dispose", include_in_schema=False)
async def gui_dispose_part(aid: str, request: Request, db: Session = Depends(get_db)):
    p = get_or_404(db, Part, aid)
    form = await request.form()
    p.disposed = True
    p.disposed_at = _parse_date(form.get("date", "")) or date.today()
    p.disposed_note = form.get("note", "") or ""
    add_log(db, aid, _disposal_log(p))
    db.commit()
    return RedirectResponse(f"/parts/{aid}", status_code=303)


@app.post("/parts/{aid}/restore", include_in_schema=False)
def gui_restore_part(aid: str, db: Session = Depends(get_db)):
    p = get_or_404(db, Part, aid)
    p.disposed = False
    p.disposed_at = None
    p.disposed_note = ""
    add_log(db, aid, "restored")
    db.commit()
    return RedirectResponse(f"/parts/{aid}", status_code=303)


@app.get("/parts/{aid}/delete", response_class=HTMLResponse, include_in_schema=False)
def gui_delete_part_form(aid: str, request: Request, db: Session = Depends(get_db)):
    p = get_or_404(db, Part, aid)
    _require_disposed(p, "part")
    return templates.TemplateResponse(request, "delete.html",
                                      _delete_ctx(request, db, "parts", p))


@app.post("/parts/{aid}/delete", include_in_schema=False)
async def gui_delete_part(aid: str, request: Request, db: Session = Depends(get_db)):
    p = get_or_404(db, Part, aid)
    _require_disposed(p, "part")
    form = await request.form()
    if not _confirms_url(form.get("confirm", ""), "parts", p.asset_id):
        return templates.TemplateResponse(
            request, "delete.html",
            _delete_ctx(request, db, "parts", p,
                        error="That is not this item's URL. Nothing was deleted."),
            status_code=400)
    # Back to the machine it was in if it was in one, since that page is now a
    # part short and is the thing worth looking at; otherwise to the gallery.
    where = f"/computers/{p.computer_id}" if p.computer_id else "/"
    delete_part(db, p)
    return RedirectResponse(where, status_code=303)


@app.post("/parts/{aid}/note", include_in_schema=False)
async def gui_part_note(aid: str, request: Request, db: Session = Depends(get_db)):
    get_or_404(db, Part, aid)
    form = await request.form()
    add_log(db, aid, (form.get("message", "") or "").strip(), kind="note")
    db.commit()
    return RedirectResponse(f"/parts/{aid}", status_code=303)


@app.post("/parts/{aid}/photo", include_in_schema=False)
async def gui_part_photo(aid: str, photos: list[UploadFile] = File(...),
                         db: Session = Depends(get_db)):
    p = get_or_404(db, Part, aid)
    first = None
    n = 0
    for up in photos:
        if (up.filename or "").strip():
            rel = _save_photo("parts", aid, up)
            n += 1
            if first is None:
                first = rel
    if first and not p.image:
        p.image = first
    if n:
        add_log(db, aid, f"added {n} photo(s)")
    db.commit()
    return RedirectResponse(f"/parts/{aid}", status_code=303)


@app.post("/parts/{aid}/fetch-image", include_in_schema=False)
def gui_part_fetch_image(aid: str, db: Session = Depends(get_db)):
    p = get_or_404(db, Part, aid)
    rel = _fetch_reference_photo("parts", aid, p.url or "") if p.url else None
    if rel:
        if not p.image:
            p.image = rel
        add_log(db, aid, "fetched a photo from the reference")
        db.commit()
    return RedirectResponse(f"/parts/{aid}" + ("" if rel else "?imgerr=1"),
                            status_code=303)


@app.post("/parts/{aid}/unlink", include_in_schema=False)
async def gui_unlink_part(aid: str, request: Request, db: Session = Depends(get_db)):
    p = get_or_404(db, Part, aid)
    form = await request.form()
    nxt = form.get("next", "") or f"/parts/{aid}"
    old_cid = p.computer_id
    p.computer_id = None
    if old_cid:
        add_log(db, aid, f"unlinked from computer {old_cid}")
    db.commit()
    return RedirectResponse(_safe_next(nxt), status_code=303)


@app.post("/parts/{aid}/link", include_in_schema=False)
async def gui_link_part_to_computer(aid: str, request: Request,
                                    db: Session = Depends(get_db)):
    """Install this part into an existing computer (chosen from the part page)."""
    p = get_or_404(db, Part, aid)
    form = await request.form()
    cid = form.get("computer_id", "") or ""
    if cid:
        get_or_404(db, Computer, cid)
        p.computer_id = cid
        p.parent_id = None
        add_log(db, aid, f"installed in {cid}")
        add_log(db, cid, f"linked part {aid}")
        db.commit()
    return RedirectResponse(f"/parts/{aid}", status_code=303)


@app.post("/parts/{aid}/attach", include_in_schema=False)
async def gui_attach_part(aid: str, request: Request, db: Session = Depends(get_db)):
    """Mount another part onto this one (e.g. a hard disk on a controller card)."""
    get_or_404(db, Part, aid)
    form = await request.form()
    child = get_or_404(db, Part, form.get("part_id", ""))
    child.parent_id = aid
    child.computer_id = None
    add_log(db, aid, f"mounted {child.asset_id}")
    add_log(db, child.asset_id, f"mounted on {aid}")
    db.commit()
    return RedirectResponse(f"/parts/{aid}", status_code=303)


@app.post("/parts/{aid}/detach", include_in_schema=False)
async def gui_detach_part(aid: str, request: Request, db: Session = Depends(get_db)):
    p = get_or_404(db, Part, aid)
    form = await request.form()
    old_host = p.parent_id
    p.parent_id = None
    if old_host:
        add_log(db, aid, f"unmounted from {old_host}")
    db.commit()
    return RedirectResponse(_safe_next(form.get("next", "") or f"/parts/{aid}"),
                            status_code=303)


@app.post("/parts/{aid}/primary-photo", include_in_schema=False)
async def gui_part_primary(aid: str, request: Request,
                           db: Session = Depends(get_db)):
    p = get_or_404(db, Part, aid)
    form = await request.form()
    p.image = _set_primary_photo("parts", aid, form.get("image", ""))
    add_log(db, aid, "changed the default photo")
    db.commit()
    return RedirectResponse(f"/parts/{aid}", status_code=303)


@app.post("/parts/{aid}/photo-delete", include_in_schema=False)
async def gui_part_photo_delete(aid: str, request: Request,
                                db: Session = Depends(get_db)):
    p = get_or_404(db, Part, aid)
    form = await request.form()
    was_primary, new_primary = _delete_image("parts", aid, form.get("image", ""))
    if was_primary:
        p.image = new_primary or ""
    add_log(db, aid, "deleted a photo")
    db.commit()
    return RedirectResponse(f"/parts/{aid}", status_code=303)


@app.post("/parts/{aid}/photo-reference", include_in_schema=False)
async def gui_part_photo_reference(aid: str, request: Request,
                                   db: Session = Depends(get_db)):
    p = get_or_404(db, Part, aid)
    form = await request.form()
    rel = form.get("image", "")
    if rel not in detect_images("parts", aid):
        raise HTTPException(404, "no such photo for this item")
    on = form.get("set", "1") == "1"
    _mark_reference(rel, on, (form.get("note", "") or "").strip(), p.url or "")
    add_log(db, aid, "flagged a photo as a reference image" if on
            else "unflagged a reference photo")
    db.commit()
    return RedirectResponse(f"/parts/{aid}", status_code=303)


@app.get("/parts/{aid}/edit-photo", response_class=HTMLResponse, include_in_schema=False)
def gui_part_edit_photo(aid: str, image: str = ""):
    return _photo_edit_redirect("parts", aid, image)


@app.post("/parts/{aid}/photo-rotate", include_in_schema=False)
async def gui_part_photo_rotate(aid: str, request: Request,
                                db: Session = Depends(get_db)):
    form = await request.form()
    _do_photo_rotate(db, Part, "parts", aid, form)
    return RedirectResponse(_safe_next(form.get("next") or f"/parts/{aid}"),
                            status_code=303)


@app.post("/parts/{aid}/photo-crop", include_in_schema=False)
async def gui_part_photo_crop(aid: str, request: Request,
                              db: Session = Depends(get_db)):
    form = await request.form()
    _do_photo_crop(db, Part, "parts", aid, form)
    return RedirectResponse(_safe_next(form.get("next") or f"/parts/{aid}"),
                            status_code=303)


@app.get("/parts/{aid}/label.pdf", include_in_schema=False)
def gui_part_label(aid: str, small: int = 1, db: Session = Depends(get_db)):
    p = get_or_404(db, Part, aid)
    pdf = labels.render_pdf(to_dict(p), [], is_computer=False, small=bool(small),
                            spec_pairs=specdb.pairs(db, p, display=True))
    return Response(pdf, media_type="application/pdf", headers={
        "Content-Disposition": f'inline; filename="{aid}{"-small" if small else ""}.pdf"'})
