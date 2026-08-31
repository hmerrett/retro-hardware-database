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
import re
import secrets
import shutil
from collections import Counter
from datetime import UTC, date, datetime, timedelta
from pathlib import Path
from types import SimpleNamespace
import json
from urllib.parse import parse_qs, quote, urlparse
from xml.sax.saxutils import escape

from fastapi import (Depends, FastAPI, File, HTTPException, Query, Request,
                     UploadFile)
from fastapi.responses import FileResponse, HTMLResponse, RedirectResponse, Response
from itsdangerous import BadSignature, SignatureExpired, URLSafeTimedSerializer
from markupsafe import Markup
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from sqlalchemy import case, func
from sqlalchemy.orm import Session

from . import (drivedb, enrich, entry, filesdb, labels, machinedb, machines,
               ramdb, specdb, specstruct, thumbs)
from .db import get_db
from .ids import next_asset_id
from .models import (AssetChip, AssetVariant, Computer, ComputerDrive,
                     ComputerRamChip, ComputerRamModule, IoSpec, LogEntry, LogPhoto,
                     MotherboardSpec, NetworkSpec, Part, PartPort, PartRamSlot,
                     PartSlot, SoundSpec, StorageSpec, StoredFile, VideoSpec)
from .schemas import ComputerIn, ComputerOut, PartIn, PartOut
import contextlib

# Schema is owned by Alembic now (entrypoint.sh runs `alembic upgrade head` on
# start); no create_all here.

app = FastAPI(title="Retro Hardware Database API", version="0.3.0")
templates = Jinja2Templates(directory=str(Path(__file__).resolve().parent / "templates"))
templates.env.globals.update(
    display_name=entry.display_name, type_label=entry.type_label,
    bezel_css=entry.bezel_css,
    # For the pages that list parts rather than show one: a part's rendered specs
    # broken back into pairs so they can be laid out as labelled columns. The item's
    # own page reads the typed tables instead (specdb.pairs) -- this is the same
    # reading of the same string that the change log already takes of it.
    parse_specs=entry.parse_specs,
    # Markup here rather than |safe at each use: the markup is ours, built by segno
    # from a URL the app made, and no template should have to remember that.
    qr_svg=lambda data: Markup(labels.qr_svg(data)),
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
# The two cookies the site sets for a visitor who is only reading, both first party,
# both holding a choice that visitor made themselves and nothing else. Neither is
# written until the choice is made, so arriving and reading stores nothing at all --
# which is what the notice at the foot of the page is able to say.
SORT_COOKIE = "rhdb_sort"
# That the notice has been read. Set only by dismissing it, and strictly necessary in
# the plain sense: without it the notice cannot stay dismissed.
NOTICE_COOKIE = "rhdb_noticed"
# The names, so the script that writes them and the notice that describes them cannot
# come to disagree with the code that reads them.
templates.env.globals["sort_cookie"] = SORT_COOKIE
templates.env.globals["notice_cookie"] = NOTICE_COOKIE
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
    # The catalogue, in both the shapes it is offered in. This is the one corner of
    # the JSON API that is public, and it is public because there is nothing of the
    # register in it: /api/machines answers with what was made rather than with what
    # is here, the same list that is in the repository as machines.yaml and
    # catalogue.txt. Putting the page behind the login and not the data behind it
    # would be a lock on a door in a field.
    if path in ("/machines", "/api/machines"):
        return True
    if path.startswith(("/images/", "/static/")):
        return True
    # The files kept beside the register read like the photographs do: a driver or
    # a manual is part of what the catalogue is for. Downloading one is public;
    # putting one there, re-filing it and deleting it are all POSTs, so they are
    # already behind the login by the rule above.
    if path == "/files" or path.startswith("/files/"):
        return True
    if path.startswith("/items/"):
        return True
    if path.startswith(("/computers/", "/parts/")):
        return not (path.endswith(("/new", "/delete"))
                    or "/edit" in path or "/label.pdf" in path)
    return False


@app.middleware("http")
async def no_stale_pages(request: Request, call_next):
    """Every page, freshly asked for.

    The pages carried no cache headers at all, and a response with neither
    freshness nor a validator is one a browser may cache for as long as it
    likes -- Safari does, and does it hardest on a phone. The site was
    deployed, the code was on the server, and the reader had yesterday's
    Javascript. `no-cache` is not "do not store": it is "ask me first", which
    is what a page whose whole point is that it changes wants.

    Only the pages. Photographs and static files carry their own headers, and
    those say the opposite on purpose -- they are stamped with a version, so
    they may be kept for a year (see `img_url` and `_static_headers`).
    """
    response = await call_next(request)
    if response.headers.get("content-type", "").startswith("text/html"):
        response.headers.setdefault("Cache-Control", "no-cache")
    return response


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
    # Read here so the notice can be left out of the markup altogether once it has
    # been dismissed, rather than shipped on every page and hidden by a script.
    request.state.noticed = NOTICE_COOKIE in request.cookies
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

# These are rendered from the memory, drive and catalogue child tables, so the form
# loop must not write them, and the change log need not repeat the derived total.
DERIVED_FIELDS = {"installed_ram", "installed_ram_kb", "drives", "drives_note",
                  "variant"}
COMPUTER_DIFF_FIELDS = [f for f in COMPUTER_FIELDS if f != "installed_ram_kb"]

# The same for a part: its variant line is rendered from the catalogue rows, so
# nothing that copies or writes a part's columns wholesale may set it.
PART_DERIVED_FIELDS = {"variant"}

# Container paths by default (the `images` volume and the goaccess report mount);
# overridable so the app can be imported and run outside Docker for local
# development, which the hardcoded absolute paths used to make impossible.
IMAGES_DIR = Path(os.getenv("RHDB_IMAGES_DIR", "/app/images"))
IMAGE_EXTS = (".jpg", ".jpeg", ".png", ".webp", ".gif")

# The three folders photographs live in, and why the third is not one of the first
# two. A folder under here is read by filename: everything in computers/ whose stem
# is an asset id belongs to that asset, and the first of them is its portrait. That
# is exactly what a photograph hung on a history entry must not be -- a picture of
# a recap is not a picture of the part -- so it is filed under the entry's own id
# in a folder nothing scans by asset id. See models.LogPhoto.
LOG_KIND = "log"

# GoAccess writes a self-contained traffic report here (read-only mount from the
# shared volume). The route is login-only via the auth gate above.
STATS_DIR = Path(os.getenv("RHDB_STATS_DIR", "/app/stats"))


@app.get("/traffic", response_class=HTMLResponse, include_in_schema=False)
def gui_traffic():
    report = STATS_DIR / "index.html"
    if not report.exists():
        return HTMLResponse(
            "<p style='font-family:system-ui;margin:2rem'>No traffic report yet "
            "&mdash; it is generated from the access logs every five minutes, so "
            "check back shortly.</p>")
    return HTMLResponse(report.read_text(encoding="utf-8"))


# Disposed items are records of things that have gone. A figure about the collection
# is about what is in it, so everything on /stats counts only what is still held --
# the exceptions being the figures that are *about* disposal, which say so where they
# are written. This is the filter, in one place, so "still here" means one thing.
def _held(query, model):
    return query.filter(model.disposed.is_(False))


def _all_years(db, held=True):
    """Every year recorded against anything still here, machines and parts together."""
    out = []
    for model in (Computer, Part):
        q = db.query(model.year).filter(model.year.isnot(None))
        out += [y for (y,) in (_held(q, model) if held else q)]
    return out


# --- the pointless department -----------------------------------------------
# Figures that answer nothing anyone needs to know, which is the point of them. A
# page of totals says how big the collection is; these say what it is like.

# How many parts a maker needs before its record means anything. Below this a maker
# with one working card would top the table on a sample of one, which is not a
# fact about the maker. The caption on the page says the threshold, because a
# ranking whose entry condition is hidden is a ranking that flatters itself.
RELIABILITY_MIN = 5
# Ways of attaching a disk that died with the 1980s, named rather than worked out:
# what makes MFM historic is not something the database can derive. Read by the
# figure and by the /browse view behind it, so both mean the same four things.
LEGACY_DISK_BUSES = ("MFM", "RLL", "ESDI", "XTA")
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


def _stem_owner(stem, ids):
    """Whose photograph a filename is, or None. A photo is <asset_id>.<ext> or
    <asset_id>-<something>.<ext>, so the owner is the stem itself or the stem with
    its suffix taken off -- and the tags are matched against the register rather
    than guessed at with a regex, because an asset id is whatever ids.py says it is
    and not a shape this function should be repeating.

    The suffix comes off one hyphen at a time rather than all at once, so that
    RH-0001-back-left belongs to the machine exactly as RH-0001-2 does. This has to
    answer precisely what pick_images answers: the count of what is photographed and
    the list of what is not are the same question asked twice, and a file with two
    hyphens in its name is not a place for them to start disagreeing."""
    while stem:
        if stem in ids:
            return stem
        stem = stem.rpartition("-")[0]
    return None


def _photo_counts(ids_by_kind):
    """How many portraits each asset has, from one pass over each folder named.

    Keyed by kind, because a photograph belongs to the folder it is in: a picture in
    parts/ is a picture of a part, and matching it against every tag in the register
    would let it stand as some machine's portrait.

    Only computers/ and parts/ are ever read, which is how a photograph on a history
    entry stays out of this: it lives in log/, filed under the entry's id rather
    than the asset's. That is deliberate and load-bearing rather than an oversight
    of two folder names. Six photographs of a recap say what happened to a machine;
    they do not say which machine this is, so an object with six of them and no
    portrait is still an object nobody has photographed in the sense this counts."""
    counts = {}
    for kind, ids in ids_by_kind.items():
        for stem, _name in folder_images(kind):
            aid = _stem_owner(stem, ids)
            if aid:
                counts[aid] = counts.get(aid, 0) + 1
    return counts


# The portrait is the file named after the tag, and the filesystem is what says so.
# There is an `image` column beside it, but that is a note of which file was chosen
# last, not the choosing itself -- promoting a photo renames files, and the column
# is written afterwards. On the live register a dozen rows have a photograph on disk
# and a blank column, filed by the import tools, which never wrote it. The item page
# draws the file; so does the gallery card; so does this.
def _portraits(db):
    """(counts, missing): how many portraits each thing still here has, and the tags
    of the ones that have none.

    Held items only -- see _held. The count of what is unphotographed is a job list,
    and a disposed item cannot be photographed, so putting one on the list is handing
    somebody work they cannot do."""
    ids = {"computers": {a for (a,) in _held(db.query(Computer.asset_id), Computer)},
           "parts": {a for (a,) in _held(db.query(Part.asset_id), Part)}}
    counts = _photo_counts(ids)
    missing = {a for group in ids.values() for a in group if a not in counts}
    return counts, missing


def _big_total(kb):
    """A grand total in the unit a person would say it in. entry.fmt_kb keeps a
    non-round figure in MiB, which is right for one drive -- 2096128 KiB is the 2047
    MiB BIOS limit, not "2 GiB" -- and unreadable for the sum of every drive there
    is, where it gives "124222 MiB"."""
    if kb >= 1024 * 1024:
        return f"{kb / (1024 * 1024):.1f} {entry.GIB}"
    return entry.fmt_kb(kb, True)


def _facts(db, st, this_year):
    """Every figure the collection can currently answer, in one pool for the page to
    draw a handful from.

    There used to be two halves: a fixed set of tiles that were always on the page,
    and a shuffled set of odder ones underneath. The split flattered the fixed half --
    "spares on the shelf" is no more a headline than "longest wait" -- and it meant
    the interesting figures were the ones you had to scroll to. One pool, shuffled,
    and the page is different every time you look at it.

    Each figure is skipped rather than shown empty, so the pool is what the register
    can currently answer: a collection with no acquisition dates simply never offers
    the ones about waiting, and a fresh install offers none of them.

    Disposed items are left out throughout -- see _held -- bar the one figure that is
    about them.
    """
    out = []

    def add(k, v, s, href=None):
        out.append({"k": k, "v": v, "s": s, "href": href})

    def named(obj):
        return entry.display_name(to_dict(obj))

    # --- how big it is ------------------------------------------------------

    if st["top_maker"]:
        add("Most represented maker", st["top_maker"][0],
            f"{st['top_maker'][1]} parts",
            f"/browse?f=maker&v={quote(st['top_maker'][0])}")
    if st["top_type"]:
        add("Most collected thing", entry.type_label(st["top_type"][0]),
            f"{st['top_type'][1]} of them",
            f"/browse?f=type&v={quote(st['top_type'][0])}")
    if st["mean_year"]:
        add("The average item", str(st["mean_year"]),
            f"{this_year - st['mean_year']} years old", "/browse?f=year")
    if st["top_ram"]:
        each = " each" if len(st["top_ram"]) > 1 else ""
        n = st["top_ram"][0][1]
        add("Usual amount of memory",
            " / ".join(r[0] for r in st["top_ram"]),
            f"{n} machine{'' if n == 1 else 's'}{each}",
            "/browse?f=ram&v=" + ",".join(str(k) for k in st["top_ram_kb"]))
    if st["fitted_kb"]:
        add("Memory fitted, everything added up",
            entry.fmt_kb(st["fitted_kb"], True), "across every machine here",
            "/browse?f=ramfitted")
    if st["stored_kb"]:
        # The comparison used to be a hardcoded "one modern phone's worth", which
        # stopped being true as the register grew. Worked out, it stays true.
        phone_kb = 128 * 1024 * 1024
        share = st["stored_kb"] / phone_kb
        how = (f"about {share:.0%} of one modern phone" if share < 1
               else f"{share:.1f} modern phones' worth")
        add("Storage, everything added up", _big_total(st["stored_kb"]), how,
            "/browse?f=storage")
    if st["slots_per_board"]:
        add("Expansion slots", str(st["slots"]),
            f"on {st['boards']} boards, {st['slots_per_board']} each",
            "/browse?f=slots")
    if st["chips"]:
        add("Memory chips counted individually", str(int(st["chips"])),
            "soldered or socketed on a board", "/browse?f=chips")
    if st["drives"]:
        add("Drives fitted", str(int(st["drives"])),
            f"{st['gotek']} of them a Gotek" if st["gotek"]
            else "in the machines, counted individually", "/browse?f=drives")
    if st["working_pct"] is not None:
        add("Still working", f"{st['working_pct']}%",
            f"{st['working']} of {st['n_parts']} parts",
            "/browse?f=condition&v=Working")
    if st["oldest_year"] and st["newest_year"] > st["oldest_year"]:
        add("Oldest and newest", f"{st['oldest_year']}–{st['newest_year']}",
            f"{st['newest_year'] - st['oldest_year']} years apart",
            "/browse?f=extremes")
    if st["fullest"]:
        add("Best equipped machine", named(st["fullest"][0]),
            f"{st['fullest'][1]} parts fitted",
            f"/browse?f=in&v={st['fullest'][0].asset_id}")
    if st["oldest_held"]:
        add("Longest in the collection", named(st["oldest_held"]),
            f"since {st['oldest_held'].acquired_date}", "/browse?f=held")
    if st["fitted_per_machine"] is not None and st["fitted"]:
        add("Fitted in a machine", str(st["fitted"]),
            f"{st['fitted_per_machine']} per machine on average", "/browse?f=fitted")
    if st["spares"]:
        add("Spares on the shelf", str(st["spares"]), "waiting for a home",
            "/browse?f=spares")
    if st["disposed"]:
        # Counts the disposed, being the figure that is about them.
        add("No longer with us", str(st["disposed"]), "binned, sold or donated",
            "/browse?f=disposed")

    # --- and what it is like ------------------------------------------------

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
        for obj in _held(db.query(model).filter(model.year.isnot(None),
                                                model.acquired_date.isnot(None)),
                         model):
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
    # draft of this said 7189 MiB, of which 7000 was two memory cards.
    floppy_kb, floppy_n = 0, 0
    for size, count in _held(
            db.query(ComputerDrive.size, ComputerDrive.count)
            .join(Computer, Computer.asset_id == ComputerDrive.computer_id)
            .filter(ComputerDrive.size != "",
                    ComputerDrive.kind.in_(("floppy", "Gotek"))), Computer):
        kb = entry.to_kb(size)
        if kb:
            floppy_kb += kb * (count or 1)
            floppy_n += count or 1
    # Three drives is where adding them up starts being a joke rather than a sum;
    # below that "if all 2 drives had a disk in them" is just arithmetic.
    if floppy_kb and floppy_n >= 3:
        add("Every floppy at once", f"{round(floppy_kb / 1024)} {entry.MIB}",
            f"if all {floppy_n} drives had a disk in them",
            "/browse?f=drives")

    held_ids = {a for (a,) in _held(db.query(Computer.asset_id), Computer)} | {
        a for (a,) in _held(db.query(Part.asset_id), Part)}

    eventful = (db.query(LogEntry.asset_id, func.count(LogEntry.id))
                .filter(LogEntry.asset_id.in_(held_ids) if held_ids else False)
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

    # How many things have no portrait used to be a figure in here. It is on the
    # page in its own right now, above the tiles: a work queue that only appears on
    # some visits is not a work queue. It is not in the pool as well, because drawn
    # beside the standing line it would read as the shuffle repeating itself -- the
    # very fault the `seen` guard in gui_stats exists to prevent, and one that guard
    # cannot catch, since it compares tiles with each other and not with the rest of
    # the page. What is photographed is still spoken for here, twice.
    shots = st["portraits"]
    if shots:
        aid, n = max(shots.items(), key=lambda kv: (kv[1], kv[0]))
        obj = db.get(Computer, aid) or db.get(Part, aid)
        if obj and n > 1:
            kind = "computers" if isinstance(obj, Computer) else "parts"
            add("Most photographed", named(obj), f"{n} pictures of it",
                f"/{kind}/{obj.asset_id}")
    if shots and st["photos"] and len(held_ids):
        add("Photographs per thing", f"{st['photos'] / len(held_ids):.1f}",
            f"{st['photos']} pictures of {len(held_ids)} things", "/browse?f=photos")

    maker_counts = _held(db.query(Part.manufacturer, func.count(Part.asset_id))
                         .filter(Part.manufacturer.isnot(None),
                                 Part.manufacturer != ""), Part) \
        .group_by(Part.manufacturer).all()
    if maker_counts:
        add("Names on the parts", str(len(maker_counts)),
            "distinct makers in the register", "/browse?f=parts")
    singles = [m for m, n in maker_counts if n == 1]
    if len(singles) >= 3:
        add("Makers represented once", str(len(singles)),
            f"of {len(maker_counts)}, a single part each: "
            + ", ".join(sorted(singles)[:3]), "/browse?f=parts")

    # Counted in Python rather than grouped by YEAR(): the app runs on SQLite for
    # local development as well as on MariaDB, and that function is not portable.
    # At this size it is a few dozen dates either way.
    arrivals = Counter(d.year for (d,) in
                       _held(db.query(Part.acquired_date)
                             .filter(Part.acquired_date.isnot(None)), Part))
    if arrivals:
        year, n = max(arrivals.items(), key=lambda kv: (kv[1], kv[0]))
        if n > 1:
            add("Busiest year for buying", str(year), f"{n} parts arrived",
                "/browse?f=held")

    source = (_held(db.query(Part.source, func.count(Part.asset_id))
                    .filter(Part.source.isnot(None), Part.source != ""), Part)
              .group_by(Part.source)
              .order_by(func.count(Part.asset_id).desc()).first())
    if source and source[1] > 1:
        add("Where things come from", source[0], f"{source[1]} parts from there",
            f"/browse?f=source&v={quote(source[0])}")

    caps = [(kb, pid) for pid, kb in
            _held(db.query(StorageSpec.part_id, StorageSpec.capacity_kb)
                  .join(Part, Part.asset_id == StorageSpec.part_id)
                  .filter(StorageSpec.capacity_kb.isnot(None),
                          StorageSpec.capacity_kb > 0), Part)]
    if len(caps) >= 2:
        big, small = max(caps), min(caps)
        add("Biggest and smallest disk",
            f"{entry.fmt_kb(big[0], True)} / {entry.fmt_kb(small[0], True)}",
            f"a factor of {round(big[0] / small[0]):,} between them",
            "/browse?f=storage")

    chips = (_held(db.query(ComputerRamChip.computer_id,
                            func.sum(ComputerRamChip.count))
                   .join(Computer,
                         Computer.asset_id == ComputerRamChip.computer_id), Computer)
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
        for obj in _held(db.query(model), model):
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

    # --- what the drives are like -------------------------------------------
    # These read the typed storage columns, which is where the per-kind form now
    # files everything a drive is asked (see entry.STORAGE_ASKS).

    def storage_rank(column, kind=None):
        """(value, count) for one storage column, commonest first, held parts only."""
        q = _held(db.query(column, func.count(StorageSpec.part_id))
                  .join(Part, Part.asset_id == StorageSpec.part_id)
                  .filter(column.isnot(None), column != ""), Part)
        if kind:
            q = q.filter(StorageSpec.kind == kind)
        return sorted(q.group_by(column).all(), key=lambda r: (-r[1], r[0]))

    ifaces = storage_rank(StorageSpec.interface)
    if ifaces:
        total = sum(n for _i, n in ifaces)
        add("How a drive usually attaches", ifaces[0][0],
            f"{ifaces[0][1]} of {total} drives", "/browse?f=storage")
    if len(ifaces) >= 3:
        add("Ways of attaching a drive", str(len(ifaces)),
            "in use here: " + ", ".join(i for i, _n in ifaces[:4])
            + ("…" if len(ifaces) > 4 else ""), "/browse?f=storage")

    discs = storage_rank(StorageSpec.media, entry.OPTICAL_KIND)
    if discs and discs[0][1] > 1:
        add("The usual disc", discs[0][0], f"{discs[0][1]} optical drives take it",
            "/browse?f=storage")

    kinds = storage_rank(StorageSpec.kind)
    if len(kinds) >= 2:
        add("What the drives are", str(sum(n for _k, n in kinds)),
            ", ".join(f"{n} × {k}" for k, n in kinds),
            "/browse?f=storage")

    disk_caps = [kb for (kb,) in
                 _held(db.query(StorageSpec.capacity_kb)
                       .join(Part, Part.asset_id == StorageSpec.part_id)
                       .filter(StorageSpec.kind == entry.DISK_KIND,
                               StorageSpec.capacity_kb.isnot(None),
                               StorageSpec.capacity_kb > 0), Part)]
    if len(disk_caps) >= 2:
        add("Every hard disk added up", _big_total(sum(disk_caps)),
            f"across {len(disk_caps)} of them", "/browse?f=storage")

    # The 137 GiB wall, as reported by the drive: a disk bigger than 8.4 GiB has to
    # lie about its geometry, and 16383/16/63 is the lie they all tell.
    clamped = _held(db.query(func.count(StorageSpec.part_id))
                    .join(Part, Part.asset_id == StorageSpec.part_id)
                    .filter(StorageSpec.chs_c == 16383, StorageSpec.chs_h == 16,
                            StorageSpec.chs_s == 63), Part).scalar() or 0
    if clamped:
        add("Drives that lie about their shape", str(clamped),
            "reporting the ATA limit of 16383/16/63 rather than their real geometry",
            "/browse?f=storage")

    shades = storage_rank(StorageSpec.colour)
    if shades:
        add("The usual shade", shades[0][0],
            f"{shades[0][1]} of {sum(n for _s, n in shades)} bezels on file",
            "/browse?f=storage")
    yellowed = storage_rank(StorageSpec.yellowing)
    if yellowed:
        n = sum(n for _y, n in yellowed)
        add("Bezels gone yellow", str(n),
            f"most often {yellowed[0][0].lower()}", "/browse?f=storage")

    # --- and the shape of the whole thing -----------------------------------

    years = _all_years(db)
    if years:
        decades = Counter((y // 10) * 10 for y in years)
        decade, n = max(decades.items(), key=lambda kv: (kv[1], kv[0]))
        if len(decades) > 1:
            add("Best represented decade", f"{decade}s", f"{n} things made then",
                "/browse?f=year")

    for label, pick, blurb in (
            ("The oldest thing here", min, "the earliest year on anything"),
            ("The newest thing here", max, "the latest year on anything")):
        dated = []
        for model, kind in ((Computer, "computers"), (Part, "parts")):
            for obj in _held(db.query(model).filter(model.year.isnot(None)), model):
                dated.append((obj.year, kind, obj))
        if dated:
            year, kind, obj = pick(dated, key=lambda d: d[0])
            add(label, str(year), f"{named(obj)} — {blurb}",
                f"/{kind}/{obj.asset_id}")

    untested = _held(db.query(func.count(Part.asset_id))
                     .filter(Part.condition == "Untested"), Part).scalar() or 0
    if untested and st["n_parts"]:
        add("Never tested", str(untested),
            f"{round(100 * untested / st['n_parts'])}% of the parts, plugged into "
            "nothing yet", "/browse?f=condition&v=Untested")

    # The rest of the pool, by theme. Split out because one function of forty
    # figures had stopped being readable, not because these are a lesser sort of
    # figure: the page shuffles the whole pool together and does not know which
    # function a tile came from.
    out += _facts_boards(db, st)
    out += _facts_cards(db, st)
    out += _facts_drives(db, st)
    out += _facts_machines(db, st)
    out += _facts_ages(db, st, this_year)
    out += _facts_provenance(db, st)
    out += _facts_register(db, st)
    out += _facts_condition(db, st)
    return out
# --- the pointless department, by theme -------------------------------------
# The pool above grew out of one function, and past about forty figures that
# stopped being readable. What follows is the same thing in themed groups: each
# returns a list of figures and is skippable on its own, and each keeps the rules
# the pool has always had -- held items only (see _held), a figure omitted rather
# than shown empty, and quantities read from typed columns rather than parsed back
# out of text.
#
# A figure that is about the whole register rather than about any set of items
# passes no href. The tiles have always been links; a handful of them now are not,
# because "1327 entries in the register" leads nowhere the gallery can show, and a
# link to everything would be a link that lied about what it counted.

def _fact(k, v, s, href=None):
    """One figure for the pool, in the shape the template reads."""
    return {"k": k, "v": v, "s": s, "href": href}


def _named(obj):
    return entry.display_name(to_dict(obj))


def _spec_rank(db, model, column, *conds):
    """(value, count) for one text column of a spec table, commonest first.

    The join back to `parts` is not decoration: a spec row has no disposed flag of
    its own, so without it a binned board's chipset would still be a chipset the
    collection claims to hold."""
    q = (db.query(column, func.count(column))
         .join(Part, Part.asset_id == model.part_id)
         .filter(column.isnot(None), column != ""))
    for c in conds:
        q = q.filter(c)
    return sorted(_held(q, Part).group_by(column).all(), key=lambda r: (-r[1], r[0]))


def _spec_count(db, model, *conds):
    """How many held parts have a spec row matching."""
    q = db.query(func.count(model.part_id)).join(Part, Part.asset_id == model.part_id)
    for c in conds:
        q = q.filter(c)
    return _held(q, Part).scalar() or 0


def _commas(db, model, column):
    """A Counter over a text column that holds a comma-separated list.

    Video connectors are written 'VGA, EGA, Composite' -- one field, several
    answers -- so counting the column whole would file that card under a fourth
    kind of output rather than under the three it has. Ports and buses have proper
    child tables and are counted there; this is for the fields that do not."""
    out = Counter()
    for (v,) in _held(db.query(column).join(Part, Part.asset_id == model.part_id)
                      .filter(column.isnot(None), column != ""), Part):
        for one in (x.strip() for x in v.split(",")):
            if one:
                out[one] += 1
    return out


def _facts_boards(db, st):
    """Figures about motherboards: what shape they are, whose BIOS they answer to,
    and what can be plugged into them.

    The board is the part everything else in a machine hangs off, and it is the
    best represented category in the register, so it carries more of these than
    anything else does."""
    out = []
    shapes = _spec_rank(db, MotherboardSpec, MotherboardSpec.form_factor)
    if shapes:
        n_shaped = sum(n for _s, n in shapes)
        # "proprietary" -- the last of entry.MOBO_FORM_FACTORS -- is not a form
        # factor so much as the absence of one, and it is the commonest answer here.
        # Counted by prefix, so whatever was typed after the word lands in the same
        # pile; everything else counts as a named shape, including the spellings the
        # canonical list does not have ("Baby AT", "PC104"), because a shape someone
        # wrote down is still a shape.
        odd = sum(n for s, n in shapes if s.lower().startswith("proprietary"))
        if odd:
            out.append(_fact("Boards that fit nothing else", str(odd),
                             f"of {n_shaped} with a shape recorded, built to a plan "
                             "of their maker's own", "/browse?f=boards"))
        named_shapes = [(s, n) for s, n in shapes
                        if not s.lower().startswith("proprietary")]
        if named_shapes:
            out.append(_fact("The usual board shape", named_shapes[0][0],
                             f"{named_shapes[0][1]} boards, the commonest of the "
                             f"{len(named_shapes)} named shapes here",
                             f"/browse?f=formfactor&v={quote(named_shapes[0][0])}"))

    bios = _spec_rank(db, MotherboardSpec, MotherboardSpec.bios)
    if bios:
        out.append(_fact("Whose BIOS it usually is", bios[0][0],
                         f"{bios[0][1]} of the {sum(n for _b, n in bios)} boards that say",
                         f"/browse?f=bios&v={quote(bios[0][0])}"))

    fam = _spec_rank(db, MotherboardSpec, MotherboardSpec.cpu_family)
    if fam:
        out.append(_fact("The commonest class of board", fam[0][0],
                         f"{fam[0][1]} of the {sum(n for _f, n in fam)} that name one",
                         f"/browse?f=family&v={quote(fam[0][0])}"))

    chipsets = _spec_rank(db, MotherboardSpec, MotherboardSpec.chipset)
    if len(chipsets) >= 3:
        out.append(_fact("Chipsets named", str(len(chipsets)),
                         f"across {sum(n for _c, n in chipsets)} boards — hardly any "
                         "two of them agree", "/browse?f=boards"))

    cache = _held(db.query(func.sum(MotherboardSpec.cache_kb),
                           func.count(MotherboardSpec.part_id))
                  .join(Part, Part.asset_id == MotherboardSpec.part_id)
                  .filter(MotherboardSpec.cache_kb.isnot(None),
                          MotherboardSpec.cache_kb > 0), Part).first()
    if cache and cache[0]:
        out.append(_fact("Cache on the boards, added up",
                         entry.fmt_kb(int(cache[0]), True),
                         f"across the {cache[1]} boards that have any",
                         "/browse?f=cache"))

    onboard = _spec_count(db, MotherboardSpec,
                          MotherboardSpec.onboard_video.isnot(None),
                          MotherboardSpec.onboard_video != "")
    if onboard:
        out.append(_fact("Boards with the video already on them", str(onboard),
                         "no card required, which was once the remarkable part",
                         "/browse?f=onboardvideo"))

    boards = {a for (a,) in _held(db.query(MotherboardSpec.part_id)
                                  .join(Part, Part.asset_id == MotherboardSpec.part_id),
                                  Part)}
    slotted = {a for (a,) in db.query(PartSlot.part_id).distinct()}
    bare = boards - slotted
    if bare and boards:
        out.append(_fact("Boards with nowhere to expand", str(len(bare)),
                         f"of {len(boards)}: whatever they do, they do already",
                         "/browse?f=noslots"))

    per_board = sorted(_held(db.query(PartSlot.part_id, func.sum(PartSlot.count))
                             .join(Part, Part.asset_id == PartSlot.part_id), Part)
                       .group_by(PartSlot.part_id).all(), key=lambda r: -r[1])
    if per_board:
        top = int(per_board[0][1])
        tied = [p for p, n in per_board if int(n) == top]
        holder = db.get(Part, tied[0])
        out.append(_fact("Most slots on one board", str(top),
                         f"shared by {len(tied)} boards" if len(tied) > 1
                         else _named(holder),
                         "/browse?f=slots" if len(tied) > 1
                         else f"/parts/{holder.asset_id}"))

    # ISA outlasted its own replacements: a board here is likelier to have an ISA
    # slot than any other kind, forty years after the first one.
    isa = _held(db.query(func.sum(PartSlot.count))
                .join(Part, Part.asset_id == PartSlot.part_id)
                .filter(PartSlot.bus.like("%ISA%")), Part).scalar() or 0
    if isa and st["slots"]:
        out.append(_fact("Slots that are ISA", str(int(isa)),
                         f"of {st['slots']}, {round(100 * int(isa) / st['slots'])}% — "
                         "the bus that would not die", "/browse?f=slots"))

    sockets = sorted(_held(db.query(PartRamSlot.slot_type, func.sum(PartRamSlot.count))
                           .join(Part, Part.asset_id == PartRamSlot.part_id), Part)
                     .group_by(PartRamSlot.slot_type).all(),
                     key=lambda r: (-r[1], r[0]))
    if sockets:
        total = int(sum(n for _s, n in sockets))
        holders = _held(db.query(func.count(func.distinct(PartRamSlot.part_id)))
                        .join(Part, Part.asset_id == PartRamSlot.part_id),
                        Part).scalar() or 0
        out.append(_fact("Memory sockets", str(total),
                         f"on {holders} boards, filled or empty",
                         "/browse?f=ramslots"))
        out.append(_fact("The usual memory socket", sockets[0][0],
                         f"{int(sockets[0][1])} of {total} sockets",
                         f"/browse?f=ramslot&v={quote(sockets[0][0])}"))
        thirty = next((int(n) for s, n in sockets if s.startswith("30-pin")), 0)
        if thirty:
            out.append(_fact("30-pin SIMM sockets", str(thirty),
                             "filled four to a bank on a 32-bit board, two on a 286",
                             "/browse?f=ramslot&v=" + quote("30-pin SIMM")))
    return out


def _facts_cards(db, st):
    """Figures about the things that go in the slots: video, sound, network and I/O.

    These read the per-type spec tables, which is where the typed form files what a
    card is asked. The four tables share the shape of several columns -- `interface`
    for the bus, `chip` for the silicon -- so the questions that span all four are
    counted in one pass over them at the end, rather than four times over."""
    out = []

    # --- what a graphics card is ------------------------------------------
    outputs = _commas(db, VideoSpec, VideoSpec.connector)
    if outputs:
        best, n = outputs.most_common(1)[0]
        out.append(_fact("Video outputs counted", str(sum(outputs.values())),
                         f"most often {best}, on {n} cards",
                         "/browse?f=type&v=video"))
    multi = _spec_count(db, VideoSpec, VideoSpec.connector.like("%,%"))
    if multi:
        out.append(_fact("Cards that hedge their bets", str(multi),
                         "more than one kind of output on the same bracket",
                         "/browse?f=type&v=video"))
    # Cards whose outputs a VGA monitor will not take: MDA, CGA, EGA and composite
    # are all a different signal on a different plug, and a card with none of the
    # later ones is a card from before the standard that outlasted them.
    prevga = _spec_count(db, VideoSpec, VideoSpec.connector.isnot(None),
                         VideoSpec.connector != "",
                         ~VideoSpec.connector.like("%VGA%"),
                         ~VideoSpec.connector.like("%DVI%"))
    if prevga:
        out.append(_fact("Graphics cards from before VGA", str(prevga),
                         "nothing a VGA monitor would accept", "/browse?f=prevga"))

    chips = _spec_rank(db, VideoSpec, VideoSpec.chip)
    if len(chips) >= 3:
        out.append(_fact("Graphics chips named", str(len(chips)),
                         f"across {sum(n for _c, n in chips)} cards",
                         "/browse?f=type&v=video"))
        if chips[0][1] > 1:
            out.append(_fact("The commonest graphics chip", chips[0][0],
                             f"{chips[0][1]} cards carry it",
                             "/browse?f=type&v=video"))

    vram = [kb for (kb,) in
            _held(db.query(VideoSpec.memory_kb)
                  .join(Part, Part.asset_id == VideoSpec.part_id)
                  .filter(VideoSpec.memory_kb.isnot(None),
                          VideoSpec.memory_kb > 0), Part)]
    if vram:
        out.append(_fact("Video memory, everything added up",
                         entry.fmt_kb(sum(vram), True),
                         f"across the {len(vram)} cards that state any",
                         "/browse?f=vram"))
        # The commonest amount, not the total: the same question the register asks
        # of a machine's memory, and ties share the honour there for the same reason.
        sizes = Counter(vram)
        top = max(sizes.values())
        tied = sorted(kb for kb, n in sizes.items() if n == top)
        out.append(_fact("The usual amount of video memory",
                         " / ".join(entry.fmt_kb(kb, True) for kb in tied),
                         f"{top} cards" + (" each" if len(tied) > 1 else "")
                         + f", of {len(vram)} that state any",
                         "/browse?f=vramsize&v=" + ",".join(str(kb) for kb in tied)))
    if len(vram) >= 2 and max(vram) > min(vram):
        out.append(_fact("Biggest and smallest video memory",
                         f"{entry.fmt_kb(max(vram), True)} / "
                         f"{entry.fmt_kb(min(vram), True)}",
                         f"a factor of {round(max(vram) / min(vram)):,} between them",
                         "/browse?f=vram"))

    # --- and of the other three -------------------------------------------
    sound = _spec_rank(db, SoundSpec, SoundSpec.chip)
    if sound and sound[0][1] > 1:
        out.append(_fact("The commonest sound chip", sound[0][0],
                         f"{sound[0][1]} of the {sum(n for _c, n in sound)} cards "
                         "that name one", "/browse?f=type&v=sound"))
    nets = _spec_rank(db, NetworkSpec, NetworkSpec.interface)
    if len(nets) >= 2:
        out.append(_fact("Network cards, either side of the changeover",
                         f"{nets[0][1]} / {nets[1][1]}",
                         f"{nets[0][0]} against {nets[1][0]}",
                         "/browse?f=type&v=network"))

    # --- and what is true of all four -------------------------------------
    # One pass, four counters: how many cards there are at all, how many say which
    # bus, how many of those are ISA, and how many never had their chip written
    # down. Counted together because the figures below have to agree about how many
    # cards there are -- read as two tiles in one draw, 165 and 166 look like a bug.
    ISA_BUSES = ("8-bit ISA", "16-bit ISA", "ISA")
    n_cards = named_bus = on_isa = chip_blank = 0
    for model in (VideoSpec, SoundSpec, NetworkSpec, IoSpec):
        n_cards += _spec_count(db, model)
        named_bus += _spec_count(db, model, model.interface.isnot(None),
                                 model.interface != "")
        on_isa += _spec_count(db, model, model.interface.in_(ISA_BUSES))
        chip_blank += _spec_count(db, model, (model.chip.is_(None))
                                  | (model.chip == ""))

    # The whole changeover in one figure: a card here is still likelier to be ISA
    # than anything else, PCI having arrived late enough that most of this was
    # already on the shelf.
    if on_isa and named_bus:
        out.append(_fact("Cards that never left ISA", str(on_isa),
                         f"of {named_bus} with a bus recorded, "
                         f"{round(100 * on_isa / named_bus)}% of them",
                         "/browse?f=cards"))
    # Whose chip it is goes unrecorded far more often on a serial card than on a
    # graphics card, and the figure says which way round that is.
    if chip_blank and n_cards:
        out.append(_fact("Cards whose chip nobody has written down", str(chip_blank),
                         f"of {n_cards}: mostly the serial and network cards, where "
                         "nobody thinks to look", "/browse?f=nochip"))
    # Whimsy, and it says so: cards and slots are counted honestly and then set
    # against each other as though any card went in any slot, which no card does.
    # Only while there are slots to spare -- the other way round is a different
    # remark about a different collection, and this one would read as nonsense.
    if n_cards and st["slots"] and st["slots"] > n_cards:
        out.append(_fact("If every card were plugged in",
                         f"{st['slots'] - n_cards} slots",
                         f"would still be empty — {n_cards} cards against "
                         f"{st['slots']} slots, never mind which bus fits which",
                         "/browse?f=cards"))

    # --- ports, which are on the boards as well as on the cards -----------
    ports = _held(db.query(func.sum(PartPort.count),
                           func.count(func.distinct(PartPort.part_id)))
                  .join(Part, Part.asset_id == PartPort.part_id), Part).first()
    if ports and ports[0]:
        # The ranked list further down the page is capped, so this total is bigger
        # than its bars add up to. Said out loud -- but only when it is true, which
        # is why it is compared against that list rather than asserted about it.
        shown = sum(n for _p, n, _v in st["ports"])
        out.append(_fact("Ports counted", str(int(ports[0])),
                         f"on {ports[1]} boards and cards"
                         + (f" — the list below ranks only the commonest "
                            f"{len(st['ports'])}" if int(ports[0]) > shown else ""),
                         "/browse?f=ports"))
    per_carrier = sorted(_held(db.query(PartPort.part_id, func.sum(PartPort.count))
                               .join(Part, Part.asset_id == PartPort.part_id), Part)
                         .group_by(PartPort.part_id).all(), key=lambda r: -r[1])
    if per_carrier and int(per_carrier[0][1]) > 1:
        holder = db.get(Part, per_carrier[0][0])
        if holder:
            out.append(_fact("Most ports on one thing", str(int(per_carrier[0][1])),
                             _named(holder), f"/parts/{holder.asset_id}"))
    return out


def _facts_drives(db, st):
    """Figures about drives beyond the totals above: how they attach, how fast they
    turn, and what shape they claim to be."""
    out = []
    # Interfaces that were obsolete before most of this collection was made, and
    # are still represented in it. Named explicitly rather than inferred: what
    # makes MFM historic is not anything the database can work out.
    GONE = ("MFM", "RLL", "ESDI", "XTA")
    old = _spec_rank(db, StorageSpec, StorageSpec.interface,
                     StorageSpec.interface.in_(GONE))
    if old:
        out.append(_fact("Drives on an interface nobody uses",
                         str(sum(n for _i, n in old)),
                         ", ".join(i for i, _n in old) + " — all of them dead ends",
                         "/browse?f=legacydisk"))

    rpm = sorted(_held(db.query(StorageSpec.speed_rpm)
                       .join(Part, Part.asset_id == StorageSpec.part_id)
                       .filter(StorageSpec.speed_rpm.isnot(None),
                               StorageSpec.speed_rpm > 0), Part).all())
    if rpm:
        out.append(_fact("The fastest spindle here", f"{max(rpm)[0]:,} rpm",
                         f"of the {len(rpm)} drives that admit to a speed",
                         "/browse?f=rpm"))

    speeds = sorted(x for (x,) in
                    _held(db.query(StorageSpec.speed_x)
                          .join(Part, Part.asset_id == StorageSpec.part_id)
                          .filter(StorageSpec.speed_x.isnot(None),
                                  StorageSpec.speed_x > 0), Part))
    if len(speeds) >= 2 and speeds[-1] > speeds[0]:
        out.append(_fact("Fastest and slowest optical drive",
                         f"{speeds[-1]}× / {speeds[0]}×",
                         f"a factor of {round(speeds[-1] / speeds[0])} between them, "
                         "and about ten years", "/browse?f=optical"))

    # Whimsy, in the manner of every floppy at once: a real column, added up for no
    # reason anybody needs. Cylinders are the one part of CHS that varies enough to
    # be worth summing.
    geom = _held(db.query(func.count(StorageSpec.part_id), func.sum(StorageSpec.chs_c))
                 .join(Part, Part.asset_id == StorageSpec.part_id)
                 .filter(StorageSpec.chs_c.isnot(None), StorageSpec.chs_c > 0),
                 Part).first()
    if geom and geom[1]:
        out.append(_fact("Cylinders, added up", f"{int(geom[1]):,}",
                         f"across the {geom[0]} drives that state their geometry",
                         "/browse?f=geometry"))

    flash = _held(db.query(func.sum(ComputerDrive.count))
                  .join(Computer, Computer.asset_id == ComputerDrive.computer_id)
                  .filter(ComputerDrive.kind.in_(("CF", "SD"))), Computer).scalar()
    if flash:
        out.append(_fact("Flash standing in for a disk", str(int(flash)),
                         "cards in machines that were built before the format",
                         "/browse?f=flash"))
    return out


def _facts_machines(db, st):
    """Figures about the whole machines. There are far fewer of these than there are
    parts, so anything counted here is counted against a small number and says so."""
    out = []
    n = st["n_computers"]

    ram = Counter(kb for (kb,) in
                  _held(db.query(Computer.installed_ram_kb)
                        .filter(Computer.installed_ram_kb.isnot(None)), Computer))
    # 640 KiB is the line DOS drew and a great many machines stopped exactly on.
    if ram.get(640):
        out.append(_fact("The 640 KiB club", str(ram[640]),
                         "machines fitted with exactly as much as DOS could use",
                         "/browse?f=ram&v=640"))
    if len(ram) >= 2:
        least, most = min(ram), max(ram)
        out.append(_fact("The least memory in anything", entry.fmt_kb(least, True),
                         f"and the most is {entry.fmt_kb(most, True)}, "
                         f"a factor of {round(most / least):,}",
                         "/browse?f=ramfitted"))

    os_rank = sorted(_held(db.query(Computer.os, func.count(Computer.asset_id))
                           .filter(Computer.os.isnot(None), Computer.os != ""),
                           Computer).group_by(Computer.os).all(),
                     key=lambda r: (-r[1], r[0]))
    if os_rank and n:
        out.append(_fact("Machines with an operating system on them",
                         str(sum(x for _o, x in os_rank)),
                         f"of {n}; the rest are bare metal as they stand",
                         "/browse?f=os"))
    dos = _held(db.query(func.count(Computer.asset_id))
                .filter(Computer.os.like("%DOS%")), Computer).scalar() or 0
    if dos:
        out.append(_fact("Machines running DOS of some sort", str(dos),
                         "MS-DOS, FreeDOS or the like, as recorded",
                         "/browse?f=dos"))

    cpus = sorted(_held(db.query(Computer.cpu, func.count(Computer.asset_id))
                        .filter(Computer.cpu.isnot(None), Computer.cpu != ""),
                        Computer).group_by(Computer.cpu).all(),
                  key=lambda r: (-r[1], r[0]))
    if cpus and cpus[0][1] > 1:
        out.append(_fact("The commonest processor", cpus[0][0],
                         f"{cpus[0][1]} of the {sum(x for _c, x in cpus)} machines "
                         "that name one", "/browse?f=cpu"))

    chassis = sorted(_held(db.query(Computer.chassis, func.count(Computer.asset_id))
                           .filter(Computer.chassis.isnot(None),
                                   Computer.chassis != ""), Computer)
                     .group_by(Computer.chassis).all(),
                     key=lambda r: (-r[1], r[0]))
    if chassis:
        out.append(_fact("What shape the machines are", chassis[0][0],
                         f"{chassis[0][1]} of {sum(x for _c, x in chassis)}, and "
                         f"{len(chassis) - 1} other shapes besides",
                         f"/browse?f=chassis&v={quote(chassis[0][0])}"))
    # Portable in the sense the word had at the time, which is to say heavy.
    portable = sum(x for c, x in chassis if c.lower() in ("laptop", "luggable"))
    if portable:
        out.append(_fact("Portable, in the period sense", str(portable),
                         "laptops and luggables, the latter being portable only in "
                         "that it had a handle", "/browse?f=portable"))

    known = db.query(func.count(func.distinct(AssetVariant.asset_id))).scalar() or 0
    if known and n:
        out.append(_fact("Machines the catalogue knows", str(known),
                         f"of {n} filed as a model it can name",
                         "/browse?f=variant"))

    fitted_in = {c for (c,) in _held(db.query(Part.computer_id)
                                     .filter(Part.computer_id.isnot(None)), Part)}
    all_machines = {a for (a,) in _held(db.query(Computer.asset_id), Computer)}
    empty = all_machines - fitted_in
    if empty and all_machines:
        out.append(_fact("Machines with nothing in them", str(len(empty)),
                         f"of {len(all_machines)}: nothing tagged is fitted to them",
                         "/browse?f=emptymachines"))

    bench = _held(db.query(func.count(Computer.asset_id))
                  .filter(Computer.topbench.isnot(None)), Computer).scalar() or 0
    if bench and n:
        out.append(_fact("Machines actually benchmarked", str(bench),
                         f"of {n}: TopBench has to be run, and mostly has not been",
                         "/browse?f=benchmarked"))
    return out


def _facts_ages(db, st, this_year):
    """Figures about when all this was made, and about the gaps between the dates on
    things that ended up in the same box."""
    out = []
    years = _all_years(db)
    if years:
        span = max(years) - min(years) + 1
        if span > len(set(years)):
            out.append(_fact("Years represented", str(len(set(years))),
                             f"of the {span} the collection spans — "
                             f"{span - len(set(years))} with nothing made in them",
                             "/browse?f=year"))
        modern = sum(1 for y in years if y >= 2000)
        if modern:
            out.append(_fact("Made this century", str(modern),
                             f"of the {len(years)} things with a year on them",
                             "/browse?f=century"))
        recent = sum(1 for y in years if y >= this_year - 10)
        if recent:
            out.append(_fact("Made in the last ten years", str(recent),
                             "new parts for old machines, still being made",
                             "/browse?f=recent"))

    machine_years = [y for (y,) in _held(db.query(Computer.year)
                                         .filter(Computer.year.isnot(None)),
                                         Computer)]
    part_years = [y for (y,) in _held(db.query(Part.year)
                                      .filter(Part.year.isnot(None)), Part)]
    if machine_years and part_years:
        mm, mp = round(sum(machine_years) / len(machine_years)), \
            round(sum(part_years) / len(part_years))
        if mm != mp:
            older = "machines" if mm < mp else "parts"
            out.append(_fact(f"The {older} are the older half", f"{mm} / {mp}",
                             "average year of a machine against a part",
                             "/browse?f=year"))

    # Machines as well as parts: "thing" means both everywhere else on this page,
    # and a working machine of 1981 would be a strange one to leave out of a figure
    # about the oldest thing that still works.
    working = []
    for model, kind in ((Computer, "computers"), (Part, "parts")):
        oldest = _held(db.query(model).filter(model.year.isnot(None),
                                              model.condition == "Working"),
                       model).order_by(model.year).first()
        if oldest:
            working.append((oldest.year, oldest, kind))
    if working:
        year, obj, kind = min(working, key=lambda w: w[0])
        out.append(_fact("The oldest thing that still works", str(year),
                         _named(obj), f"/{kind}/{obj.asset_id}"))

    # The gap between a part's year and its machine's. Both dates in one row,
    # because the figure is the difference and a difference needs both ends.
    pairs = _held(db.query(Part, Computer)
                  .join(Computer, Computer.asset_id == Part.computer_id)
                  .filter(Part.year.isnot(None), Computer.year.isnot(None),
                          Computer.disposed.is_(False)), Part).all()
    if pairs:
        ahead = [(p.year - c.year, p, c) for p, c in pairs if p.year > c.year]
        if ahead:
            gap, p, c = max(ahead, key=lambda r: r[0])
            out.append(_fact("The biggest anachronism", f"{gap} years",
                             f"{_named(p)} of {p.year}, fitted to a machine from "
                             f"{c.year}", f"/computers/{c.asset_id}"))
        together = sum(1 for p, c in pairs if p.year == c.year)
        if together:
            out.append(_fact("Parts as old as their machine", str(together),
                             f"of {len(pairs)} where both dates are known, made the "
                             "same year as the thing they are in",
                             "/browse?f=born"))
        before = sum(1 for p, c in pairs if p.year < c.year)
        if before:
            out.append(_fact("Parts older than their machine", str(before),
                             "already out of date the day they were fitted",
                             "/browse?f=older"))
    return out


def _facts_provenance(db, st):
    """Where things came from and when they turned up. Provenance is the field
    least often filled in, and the figure about how often is one of the more
    honest ones here."""
    out = []
    nowhere = _held(db.query(func.count(Part.asset_id))
                    .filter((Part.source == "") | (Part.source.is_(None))),
                    Part).scalar() or 0
    if nowhere and st["n_parts"]:
        out.append(_fact("Parts with no idea where they came from", str(nowhere),
                         f"{round(100 * nowhere / st['n_parts'])}% of them: no source "
                         "recorded at all", "/browse?f=nosource"))
    # Two conventions of this register's source field rather than anything the
    # schema knows: an order number is written "eBay order no. ...", and something
    # built here is "Self-made". Both figures simply stand down on a register that
    # writes provenance some other way, which is what every figure here does.
    bought = _held(db.query(func.count(Part.asset_id))
                   .filter(Part.source.like("eBay%")), Part).scalar() or 0
    if bought:
        out.append(_fact("Bought from strangers", str(bought),
                         "traced to an eBay order number",
                         "/browse?f=sourcelike&v=eBay"))
    made = _held(db.query(func.count(Part.asset_id))
                 .filter(Part.source.like("Self-made%")), Part).scalar() or 0
    if made:
        out.append(_fact("Made here rather than bought", str(made),
                         "built on the bench it sits on",
                         "/browse?f=sourcelike&v=Self-made"))

    arrivals = [d for (d,) in _held(db.query(Part.acquired_date)
                                    .filter(Part.acquired_date.isnot(None)), Part)]
    if arrivals and st["n_parts"]:
        out.append(_fact("Parts with an arrival date", str(len(arrivals)),
                         f"of {st['n_parts']}; the rest were simply there one day",
                         "/browse?f=held"))
        # Ties share the honour, as they do for the usual amount of memory: two days
        # with nine arrivals each are both the day things arrive.
        days = Counter(d.strftime("%A") for d in arrivals)
        top = max(days.values())
        winners = sorted(d for d, x in days.items() if x == top)
        if len(winners) == 1:
            out.append(_fact(f"Things arrive on a {winners[0]}", str(top),
                             "more of them than on any other day", "/browse?f=held"))
        else:
            out.append(_fact("The day things arrive", " / ".join(winners),
                             f"tied on {top} arrivals each", "/browse?f=held"))
        busiest, count = Counter(arrivals).most_common(1)[0]
        if count > 1:
            out.append(_fact("The busiest single day", str(count),
                             f"parts all dated {busiest}", "/browse?f=held"))
    return out


def _facts_register(db, st):
    """Figures about the register rather than about the hardware: how much has been
    written down, how much has been photographed, and how new all the writing is.

    These are the figures with no gallery view behind them -- an entry in a
    history is not an item -- so the first few pass no link at all.

    The entry counts are also the one place _held does not apply: they count what
    has been written, and a note about something since disposed was still written.
    The figures about parts below are about the collection again, and do."""
    out = []
    entries = db.query(func.count(LogEntry.id)).scalar() or 0
    started = db.query(func.min(LogEntry.created_at)).scalar()
    if entries and started:
        days = max((date.today() - started.date()).days, 1)
        out.append(_fact("The register is younger than everything in it",
                         f"{days} days",
                         f"{entries:,} entries written since {started.date()}"))
    kinds = dict(db.query(LogEntry.kind, func.count(LogEntry.id))
                 .group_by(LogEntry.kind).all())
    if kinds.get("note"):
        out.append(_fact("Notes written by hand", str(kinds["note"]),
                         f"of {entries:,} entries; the rest are the database "
                         "recording its own changes"))
    longest_note = (db.query(LogEntry.asset_id, func.length(LogEntry.message))
                    .filter(LogEntry.kind == "note")
                    .order_by(func.length(LogEntry.message).desc()).first())
    if longest_note and longest_note[1] and longest_note[0]:
        obj = db.get(Computer, longest_note[0]) or db.get(Part, longest_note[0])
        if obj:
            kind = "computers" if isinstance(obj, Computer) else "parts"
            out.append(_fact("The longest note anyone has written",
                             f"{longest_note[1]} characters", _named(obj),
                             f"/{kind}/{obj.asset_id}"))

    shots = st["portraits"]
    if shots:
        once = sum(1 for x in shots.values() if x == 1)
        if once:
            out.append(_fact("Things photographed exactly once", str(once),
                             f"of {len(shots)} photographed at all: one angle and no "
                             "more", "/browse?f=photos"))
        many = sum(1 for x in shots.values() if x >= 5)
        if many:
            out.append(_fact("Things photographed five times or more", str(many),
                             "properly documented, as opposed to merely recorded",
                             "/browse?f=photos"))

    unwritten = _held(db.query(func.count(Part.asset_id))
                      .filter(Part.summary == "", Part.notes == ""), Part).scalar() or 0
    if unwritten and st["n_parts"]:
        out.append(_fact("Parts nobody has written a word about", str(unwritten),
                         f"{round(100 * unwritten / st['n_parts'])}% of them: no "
                         "summary and no notes", "/browse?f=unwritten"))
    linked = _held(db.query(func.count(Part.asset_id))
                   .filter(Part.url != "", Part.url.isnot(None)), Part).scalar() or 0
    if linked:
        out.append(_fact("Parts with a link out", str(linked),
                         "somebody else's page about the same thing",
                         "/browse?f=links"))
    images = _held(db.query(func.count(Part.asset_id))
                   .filter(Part.disk_image != "", Part.disk_image.isnot(None)),
                   Part).scalar() or 0
    if images:
        out.append(_fact("Disk images kept", str(images),
                         "the contents as well as the object",
                         "/browse?f=diskimages"))
    nested = _held(db.query(func.count(Part.asset_id))
                   .filter(Part.parent_id.isnot(None)), Part).scalar() or 0
    if nested:
        out.append(_fact("Parts fitted to another part", str(nested),
                         "a riser, a daughterboard, or a chip on a carrier",
                         "/browse?f=subparts"))

    dupes = sorted(_held(db.query(Part.manufacturer, Part.model,
                                  func.count(Part.asset_id))
                         .filter(Part.model != "", Part.model.isnot(None)), Part)
                   .group_by(Part.manufacturer, Part.model).all(),
                   key=lambda r: -r[2])
    repeated = [r for r in dupes if r[2] > 1]
    if repeated:
        out.append(_fact("Things there is more than one of", str(len(repeated)),
                         f"models held twice or more, of {len(dupes)} in the register",
                         "/browse?f=dupes"))
        top = repeated[0][2]
        tied = sorted(f"{r[0]} {r[1]}".strip() for r in repeated if r[2] == top)
        if len(tied) == 1:
            said = tied[0]
        elif len(tied) == 2:
            said = f"{tied[0]} and {tied[1]}, tied"
        else:
            said = f"{tied[0]} and {len(tied) - 1} others, tied"
        out.append(_fact("The most duplicated thing here", str(top), said,
                         "/browse?f=dupes"))

    # The other end of the longest name, which is counted the same way in the pool
    # above. A second walk over every held object rather than one walk answering
    # both, because at this size it costs nothing and the two figures belong to
    # different groups.
    names = []
    for model in (Computer, Part):
        for obj in _held(db.query(model), model):
            names.append((len(_named(obj)), obj,
                          "computers" if model is Computer else "parts"))
    short = min(names, key=lambda n: n[0], default=None)
    if short and short[0] > 1:
        out.append(_fact("Shortest name in the register", f"{short[0]} characters",
                         _named(short[1]), f"/{short[2]}/{short[1].asset_id}"))
    return out


def _facts_condition(db, st):
    """Figures about what state it is all in, beyond the working share on the page
    above and the two reliability tables below it."""
    out = []
    rel = _maker_reliability(db)
    perfect = [r for r in rel if r[3] == 100]
    if perfect and len(rel) > len(perfect):
        out.append(_fact("Makers with a clean sheet", str(len(perfect)),
                         f"of {len(rel)} with {RELIABILITY_MIN}+ parts here, every "
                         "one of them working"))

    # Four of the six values in entry.CONDITIONS, each with a sentence of its own,
    # because each says something the working share does not: what was kept anyway,
    # and what was worked on. Working and Untested already have figures above.
    for label, key, blurb in (
            ("Broken and kept anyway", "Faulty",
             "known bad and still on the shelf"),
            ("Works, but not all of it", "Partially working",
             "the most honest category there is"),
            ("Brought back", "Restored",
             "working, but it did not arrive that way"),
            ("Good only for parts", "For parts/repair",
             "kept for what can be taken off it")):
        n = _held(db.query(func.count(Part.asset_id))
                  .filter(Part.condition == key), Part).scalar() or 0
        if n:
            out.append(_fact(label, str(n), blurb,
                             f"/browse?f=condition&v={quote(key)}"))

    spare_types = sorted(_held(db.query(Part.type, func.count(Part.asset_id))
                               .filter(Part.computer_id.is_(None)), Part)
                         .group_by(Part.type).all(), key=lambda r: (-r[1], r[0]))
    if spare_types and st["spares"]:
        out.append(_fact("The commonest thing to have spare",
                         entry.type_label(spare_types[0][0]),
                         f"{spare_types[0][1]} of {st['spares']} on the shelf",
                         f"/browse?f=sparetype&v={quote(spare_types[0][0])}"))
    return out


def _collection_stats(db):
    """Figures about the collection for the public /stats page. Everything here is
    counted from the typed columns and child tables rather than parsed out of
    strings, which is the whole point of their being typed.

    The ranked lists carry three fields per row -- label, count, and the value to
    query on -- so that a bar on the page can link to the items behind it. Usually
    the label is the value; for part types the label is prettified and the raw type
    key is what /browse needs."""
    n_computers = _held(db.query(func.count(Computer.asset_id)), Computer).scalar() or 0
    n_parts = _held(db.query(func.count(Part.asset_id)), Part).scalar() or 0

    def ranked(query, limit=None):
        rows = [(k, n, k) for k, n in query if (k or "").strip()]
        rows.sort(key=lambda r: (-r[1], r[0]))
        return rows[:limit] if limit else rows

    makers = ranked(_held(db.query(Part.manufacturer, func.count(Part.asset_id)), Part)
                    .group_by(Part.manufacturer), 8)
    types = ranked(_held(db.query(Part.type, func.count(Part.asset_id)), Part)
                   .group_by(Part.type))
    # The child tables have no disposed flag of their own, so these join back to the
    # part that owns the row: a binned board's slots are not slots the collection has.
    buses = ranked(_held(db.query(PartSlot.bus, func.sum(PartSlot.count))
                         .join(Part, Part.asset_id == PartSlot.part_id), Part)
                   .group_by(PartSlot.bus), 6)
    ports = ranked(_held(db.query(PartPort.port, func.sum(PartPort.count))
                         .join(Part, Part.asset_id == PartPort.part_id), Part)
                   .group_by(PartPort.port), 6)
    conditions = ranked(_held(db.query(Part.condition, func.count(Part.asset_id)), Part)
                        .group_by(Part.condition))

    years = _all_years(db)
    ram = [kb for (kb,) in _held(db.query(Computer.installed_ram_kb)
                                 .filter(Computer.installed_ram_kb.isnot(None)),
                                 Computer)]
    common_ram = sorted(((entry.fmt_kb(kb), ram.count(kb), kb) for kb in set(ram)),
                        key=lambda r: (-r[1], r[0]))
    # Ties share the honour: two sizes fitted to three machines each are both "the
    # usual amount". Sorted by count, so the ties are the rows at the front.
    top_ram = [r for r in common_ram if r[1] == common_ram[0][1]][:3] if common_ram else []

    fitted_kb = sum(ram)
    stored_kb = _held(db.query(func.sum(StorageSpec.capacity_kb))
                      .join(Part, Part.asset_id == StorageSpec.part_id),
                      Part).scalar() or 0
    slots = _held(db.query(func.sum(PartSlot.count))
                  .join(Part, Part.asset_id == PartSlot.part_id), Part).scalar() or 0
    boards = _held(db.query(func.count(func.distinct(PartSlot.part_id)))
                   .join(Part, Part.asset_id == PartSlot.part_id), Part).scalar() or 0
    chips = _held(db.query(func.sum(ComputerRamChip.count))
                  .join(Computer, Computer.asset_id == ComputerRamChip.computer_id),
                  Computer).scalar() or 0
    drives = _held(db.query(func.sum(ComputerDrive.count))
                   .join(Computer, Computer.asset_id == ComputerDrive.computer_id),
                   Computer).scalar() or 0
    gotek = _held(db.query(func.count(ComputerDrive.id))
                  .join(Computer, Computer.asset_id == ComputerDrive.computer_id)
                  .filter(ComputerDrive.kind == "Gotek"), Computer).scalar() or 0
    working = _held(db.query(func.count(Part.asset_id))
                    .filter(Part.condition == "Working"), Part).scalar() or 0
    # The one figure that is about the disposed, so the only one that counts them.
    disposed = ((db.query(func.count(Part.asset_id)).filter(Part.disposed).scalar() or 0)
                + (db.query(func.count(Computer.asset_id))
                   .filter(Computer.disposed).scalar() or 0))

    fullest = (_held(db.query(Part.computer_id, func.count(Part.asset_id))
                     .filter(Part.computer_id.isnot(None)), Part)
               .group_by(Part.computer_id)
               .order_by(func.count(Part.asset_id).desc()).first())
    fullest_machine = db.get(Computer, fullest[0]) if fullest else None
    if fullest_machine and fullest_machine.disposed:
        fullest, fullest_machine = None, None

    oldest_held = _held(db.query(Part).filter(Part.acquired_date.isnot(None)),
                        Part).order_by(Part.acquired_date).first()
    photos = sum(len(folder_images(k)) for k in ("computers", "parts"))
    # Portrait coverage: the one figure on the page that is a job rather than a
    # curiosity, so the page shows it every visit rather than dealing it into the
    # shuffle. Both halves come from here -- the standing line and the pool's
    # figures about photographs -- so the page cannot disagree with itself about
    # what a photograph is.
    portraits, unphotographed = _portraits(db)
    # A share that rounds to nothing is still one thing nobody has photographed, and
    # "0% of the register, waiting for a camera" beside a count of 1 reads as a bug
    # rather than as a nearly-finished job.
    share = 100 * len(unphotographed) / ((n_computers + n_parts) or 1)
    # Most parts are spares on a shelf, so "parts per machine" over the whole
    # register would say 19 and mean nothing. Only the fitted ones divide.
    fitted = _held(db.query(func.count(Part.asset_id))
                   .filter(Part.computer_id.isnot(None)), Part).scalar() or 0

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
        "portraits": portraits, "unphotographed": len(unphotographed),
        "unphotographed_pct": "under 1" if 0 < share < 0.5 else str(round(share)),
        "fullest": (fullest_machine, fullest[1]) if fullest_machine else None,
        "oldest_held": oldest_held,
        "fitted": fitted, "spares": n_parts - fitted,
        # Guarded because an empty register is a real state -- a fresh install --
        # and a stats page that divides by zero on day one is no use to anyone.
        "fitted_per_machine": (round(fitted / n_computers, 1) if n_computers else None),
        "working_pct": (round(100 * working / n_parts) if n_parts else None),
        "slots_per_board": (round(slots / boards, 1) if boards else None),
    }


# How many figures a visit gets. Eight fills two rows on a wide screen, and with the
# whole pool shuffled rather than half of it there is no fixed half left for them to
# be a preamble to.
FACTS_SHOWN = 8


@app.get("/stats", response_class=HTMLResponse, include_in_schema=False)
def gui_stats(request: Request, db: Session = Depends(get_db)):
    this_year = date.today().year
    st = _collection_stats(db)
    # A different handful each time the page is looked at. The pool is only the
    # figures that have something to say today, so the draw is never padded with
    # blanks.
    #
    # Shuffled and then taken one at a time, skipping any figure whose headline a
    # tile in this draw already shows: the storage total and the hard disks that are
    # very nearly all of it both read "2464.1 GiB" here, and two tiles showing one
    # number looks like the shuffle is broken rather than like two facts. Same reason
    # "arrived this year" stands down when this year is also the busiest.
    pool = _facts(db, st, this_year)
    drawn, seen = [], set()
    for fact in random.sample(pool, len(pool)):
        if fact["v"] in seen:
            continue
        seen.add(fact["v"])
        drawn.append(fact)
        if len(drawn) == FACTS_SHOWN:
            break
    st["facts"] = drawn
    st["n_facts"] = len(pool)
    rel = _maker_reliability(db)
    # Shaped for the rank macro here rather than in the template: (label, bar, the
    # value /browse needs). The macro takes rows, not a data model.
    st["reliability_rank"] = [(maker, pct, maker) for maker, _n, _w, pct in rel]
    st["reliability_min"] = RELIABILITY_MIN
    # The description a crawler or a chat window sees is the collection, not
    # whichever eight figures this particular render drew.
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
        # /login is deliberately not here. It answers with a noindex meta tag, and
        # a crawler has to be let in to be told to stay out: disallowed, it was kept
        # out of sight rather than out of the index, and Search Console filed it
        # under "blocked by robots.txt" every time a link to it was followed. /logout
        # keeps its line -- it is POST-only, so a crawler has nothing to fetch there.
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
    urls = [(f"{base}/", None), (f"{base}/stats", None),
            (f"{base}/machines", None)]
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


class _CachedStatic(StaticFiles):
    """The static files, with a Cache-Control on them.

    StaticFiles sends an ETag and a Last-Modified and no Cache-Control at all,
    which means the browser asks about every one of them on every page: ten
    conditional requests for the logo, the icons and the placeholder drawings,
    each answered 304 Not Modified, each a round trip. On a phone on a slow link
    that is most of what a second page view costs.

    Every one of them is linked with ?v=<hash of the file>, so the URL already
    says which version it wants and cannot go stale -- change the file and the
    markup asks for a different URL. Those may be kept for a year and never asked
    about again. A request without the stamp is somebody typing the path, and
    keeps a short life so it cannot pin an old copy in a cache for a year.
    """

    def file_response(self, full_path, stat_result, scope, status_code=200):
        response = super().file_response(full_path, stat_result, scope, status_code)
        query = parse_qs(scope.get("query_string", b"").decode("latin-1"))
        response.headers["Cache-Control"] = (
            "public, max-age=31536000, immutable" if query.get("v")
            else "public, max-age=3600")
        return response


for sub in ("computers", "parts"):
    (IMAGES_DIR / sub).mkdir(parents=True, exist_ok=True)
app.mount("/static", _CachedStatic(directory=str(STATIC_DIR)), name="static")

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
# every photo cached before it was is missing. 3: every copy made before photographs
# were written atomically may have been composited from a fragment of one -- a
# photograph half-written by a crop happening at that moment -- and a fragment
# decodes to a picture that is half grey rather than to an error. Nothing can tell
# those copies from the good ones by looking at them, so they all go.
WM_BUILD = 3

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

# The resized copies keep their own cache beside it, swept the same way.
thumbs.sweep(IMAGES_DIR)


def _write_atomically(dst: Path, write):
    """Write an image file by way of a temporary one beside it, then move it into
    place. `write` is handed the temporary path.

    Every image here is read while something else is writing it: a photograph is
    served to one browser while another crops it, and both caches are built from
    whatever the file says at the moment they look at it. Saving straight onto the
    path truncates it first, so for as long as the encoder is running -- a tenth of
    a second for a phone photograph, and longer for a big one -- what is on disk is
    a fragment of a JPEG. A reader that arrives in that window does not get an
    error it can retry: it gets a fragment, and a fragment decodes to a picture
    that is half grey. Served under a `?v=` URL, which is `immutable` for a year,
    that half-grey picture is then kept by the browser and never asked for again.

    os.replace is atomic on POSIX: a reader holds either the whole old file or the
    whole new one and never half of either, and one that opened the old file keeps
    reading it safely after the swap. thumbs._make has done this since it was
    written; this is the same rule for the three paths that had not learned it.
    """
    dst.parent.mkdir(parents=True, exist_ok=True)
    # Not a .jpeg/.png: folder_images picks photographs out of the directory by
    # extension, so a half-written one must not look like a photograph to it.
    tmp = dst.with_name(dst.name + ".part")
    try:
        write(tmp)
        os.replace(tmp, dst)
    except BaseException:
        with contextlib.suppress(OSError):
            tmp.unlink(missing_ok=True)
        raise


def _image_format(path: Path, opened=None) -> str:
    """The format to encode as. Taken from the file that was opened where there is
    one, and from the extension otherwise -- it cannot be left to Pillow to infer,
    because what it would infer it from is the temporary name ending in .part."""
    from PIL import Image
    return (opened.format if opened is not None and opened.format
            else Image.registered_extensions().get(path.suffix.lower(), "JPEG"))


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
    if dst_path.suffix.lower() in (".jpg", ".jpeg"):
        rgb = out.convert("RGB")
        _write_atomically(dst_path,
                          lambda tmp: rgb.save(tmp, "JPEG", quality=88))
    else:
        fmt = _image_format(dst_path)
        _write_atomically(dst_path, lambda tmp: out.save(tmp, fmt))


def _watermarked_file(rel: str) -> Path:
    """Path to the cached watermarked copy of an image, regenerated if stale.
    Falls back to the original on any compositing error."""
    src = IMAGES_DIR / rel
    dst = WM_CACHE / rel
    try:
        # Read once, before the copy is made, and stamped onto the copy after: what
        # this says is "made from the photograph as it stood at that moment". Taking
        # the clock instead would date a copy later than a photograph that had been
        # replaced while it was being made, and that copy -- of the picture before
        # the crop -- would then look fresh forever.
        stamp = src.stat().st_mtime
        if not dst.exists() or dst.stat().st_mtime < stamp:
            _make_watermark(src, dst)
            with contextlib.suppress(OSError):
                os.utime(dst, (stamp, stamp))
        return dst
    except Exception:
        return src


def _wm_forget(rel: str):
    """Drop an image's cached watermark and its resized copies (on delete, rename or
    edit) so they regenerate.

    A copy is rebuilt anyway once it is older than what it was made from, which is
    what covers an edit. This is for the case that check cannot see: a photograph
    that is gone, whose copies would otherwise sit on the disk forever.
    """
    with contextlib.suppress(OSError):
        (WM_CACHE / rel).unlink(missing_ok=True)
    thumbs.forget(IMAGES_DIR, rel)


def _is_own_photo(rel: str) -> bool:
    # A photograph on a history entry is marked like any other: it is this
    # collection's own photograph of its own machine, taken by whoever did the
    # work, and the mark is there for where a photograph goes rather than for
    # which page of the site it was shown on.
    ext = Path(rel).suffix.lower()
    return (WATERMARK and ext in IMAGE_EXTS
            and (rel.startswith(("computers/", "parts/", LOG_KIND + "/")))
            and not is_reference(rel))


def _image_cache(versioned: bool) -> dict:
    """How long the browser may keep an image.

    A URL carrying ?v= names which version of the photograph it wants -- img_url
    stamps it from the file's mtime -- so that URL can never go stale and may be
    kept for as long as the browser likes. Editing the photograph changes the stamp
    and therefore the URL, which is the whole point of having one. A URL without a
    stamp could mean anything later, so it gets the hour it always had.
    """
    return {"Cache-Control": "public, max-age=31536000, immutable" if versioned
            else "public, max-age=3600"}


@app.get("/images/{path:path}", include_in_schema=False)
def serve_image(path: str, v: str = "", w: int = 0):
    # Reject traversal, dotfiles/dotdirs (e.g. the .wm and .sized caches) and
    # non-images.
    if any(seg.startswith(".") for seg in path.split("/")):
        raise HTTPException(404)
    full = (IMAGES_DIR / path).resolve()
    if not str(full).startswith(str(IMAGES_DIR.resolve()) + os.sep) or not full.is_file():
        raise HTTPException(404)
    if full.suffix.lower() not in IMAGE_EXTS:
        raise HTTPException(404)
    served = _watermarked_file(path) if _is_own_photo(path) else full
    # ?w= asks for a copy no wider than that, made and kept on first request. Only
    # the widths the templates use are made; anything else is served whole rather
    # than refused, because a photograph is never the wrong answer to a request for
    # a photograph.
    if w:
        served = thumbs.served_path(IMAGES_DIR, path, w, served)
    # A copy can still go between being chosen and being opened -- deleting a
    # photograph takes its copies with it. The original is the same picture and is
    # still here; a slower answer beats a broken one.
    if not served.exists():
        served = full
    return FileResponse(served, headers=_image_cache(bool(v)))


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
    """Record a dated history entry for an asset, and hand the row back for
    anything that wants to hang photographs on it. The caller commits.

    An empty message writes nothing and returns None: there is no such thing as an
    entry that does not say anything, and a caller with photographs and no words to
    file them under has nothing to file them against.
    """
    if not message:
        return None
    db.add(row := LogEntry(asset_id=asset_id, created_at=_now(),
                           kind=kind, message=message))
    return row


def item_log(db, asset_id):
    return (db.query(LogEntry).filter(LogEntry.asset_id == asset_id)
            .order_by(LogEntry.created_at.desc(), LogEntry.id.desc()).all())


# How far apart two of the same thing can be and still be one sitting. Long enough
# to cover picking the next photo out of a folder, short enough that coming back to
# the same machine after tea is a separate line.
FOLD_WINDOW = timedelta(minutes=5)

# "deleted a photo" ten times over is "deleted 10 photos", which is the sentence a
# person would have written. Where a message does not name a single thing that way,
# the count is appended instead rather than guessed at.
_ONE_OF = re.compile(r"\ba (photo|file)\b")


def _folded_message(message, n):
    if n < 2:
        return message
    plural, hit = _ONE_OF.subn(lambda m: f"{n} {m.group(1)}s", message, count=1)
    return plural if hit else f"{message} ×{n}"


def log_photos(db, log_ids):
    """{log entry id: [photo path]} for a page's worth of entries, in one query and
    in the order they were attached."""
    if not log_ids:
        return {}
    out = {}
    for log_id, rel in (db.query(LogPhoto.log_id, LogPhoto.rel)
                        .filter(LogPhoto.log_id.in_(log_ids))
                        .order_by(LogPhoto.id)):
        out.setdefault(log_id, []).append(rel)
    return out


def _fold_log(entries, photos=None):
    """The history as a page shows it, with a run of the same thing done over and
    over collapsed into one line.

    Clearing out a folder of photographs writes "deleted a photo" once per
    photograph, and twenty of those push the history the machine actually has --
    what it was fitted with, what was corrected -- off the bottom of the page. They
    are one action to the person who did them, so they read as one line.

    Only entries next to each other, saying exactly the same thing, and within
    FOLD_WINDOW of the one before: a chain, so a long tidying session is still one
    line, while the same thing done again next week is its own. A note is never
    folded -- it is a person's own words about the machine, and it stands as
    written, however like the last one it reads.

    The record itself is untouched: the rows stay one per action, and the API's log
    still lists them. This is how the page reads them out.

    An entry carrying photographs is never folded either, into or out of. Folding
    rewrites several entries as one sentence, and the photographs would then either
    be lost with the entries that are no longer shown or be gathered under a line
    that is not the one they were taken for. `photos` is what log_photos read, so
    an entry with none behaves exactly as it did before this existed.
    """
    photos = photos or {}
    out = []
    for e in entries:
        last = out[-1] if out else None
        mine = photos.get(e.id) or []
        if (last is not None and not mine and not last.photos
                and e.kind != "note" and last.kind == e.kind
                and last.message == e.message and last.created_at and e.created_at
                and last.oldest - e.created_at <= FOLD_WINDOW):
            last.count += 1
            last.oldest = e.created_at
            # Every row the one line stands for, so that deleting it removes what it
            # says it is rather than one twentieth of it.
            last.ids.append(e.id)
            continue
        out.append(SimpleNamespace(id=e.id, created_at=e.created_at, kind=e.kind,
                                   message=e.message, count=1, photos=mine,
                                   oldest=e.created_at, ids=[e.id]))
    # Newest first, so a run's own stamp is the last time it was done; the count in
    # the message says the rest.
    for e in out:
        e.message = _folded_message(e.message, e.count)
    return out


def _history(db, asset_id):
    """One item's history as its page wants it: folded, with each entry's
    photographs on it. Two queries whatever the history is long -- the entries, and
    the photographs of all of them at once."""
    entries = item_log(db, asset_id)
    return _fold_log(entries, log_photos(db, [e.id for e in entries]))


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
    if field in ("year", "topbench"):
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
    """installed_ram over the wire is a plain amount ('640KiB') or free text, never
    a module breakdown -- that has its own grids in the GUI. A caller sending one
    replaces any note and total but leaves the fitted modules and chips alone."""
    total_kb, note = ramdb.from_string(text)
    ramdb.write(db, computer, note=note, total_kb=total_kb)


def _machine_from_api(db, asset, machine):
    """An asset's catalogue identity as the wire gives it: an object naming a
    catalogue model and any of the variations it was built in, or null to forget the
    catalogue for it.

    A key or a chip socket the catalogue does not have is refused rather than stored.
    Everything else here takes what it is given and the register keeps it -- but the
    point of a catalogue is that it is the thing being filed against, and a `sid` on
    an Amiga or a model key with a typo in it is a mistake the caller wants to hear
    about rather than a fact about anyone's hardware.
    """
    if machine is None:
        machinedb.clear(db, asset)
        return
    fields = machine.model_dump(exclude_unset=True)
    key = fields.get("model_key")
    if key and machines.model(key) is None:
        raise HTTPException(422, f"no such machine model: {key} -- "
                                 "GET /api/machines lists them")
    # Which model the chips are being checked against: the one this request sets, or
    # the one the asset is already filed as.
    against = key if key is not None else machinedb.read(db, asset)["model_key"]
    for role in {*(fields.get("chips") or {}), *(fields.get("sockets") or {})}:
        if role not in machines.roles(against):
            raise HTTPException(422, f"{against or 'a machine with no model'} has no "
                                     f"{role} socket to record a chip in")
    machinedb.write(db, asset, **fields)


def _board_from_api(db, part, machine):
    """The same for a part, which only a motherboard may have. Every other kind is
    refused rather than quietly ignored: a card or a SIMM filed as a Commodore 64 is
    a mistake the caller wants to hear about, and the register would have no way to
    show what it had been told.

    Null is the exception, because null asks for nothing to be there -- and anything
    may be asked to forget a catalogue identity it has not got."""
    if machine is not None and (part.type or "") != "motherboard":
        raise HTTPException(
            422, f"a {entry.type_label(part.type) or 'part'} cannot be a catalogue "
                 "machine -- only a motherboard is filed against the catalogue")
    _machine_from_api(db, part, machine)


def _machine_out(db, asset, identity=None):
    """An asset's catalogue identity for the wire: what is stored, plus the
    catalogue's own name for the model, or None for one that is not filed as a
    catalogue machine at all."""
    v = machinedb.read(db, asset) if identity is None else identity
    if not any(v.values()):
        return None
    m = machines.model(v["model_key"]) or {}
    return v | {"model": m.get("model", ""), "family": m.get("family", "")}


def _computer_out(db, computer, identity=None):
    """One computer as the API returns it: its own columns, and the catalogue
    identity read from its rows rather than from the line rendered off them."""
    return to_dict(computer) | {"machine": _machine_out(db, computer, identity)}


def _part_out(db, part, identity=None):
    """One part as the API returns it. The same two pieces as a computer's, and for
    a part that is not a board `machine` is simply null."""
    return to_dict(part) | {"machine": _machine_out(db, part, identity)}


@app.get("/machines", response_class=HTMLResponse, include_in_schema=False)
def gui_machines(request: Request, db: Session = Depends(get_db)):
    """Every machine the catalogue names, on one page, and which of them are here.

    catalogue.txt answers this question in a text file and /api/machines answers it
    in JSON; this is the same question asked in a browser, which is where it
    actually gets asked -- "does it know my machine?" is what somebody wants to
    know before they type one in, and reading a JSON document to find out is not a
    reasonable thing to ask of anybody.

    The count of what is held against each model comes from the register, so the
    page doubles as the other view of the catalogue: not what was made, but how
    much of it is on the shelf."""
    held = Counter()
    for row in db.query(AssetVariant.model_key).filter(AssetVariant.model_key != ""):
        held[row[0]] += 1
    families = [{"name": name, "models": group} for name, group in machines.grouped()]
    return templates.TemplateResponse(request, "machines.html", {
        "families": families, "held": held,
        "n_models": len(machines.keys()), "n_families": len(families),
        "og": _og(request, "Machines the catalogue names",
                  f"{len(machines.keys())} machines the register knows as models, "
                  "with the board issues, styles and chips each was built in.")})


@app.get("/api/machines", tags=["computers"])
def api_list_machines():
    """The catalogue of machines the register knows as models -- home computers,
    consoles and the documented branded PCs -- with the memory sizes, board issues,
    case and keyboard styles, regions and chip sockets each was built in. `key` is
    what a computer's `machine.model_key` is set to.

    Every list names what is commonly seen rather than everything that exists, so a
    board issue or a chip from outside one is recorded as it is given."""
    return {"families": [{"name": name,
                          "models": [{"key": m["key"], "model": m["model"],
                                      "year": m["year"],
                                      "manufacturer": m["manufacturer"],
                                      "summary": m["summary"],
                                      "ram": [lbl for lbl, _kb in m["ram"]],
                                      "issues": m["issues"], "styles": m["styles"],
                                      "regions": m["regions"],
                                      "chips": [{"role": c["role"],
                                                 "label": c["label"],
                                                 "variants": c["variants"]}
                                                for c in m["chips"]]}
                                     for m in group]}
                         for name, group in machines.grouped()]}


@app.get("/api/computers", response_model=list[ComputerOut], tags=["computers"])
def api_list_computers(db: Session = Depends(get_db)):
    rows = db.query(Computer).order_by(Computer.asset_id).all()
    # One pair of queries for the whole list rather than a pair per machine.
    identities = machinedb.read_many(db, rows)
    return [_computer_out(db, c, identities.get(c.asset_id, dict(machinedb.BLANK)))
            for c in rows]


@app.post("/api/computers", response_model=ComputerOut, tags=["computers"])
def api_create_computer(data: ComputerIn, db: Session = Depends(get_db)):
    fields = data.model_dump()
    ram = fields.pop("installed_ram", "")
    drives = fields.pop("drives", "")
    machine = data.machine
    fields.pop("machine", None)
    obj = Computer(asset_id=next_asset_id(db), **fields)
    db.add(obj)
    db.flush()
    _ram_from_api(db, obj, ram)
    _drives_from_api(db, obj, drives)
    if machine is not None:
        _machine_from_api(db, obj, machine)
    add_log(db, obj.asset_id, "created", "created")
    db.commit()
    db.refresh(obj)
    return _computer_out(db, obj)


@app.get("/api/computers/{aid}", response_model=ComputerOut, tags=["computers"])
def api_get_computer(aid: str, db: Session = Depends(get_db)):
    obj = get_or_404(db, Computer, aid)
    return _computer_out(db, obj)


@app.patch("/api/computers/{aid}", response_model=ComputerOut, tags=["computers"])
def api_update_computer(aid: str, data: ComputerIn, db: Session = Depends(get_db)):
    obj = get_or_404(db, Computer, aid)
    fields = data.model_dump(exclude_unset=True)
    ram = fields.pop("installed_ram", None)
    drives = fields.pop("drives", None)
    # An omitted machine leaves the catalogue rows alone; an explicit null forgets
    # them. Both arrive here as None, so which was meant is read from what the
    # request set rather than from the value.
    sent_machine = "machine" in fields
    fields.pop("machine", None)
    derived = ("installed_ram", "drives", "variant")
    old = {k: getattr(obj, k) for k in fields} | {k: getattr(obj, k) for k in derived}
    for k, v in fields.items():
        setattr(obj, k, v)
    if ram is not None:
        _ram_from_api(db, obj, ram)
    if drives is not None:
        _drives_from_api(db, obj, drives)
    if sent_machine:
        _machine_from_api(db, obj, data.machine)
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
    return _computer_out(db, obj)


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
    rows = q.order_by(Part.asset_id).all()
    identities = machinedb.read_many(db, rows)
    return [_part_out(db, p, identities.get(p.asset_id, dict(machinedb.BLANK)))
            for p in rows]


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
    fields = data.model_dump()
    machine = fields.pop("machine")
    _check_links(db, fields)
    obj = Part(asset_id=next_asset_id(db), **fields)
    db.add(obj)
    db.flush()
    specdb.write(db, obj)
    if machine is not None:
        _board_from_api(db, obj, data.machine)
    add_log(db, obj.asset_id, "created", "created")
    db.commit()
    db.refresh(obj)
    return _part_out(db, obj)


@app.get("/api/parts/{aid}", response_model=PartOut, tags=["parts"])
def api_get_part(aid: str, db: Session = Depends(get_db)):
    return _part_out(db, get_or_404(db, Part, aid))


@app.patch("/api/parts/{aid}", response_model=PartOut, tags=["parts"])
def api_update_part(aid: str, data: PartIn, db: Session = Depends(get_db)):
    obj = get_or_404(db, Part, aid)
    fields = data.model_dump(exclude_unset=True)
    machine = fields.pop("machine", ...)
    _check_links(db, fields)
    old = {k: getattr(obj, k) for k in fields}
    for k, v in fields.items():
        setattr(obj, k, v)
    specdb.write(db, obj)
    # After the columns are set, so a request that renames the type and files the
    # board in one go is checked against the type it is being given.
    if machine is not ...:
        _board_from_api(db, obj, data.machine)
    elif "type" in fields and obj.type != "motherboard" and obj.variant:
        # Retyped out of being a board, and the catalogue answer goes with it -- the
        # same rule the edit form follows.
        machinedb.clear(db, obj)
    new = {k: getattr(obj, k) for k in fields}
    diff = _field_diffs(old, new, list(fields), semantic_specs=True)
    if diff:
        add_log(db, aid, diff)
    db.commit()
    db.refresh(obj)
    return _part_out(db, obj)


@app.delete("/api/parts/{aid}", tags=["parts"])
def api_delete_part(aid: str, db: Session = Depends(get_db)):
    """Delete a part, with its typed spec rows, photos and history. Anything
    mounted on it is unlinked, not deleted."""
    obj = get_or_404(db, Part, aid)
    return {"deleted": aid, "photos": len(delete_part(db, obj))}


@app.get("/api/items/{aid}/log", tags=["log"])
def api_item_log(aid: str, db: Session = Depends(get_db)):
    """One asset's history, entry by entry and unfolded -- the record as it was
    written, not as a page reads it out. `photos` are the paths of anything hung on
    the entry, to be fetched from /images/ like any other photograph."""
    entries = item_log(db, aid)
    photos = log_photos(db, [e.id for e in entries])
    return [{"created_at": e.created_at.isoformat() if e.created_at else None,
             "kind": e.kind, "message": e.message,
             "photos": photos.get(e.id, [])} for e in entries]


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

    def write(tmp):
        with open(tmp, "wb") as f:
            shutil.copyfileobj(upload.file, f)

    # A page loading while this one is still arriving reads the folder and finds
    # whatever is in it; until the move, what is in it is not this photograph.
    _write_atomically(path, write)
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


# --- photographs of what happened, as against the portrait of the thing ------
# These reuse everything the gallery photographs use -- the same storage, the same
# watermark, the same resized copies -- and differ in one thing only: the folder
# they go in, and therefore that nothing reading an asset's folder can mistake one
# for a picture of the asset. The log entry's id stands where an asset id stands,
# so _photo_target's <id>.jpg, <id>-2.jpg naming works unchanged, and entry 12's
# photographs cannot be claimed by entry 120 because the second name always has the
# hyphen in it.

def _attach_log_photos(db, row, uploads):
    """Store photographs against a history entry. Returns how many were kept.

    The entry is flushed first: the photographs are filed under its id, and until
    the insert has gone to the database there is no id to file them under. Nothing
    is committed here -- the caller does that, once the entry and its photographs
    are both written.
    """
    if row is None or not uploads:
        return 0
    db.flush()
    for up in uploads:
        db.add(LogPhoto(log_id=row.id, rel=_save_photo(LOG_KIND, str(row.id), up)))
    return len(uploads)


def _drop_log_photos(db, asset_id):
    """Clear the photographs hung on one asset's history, and return their paths for
    the caller to delete once the transaction is safe.

    By hand rather than by the foreign key's cascade, for the reason the log entries
    themselves are: the paths have to be read while the rows are still there, since
    a file is the one thing here that cannot be rolled back.
    """
    ids = [i for (i,) in db.query(LogEntry.id)
           .filter(LogEntry.asset_id == asset_id)]
    if not ids:
        return []
    rels = [rel for (rel,) in db.query(LogPhoto.rel)
            .filter(LogPhoto.log_id.in_(ids)).order_by(LogPhoto.id)]
    db.query(LogPhoto).filter(LogPhoto.log_id.in_(ids)).delete(
        synchronize_session=False)
    return rels


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


def img_url(rel, width=None):
    """/images URL for a photo with a cache-busting ?v= stamp from its mtime, so
    the browser refetches after an edit or watermark change rather than showing a
    stale cached copy. Reflects the reference-marker sidecar too (its toggle
    changes whether the served image is watermarked).

    `width` asks for a copy no wider than that many pixels -- see thumbs.py. Leave
    it out for the original, which is what the lightbox wants and what everything
    wanted before there were copies to ask for.
    """
    if not rel:
        return ""
    ts = 0
    for p in (IMAGES_DIR / rel, _ref_sidecar(rel)):
        with contextlib.suppress(OSError):
            ts = max(ts, int(p.stat().st_mtime))
    query = f"?v={ts}" if ts else ""
    if width:
        query += ("&" if query else "?") + f"w={int(width)}"
    return f"/images/{rel}{query}"


def img_srcset(rel, widths):
    """A srcset for one photo at several widths, so the browser takes the one that
    suits its screen: a card is 400 wide on an ordinary display and 800 on a retina
    one, and only it knows which it is."""
    return ", ".join(f"{img_url(rel, w)} {w}w" for w in widths) if rel else ""


templates.env.globals["img_url"] = img_url
templates.env.globals["img_srcset"] = img_srcset
templates.env.globals["THUMB_CARD"] = 300
templates.env.globals["THUMB_MAIN"] = 1200
templates.env.globals["human_size"] = filesdb.human_size
templates.env.globals["max_file_mb"] = filesdb.MAX_BYTES // (1024 * 1024)


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
    # By hand rather than by cascade, for the reason log_entry is: these are keyed
    # by an asset id from the shared register, which no one table can own. The
    # log's own photographs go first, while there are still entries to find them by.
    photos = _drop_log_photos(db, aid)
    for model in (AssetChip, AssetVariant, LogEntry):
        db.query(model).filter(
            model.asset_id == aid).delete(synchronize_session=False)
    photos += detect_images("parts", aid)
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
    photos += _drop_log_photos(db, aid)
    for model in (AssetChip, AssetVariant, LogEntry):
        db.query(model).filter(
            model.asset_id == aid).delete(synchronize_session=False)
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
        fmt = _image_format(src, im)
        kwargs = {}
        if src.suffix.lower() in (".jpg", ".jpeg"):
            out = out.convert("RGB")
            kwargs = {"quality": 90}
        # Never onto `src` itself: it is being served to other browsers while this
        # runs, and a truncated photograph is what they would be handed and then
        # keep. See _write_atomically.
        _write_atomically(src, lambda tmp: out.save(tmp, fmt, **kwargs))
    # Deliberately not _wm_forget: the copies are dated by the photograph they were
    # made from, so replacing it has already made them stale and they rebuild on
    # the next request. Unlinking them here raced with anyone reading -- a request
    # that had chosen a copy to serve found it deleted out from under it between
    # choosing and opening, and answered a broken image. _wm_forget is for the case
    # the freshness check cannot see, which is a photograph that is gone.


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


def _change_token(db, aid: str) -> str:
    """What an item's page was built from, as one short string.

    Every change to an asset writes a history entry -- a field edited, a photograph
    added, rotated, cropped or deleted -- so the highest id in that item's history
    already answers "has anything happened to this?" without a column being added
    anywhere. Files are the one thing an item page shows that is not filed against
    it (a driver belongs to a model, not to the card on the shelf), so the register
    of files is counted alongside: the newest id, and how many there are, because
    deleting one that is not the newest leaves the maximum where it was.

    Cheap on purpose. This is asked every few seconds by every open page, and it is
    two indexed aggregates over columns that are already there.
    """
    logged = db.query(func.max(LogEntry.id)).filter(LogEntry.asset_id == aid).scalar()
    newest = db.query(func.max(StoredFile.id)).scalar()
    count = db.query(func.count(StoredFile.id)).scalar()
    return f"{logged or 0}.{newest or 0}.{count or 0}"


@app.get("/items/{aid}/version", include_in_schema=False)
def gui_item_version(aid: str, db: Session = Depends(get_db)):
    """The token above, for a page to compare against the one it was built with.

    Public, like the page it belongs to: it says that something changed, never what.
    No 404 for an unknown asset -- a page whose item has been deleted asks this too,
    and the honest answer is a token that will not match, which sends it to reload
    and find out properly."""
    return {"v": _change_token(db, (aid or "").upper())}


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


def _part_placeholder(db, part):
    """The stand-in drawing for one part, routed exactly as the gallery routes it.

    One row read rather than the whole table: the gallery wants every storage part's
    Kind at once and this wants one, and asking the same question two ways is how
    a card and the page it opens come to disagree about what a thing looks like."""
    if (part.type or "") != "storage":
        return entry.placeholder_for(part.type or "other")
    return _storage_placeholder(specdb.scalars(db, part).get("kind"))


def part_thumbs(db, parts):
    """The picture to put on each part's card in a list of them, by asset id.

    A list of parts said what each one was and never showed it: "PT-0031 · storage /
    drive, Teac FD-235HF" names a floppy drive without saying whether the one in this
    machine is beige or grey, full-height or slim, or photographed at all. The
    picture is the fastest way to know which of four identical-sounding drives you
    are looking at, and the gallery card for the same part has been carrying it all
    along.

    The same reading the gallery makes of the same parts -- one folder scan and one
    query for every storage part's Kind, rather than either per row -- so a part's
    card in a machine and its card on the shelf cannot come to wear different
    pictures. Where nobody has photographed it, the drawing stands in, exactly as it
    does there; and a photograph of the model rather than of this unit says so, for
    the same reason it says so everywhere else it is shown.
    """
    listing = folder_images("parts")
    kinds = specdb.storage_kinds(db)
    thumbs = {}
    for p in parts:
        imgs = pick_images("parts", p.asset_id, listing)
        rel = imgs[0] if imgs else ""
        ptype = p.type or "other"
        thumbs[p.asset_id] = {
            "img": rel, "ref": is_reference(rel),
            "icon": _favicon_for_rel(rel),
            "ph": (_storage_placeholder(kinds.get(p.asset_id)) if ptype == "storage"
                   else entry.placeholder_for(ptype)),
        }
    return thumbs


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
            "img": img_url(imgs[0], 300) if imgs else "",
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
        # The queue behind the coverage figure, and it reads the same answer the
        # figure did rather than a row test that resembles it: one pass over the two
        # folders, then a set lookup per row, the way _tagged works. Held only, so
        # unlike its opposite above this view excludes the disposed -- a record of
        # something gone can still have its picture, but nobody can go and take one.
        missing = _portraits(db)[1]
        return ("Not photographed yet", "everything still here waiting for a camera",
                None, lambda r: r["obj"].asset_id in missing)
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
    if key == "model":
        # Everything filed as one catalogue model, machines and bare boards alike:
        # asset_variant is keyed by a plain asset id and does not care which it has,
        # which is the whole of what stage 1 bought. An unknown key is a 404 rather
        # than an empty page, the same as a machine that is not there.
        m = machines.model(val)
        if m is None:
            return None
        return (m["full_name"], "everything in the register filed as this model",
                None, _tagged(db.query(AssetVariant.asset_id)
                              .filter(AssetVariant.model_key == val)))
    if key == "in":
        machine = db.get(Computer, (val or "").upper())
        if machine is None:
            return None
        name = entry.display_name(to_dict(machine))
        return (f"Parts fitted in {name}", "everything installed in this machine",
                (f"/computers/{machine.asset_id}", name),
                lambda r: r["kind"] == "part"
                and r["obj"].computer_id == machine.asset_id)
    # --- the views behind the themed figures ------------------------------
    # One per group in the pool, in the same order. Most are a set of asset ids
    # read straight out of the table the figure was counted from, which is what
    # _tagged is for: the figure and the page behind it then cannot disagree, since
    # both are the same query.
    if key == "boards":
        return ("Motherboards", "everything with a board's specs on file", None,
                _tagged(db.query(MotherboardSpec.part_id)))
    if key == "formfactor":
        return (f"Boards built to {val}", "as recorded in the form factor field",
                None, _tagged(db.query(MotherboardSpec.part_id)
                              .filter(MotherboardSpec.form_factor == val)))
    if key == "bios":
        return (f"Boards with a {val} BIOS", "as recorded in the BIOS field", None,
                _tagged(db.query(MotherboardSpec.part_id)
                        .filter(MotherboardSpec.bios == val)))
    if key == "family":
        return (f"Boards for a {val} processor", "as recorded in the CPU family field",
                None, _tagged(db.query(MotherboardSpec.part_id)
                              .filter(MotherboardSpec.cpu_family == val)))
    if key == "cache":
        return ("Boards with cache on them",
                "the boards the cache total is added up from", None,
                _tagged(db.query(MotherboardSpec.part_id)
                        .filter(MotherboardSpec.cache_kb.isnot(None),
                                MotherboardSpec.cache_kb > 0)))
    if key == "onboardvideo":
        return ("Boards with video on the board", "no expansion card required", None,
                _tagged(db.query(MotherboardSpec.part_id)
                        .filter(MotherboardSpec.onboard_video.isnot(None),
                                MotherboardSpec.onboard_video != "")))
    if key == "noslots":
        # The difference between two sets rather than a NOT EXISTS: the figure is
        # worked out that way too, and this page has to show the same boards.
        slotted = {a for (a,) in db.query(PartSlot.part_id).distinct()}
        return ("Boards with no expansion slots", "nothing can be added to these",
                None, _tagged(db.query(MotherboardSpec.part_id)
                              .filter(MotherboardSpec.part_id.notin_(slotted))
                              if slotted else db.query(MotherboardSpec.part_id)))
    if key == "ramslots":
        return ("Boards with memory sockets", "the boards those sockets are on", None,
                _tagged(db.query(PartRamSlot.part_id).distinct()))
    if key == "ramslot":
        return (f"Boards with {val} sockets", "the boards those sockets are on", None,
                _tagged(db.query(PartRamSlot.part_id)
                        .filter(PartRamSlot.slot_type == val)))
    if key == "cards":
        # Everything with a card's specs on file, of any of the four kinds: the
        # population the figures about cards are counted against, rather than any
        # one of their answers. The four share the shape of most of the questions --
        # which bus, whose chip -- so they share a view.
        ids = set()
        for spec in (VideoSpec, SoundSpec, NetworkSpec, IoSpec):
            ids |= {a for (a,) in db.query(spec.part_id)}
        return ("Expansion cards", "video, sound, network and I/O together", None,
                lambda r: r["obj"].asset_id in ids)
    if key == "vram":
        return ("Graphics cards with their memory recorded",
                "the cards the video memory total is added up from", None,
                _tagged(db.query(VideoSpec.part_id)
                        .filter(VideoSpec.memory_kb.isnot(None),
                                VideoSpec.memory_kb > 0)))
    if key == "vramsize":
        sizes = sorted({int(x) for x in val.split(",") if x.strip().isdigit()})
        return (("Graphics cards with " + " or ".join(entry.fmt_kb(kb, True)
                                                     for kb in sizes))
                if sizes else "Graphics cards by memory",
                "read from the typed memory column, not from the text", None,
                _tagged(db.query(VideoSpec.part_id)
                        .filter(VideoSpec.memory_kb.in_(sizes) if sizes
                                else VideoSpec.memory_kb.isnot(None))))
    if key == "prevga":
        # The same four LIKEs the figure is counted with, so the page cannot show a
        # different set of cards from the one the number claimed.
        return ("Graphics cards from before VGA",
                "MDA, CGA, EGA or composite, and nothing later", None,
                _tagged(db.query(VideoSpec.part_id)
                        .filter(VideoSpec.connector.isnot(None),
                                VideoSpec.connector != "",
                                ~VideoSpec.connector.like("%VGA%"),
                                ~VideoSpec.connector.like("%DVI%"))))
    if key == "nochip":
        ids = set()
        for spec in (VideoSpec, SoundSpec, NetworkSpec, IoSpec):
            ids |= {a for (a,) in db.query(spec.part_id)
                    .filter((spec.chip.is_(None)) | (spec.chip == ""))}
        return ("Cards with no chip recorded", "nobody has written down what is on "
                "them", None, lambda r: r["obj"].asset_id in ids)
    if key == "ports":
        return ("Boards and cards with ports", "the things those ports are on", None,
                _tagged(db.query(PartPort.part_id).distinct()))
    if key == "legacydisk":
        return ("Drives on a dead interface",
                "MFM, RLL, ESDI and XTA: none of them survived the 1990s", None,
                _tagged(db.query(StorageSpec.part_id)
                        .filter(StorageSpec.interface.in_(LEGACY_DISK_BUSES))))
    if key == "rpm":
        return ("Drives with a spindle speed recorded", "mechanical disks that say",
                None, _tagged(db.query(StorageSpec.part_id)
                              .filter(StorageSpec.speed_rpm.isnot(None),
                                      StorageSpec.speed_rpm > 0)))
    if key == "optical":
        return ("Optical drives", "everything that takes a disc", None,
                _tagged(db.query(StorageSpec.part_id)
                        .filter(StorageSpec.kind == entry.OPTICAL_KIND)))
    if key == "geometry":
        return ("Drives with their geometry on file",
                "cylinders, heads and sectors as the drive reports them", None,
                _tagged(db.query(StorageSpec.part_id)
                        .filter(StorageSpec.chs_c.isnot(None), StorageSpec.chs_c > 0)))
    if key == "flash":
        return ("Machines with a card standing in for a drive",
                "CF or SD where a disk or a floppy used to be", None,
                _tagged(db.query(ComputerDrive.computer_id)
                        .filter(ComputerDrive.kind.in_(("CF", "SD"))).distinct()))
    if key == "os":
        return ("Machines with an operating system recorded",
                "what each of them boots, as last seen", None,
                lambda r: r["kind"] == "computer" and bool(r["obj"].os))
    if key == "dos":
        return ("Machines running DOS", "MS-DOS, FreeDOS or the like", None,
                lambda r: r["kind"] == "computer" and "DOS" in (r["obj"].os or ""))
    if key == "cpu":
        return ("Machines with their processor recorded",
                "the machines the processor figures are counted from", None,
                lambda r: r["kind"] == "computer" and bool(r["obj"].cpu))
    if key == "chassis":
        return (f"Machines in a {val} case", "as recorded in the chassis field", None,
                lambda r: r["kind"] == "computer" and (r["obj"].chassis or "") == val)
    if key == "portable":
        return ("Machines meant to be carried",
                "laptops and luggables, the second word doing a lot of work", None,
                lambda r: r["kind"] == "computer"
                and (r["obj"].chassis or "").lower() in ("laptop", "luggable"))
    if key == "benchmarked":
        return ("Machines with a TopBench score", "the ones it has been run on", None,
                lambda r: r["kind"] == "computer" and r["obj"].topbench is not None)
    if key == "variant":
        return ("Filed as a catalogue model",
                "machines and boards the catalogue can name", None,
                _tagged(db.query(AssetVariant.asset_id)))
    if key == "emptymachines":
        fitted = {c for (c,) in _held(db.query(Part.computer_id)
                                      .filter(Part.computer_id.isnot(None)), Part)}
        return ("Machines with nothing fitted",
                "no part in the register is installed in these", None,
                lambda r: r["kind"] == "computer"
                and r["obj"].asset_id not in fitted)
    if key == "century":
        return ("Made in this century", "2000 or later, by the year on the record",
                None, lambda r: (r["obj"].year or 0) >= 2000)
    if key == "recent":
        cutoff = date.today().year - 10
        return ("Made in the last ten years",
                f"{cutoff} or later — new parts for old machines", None,
                lambda r: (r["obj"].year or 0) >= cutoff)
    if key in ("born", "older"):
        # Both compare a fitted part's year against its machine's, so both are the
        # same join with one operator changed.
        gaps = (db.query(Part.asset_id, Part.year - Computer.year)
                .join(Computer, Computer.asset_id == Part.computer_id)
                .filter(Part.year.isnot(None), Computer.year.isnot(None)).all())
        if key == "born":
            ids = {a for a, gap in gaps if gap == 0}
            return ("Fitted to a machine of its own year",
                    "part and machine made the same year", None,
                    lambda r: r["obj"].asset_id in ids)
        ids = {a for a, gap in gaps if gap is not None and gap < 0}
        return ("Older than the machine it is in",
                "made before the thing it was fitted to", None,
                lambda r: r["obj"].asset_id in ids)
    if key == "nosource":
        return ("Parts with no recorded source",
                "nothing on file about where they came from", None,
                lambda r: r["kind"] == "part" and not (r["obj"].source or "").strip())
    if key == "unwritten":
        return ("Parts with nothing written about them",
                "no summary and no notes", None,
                lambda r: r["kind"] == "part" and not (r["obj"].summary or "")
                and not (r["obj"].notes or ""))
    if key == "links":
        return ("Parts with a link out", "somebody else's page about the same thing",
                None, lambda r: r["kind"] == "part" and bool(r["obj"].url))
    if key == "diskimages":
        return ("Parts with a disk image kept", "the contents as well as the object",
                None, lambda r: r["kind"] == "part" and bool(r["obj"].disk_image))
    if key == "subparts":
        return ("Parts fitted to another part",
                "a daughterboard, a riser, or a chip on a carrier", None,
                lambda r: r["kind"] == "part" and bool(r["obj"].parent_id))
    if key == "sourcelike":
        # A prefix, not the whole field: "eBay order no. 19-14922-72542" is one
        # order and there are dozens of them, but "bought on eBay" is one answer.
        # Folded, because the figures behind this are counted with SQL LIKE, which
        # is case-insensitive under both engines the app runs on. A bare
        # str.startswith is not, and would show fewer items than the number claimed.
        fold = val.lower()
        return (f"Came from {val}", "everything whose source starts with this", None,
                lambda r: (r["obj"].source or "").lower().startswith(fold))
    if key == "sparetype":
        return (f"{entry.type_label(val)} on the shelf",
                "not fitted to anything", None,
                lambda r: r["kind"] == "part" and r["cat"] == val
                and not r["obj"].computer_id)
    if key == "dupes":
        # Every maker-and-model held more than once, which is the set the figure
        # counted rather than a resemblance to it.
        repeated = {(m or "", mo or "") for m, mo, n in
                    _held(db.query(Part.manufacturer, Part.model,
                                   func.count(Part.asset_id))
                          .filter(Part.model.isnot(None), Part.model != ""), Part)
                    .group_by(Part.manufacturer, Part.model).all() if n > 1}
        return ("Held more than once", "the same maker and model, twice or more", None,
                lambda r: r["kind"] == "part"
                and ((r["obj"].manufacturer or ""), (r["obj"].model or "")) in repeated)
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


def _boardparts_ctx(db, c):
    """The motherboard and parts sections, for the edit form of the one machine
    whose own page does not carry them: a catalogue machine with nothing fitted.

    Empty for every other machine, because the page it is read on already has them
    and offering the same two sections twice would be two places to add the same
    drive. The queries are the page's own, and only run for the machine that needs
    them."""
    if c is None or db is None or not machinedb.read(db, c)["model_key"]:
        return {}
    parts = db.query(Part).filter(Part.computer_id == c.asset_id).all()
    if parts:
        return {}
    return {"boardparts": True, "motherboard": None, "parts": [],
            "card_steps": entry.CARD_STEPS,
            "free_boards": (db.query(Part)
                            .filter(Part.type == "motherboard",
                                    Part.computer_id.is_(None))
                            .order_by(Part.asset_id).all()),
            "link_candidates": (db.query(Part)
                                .filter(Part.type != "motherboard",
                                        Part.computer_id.is_(None),
                                        Part.parent_id.is_(None))
                                .order_by(Part.type, Part.asset_id).all())}


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
            "drive_speeds": drivedb.SPEEDS, **_bezel_ctx(), **_machine_ctx(c, db),
            **_boardparts_ctx(db, c)}


# What a typed answer to one of the catalogue pickers may be as long as: the column
# it lands in. The same rule the drive pickers follow (see _ASK_WIDTHS) -- a box that
# accepted more than the column holds would fail on save rather than at the keyboard.
_MACHINE_WIDTHS = {"issue": AssetVariant.issue.type.length,
                   "style": AssetVariant.style.type.length,
                   "region": AssetVariant.region.type.length,
                   "chip": AssetChip.variant.type.length}

# The two answers a board is not asked for. A case or keyboard style and the market
# a machine was built for are facts about a whole computer in a case, so a board's
# form leaves them off -- and the save reads only what the form asked.
_MACHINE_ONLY = ("style", "region")


def _machine_ctx(obj, db=None, board=False):
    """The catalogue and this asset's place in it, for the edit form of a machine or
    of a board.

    The whole catalogue goes to the browser as JSON because the variation fields are
    built from whichever model is picked: sixty models' worth of menus rendered at
    once would be most of the page, and all but one set of them would be wrong."""
    saved = machinedb.read(db, obj) if (obj is not None and db is not None) \
        else dict(machinedb.BLANK)
    # What the catalogue names, plus what the register has since been told: a chip
    # somebody had to type once is a radio button from then on. Boards teach it the
    # same as machines do -- the query behind this reads the whole register.
    catalogue = machines.with_recorded(machines.form_catalogue(),
                                       machinedb.recorded(db) if db is not None
                                       else {})
    return {"machine_groups": machines.grouped(), "machine_saved": saved,
            "machine_catalogue": catalogue, "machine_widths": _MACHINE_WIDTHS,
            "machine_board": board}


def _machine_from_form(form, board=False):
    """An asset's catalogue identity as the form gives it, as keyword arguments for
    machinedb.write -- or None where the form did not carry the question at all.

    The variation fields are built in the browser from the catalogue, and
    `mach_fields` is the marker the script sets once it has built them. Without it --
    no JavaScript, or a script that did not run -- only the model choice is read and
    the board issue, style, region and chips already on file are left alone: a form
    that could not draw them must not be able to erase them either.

    `board` is the board's form, which asks the model, the issue and the chips and
    not the two that belong to a whole machine. They are left unnamed rather than
    blanked, so a question this form never put cannot answer itself.

    Only the sockets the chosen model has are read, so fields left over from another
    model in the same browser tab cannot put a ULA in a Commodore 64."""
    if "mach_model" not in form:
        return None
    key = (form.get("mach_model", "") or "").strip()
    out = {"model_key": key}
    if not key or not (form.get("mach_fields", "") or "").strip():
        return out
    asked = ["issue"] if board else ["issue", *_MACHINE_ONLY]
    for field in asked:
        out[field] = _machine_pick(form, f"mach_{field}")
    out["chips"] = {role: _machine_pick(form, f"chip:{role}")
                    for role in machines.roles(key)}
    # The tickbox beside each chip: on for a socket, off for soldered to the board.
    # A box that is off is only an answer for a chip that has one -- a socket left
    # at "not recorded" stores no row at all, so saving the form cannot quietly
    # decide that a chip nobody has looked at is soldered down.
    out["sockets"] = {role: bool(form.get(f"chip:{role}:socketed"))
                      for role in machines.roles(key) if out["chips"].get(role)}
    return out


def _machine_pick(form, field):
    """What one of the catalogue's radio groups chose: one of the answers it offered,
    or whatever was typed beside "custom" for the machine the catalogue has not met
    yet. Blank is a deliberate answer too -- it is how a socket nobody has looked at
    is left unrecorded, and how a chip written down by mistake is taken back off."""
    picked = (form.get(field, "") or "").strip()
    if picked == "custom":
        return " ".join((form.get(f"{field}_custom", "") or "").split())
    return picked


def _machine_page(db, obj):
    """An asset's catalogue identity for its page: what it is filed as, then what
    makes this one of them, then the chips in the order a board is read in. None for
    an asset outside the catalogue, so the section does not appear at all.

    The same shape for a machine and for a board, because it is the same answer: a
    board is filed as an Amiga 500 exactly as the Amiga 500 it came out of is, and a
    page that said it two ways would be inviting the reader to look for a difference
    that is not there. A board simply has nothing in the two rows a case answers.

    Every label is read from the catalogue rather than from the record, so a page
    shows the current words for what was recorded -- and a chip whose socket the
    catalogue has since dropped still shows, under the role's own name, because what
    was seen on the board is not wrong for having gone out of the catalogue. The
    catalogue's line about a socket stays on the form, where it helps decide what to
    look at; here it would be the same sentence under every machine of the model.

    The row keys are machines.ISSUE_KEY and the two beside it, so the page and the
    rendered line call the same three answers by the same names."""
    v = machinedb.read(db, obj)
    if not any(v.values()):
        return None
    m = machines.model(v["model_key"])
    return {
        # The stable key as well as the words, because a page that offers an action
        # on a filed asset has to ask whether it is filed -- and the rendered model
        # name falls back to the key, so it cannot answer that.
        "key": v["model_key"],
        "model": (m["model"] if m else v["model_key"]),
        "family": m["family"] if m else "",
        "year": m["year"] if m else None,
        # What the model is, where the catalogue has it written. Read from the
        # catalogue and not the record, like every label here: the paragraph is
        # about the model, so correcting it corrects every machine filed as one.
        "summary": m.get("summary", "") if m else "",
        "rows": [(label, value) for label, value in
                 ((machines.ISSUE_KEY, v["issue"]), (machines.STYLE_KEY, v["style"]),
                  (machines.REGION_KEY, v["region"])) if value],
        "chips": [{"label": machines.chip_label(v["model_key"], role),
                   "variant": variant,
                   "socketed": v["sockets"].get(role)}
                  for role, variant in v["chips"].items()],
    }


def _bezel_ctx():
    """The bezel vocabularies and their swatches, for any form that records one:
    a machine's drive rows, a storage part and a display all do."""
    return {"bezel_colours": entry.BEZEL_COLOURS, "yellowing": entry.YELLOWING,
            "bezel_colour_labels": entry.BEZEL_COLOUR_LABELS,
            "yellowing_labels": entry.YELLOWING_LABELS,
            "bezel_swatches": entry.bezel_swatch_map()}


@app.get("/computers/new", response_class=HTMLResponse, include_in_schema=False)
def gui_new_computer(request: Request, db: Session = Depends(get_db)):
    # With a session, because the catalogue's pickers offer what other machines have
    # already been found to have as well as what the catalogue names -- and the form
    # for a machine being entered for the first time is where that matters most.
    return templates.TemplateResponse(request, "computer_form.html",
                                      _computer_form_ctx(None, "New computer", db))


@app.post("/computers/new", include_in_schema=False)
async def gui_create_computer(request: Request, db: Session = Depends(get_db)):
    form = await request.form()
    photos = _chosen_photos(form)
    # Everything the child tables render is left to them, as the edit path does: the
    # form's own installed_ram and drive fields are read by ramdb and drivedb below.
    data = {k: _coerce(k, form[k]) for k in COMPUTER_FIELDS
            if k in form and k not in DERIVED_FIELDS}
    for f in ("manufacturer", "model"):
        if f in data:
            data[f] = entry.deshout(data[f])
    obj = Computer(asset_id=next_asset_id(db), **data)
    db.add(obj)
    db.flush()
    ramdb.write(db, obj, *_ram_from_form(form))
    drivedb.write(db, obj, _drives_from_form(form),
                  (form.get("drives_note", "") or "").strip())
    if (mach := _machine_from_form(form)) is not None:
        machinedb.write(db, obj, **mach)
    add_log(db, obj.asset_id, "created", "created")
    db.commit()
    if photos:
        _attach_photos(db, obj, "computers", photos)
        db.commit()
    # Land on the build walk so the next step (motherboard) is front and centre.
    return RedirectResponse(f"/computers/{obj.asset_id}?build=1", status_code=303)


@app.get("/computers/{aid}", response_class=HTMLResponse, include_in_schema=False)
def gui_computer(aid: str, request: Request, build: int = 0, imgerr: int = 0,
                 fileerr: int = 0, db: Session = Depends(get_db)):
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
    # Whether a board can be lifted out of this machine, worked out from what the
    # page has already read rather than by asking again: a machine the catalogue
    # names, with no board linked to it yet. _board_out_of is the same two conditions
    # at the door, so the button and the route cannot disagree.
    machine = _machine_page(db, c)
    detachable = bool(request.state.authed and machine and machine["key"]
                      and motherboard is None)
    return templates.TemplateResponse(request, "computer.html", {
        "machine": machine, "detachable": detachable,
        "item": (cdict := to_dict(c)), "kind": "computers",
        "files": filesdb.for_item(db, cdict), "fileerr": bool(fileerr),
        "c": c, "parts": [p for p in parts if p is not motherboard],
        "motherboard": motherboard, "form_factor": form_factor,
        # A picture for each of them, read once for the page rather than per card.
        "thumbs": part_thumbs(db, parts),
        "free_boards": free_boards,
        "link_candidates": link_candidates, "images": images,
        # The drawing to stand in for a photograph nobody has taken yet -- the same
        # one the gallery card for this item is already wearing, so the two places
        # it appears agree about what it is a picture of.
        "placeholder": entry.placeholder_for("computer"),
        "ref_marks": reference_marks("computers", aid),
        "card_steps": entry.CARD_STEPS, "build": bool(build), "imgerr": bool(imgerr),
        "log": _history(db, aid), "nav": _item_nav(db, aid),
        "live_aid": aid, "live_v": _change_token(db, aid),
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
    if (mach := _machine_from_form(form)) is not None:
        machinedb.write(db, c, **mach)
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
    pid = form.get("part_id", "") or ""
    if not pid:
        return RedirectResponse(f"/computers/{aid}?build=1", status_code=303)
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
    pid = form.get("part_id", "") or ""
    if not pid:
        return RedirectResponse(f"/computers/{aid}", status_code=303)
    part = get_or_404(db, Part, pid)
    part.computer_id = aid
    part.parent_id = None
    add_log(db, aid, f"linked part {part.asset_id}")
    add_log(db, part.asset_id, f"installed in {aid}")
    db.commit()
    return RedirectResponse(f"/computers/{aid}", status_code=303)


# --- detaching the board: the moment a description becomes an object ---------
#
# A machine the catalogue names is one object, and the board inside it is part of
# the description of that object: the board issue and the chips in its sockets are
# answers the machine gives about itself. Lift the board out and put it on a shelf
# and that stops being true -- it is now a thing that can be photographed, tagged,
# swapped into another machine and sold on its own, which is the register's whole
# test for what deserves an asset id. So this verb is the moment of physical
# separation written down, and nothing here happens speculatively: no machine grows
# a board object because the catalogue says it has one.
#
# What moves is exactly what stops being true of the machine. The board issue and
# the chips go, because they were always facts about the board. The model key is
# copied rather than moved -- the machine is still a Spectrum and the board is a
# Spectrum board -- and the style and the region stay behind, because a case and a
# market are facts about the assembled machine and a board has neither.
#
# One way only. Refitting a board, to this machine or to another, is setting
# computer_id like any other part: there is no re-absorb that would fold the object
# back into a description, because the object exists now and pretending otherwise
# would mean deleting a tagged, photographed thing.
#
# Two open questions, left open rather than guessed at:
#
#   * The memory tables (computer_ram_module, computer_ram_chip) are keyed to the
#     computer and stay there. DRAM soldered to the board arguably went with it,
#     but those rows count chips rather than identify them, they are half of how a
#     machine's installed RAM is rendered, and a machine that lost its memory
#     figure by having its board tagged would be a worse record than one whose
#     memory row is filed a level up. Deciding it needs a look at how a refitted
#     board should read, which nothing has asked for yet.
#   * A board detached and then unlinked leaves the machine looking detachable
#     again, and pressing it a second time would put a second object on the shelf
#     where there is one piece of hardware. The register cannot tell an empty case
#     from an unopened one -- both hold no board -- and the person holding the
#     machine can, so the guard below is the one it can make honestly and the
#     history says what happened either way.

def _board_out_of(db, c):
    """The machine's catalogue identity, if a board can be lifted out of it -- or a
    400 naming which of the two conditions it fails.

    It has to be a machine the catalogue names, because what this verb moves is the
    machine's catalogue answers and a PC has none: a PC's board is already an object
    with its own chipset and slot counts written on it.

    And nothing of type motherboard may be linked to it, because a machine has one
    board. Without that, the button is one press per object rather than one object
    per separation, which is the difference between recording what happened and
    inventing hardware."""
    v = machinedb.read(db, c)
    if not v["model_key"]:
        raise HTTPException(
            400, f"{c.asset_id} is not a catalogue machine, so it has no board "
                 f"issue and no chips to move onto one. A PC's board is entered as "
                 f"a part in the ordinary way.")
    fitted = (db.query(Part)
              .filter(Part.computer_id == c.asset_id,
                      Part.type == "motherboard").first())
    if fitted is not None:
        raise HTTPException(
            400, f"{c.asset_id} already has board {fitted.asset_id} linked to it. "
                 f"A machine has one board.")
    return v


def _detach_ctx(db, c, v):
    """What lifting the board out will do, for the page that asks first.

    Read through the catalogue's current words, exactly as _machine_page reads the
    panel this was picked from, so the page names what is about to move in the same
    language it was recorded in."""
    return {"c": c, "aid": c.asset_id, "name": entry.display_name(to_dict(c)),
            "model": machines.full_name(v["model_key"]),
            "issue_label": machines.ISSUE_KEY, "issue": v["issue"],
            "chips": [{"label": machines.chip_label(v["model_key"], role),
                       "variant": variant, "socketed": v["sockets"].get(role)}
                      for role, variant in v["chips"].items()],
            "staying": [(label, value) for label, value in
                        ((machines.STYLE_KEY, v["style"]),
                         (machines.REGION_KEY, v["region"])) if value],
            "noindex": True}


@app.get("/computers/{aid}/detach-board", response_class=HTMLResponse,
         include_in_schema=False)
def gui_detach_board_form(aid: str, request: Request,
                          db: Session = Depends(get_db)):
    c = get_or_404(db, Computer, aid)
    return templates.TemplateResponse(request, "detach.html",
                                      _detach_ctx(db, c, _board_out_of(db, c)))


@app.post("/computers/{aid}/detach-board", include_in_schema=False)
async def gui_detach_board(aid: str, request: Request,
                           db: Session = Depends(get_db)):
    """Make the board in this machine an object of its own.

    The identity move is a rewrite inside the two catalogue tables rather than a
    copy between a machine's and a part's, which is what keying them by a plain
    asset id bought: read the machine's answers, write the board's, blank the two
    the machine has stopped being able to answer. No schema knows this verb exists.

    The machine keeps its asset id, its model, its style, its region and every line
    of its history. It is still the machine on the shelf; what has changed is that
    one of the things it is made of is now on the shelf beside it.

    The photographs come with the form for the reason they do on any create form --
    there is no asset tag to file them under until the part exists -- but here they
    are also the point of the page. A board is photographable at the moment it is
    out and before it goes back in, and that moment does not come round again."""
    c = get_or_404(db, Computer, aid)
    v = _board_out_of(db, c)
    form = await request.form()
    photos = _chosen_photos(form)
    # The maker and the model come across because the maker of the machine made the
    # board and it is the board for that model -- the same carry the duplicate
    # button makes, and without it the board is an asset id with no name in a list.
    # Nothing else does: the condition of a board out of a working machine, where it
    # came from and what it cost are its own answers now, and the machine's history
    # is where it came from.
    board = Part(asset_id=next_asset_id(db), type="motherboard", computer_id=aid,
                 manufacturer=c.manufacturer, model=c.model)
    db.add(board)
    db.flush()
    specdb.write(db, board)
    machinedb.write(db, board, model_key=v["model_key"], issue=v["issue"],
                    chips=v["chips"], sockets=v["sockets"])
    # Blanked, not cleared: clear() would take the model with it, and this machine is
    # still a Spectrum. The style and the region are not touched at all -- the form
    # never asked them of the board and the case did not go anywhere.
    machinedb.write(db, c, issue="", chips={})
    # The board's history opens with where it came from, because that is its birth:
    # it was not created out of nothing, it was taken out of RH-xxxx.
    add_log(db, board.asset_id, f"detached from computer {aid}", kind="created")
    add_log(db, aid, f"board detached as {board.asset_id}, and linked back in")
    db.commit()
    if photos:
        _attach_photos(db, board, "parts", photos)
        db.commit()
    return RedirectResponse(f"/parts/{board.asset_id}", status_code=303)


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


def _asset_log_photos(db, asset_id):
    """The photographs hung on one asset's history, read without touching them --
    what _drop_log_photos will return when the record is actually deleted."""
    return [rel for (rel,) in db.query(LogPhoto.rel)
            .join(LogEntry, LogEntry.id == LogPhoto.log_id)
            .filter(LogEntry.asset_id == asset_id).order_by(LogPhoto.id)]


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
    # The photographs hung on the history count here too. They are not shown in the
    # gallery and are not the portrait, but they are files, they go when the record
    # goes, and the page's promise is "deleted from disk" -- so leaving them out
    # would be under-promising what the button does.
    return {"kind": kind, "obj": obj, "aid": aid,
            "name": entry.display_name(to_dict(obj)),
            "url": _abs_url(request, f"/{kind}/{aid}"),
            "photos": detect_images(kind, aid) + _asset_log_photos(db, aid),
            "logs": _log_count(db, [aid]),
            "inside": inside, "deletable": deletable,
            "kept": [p for p in inside if not p.disposed],
            "parts_photos": sum(len(detect_images("parts", p.asset_id))
                                + len(_asset_log_photos(db, p.asset_id))
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


# --- writing the history, and hanging photographs on it ----------------------
# A note and its photographs go in one gesture, because the entry's message is
# their caption and writing the caption is the same act as choosing them. The two
# routes below are the other half: a photograph for an entry that is already
# written -- the swap the register logged last week, photographed when the lid next
# came off -- and taking one back off again.
#
# Those two are under /items/, not under /computers/ or /parts/, because a history
# entry belongs to an asset id from the shared register rather than to either
# table, which is the whole reason log_entry has no foreign key. /items/<id> is
# already the register-wide address the QR codes print and the JSON log is read
# from. They are POSTs, so the auth gate has them whatever the prefix.

def _note_with_photos(db, aid, form):
    """A note and whatever came with it. Every upload is checked before the entry is
    written, so a rejected file leaves no half-written history behind; and an empty
    message writes nothing at all, photographs included, because there would be no
    entry for them to be the caption of."""
    uploads = _chosen_photos(form)
    row = add_log(db, aid, (form.get("message", "") or "").strip(), kind="note")
    _attach_log_photos(db, row, uploads)
    db.commit()


def _asset_page(db, aid):
    """Where an asset's page is, for a route that serves either kind."""
    for kind, cls in (("computers", Computer), ("parts", Part)):
        if db.get(cls, aid):
            return f"/{kind}/{aid}"
    raise HTTPException(404, f"no asset {aid}")


def _log_entry_or_404(db, aid, log_id):
    """One history entry, and the page to go back to. The asset id in the URL is
    checked against the entry's rather than taken on trust: an entry id on its own
    would let a photograph of one machine be hung on another machine's history."""
    aid = (aid or "").upper()
    where = _asset_page(db, aid)
    row = db.get(LogEntry, log_id)
    if row is None or row.asset_id != aid:
        raise HTTPException(404, f"no history entry {log_id} for {aid}")
    return row, where


@app.post("/items/{aid}/log/{log_id}/photo", include_in_schema=False)
async def gui_log_photo(aid: str, log_id: int, request: Request,
                        db: Session = Depends(get_db)):
    row, where = _log_entry_or_404(db, aid, log_id)
    _attach_log_photos(db, row, _chosen_photos(await request.form()))
    db.commit()
    return RedirectResponse(where, status_code=303)


@app.post("/items/{aid}/log/{log_id}/photo-delete", include_in_schema=False)
async def gui_log_photo_delete(aid: str, log_id: int, request: Request,
                               db: Session = Depends(get_db)):
    row, where = _log_entry_or_404(db, aid, log_id)
    form = await request.form()
    photo = (db.query(LogPhoto).filter(LogPhoto.log_id == row.id,
                                       LogPhoto.rel == form.get("image", ""))
             .first())
    if photo is None:
        raise HTTPException(404, "no such photo on this history entry")
    rel = photo.rel
    db.delete(photo)
    # Nothing is written to the history about this, either way round. An entry
    # gaining or losing a photograph is an edit to the record rather than something
    # that happened to the machine, and a history that logged its own editing would
    # grow a line for every line it already has.
    db.commit()  # the row first: a file cannot be rolled back
    _purge_photos([rel])
    return RedirectResponse(where, status_code=303)


@app.post("/items/{aid}/log/delete", include_in_schema=False)
async def gui_log_delete(aid: str, request: Request, db: Session = Depends(get_db)):
    """Remove history entries.

    Several ids rather than one, because a run of the same thing done in one sitting
    reads as a single line and has to delete as one: "deleted 10 photographs" that
    took one row away and came back saying nine would be a button that does not do
    what it says.

    Every id is checked against this asset before anything goes, the way hanging a
    photograph on an entry is -- an id on its own would let one machine's history be
    deleted from another machine's page.

    Nothing is written to the history about this, which is the rule a history entry
    losing a photograph already follows: editing the record is not something that
    happened to the machine, and a history that logged its own editing would grow a
    line for every line it lost.
    """
    aid = (aid or "").upper()
    where = _asset_page(db, aid)
    form = await request.form()
    ids = [int(i) for i in form.getlist("id") if str(i).strip().isdigit()]
    rows = (db.query(LogEntry).filter(LogEntry.id.in_(ids),
                                      LogEntry.asset_id == aid).all()
            if ids else [])
    if not rows:
        raise HTTPException(404, f"no such history entry for {aid}")
    # The photographs hung on them go too, and their paths are read while the rows
    # are still there: a file is the one thing here that cannot be rolled back.
    found = [r.id for r in rows]
    rels = [rel for (rel,) in db.query(LogPhoto.rel)
            .filter(LogPhoto.log_id.in_(found)).order_by(LogPhoto.id)]
    db.query(LogPhoto).filter(LogPhoto.log_id.in_(found)).delete(
        synchronize_session=False)
    for row in rows:
        db.delete(row)
    db.commit()   # the rows first, then the files
    _purge_photos(rels)
    return RedirectResponse(where, status_code=303)


@app.post("/computers/{aid}/note", include_in_schema=False)
async def gui_computer_note(aid: str, request: Request, db: Session = Depends(get_db)):
    get_or_404(db, Computer, aid)
    _note_with_photos(db, aid, await request.form())
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


# How long a typed "custom" answer may be: the column the answer lands in. The four
# that can become a machine's drive row are held to the row's width, because a picker
# that let you type more than the column holds would fail on save.
_ASK_WIDTHS = {
    "Form factor": ComputerDrive.form_factor.type.length,
    "Size": ComputerDrive.size.type.length,
    "Media": ComputerDrive.media.type.length,
    "Speed": ComputerDrive.speed.type.length,
    "Interface": StorageSpec.interface.type.length,
    "Protocol": StorageSpec.protocol.type.length,
}


def _spec_field(key):
    """The form field a spec key is asked with. The spec_ prefix keeps these clear of
    the part's own columns (a RAM 'Type' spec vs the part type, etc.)."""
    return "spec_" + key.lower().replace(" ", "_").replace("/", "_")


def _storage_asks_ctx():
    """entry.STORAGE_ASKS dressed for the form: the field each group posts, how long a
    custom answer may be, and whether the answer has anywhere to go on a machine's
    drive row -- the four that do are the only ones still asked once a drive is folded
    into a machine, the rest being fields on a part that will not exist."""
    return [ask | {"field": PICK_FIELDS.get(ask["key"], _spec_field(ask["key"])),
                   "max": _ASK_WIDTHS.get(ask["key"], 255),
                   "row": ask["key"] in DRIVE_PICKS,
                   "kinds": list(ask["kinds"])}
            for ask in entry.STORAGE_ASKS]


# The field each display ask posts, named for its spec key like every other field
# on this form. One mapping, used to build the form and to read it back.
DISPLAY_FIELDS = {ask["key"]: _spec_field(ask["key"]) for ask in entry.DISPLAY_ASKS}
DISPLAY_ASK_BY_KEY = {ask["key"]: ask for ask in entry.DISPLAY_ASKS}


def _display_asks_ctx():
    """entry.DISPLAY_ASKS dressed for the form: the field each group posts."""
    return [ask | {"field": DISPLAY_FIELDS[ask["key"]]} for ask in entry.DISPLAY_ASKS]


def _picked_display(form, ask):
    """What one of a screen's groups chose.

    One of the offered answers, or whatever was typed beside "custom" for the
    hardware the list does not name. Blank when nothing was picked, which is how an
    answer is taken back off again.

    An answer is checked against the list it was offered from before it is kept, the
    same way a drive's is: a value posted straight to the endpoint that was never on
    the form is not an answer to the question that was asked.
    """
    field = DISPLAY_FIELDS[ask["key"]]
    custom = " ".join((form.get(field + "_custom", "") or "").split())
    if ask.get("multi"):
        # Several sockets, in the order the list offers them, and then whatever the
        # list could not name -- so the rendering is stable whichever order they
        # were ticked in.
        ticked = [v for v in form.getlist(field) if v in ask["options"]]
        return ", ".join([*ticked, *([custom] if custom else [])])
    raw = (form.get(field, "") or "").strip()
    if raw == "custom":
        return custom
    return raw if raw in ask["options"] else ""


def _part_form_ctx(db, obj, ptype, computer_id, parent_id="", action=None):
    # Existing values come from the typed tables, not from re-parsing the string.
    mb_slots, mb_ram, mb_ports, mb_cpufams = {}, {}, {}, []
    spec_keys = {}
    if obj:
        st = specdb.read(db, obj)
        # The form's text inputs are keyed by display name, and want the same
        # rendering the item page shows ('256 KiB', not 256).
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
    # A board is the one part that can answer the catalogue: it is the thing the
    # board issue and the chip sockets were always about, and a bare one on a shelf
    # is an Amiga 500 board rather than an unidentified green rectangle. Nothing
    # else is offered it -- a SIMM is not a model of machine -- and the catalogue is
    # a quarter of a megabyte of JSON, which is not shipped to a form that cannot
    # use it.
    catalogue = _machine_ctx(obj, db, board=True) if ptype == "motherboard" else {}
    return {
        **catalogue,
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
        # Every question a drive is asked, for the form to build itself from.
        "storage_asks": _storage_asks_ctx(),
        # And every question a screen is asked, the same way.
        "display_asks": _display_asks_ctx(),
        "bezel_kinds": list(entry.BEZEL_KINDS),
        "disk_image_kinds": list(entry.DISK_IMAGE_KINDS),
        "row_kinds": [k for k in entry.STORAGE_KINDS
                      if k not in entry.PART_STORAGE_KINDS],
        "floppy_kind": entry.FLOPPY_KIND, "optical_kind": entry.OPTICAL_KIND,
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
                       if k not in DUP_EXCLUDE and k not in PART_DERIVED_FIELDS})
    ctx["title"] = f"New {entry.type_label(ptype)}"
    ctx["from_part"] = src.asset_id
    # The same rule the duplicate button follows: another board of this model is
    # another board of this model, but which revision it is and what is in its
    # sockets are found by looking at the board in your hand.
    if ctx.get("machine_saved"):
        ctx["machine_saved"] = dict(machinedb.BLANK) | {
            "model_key": ctx["machine_saved"]["model_key"]}
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
        "display": ["Type", "Panel", "Screen size", "Aspect", "Resolution",
                    "Refresh", "Sync", "Dot pitch", "Interface", "Picture",
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
        field = fields.get(key) or _spec_field(key)
        raw = None
        if ptype == "display" and key in DISPLAY_ASK_BY_KEY:
            # Picked from a group rather than typed into one box. Its answer stands,
            # blank included -- that is how a value is taken back off.
            raw = _picked_display(form, DISPLAY_ASK_BY_KEY[key])
        elif ptype == "storage" and key in PICK_FIELDS:
            # Picked from a radio group with a box beside it, not typed into one
            # input, and read only for the kinds the group is offered for. Where it
            # is offered its answer stands, blank included -- that is how a value is
            # taken back off -- and where it is not, nothing here replaces what the
            # record already said.
            raw = _picked_ask(form, key)
        if raw is None:
            raw = (form.get(field, "") or "").strip()
        if not raw:
            continue
        if key == "Ports":
            raw = entry.expand_ports(raw)
        elif key == "Slots":
            raw = entry.expand_slots(raw)
        elif key in ("Size", "Memory") and ptype != "storage":
            # A memory amount is a quantity, and normalises to KiB so it sorts and
            # compares. A drive's size is a media designation and must not: 1.44MB
            # is 1475 KiB only by convention, and nobody calls that disk a 1475 KiB.
            raw = entry.normalise_amount(key, raw)
        specs = entry.merge_spec(specs, key, raw)
    return _append_unmanaged(specs, extra, managed)


# The pick-or-type groups, and the drive row column each becomes where the drive is
# folded into a machine. Which kinds are asked, and what each picks from, is not
# repeated here: it comes from entry.STORAGE_ASKS, the one table the form is built
# from, so a group cannot be on screen for a kind the server reads past.
DRIVE_PICKS = {
    "Form factor": ("drive_form", "form_factor"),
    "Size": ("drive_size", "size"),
    "Media": ("drive_media", "media"),
    "Speed": ("drive_speed", "speed"),
}

# The form field each ask's radio group is named for: the four above keep the
# drive_-prefixed names a machine's own form posts, and the rest are named for their
# spec key like every other field on the part form.
PICK_FIELDS = {
    ask["key"]: (DRIVE_PICKS[ask["key"]][0] if ask["key"] in DRIVE_PICKS
                 else "spec_" + ask["key"].lower().replace(" ", "_"))
    for ask in entry.STORAGE_ASKS if ask["options"]
}

# Which kinds each ask is offered for, straight off the table the form is built
# from, so a group cannot be on screen for a kind the server reads past.
ASK_KINDS = {ask["key"]: ask["kinds"] for ask in entry.STORAGE_ASKS}


def _ask_options(key, kind):
    """The answers one kind is offered for one ask, () where it is asked with a text
    box instead."""
    for ask in entry.storage_asks(kind):
        if ask["key"] == key:
            return ask["options"] or ()
    return ()


def _require_storage_interface(ptype, form):
    """A storage part has to say how it attaches, so that "every SCSI drive" stays a
    question the collection can answer. The radios are marked required, so this is
    the backstop for anything posting straight to the endpoint. A drive folded into a
    machine's drive row never reaches here: it is a field on that machine rather than
    a part, and has no interface column of its own to fill."""
    if ptype != "storage":
        return
    # Read exactly as the value that gets saved is read, or the two could disagree and
    # let a part through with an interface that is then dropped for not being one.
    picked = _picked_ask(form, "Interface")
    if picked is None:
        return
    if not picked:
        raise HTTPException(400, "a storage part needs an interface: one of "
                            + ", ".join(entry.STORAGE_INTERFACES) + ", or custom")


def _picked_ask(form, key):
    """What one of those groups chose: one of the standard answers, or whatever was
    typed beside "custom" for the hardware the list does not name (a 3" Amstrad, a
    Floptical). Blank when nothing was picked, which leaves the description to say
    it.

    None -- not blank -- for a kind the group is not offered for, which is the
    difference between "asked, and the answer is nothing" and "never asked". A radio
    left checked from a kind since changed must not be saved against a drive it never
    described, and a value already on a record must not be thrown away by a group
    that was never on screen to replace it.
    """
    kind = form.get("kind", "") or ""
    if kind not in ASK_KINDS.get(key, ()):
        return None
    field = PICK_FIELDS[key]
    raw = (form.get(field, "") or "").strip()
    if raw == "custom":
        return " ".join((form.get(field + "_custom", "") or "").split())
    # Against this kind's own list, not just any of them. Media and Speed are asked
    # of more than one kind and each kind has its own vocabulary, so the groups share
    # a field name -- which means a radio left checked from a kind since changed
    # arrives here looking like an answer. A CD-RW is not something a floppy takes.
    return raw if raw in _ask_options(key, kind) else ""


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
    picks = {col: _picked_ask(form, key) or ""
             for key, (_f, col) in DRIVE_PICKS.items()}
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
    _require_storage_interface(ptype, form)
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
    # Only a board is filed against the catalogue, whatever a hand-made post claims:
    # the pickers are on no other type's form, and a SIMM filed as a Commodore 64
    # would be a record of nothing anybody owns.
    if ptype == "motherboard" and \
            (mach := _machine_from_form(form, board=True)) is not None:
        machinedb.write(db, obj, **mach)
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
def gui_part(aid: str, request: Request, imgerr: int = 0, fileerr: int = 0,
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
    # say the figures the page says -- not the stored string's exact-to-the-KiB ones.
    blurb = p.summary or _dot(entry.type_label(p.type),
                              " ".join(x for x in (p.manufacturer, p.model, str(p.year or "")) if x),
                              specstruct.join(spec_pairs))
    return templates.TemplateResponse(request, "part.html", {
        "machine": _machine_page(db, p),
        "p": p, "parent": parent, "host": host, "children": children,
        "thumbs": part_thumbs(db, children),
        "item": (pdict := to_dict(p)), "kind": "parts",
        "files": filesdb.for_item(db, pdict), "fileerr": bool(fileerr),
        "candidates": candidates, "computers": computers,
        "images": images, "placeholder": _part_placeholder(db, p),
        "ref_marks": reference_marks("parts", aid),
        "spec_pairs": spec_pairs, "imgerr": bool(imgerr),
        "log": _history(db, aid), "nav": _item_nav(db, aid),
        "live_aid": aid, "live_v": _change_token(db, aid),
        "og": (og := _og(request, entry.display_name(to_dict(p)), blurb,
                         images[0] if images else None)),
        "jsonld": _jsonld(og, p.asset_id, p.manufacturer,
                          entry.type_label(p.type) or "Computer part")})


@app.get("/parts/{aid}/edit", response_class=HTMLResponse, include_in_schema=False)
def gui_edit_part(aid: str, request: Request, type: str = "",
                  db: Session = Depends(get_db)):
    """The edit form. `type` builds it for a type other than the one the part is
    filed under, which is what the type menu asks for: what a part is asked depends
    on its type, so changing that has to fetch the form again to have the new
    type's fields on screen at all. Nothing is saved by looking -- the record still
    says what it always did until the form is submitted.

    Only a type the register knows. A made-up one would fall through to the
    free-text box and then become the part's type on save, which is a way to file a
    SIMM as a "gizmo" by editing a URL."""
    p = get_or_404(db, Part, aid)
    ptype = type if type in entry.TYPE_ORDER else (p.type or "other")
    ctx = _part_form_ctx(db, p, ptype, p.computer_id or "", p.parent_id or "")
    ctx["title"] = f"Edit {aid}"
    return templates.TemplateResponse(request, "part_form.html", ctx)


@app.post("/parts/{aid}/edit", include_in_schema=False)
async def gui_save_part(aid: str, request: Request, db: Session = Depends(get_db)):
    p = get_or_404(db, Part, aid)
    form = await request.form()
    ptype = form.get("type", p.type) or "other"
    _require_storage_interface(ptype, form)
    # Unmanaged keys live in part_attribute; carry them across the edit.
    #
    # Retyping is the case that needs more than those. A part's structured specs are
    # read from the table its old type owns, and only what would not fit there is an
    # attribute -- so on the way to a type with different questions, everything that
    # did fit was being dropped on the floor. Retyping a video card to a display kept
    # nothing but what the display form itself asked: the chip it was built round and
    # how much memory it had simply went.
    #
    # So when the type changes, everything the old type recorded comes across as
    # unmanaged, and _append_unmanaged keeps whatever the new form has no question
    # for. A key both types ask about is left to the form, because that is the answer
    # somebody has just given to a question they were actually shown.
    old_type = p.type or "other"
    carried = (specdb.pairs(db, p) if ptype != old_type
               else specdb.read(db, p).attributes)
    data = await _part_from_form(form, ptype, carried)
    if ptype == "storage" and (form.get("kind", "") or ""):
        data["specs"] = entry.merge_spec(data["specs"], "Kind", form.get("kind"))
    old = {k: getattr(p, k) for k in data}
    for k, v in data.items():
        setattr(p, k, v)
    specdb.write(db, p)
    if ptype == "motherboard":
        if (mach := _machine_from_form(form, board=True)) is not None:
            machinedb.write(db, p, **mach)
    elif p.variant:
        # Retyped out of being a board, and the catalogue answer goes with it: a
        # record saying this RAM stick is an Amiga 500 board describes nothing
        # anybody owns. The same rule as filing a machine out of the catalogue.
        machinedb.clear(db, p)
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
    """A second identical part. On a board the catalogue model comes across for the
    same reason the model field does -- another Amiga 500 board is another Amiga 500
    board -- and the revision and the chips do not, because those are read off the
    board in your hand rather than off the one it was copied from."""
    src = get_or_404(db, Part, aid)
    data = {k: getattr(src, k) for k in PART_FIELDS
            if k not in DUP_EXCLUDE and k not in PART_DERIVED_FIELDS}
    obj = Part(asset_id=next_asset_id(db), **data)
    db.add(obj)
    db.flush()
    specdb.write(db, obj)
    machinedb.duplicated_from(db, src, obj)
    add_log(db, obj.asset_id, f"created as a duplicate of {aid}", kind="created")
    add_log(db, aid, f"duplicated to {obj.asset_id}", kind="duplicate")
    db.commit()
    return RedirectResponse(f"/parts/{obj.asset_id}", status_code=303)


@app.post("/computers/{aid}/duplicate", include_in_schema=False)
def gui_duplicate_computer(aid: str, db: Session = Depends(get_db)):
    """A second machine of the same model. Its memory and drives come across --
    they describe the build -- but its parts do not: those are tagged objects
    fitted to the original, and the copy starts as an empty chassis to fill. The
    catalogue model comes across for the same reason the model field does; the
    board issue and the chips do not, because those are found by opening this
    machine rather than the one it was copied from."""
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
    machinedb.duplicated_from(db, src, obj)
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
    _note_with_photos(db, aid, await request.form())
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
    pid = form.get("part_id", "") or ""
    if not pid:
        return RedirectResponse(f"/parts/{aid}", status_code=303)
    child = get_or_404(db, Part, pid)
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


# --- files kept beside the register -----------------------------------------
# Drivers, manuals, ROM dumps. Not hung off an asset id: a file is tagged with the
# names it is for and every item answering to one of them offers it, which is what
# stops a collection with three of the same card holding the same driver three
# times. app/filesdb.py owns the matching and the bytes; these are the four things
# a person does with one.


def _file_or_404(db, fid):
    row = db.get(StoredFile, fid)
    if row is None:
        raise HTTPException(404, f"file {fid} not found")
    return row


@app.get("/files/{fid}/{name}", include_in_schema=False)
def serve_file(fid: int, name: str, db: Session = Depends(get_db)):
    """Hand over the bytes, always as a download and never as a page.

    An upload is whatever somebody sent, and some of what people send is HTML, or
    an SVG, which a browser asked to display would run as this site with this
    site's cookies. So: one content type for everything, an attachment
    disposition, and nosniff to stop the browser deciding it knows better. `name`
    is in the URL for the sake of the link reading like the file, and is not what
    is opened -- the id is."""
    row = _file_or_404(db, fid)
    path = filesdb.path_of(row)
    if not path.is_file():
        raise HTTPException(404)
    return FileResponse(path, media_type="application/octet-stream", headers={
        "Content-Disposition": f'attachment; filename="{_ascii_filename(row.filename)}"',
        "X-Content-Type-Options": "nosniff",
        "Cache-Control": "public, max-age=3600"})


def _ascii_filename(name):
    """A filename safe to put in a header: no quotes, no control characters, no
    non-ASCII (which a header cannot carry). The stored name keeps the original."""
    cleaned = "".join(ch for ch in (name or "") if ch.isprintable() and ord(ch) < 128)
    return cleaned.replace('"', "").replace("\\", "").strip() or "download"


@app.post("/files", include_in_schema=False)
async def gui_upload_files(request: Request, uploads: list[UploadFile] = File(...),
                           db: Session = Depends(get_db)):
    """Take one or more files and file them under the tags the form carries. The
    tags are prefilled from the item the upload started on, which is the common
    case -- a driver found while looking at the card it is for."""
    form = await request.form()
    tags = filesdb.parse_tags(form.get("tags", ""))
    note = form.get("note", "")
    nxt = _safe_next(form.get("next") or "/files")
    saved, errors = 0, []
    for up in uploads:
        if not (up.filename or "").strip():
            continue
        try:
            if filesdb.save(db, up, tags, note) is not None:
                saved += 1
        except ValueError as exc:
            errors.append(str(exc))
    aid = (form.get("aid") or "").strip().upper()
    if saved and aid:
        add_log(db, aid, f"added {saved} file(s)")
    db.commit()
    return RedirectResponse(nxt + ("?fileerr=1" if errors else ""), status_code=303)


@app.post("/files/{fid}/tags", include_in_schema=False)
async def gui_file_tags(fid: int, request: Request, db: Session = Depends(get_db)):
    """Re-file one: what the box says is the whole list, so a name taken out of it
    stops matching."""
    row = _file_or_404(db, fid)
    form = await request.form()
    filesdb.set_tags(db, row, form.get("tags", ""))
    db.commit()
    return RedirectResponse(_safe_next(form.get("next") or "/files"),
                            status_code=303)


@app.post("/files/{fid}/delete", include_in_schema=False)
async def gui_file_delete(fid: int, request: Request, db: Session = Depends(get_db)):
    row = _file_or_404(db, fid)
    form = await request.form()
    filesdb.remove(db, row)
    db.commit()
    return RedirectResponse(_safe_next(form.get("next") or "/files"),
                            status_code=303)


@app.get("/files", response_class=HTMLResponse, include_in_schema=False)
def gui_files(request: Request, tag: str = "", db: Session = Depends(get_db)):
    """Everything on file, for finding the driver whose card is not in front of
    you and for seeing what a tag is spelled as before typing it again."""
    return templates.TemplateResponse(request, "files.html", {
        "files": filesdb.all_files(db, tag), "tag": tag,
        "og": _og(request, "Files", "Drivers, manuals and disks kept with the "
                                    "hardware they belong to")})


@app.get("/api/files", tags=["files"])
def api_list_files(tag: str = "", db: Session = Depends(get_db)):
    """Files kept beside the register, newest first, each with the names it is
    filed under. `tag` narrows it to one name, matched the way the pages match:
    ignoring case and spacing."""
    return [{"id": f.id, "filename": f.filename, "size": f.size, "note": f.note,
             "tags": f.tags, "created_at": f.created_at,
             "url": f"/files/{f.id}/{quote(f.filename)}"}
            for f in filesdb.all_files(db, tag)]
