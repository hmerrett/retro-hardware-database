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
import os
import random
import re
import secrets
import time
from collections import Counter
from datetime import UTC, date, datetime, timedelta
from pathlib import Path
from types import SimpleNamespace
from urllib.parse import parse_qs, quote, urlparse
from xml.sax.saxutils import escape

from fastapi import (Depends, FastAPI, File, HTTPException, Query, Request,
                     UploadFile)
from fastapi.responses import FileResponse, HTMLResponse, RedirectResponse, Response
from itsdangerous import BadSignature, SignatureExpired, URLSafeTimedSerializer
from markupsafe import Markup
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from sqlalchemy import func
from sqlalchemy.orm import Session

from . import __version__
from . import (drivedb, entry, filesdb, labels, machinedb, machines,
               projects, ramdb, specdb, specstruct, thumbs)
from .common import (  # shared foundations; re-exported here so existing call-sites resolve
    BRANDING_DIR, IMAGE_EXTS, IMAGES_DIR, REGISTER, RELIABILITY_MIN, STATIC_DIR,
    _file_ver, _maker_reliability, _visible, branded, folder_images, to_dict)
from .common import _all_years  # noqa: F401 -- re-exported for the tests, unused here
from .db import get_db
from .ids import next_asset_id
from .stats import FACTS_SHOWN, _collection_stats, _facts, _facts_projects, _facts_register  # noqa: F401
from .photos import (  # photo/image helpers, lifted out of this module
    _asset_log_photos, _attach_log_photos, _chosen_photos, _crop_op, _delete_image,
    _drop_log_photos, _edit_image, _favicon_for_rel, _fetch_reference_photo,
    _image_cache, _mark_reference, _photo_edit_redirect, _purge_photos,
    _restore_original, _rotate_op, _save_photo, _set_primary_photo, _tuneup_op,
    detect_images, has_original, img_srcset, img_url, is_reference, pick_images,
    reference_marks, tuned_photos)
from .photos import (  # noqa: F401 -- re-exported for the tests, unused here
    WM_CACHE, WM_SRC, WM_SCALE, WM_MIN_PX, WM_BUILD, _watermarked_file, _wm_forget,
    _is_own_photo, _image_size, _ref_sidecar, _write_atomically, _original_of,
)
from .photos import _storage_placeholder  # placeholder routing shared with search
from .search import (  # search, suggestions and the /browse views, lifted out of this module
    _browse_view, _projects_matching, _search, _suggest)
from .search import search_terms  # noqa: F401 -- re-exported for the tests, unused here
from .models import (AssetChip, AssetVariant, Computer, ComputerDrive,
                     ComputerRamChip, ComputerRamModule, LogEntry, LogPhoto,
                     Part, Project, ProjectAsset, ProjectOrder, ProjectTask,
                     StorageSpec, StoredFile)
from .schemas import (ComputerCreate, ComputerIn, ComputerOut, PartCreate,
                      PartIn, PartOut, ProjectIn, ProjectItemIn, ProjectOrderIn,
                      ProjectOrderOut, ProjectOut, ProjectTaskIn, ProjectTaskOut)

# Schema is owned by Alembic now (entrypoint.sh runs `alembic upgrade head` on
# start); no create_all here.

app = FastAPI(title="Retro Hardware Database API", version=__version__)
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
    today=lambda: date.today().isoformat(),
    # A project's vocabulary, so a status reads as words in every place one is
    # shown and the money is written the same way on the list page and the item.
    money=projects.money, status_label=projects.status_label,
    # The statuses that mean a project is over, so the pages that dim a finished
    # one do not each keep their own idea of which those are.
    closed_states=projects.CLOSED)
# A filter rather than a global, because it reads as one thing done to another at
# every one of its uses: `{{ c.notes | linked }}`. It is for text shown as text --
# prose, notes, spec values, history entries -- and never for an attribute, which
# cannot hold an anchor and would only get the escaping.
templates.env.filters["linked"] = entry.linked

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
        og["image_alt"] = "The Retro Hardware Database"
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
def _resolve_secret_key(secret: str, auth_enabled: bool) -> str:
    """The key that signs the session cookie. It must not be derived from the
    credentials: the cookie's payload is a constant, so a key made from the
    password would turn any leaked cookie into an offline oracle for it, with no
    rate limit to slow the guessing. Require it explicitly when auth is on; when
    the app runs open the cookie gates nothing, so a throwaway per-process key
    will do."""
    if secret:
        return secret
    if auth_enabled:
        raise RuntimeError(
            "RHDB_SECRET_KEY must be set when authentication is enabled. "
            "Generate one with: openssl rand -hex 32"
        )
    return secrets.token_hex(32)


SECRET_KEY = _resolve_secret_key(os.getenv("RHDB_SECRET_KEY", ""), AUTH_ENABLED)
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


class _RateLimiter:
    """A sliding-window limiter for login attempts, keyed by client IP. In-memory,
    which suits a single-worker deployment; a restart clears it, which is fine for
    slowing a guessing attack rather than accounting for one."""

    def __init__(self, max_attempts: int, window: float):
        self.max_attempts = max_attempts
        self.window = window
        self._hits: dict[str, list[float]] = {}

    def _fresh(self, key: str, now: float) -> list[float]:
        hits = [t for t in self._hits.get(key, []) if now - t < self.window]
        self._hits[key] = hits
        return hits

    def check(self, key: str, now: float | None = None) -> bool:
        """Whether another attempt is allowed for this key right now."""
        now = time.monotonic() if now is None else now
        return len(self._fresh(key, now)) < self.max_attempts

    def record(self, key: str, now: float | None = None) -> None:
        now = time.monotonic() if now is None else now
        self._fresh(key, now).append(now)

    def reset(self, key: str) -> None:
        self._hits.pop(key, None)


# 10 tries in five minutes is generous for a person and slow for a guesser.
LOGIN_MAX_ATTEMPTS = int(os.getenv("RHDB_LOGIN_MAX_ATTEMPTS", "10"))
LOGIN_WINDOW = int(os.getenv("RHDB_LOGIN_WINDOW", "300"))
_login_limiter = _RateLimiter(LOGIN_MAX_ATTEMPTS, LOGIN_WINDOW)


def _client_ip(request: Request) -> str:
    """The visitor's address, for rate-limiting. Behind Caddy every request's
    immediate peer is Caddy, which appends the real client to X-Forwarded-For, so
    the rightmost entry is the one a client cannot forge (anything it sends itself
    sits to the left of what Caddy adds). Fall back to the peer address when there
    is no proxy, as in local dev."""
    xff = request.headers.get("x-forwarded-for")
    if xff:
        return xff.rsplit(",", 1)[-1].strip()
    return request.client.host if request.client else "?"


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
    return request.method == "GET" and _public_page(request.url.path)


def _public_page(path: str) -> bool:
    """Whether a visitor who is not logged in may see this path at all.

    A question of its own because logging out asks it too: the way out lands on the
    page you were on, and "the page you were on" is only somewhere to land if it is
    still somewhere you can look at."""
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
    # Projects read like the rest of the site: what is being built and what is
    # waiting on a part is as much of the collection as the shelf is. The editing
    # GETs come out by the same rule the asset pages follow, and every write is a
    # POST and so already behind the login. What a visitor is not shown is on the
    # page rather than here -- see project.html on what an order costs.
    if path == "/projects":
        return True
    if path.startswith(("/computers/", "/parts/", "/projects/")):
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
    has_basic = request.headers.get("authorization", "").startswith("Basic ")
    basic_ok = api_path and has_basic and _check_basic(request)
    request.state.authed = (not AUTH_ENABLED or _check_cookie(request) or basic_ok)
    # A wrong Basic credential is a guess at the API's door; rate-limit it as the
    # login form is. Only counted when a Basic header was actually sent and wrong,
    # so ordinary anonymous reads are untouched.
    if AUTH_ENABLED and api_path and has_basic and not basic_ok:
        ip = _client_ip(request)
        if not _login_limiter.check(ip):
            return Response("Too many failed attempts, try again later",
                            status_code=429)
        _login_limiter.record(ip)
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
    ip = _client_ip(request)
    if not _login_limiter.check(ip):
        return templates.TemplateResponse(request, "login.html",
                                          {"next": nxt, "error": True,
                                           "rate_limited": True, "noindex": True},
                                          status_code=429)
    ok = (AUTH_ENABLED
          and secrets.compare_digest(form.get("username", ""), AUTH_USER)
          and secrets.compare_digest(form.get("password", ""), AUTH_PASS))
    if not ok:
        _login_limiter.record(ip)
        return templates.TemplateResponse(request, "login.html",
                                          {"next": nxt, "error": True, "noindex": True},
                                          status_code=401)
    _login_limiter.reset(ip)
    resp = RedirectResponse(nxt, status_code=303)
    resp.set_cookie(COOKIE, _signer.dumps("ok"), max_age=SESSION_MAX_AGE,
                    httponly=True, samesite="lax",
                    secure=request.headers.get("x-forwarded-proto") == "https")
    return resp


def _way_out(nxt: str) -> str:
    """Where logging out lands: the page it was done from, the way logging in puts
    you back on the page you asked for. The two are the same courtesy and they are
    now the same sentence.

    Unless that page was one the login was what let you see. An edit form is not
    somewhere to land -- the gate would bounce you straight back to the login you
    have just left -- but there is an item behind every edit form, and that is a
    page anybody may read, so that is where it goes. Anything else with a door on
    it (a new form, a delete confirmation, a label) has nothing behind it and falls
    back to the gallery."""
    nxt = _safe_next(nxt)
    path = urlparse(nxt).path
    if _public_page(path):
        return nxt
    item, _, last = path.rpartition("/")
    if last == "edit" and _public_page(item):
        return item
    return "/"


@app.post("/logout", include_in_schema=False)
async def gui_logout(request: Request):
    form = await request.form()
    resp = RedirectResponse(_way_out(form.get("next", "") or ""), status_code=303)
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



# Container paths by default (the `images` volume and the goaccess report mount);
# overridable so the app can be imported and run outside Docker for local
# development, which the hardcoded absolute paths used to make impossible.


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




# --- the pointless department -----------------------------------------------
# Figures that answer nothing anyone needs to know, which is the point of them. A
# page of totals says how big the collection is; these say what it is like.







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
        "Disallow: /projects/new\n"
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
            (f"{base}/machines", None), (f"{base}/projects", None)]
    for c in db.query(Computer.asset_id).order_by(Computer.asset_id):
        urls.append((f"{base}/computers/{c.asset_id}", last.get(c.asset_id)))
    for p in db.query(Part.asset_id).order_by(Part.asset_id):
        urls.append((f"{base}/parts/{p.asset_id}", last.get(p.asset_id)))
    # The projects read out of the same `last`, because a project's history is
    # log_entry keyed by its own register id -- the same rows, the same query.
    # A private project is not named here. The sitemap is the one of the five that
    # is read by machines rather than people, and a tag in it is an invitation.
    for pr in (db.query(Project.asset_id).filter(Project.private.is_(False))
               .order_by(Project.asset_id)):
        urls.append((f"{base}/projects/{pr.asset_id}", last.get(pr.asset_id)))
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




templates.env.globals["icon_ver"] = _file_ver(branded("favicon.ico"))
templates.env.globals["css_ver"] = _file_ver(STATIC_DIR / "app.css")
# Social sites cache a card hard, so its URL carries the artwork's hash too.
SITE_CARD_VER = _file_ver(branded(SITE_CARD[0].removeprefix("/static/")))
_ICON_CACHE = {"Cache-Control": "public, max-age=86400"}


# Browsers and crawlers request these at the domain root regardless of markup.
@app.get("/favicon.ico", include_in_schema=False)
def favicon():
    return FileResponse(branded("favicon.ico"), headers=_ICON_CACHE)


@app.get("/apple-touch-icon.png", include_in_schema=False)
@app.get("/apple-touch-icon-precomposed.png", include_in_schema=False)
def apple_touch_icon():
    return FileResponse(branded("apple-touch-icon.png"), headers=_ICON_CACHE)


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
_static = _CachedStatic(directory=str(STATIC_DIR))
# The deployment's own artwork first, the shipped placeholders behind it. This is
# StaticFiles' own search list, so a name that is not overridden falls through to
# what ships, and the traversal checks are the ones it already makes on every
# request -- a directory in front of another is exactly what `packages` does.
if BRANDING_DIR.is_dir():
    _static.all_directories = [str(BRANDING_DIR), *_static.all_directories]
app.mount("/static", _static, name="static")



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




def _now():
    """Naive UTC, matching the column and every row already in it. utcnow() is
    deprecated, and an aware value here would be inconsistent with the history
    written before this."""
    return datetime.now(UTC).replace(tzinfo=None)


# An entry whose content is the photographs on it rather than any words. A kind of
# its own rather than a note that happens to be blank, so that everything which asks
# what an entry is gets an answer: the page draws it its own chip, the fold leaves it
# alone, and add_log knows where the rule about empty messages stops.
PHOTO_ENTRY = "photo"


def add_log(db, asset_id, message, kind="change"):
    """Record a dated history entry for an asset, and hand the row back for
    anything that wants to hang photographs on it. The caller commits.

    An empty message writes nothing and returns None: there is no such thing as an
    entry that does not say anything. Except a photograph entry, which says it
    without words -- a picture of the board with the capacitor missing is a thing
    said about the board, and it used to need a sentence typed beside it before the
    register would keep it.
    """
    if not message and kind != PHOTO_ENTRY:
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
    if field in ("acquired_date", "disposed_at",
                 "started_at", "target_date", "finished_at"):
        return _parse_date(raw)
    if field == "disposed":
        return (raw or "").strip() not in ("", "0", "false")
    return raw or ""


def _field_diffs(old, new, keys, semantic_specs=False):
    """A one-change-per-line diff of old vs new field values, for the change log.
    specs is broken down per spec key; re-canonicalising an unchanged specs
    string produces no diff.

    Nothing is skipped here any more. It used to leave out `project` and
    `project_note`, so that a plan could not reach an item's public history; a plan
    is a project of its own now, with a page and a privacy of its own, and there is
    nothing left on a computer or a part that has to be kept out of its own log."""
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


def _project_ids(db, asset_id, prefetched=None):
    """The projects an item is on, as tags, for the API's read shape.

    `prefetched` is the whole page's answer in one query, which is what the list
    endpoints hand in: asking per row would be a query per machine on the page that
    would notice, the same reason machinedb.read_many exists.

    Nothing is hidden here. A private project is kept back from the public pages,
    and the API is behind the login entire -- there is nobody on this side of it to
    keep anything from."""
    if prefetched is not None:
        return [p.asset_id for p in prefetched.get(asset_id, [])]
    return [p.asset_id for p in projects.projects_for(db, asset_id)]


def _computer_out(db, computer, identity=None, in_projects=None):
    """One computer as the API returns it: its own columns, the catalogue identity
    read from its rows rather than from the line rendered off them, and what it is
    on the list of."""
    return to_dict(computer) | {
        "machine": _machine_out(db, computer, identity),
        "projects": _project_ids(db, computer.asset_id, in_projects)}


def _part_out(db, part, identity=None, in_projects=None):
    """One part as the API returns it. The same pieces as a computer's, and for a
    part that is not a board `machine` is simply null."""
    return to_dict(part) | {
        "machine": _machine_out(db, part, identity),
        "projects": _project_ids(db, part.asset_id, in_projects)}


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
    # One pair of queries for the whole list rather than a pair per machine, and the
    # memberships in one more for the same reason.
    identities = machinedb.read_many(db, rows)
    in_projects = projects.projects_by_asset(db, [c.asset_id for c in rows])
    return [_computer_out(db, c, identities.get(c.asset_id, dict(machinedb.BLANK)),
                          in_projects)
            for c in rows]


@app.post("/api/computers", response_model=ComputerOut, tags=["computers"])
def api_create_computer(data: ComputerCreate, db: Session = Depends(get_db)):
    fields = data.model_dump()
    # Read before anything is written, so a project tag that names nothing is a 404
    # rather than a machine entered and a note dropped.
    jobs, work = _work_from_api(db, fields)
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
    if jobs or work is not None:
        _take_on_work(db, obj.asset_id, jobs, work)
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
    in_projects = projects.projects_by_asset(db, [p.asset_id for p in rows])
    return [_part_out(db, p, identities.get(p.asset_id, dict(machinedb.BLANK)),
                      in_projects)
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
def api_create_part(data: PartCreate, db: Session = Depends(get_db)):
    fields = data.model_dump()
    jobs, work = _work_from_api(db, fields)
    machine = fields.pop("machine")
    _check_links(db, fields)
    obj = Part(asset_id=next_asset_id(db), **fields)
    db.add(obj)
    db.flush()
    specdb.write(db, obj)
    if machine is not None:
        _board_from_api(db, obj, data.machine)
    add_log(db, obj.asset_id, "created", "created")
    if jobs or work is not None:
        _take_on_work(db, obj.asset_id, jobs, work)
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






templates.env.globals["img_url"] = img_url
templates.env.globals["img_srcset"] = img_srcset
templates.env.globals["THUMB_CARD"] = 300
templates.env.globals["THUMB_MAIN"] = 1200
templates.env.globals["human_size"] = filesdb.human_size
templates.env.globals["max_file_mb"] = filesdb.MAX_BYTES // (1024 * 1024)




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
    # A project that was about this part stops being about it. By hand for the same
    # reason: project_asset.asset_id is a plain register id with no foreign key
    # behind it, so nothing in the database will clear it.
    projects.forget_asset(db, aid)
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
    projects.forget_asset(db, aid)
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


def _do_photo_tuneup(db, model, kind, aid, form):
    get_or_404(db, model, aid)
    rel = form.get("image", "")
    # Pressing it twice is the accident this guards: the file is re-encoded on
    # every edit, so a second tuneup costs another generation of JPEG for a
    # picture that has already had the fix. Nothing to do is not an error -- the
    # photograph is in the state the button asks for -- so it returns quietly
    # rather than sending back a failure for a button that appears to have worked.
    if has_original(rel) and rel in detect_images(kind, aid):
        return
    _edit_image(kind, aid, rel, _tuneup_op(), revertible=True)
    add_log(db, aid, "tuned a photo")
    db.commit()


def _do_photo_revert(db, model, kind, aid, form):
    get_or_404(db, model, aid)
    rel = form.get("image", "")
    if rel not in detect_images(kind, aid):
        raise HTTPException(404, "no such photo for this item")
    _restore_original(rel)
    add_log(db, aid, "reverted a tuned photo")
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
    """The URL printed on labels: resolve an asset id to its page, whichever of the
    three things in the register it turns out to name. Keeps the same /items/<id>
    scheme the old QR codes used.

    A project is in here despite never being printed on a label, because this is the
    register-wide address and a project holds a register id. Its history is written
    through /items/<id> like everything else's, and a route that could not find it
    would be a page whose note bar posted into nowhere."""
    return RedirectResponse(_asset_page(db, aid.upper()), status_code=307)


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


@app.get("/suggest", include_in_schema=False)
def gui_suggest(request: Request, q: str = "", db: Session = Depends(get_db)):
    items, total = _suggest(db, q, authed=request.state.authed)
    return {"q": q, "items": items, "total": total}


@app.get("/", response_class=HTMLResponse, include_in_schema=False)
def gui_index(request: Request, q: str = "", db: Session = Depends(get_db)):
    rows = _catalogue_rows(db, precise_times=request.state.authed)
    total = len(rows)
    hit_projects = 0
    if q.strip():
        rows = _search(db, rows, q, request.state.authed)
        # Counted, not shown. The grid is a wall of photographs of things owned and
        # a project is not one of those, so it does not become a card here -- but a
        # search that quietly ignored a whole section of the site would be a search
        # bar that says "anything" and means "the shelf". The line the page draws
        # from this points at /projects with the same query.
        hit_projects = len(_projects_matching(
            db, projects.summaries(db, authed=request.state.authed), q,
            request.state.authed))
    n_computers = sum(1 for r in rows if r["kind"] == "computer")
    return _grid_page(
        request, rows, q=q, searched=bool(q.strip()), total=total,
        hit_projects=hit_projects,
        og=_og(request, "Retro Hardware Database",
               f"{n_computers} computers and {len(rows) - n_computers} parts "
               "in the collection."))


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
            # The projects in hand, for the work box at the foot of the form.
            "work_projects": projects.open_projects(db) if db is not None else [],
            "dl": _datalists(db, computer=True) if db is not None else {},
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
    # After the flush above, because a membership is refused for an asset that is not
    # in the register yet -- and this one is being entered as we speak.
    _work_from_form(db, obj, form)
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
        "dl_filenotes": _answers_given(db, StoredFile.note),
        "in_projects": projects.projects_for(db, aid, request.state.authed),
        # For the picker in that panel, which only an owner is shown -- so a
        # visitor's page does not ask the question at all.
        "work_projects": (projects.open_projects(db) if request.state.authed
                          else []),
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
        "tuned": tuned_photos("computers", aid),
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
    _work_from_form(db, c, form)
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
    """Whatever the note bar was filled in with: words, photographs, or both.

    Neither half needs the other. Words alone are a note, as they always were.
    Photographs alone are an entry of their own with its own time on it, because a
    photograph of the thing is a thing said about it -- and having to type a sentence
    first was a toll on the commonest gesture in the register. Both together stay one
    entry: they were one gesture, and the words are the caption.

    Nothing at all writes nothing at all. Every upload is still checked before the
    entry is written, so a refused file leaves no half-written history behind."""
    uploads = _chosen_photos(form)
    message = (form.get("message", "") or "").strip()
    if not message and not uploads:
        return
    row = add_log(db, aid, message, kind="note" if message else PHOTO_ENTRY)
    _attach_log_photos(db, row, uploads)
    db.commit()



# The two of them that can be put on the list of things wanting work. A project is
# in the register and answers at /items/<id> like the others, but it cannot be
# flagged as one: it is already what the flag points at, and `Project` has no such
# column -- so a route handed one would set an attribute on the instance, commit
# nothing, and redirect as though it had worked.
FLAGGABLE = REGISTER[:2]


def _asset_find(db, aid, kinds=REGISTER):
    """One thing from the shared register and the page it lives on, whichever kind
    it turns out to be -- or None for no such asset.

    What a route serving more than one kind actually wants: the log routes below
    only needed the address, but a route that changes something needs the row as
    well, and looking it up twice is how the two come to be about different items.

    `kinds` narrows which tables are searched, for the callers that can only act on
    some of them."""
    aid = (aid or "").strip().upper()
    for kind, cls in kinds:
        obj = db.get(cls, aid)
        if obj is not None:
            return obj, f"/{kind}/{aid}"
    return None


def _asset_or_404(db, aid, kinds=REGISTER):
    """The same, for the callers that have nothing to say about a miss. Which is
    most of them: an id in a URL that is not an asset is a broken link, while an id
    typed into a box is a typo, and only the second has anywhere useful to go."""
    found = _asset_find(db, aid, kinds)
    if found is None:
        raise HTTPException(404, f"no asset {(aid or '').strip().upper()}")
    return found


def _asset_page(db, aid):
    """Where a register id's page is, for a route that serves any of the kinds."""
    return _asset_or_404(db, aid)[1]


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
    # A photograph entry is its photographs. Take the last one off it and there is
    # nothing left that it said, so the entry goes too rather than standing in the
    # log as a chip with nothing beside it. An entry with words keeps its line: the
    # words are still what it said.
    if row.kind == PHOTO_ENTRY:
        db.flush()
        if not db.query(LogPhoto).filter(LogPhoto.log_id == row.id).count():
            db.delete(row)
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


@app.post("/computers/{aid}/photo-tuneup", include_in_schema=False)
async def gui_computer_photo_tuneup(aid: str, request: Request,
                                    db: Session = Depends(get_db)):
    form = await request.form()
    _do_photo_tuneup(db, Computer, "computers", aid, form)
    return RedirectResponse(_safe_next(form.get("next") or f"/computers/{aid}"),
                            status_code=303)


@app.post("/computers/{aid}/photo-revert", include_in_schema=False)
async def gui_computer_photo_revert(aid: str, request: Request,
                                    db: Session = Depends(get_db)):
    form = await request.form()
    _do_photo_revert(db, Computer, "computers", aid, form)
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
        to_dict(c), rows, labels.COMPUTER, small=bool(small),
        form_factor=(specdb.scalars(db, board).get("form_factor", "")
                     if board else ""))
    return Response(pdf, media_type="application/pdf", headers={
        "Content-Disposition": f'inline; filename="{aid}{"-small" if small else ""}.pdf"'})


# --- GUI: parts (guided, typed entry) --------------------------------------

def _answers_given(db, *columns, limit=200):
    """Every answer already given to a free-text field, commonest first, for the
    pick list on the box that asks it.

    A field answered the same way over and over wants to offer its own past
    answers. `source` is the case that asked for this: 154 of them, in 69
    spellings, among which "Pete Farm" sixteen times and "Farm Pete" eight -- one
    person and one provenance, recorded as two, and now unfindable as one. A list
    does not stop anybody typing something new (it is a datalist, not a menu); it
    only makes the answer already given the easier one to give again.

    Commonest first, because a datalist is offered in the order it is written and
    the answer given twenty times is the likelier one. Case and surrounding space
    fold together for the counting, and the spelling offered back is the one used
    most -- so "eBay" wins over "ebay" by being what was actually typed, rather
    than by any rule about capitals.

    The counting is done here rather than by the query it would obviously be done
    by. MariaDB's collation folds case and ignores trailing spaces, so GROUP BY on
    the column has already merged "eBay", "ebay" and "eBay " before we see them,
    and what comes back as the group's label is whichever row it happened to read
    first -- which makes "the spelling used most" whatever the storage engine felt
    like that morning. Reading the values and counting them here makes the rule
    ours. It is a column of a few hundred short strings; the query it replaces was
    not saving anything worth this.

    Capped: this goes into the markup of every form that asks, and two hundred is
    already past what anybody scrolls.
    """
    counts, spellings = Counter(), {}
    for column in columns:
        for (value,) in db.query(column):
            text = (value or "").strip()
            if not text:
                continue
            key = text.casefold()
            counts[key] += 1
            spellings.setdefault(key, Counter())[text] += 1
    return [spellings[key].most_common(1)[0][0]
            for key, _ in counts.most_common(limit)]


def _known_makes(db):
    """The manufacturers and (make, model) pairs already recorded, for the new-part
    form's pick lists and for spotting that a part being entered is a second of
    something already here. One representative asset id per pair, so the form can
    offer to start from it.

    The makes come from both tables. A part's maker and a machine's are the same
    kind of fact and often the same company -- the Amstrad that made the machine
    made the board in it -- so a make used only on computers is still worth
    offering here; the (make, model) pairs stay parts-only, because what they are
    for is starting a new part from an identical one."""
    makes = _answers_given(db, Part.manufacturer, Computer.manufacturer)
    pairs = (db.query(Part.manufacturer, Part.model, Part.type,
                      func.max(Part.asset_id))
             .filter(Part.manufacturer != "", Part.model != "")
             .group_by(Part.manufacturer, Part.model, Part.type).all())
    known = [{"m": mk, "d": md, "t": t, "id": aid} for mk, md, t, aid in pairs]
    models = sorted({p["d"] for p in known})
    return makes, models, known


def _datalists(db, computer=False):
    """The pick lists a form's free-text boxes are offered, in one place because
    two forms ask several of the same questions.

    `computer` adds the three a machine is asked and a part is not. A part's
    equivalent of them is its typed spec table, which has its own vocabularies."""
    lists = {"source": _answers_given(db, Computer.source, Part.source)}
    if computer:
        lists |= {
            "makes": _answers_given(db, Computer.manufacturer, Part.manufacturer),
            # A machine's models only. A list of every card and drive model as well
            # would bury "PC1512" in a thousand answers to a different question.
            "models": _answers_given(db, Computer.model),
            "chassis": _answers_given(db, Computer.chassis),
            "os": _answers_given(db, Computer.os),
            "cpu": _answers_given(db, Computer.cpu),
        }
    return lists


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
        "work_projects": projects.open_projects(db),
        "dl": _datalists(db),
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
    for f in ("manufacturer", "model", "name", "year", "serial", "condition",
              "source", "acquired_date", "url", "summary", "notes", "disk_image"):
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
                # And for the same reason, work noted while adding it is the
                # machine's: the drive is a field on that record and has no tag of
                # its own for a project to be about.
                _work_from_form(db, c, form)
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
    _work_from_form(db, obj, form)
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
        "dl_filenotes": _answers_given(db, StoredFile.note),
        "in_projects": projects.projects_for(db, aid, request.state.authed),
        # For the picker in that panel, which only an owner is shown -- so a
        # visitor's page does not ask the question at all.
        "work_projects": (projects.open_projects(db) if request.state.authed
                          else []),
        "candidates": candidates, "computers": computers,
        "images": images, "placeholder": _part_placeholder(db, p),
        "ref_marks": reference_marks("parts", aid),
        "tuned": tuned_photos("parts", aid),
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
    _work_from_form(db, p, form)
    db.commit()
    return RedirectResponse(f"/parts/{aid}", status_code=303)


# A duplicate is a second identical unit, so it copies what describes the model --
# the fields, the specs, a machine's fitted memory and drives -- and nothing that
# belongs to the original object: its photos, its disposal, its provenance
# (source / acquired date / notes), its serial number, and where it sits. A second
# card is a second card, not another card in the same slot, so the copy starts
# unplaced -- and no two objects ever wore the same serial.
#
# A plan used to be on that list too, when one was a column here. It is a project of
# its own now, and a project is attached to an asset rather than copied with one --
# so a duplicate is simply not in it, and there is nothing to leave out.
DUP_EXCLUDE = {"image", "disposed", "disposed_at", "disposed_note", "source",
               "acquired_date", "notes", "serial", "computer_id", "parent_id"}


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


@app.post("/parts/{aid}/photo-tuneup", include_in_schema=False)
async def gui_part_photo_tuneup(aid: str, request: Request,
                                    db: Session = Depends(get_db)):
    form = await request.form()
    _do_photo_tuneup(db, Part, "parts", aid, form)
    return RedirectResponse(_safe_next(form.get("next") or f"/parts/{aid}"),
                            status_code=303)


@app.post("/parts/{aid}/photo-revert", include_in_schema=False)
async def gui_part_photo_revert(aid: str, request: Request,
                                    db: Session = Depends(get_db)):
    form = await request.form()
    _do_photo_revert(db, Part, "parts", aid, form)
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
    pdf = labels.render_pdf(to_dict(p), [], labels.PART, small=bool(small),
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


# --- projects: the work, as against the things it is done to ------------------
# Everything above this line describes what is owned. A project describes what is
# intended, and it is the one kind of record here that can be about nothing yet:
# the idea comes months before the hardware, and a plan to build a 486 has to be
# writable on the evening it is had rather than on the day the board turns up.
#
# It is a register asset, which is what makes this section short. A project takes
# an id from the same allocator, so its history, its notes and the photographs on
# them are the code the machines already use, unaltered -- _history.html renders
# here word for word because the note bar posts to /<kind>/<id>/note and this is
# simply a third kind. app/projects.py owns the vocabulary, the money and the
# reading of the three child tables; what is here is what a person does with one.

PROJECT_FIELDS = ("name", "status", "summary", "notes",
                  "started_at", "target_date", "finished_at", "private")


def _project_from_form(form):
    data = {k: _coerce(k, form.get(k, "")) for k in PROJECT_FIELDS}
    data["name"] = (data["name"] or "").strip()
    data["status"] = projects.clean_status(data["status"])
    # A tickbox that is not ticked sends nothing at all, so its absence is the
    # answer rather than a missing one.
    data["private"] = bool(form.get("private"))
    return data


def _project_form_ctx(p, title, error=""):
    return {"p": p, "title": title, "statuses": projects.STATUSES, "error": error}


def _project_named(p):
    """A project in a sentence written in another item's history. The name, because
    that is what it is known by, with the id so the line still points somewhere when
    two projects are called nearly the same thing."""
    return f"{p.name or 'a project'} ({p.asset_id})"


# How many photographs the suggestion at the top of the projects page carries, and
# how many of the project's jobs it lists. Enough to say what the thing is and what
# is left to do on it; more would be the project's own page, drawn twice.
TODAY_PHOTOS = 3
TODAY_TASKS = 3

# The longest a silence counts for in the draw. A project nobody has touched for
# three years is not thirty times more overdue than one left a month ago -- past
# some point it is simply "not for a while", and without a ceiling the oldest
# project would win every draw and the feature would be a fixture.
TODAY_QUIET_CAP = 180

# What being stalled is worth, as against merely being quiet. Stalled is the state
# somebody chose to record: it says out loud that this one is waiting on a part, the
# weather or the will, and those are exactly the ones that never come up again on
# their own.
TODAY_STALLED_WEIGHT = 2


def _project_of_the_day(db, authed):
    """One project to suggest, drawn now, or None if there is nothing in hand.

    Weighted towards the neglected, because the point of a nudge is the thing you
    had forgotten and not the one you were doing yesterday. A project's weight is
    how long its history has been quiet, capped, doubled if its status says stalled;
    a project touched today weighs one, which keeps it in the draw rather than
    excluding it -- what was worked on this morning is still a reasonable answer to
    what to do this afternoon.

    Drawn on every visit rather than once a day. It is a suggestion and not a queue:
    looking again for another one is a thing somebody will want to do, and the
    weighting means the same project coming up twice running is unlikely rather than
    impossible.

    A visitor is offered only the public ones, for the reason the list below them
    is filtered (see _visible)."""
    q = _visible(db.query(Project).filter(Project.status.notin_(projects.CLOSED)),
                 authed)
    pool = q.all()
    if not pool:
        return None
    # The last thing written about each of them, in one query: a project's history
    # is what says when it was last thought about at all.
    last = dict(db.query(LogEntry.asset_id, func.max(LogEntry.created_at))
                .filter(LogEntry.asset_id.in_([p.asset_id for p in pool]))
                .group_by(LogEntry.asset_id))
    now = _now()
    weights = []
    for p in pool:
        seen = last.get(p.asset_id)
        quiet = (now - seen).days if seen else TODAY_QUIET_CAP
        weight = min(max(quiet, 0), TODAY_QUIET_CAP) + 1
        if p.status == "stalled":
            weight *= TODAY_STALLED_WEIGHT
        weights.append(weight)
    return random.choices(pool, weights=weights, k=1)[0]


def _today_panel(db, project):
    """What the suggestion shows: the project, a photograph or three of the things
    it is about, the jobs still to do, and how long it has been quiet.

    The photographs are the items', because a project has none of its own -- it is a
    piece of work, and what can be photographed is the hardware it is about. One
    each from as many items as there are, then more from the first, so a project
    about three machines shows the three rather than three views of one."""
    if project is None:
        return None
    members = projects.members(db, project.asset_id)
    shots, seen = [], set()
    for wanted in (1, TODAY_PHOTOS):
        for kind, obj, _row in members:
            for rel in detect_images(kind, obj.asset_id)[:wanted]:
                if rel in seen:
                    continue
                seen.add(rel)
                # Each picture is a way through to the thing it is of, not to the
                # project: somebody looking at a photograph of a drive wants the
                # drive's page, and the project's name above it is already a link.
                shots.append({"rel": rel, "url": f"/{kind}/{obj.asset_id}",
                              "alt": entry.display_name(to_dict(obj))})
                if len(shots) == TODAY_PHOTOS:
                    break
            if len(shots) == TODAY_PHOTOS:
                break
        if len(shots) == TODAY_PHOTOS:
            break
    tasks = [t for t in projects.tasks(db, project.asset_id) if not t.done]
    orders_out = sum(1 for o in projects.orders(db, project.asset_id)
                     if not o.delivered)
    last = (db.query(func.max(LogEntry.created_at))
            .filter(LogEntry.asset_id == project.asset_id).scalar())
    return {
        "p": project,
        "members": [{"url": f"/{kind}/{obj.asset_id}",
                     "name": entry.display_name(to_dict(obj))}
                    for kind, obj, _row in members],
        "photos": shots,
        "tasks": tasks[:TODAY_TASKS], "tasks_left": len(tasks),
        "orders_out": orders_out,
        # Whole days, and None for a project nothing has ever been written about --
        # which cannot happen through the app (creating one writes a line) but can
        # through a restore, and "quiet for 20361 days" would be a strange thing for
        # a page to say about it.
        "quiet_days": (_now() - last).days if last else None,
    }


def _projects_page(request, db, q="", error="", status=200):
    """The page, drawn.

    A function rather than the route's body because the quick box has to render it
    again when what was typed is not an asset tag, with the boxes still holding what
    was typed.

    One list, where there were two. A flag on an item and a project were two sizes
    of the same idea sharing a page, and the promotion from the smaller to the
    larger was a thing you did by hand and by retyping; now the quick box makes the
    larger one directly and there is nothing to promote. What the flag really
    carried, apart from a sentence, was privacy -- and that is a column on the
    project now, so the quick box can go on being the place you write something you
    have not decided to publish.

    A visitor is shown the public ones. This is the first of the five places that is
    kept (see _visible); the other four are the project's own page, the search, the
    suggestion list and the sitemap."""
    rows = projects.summaries(db, authed=request.state.authed)
    total = len(rows)
    if q.strip():
        rows = _projects_matching(db, rows, q, request.state.authed)
    live = [r for r in rows if r["p"].status not in projects.CLOSED]
    # Not while the page is a set of search results, and not while it is telling
    # somebody their asset tag was wrong: both of those are the page answering a
    # question that was asked, and a suggestion above the answer is an interruption.
    suggestion = (None if (q.strip() or error) else
                  _today_panel(db, _project_of_the_day(db, request.state.authed)))
    return templates.TemplateResponse(request, "projects.html", {
        "rows": rows, "live": len(live), "q": q, "searched": bool(q.strip()),
        "suggestion": suggestion,
        "total": total, "error": error,
        "register": _register_order(db) if request.state.authed else [],
        "og": _og(request, "Projects", "Repairs, builds and things on order — "
                                       "the work, as against the collection")},
        status_code=status)


@app.get("/projects", response_class=HTMLResponse, include_in_schema=False)
def gui_projects(request: Request, q: str = "", db: Session = Depends(get_db)):
    """Everything planned, in hand or finished. `q` narrows it, and is a box of its
    own rather than the banner's: the banner searches the register and lands on the
    gallery, and a page of projects wants to be siftable without leaving it."""
    return _projects_page(request, db, q)


@app.post("/projects/quick", include_in_schema=False)
async def gui_project_quick(request: Request, db: Session = Depends(get_db)):
    """A project in one gesture, from the list's own page.

    This is what the flag on an item used to be, and it is here for the same
    reason: you are at the bench, you have just seen what is wrong with something,
    and finding its page to write it down is how the second thing you noticed gets
    lost. What is different is that what you get is a project -- with the item on
    it and the sentence as its first job -- rather than a flag that has to be
    turned into one by hand later.

    Public, like everything else in the register: the tick on a project's own form
    is what keeps one back, and it is a decision rather than a starting point (see
    _take_on_work, which this goes through, and ADR-0004).

    The asset tag is optional. A project need own nothing -- the idea comes before
    the hardware -- and the commonest thing to want at a bench is both: this drive,
    this fault.

    `project` names one already going for the item and the jobs to go on instead of
    raising another. The panel on an item's page offers it as a menu; the box on the
    projects page does not, because a list of projects is not where you are standing
    when you find out a part is for one of them.

    One route for both boxes and for the entry forms, so what gets made does not
    depend on which of them was to hand."""
    form = await request.form()
    jobs = _work_lines(form.get("job"))
    asset_id = (form.get("aid") or "").strip().upper()
    name = (form.get("name") or "").strip()
    found = _asset_find(db, asset_id, FLAGGABLE) if asset_id else None
    if asset_id and found is None:
        # Back to the list saying so, rather than a 404 page. A mistyped tag is the
        # ordinary way to get this wrong and the answer to it is the box to type it
        # in again, which is on the page that was already open.
        return _projects_page(request, db, error=asset_id, status=400)
    picked = (form.get("project") or "").strip().upper()
    project = db.get(Project, picked) if picked else None
    if not name:
        # Named after what it is about, where you did not say -- the same name the
        # entry forms give one, because this is the same gesture and a project
        # should not be called two different things depending on which box raised
        # it. Where there is no item, the job names it: a project called nothing is
        # a row nobody will recognise again.
        name = (_work_project_name(db, asset_id) if found
                else (jobs[0][:60] if jobs else "") or "Untitled project")
    obj = _take_on_work(db, asset_id if found is not None else "", jobs,
                        project, name=name)
    db.commit()
    return RedirectResponse(f"/projects/{obj.asset_id}", status_code=303)


@app.get("/projects/new", response_class=HTMLResponse, include_in_schema=False)
def gui_new_project(request: Request):
    return templates.TemplateResponse(request, "project_form.html",
                                      _project_form_ctx(None, "New project"))


@app.post("/projects/new", include_in_schema=False)
async def gui_create_project(request: Request, db: Session = Depends(get_db)):
    """A project needs a name and nothing else.

    A name because it is the only thing a project can be found by: a machine
    falls back to its manufacturer and model and then to its asset id, and a
    project has neither -- an untitled one is a row nobody will ever recognise
    again. Everything else can be filled in later or never."""
    form = await request.form()
    data = _project_from_form(form)
    if not data["name"]:
        return templates.TemplateResponse(
            request, "project_form.html",
            _project_form_ctx(data, "New project", "Give it a name — it is the "
                                                   "only thing it can be found by."))
    obj = Project(asset_id=next_asset_id(db), **data)
    db.add(obj)
    add_log(db, obj.asset_id, "created", "created")
    db.commit()
    return RedirectResponse(f"/projects/{obj.asset_id}", status_code=303)


@app.get("/projects/{aid}", response_class=HTMLResponse, include_in_schema=False)
def gui_project(aid: str, request: Request, db: Session = Depends(get_db)):
    p = get_or_404(db, Project, aid)
    # The second of the five. Not a 403 and not a redirect to the login: a visitor
    # who guessed the tag of a private project should not be told there is one to
    # guess at, and 404 is what every id that is nothing else answers.
    if p.private and not request.state.authed:
        raise HTTPException(404, f"projects {aid} not found")
    order_rows = projects.orders(db, p.asset_id)
    spent, unpriced = projects.spend(order_rows)
    task_rows = projects.tasks(db, p.asset_id)
    # Offered in the "add an item" box: everything in the register that is not
    # already in this project. Only for whoever is signed in -- it is the contents
    # of a form nobody else is shown -- and only as (id, name) pairs, because a
    # menu of a few hundred assets should not be a few hundred loaded rows.
    choices = []
    if request.state.authed:
        here = {a for (a,) in db.query(ProjectAsset.asset_id)
                .filter(ProjectAsset.project_id == p.asset_id)}
        for cls in (Computer, Part):
            for row in db.query(cls.asset_id, cls.name, cls.manufacturer,
                                cls.model).order_by(cls.asset_id):
                if row.asset_id in here:
                    continue
                choices.append((row.asset_id, entry.display_name({
                    "asset_id": row.asset_id, "name": row.name,
                    "manufacturer": row.manufacturer, "model": row.model})))
        choices.sort(key=lambda c: c[1].lower())
    return templates.TemplateResponse(request, "project.html", {
        "p": p, "item": to_dict(p), "kind": "projects",
        # Who things have been bought from before: the same kind of field as an
        # item's source, and answered the same few ways.
        "dl_suppliers": _answers_given(db, ProjectOrder.supplier),
        "members": projects.members(db, p.asset_id),
        "tasks": task_rows,
        "tasks_done": sum(1 for t in task_rows if t.done),
        "orders": order_rows,
        "orders_out": sum(1 for o in order_rows if not o.delivered),
        "spent": spent, "unpriced": unpriced,
        "choices": choices,
        "log": _history(db, p.asset_id),
        "og": _og(request, p.name or p.asset_id,
                  p.summary or projects.status_label(p.status))})


@app.get("/projects/{aid}/edit", response_class=HTMLResponse, include_in_schema=False)
def gui_edit_project(aid: str, request: Request, db: Session = Depends(get_db)):
    p = get_or_404(db, Project, aid)
    return templates.TemplateResponse(request, "project_form.html",
                                      _project_form_ctx(p, "Edit project"))


@app.post("/projects/{aid}/edit", include_in_schema=False)
async def gui_update_project(aid: str, request: Request,
                             db: Session = Depends(get_db)):
    p = get_or_404(db, Project, aid)
    form = await request.form()
    data = _project_from_form(form)
    if not data["name"]:
        return templates.TemplateResponse(
            request, "project_form.html",
            _project_form_ctx(p, "Edit project", "Give it a name — it is the "
                                                 "only thing it can be found by."))
    before = to_dict(p)
    for k, v in data.items():
        setattr(p, k, v)
    add_log(db, p.asset_id, _field_diffs(before, to_dict(p), PROJECT_FIELDS))
    if bool(before["private"]) != bool(p.private):
        _publish_log(db, p)
    db.commit()
    return RedirectResponse(f"/projects/{p.asset_id}", status_code=303)


@app.get("/projects/{aid}/label.pdf", include_in_schema=False)
def gui_project_label(aid: str, small: int = 1, db: Session = Depends(get_db)):
    """A printable label for a project, so a thing bought for one can carry a
    sticker saying what it is for.

    The same label the machines and the parts get, made by the same code and
    carrying the same /items/<id> code -- which is the whole reason a project was
    given a register id in the first place. Scanning the sticker on a parcel opens
    the project it was bought for, with its orders on it.

    Small by default, as a part's is. A machine gets the 6x4 by default because it
    is filed on a shelf and read across a room; this is going on a jiffy bag."""
    p = get_or_404(db, Project, aid)
    pdf = labels.render_pdf(to_dict(p), [], labels.PROJECT, small=bool(small))
    return Response(pdf, media_type="application/pdf", headers={
        "Content-Disposition": f'inline; filename="{aid}{"-small" if small else ""}.pdf"'})


@app.post("/projects/{aid}/note", include_in_schema=False)
async def gui_project_note(aid: str, request: Request,
                           db: Session = Depends(get_db)):
    """The same note bar the machines have, posting to the same shape of URL, which
    is why _history.html needed nothing said to it about projects."""
    get_or_404(db, Project, aid)
    _note_with_photos(db, aid, await request.form())
    return RedirectResponse(f"/projects/{aid}", status_code=303)


@app.post("/projects/{aid}/delete", include_in_schema=False)
async def gui_delete_project(aid: str, db: Session = Depends(get_db)):
    """Delete a project outright, with no disposal step in front of it.

    A machine has to be marked disposed before it can be deleted, because deleting
    one is claiming a physical object has left the collection and that is a thing
    worth being sure about. A project is a plan. Abandoning one is already a status
    it can be put in and kept in, so the only reason left to delete is that it was
    written by mistake -- and a confirmation is enough for that.

    Its tasks, orders and memberships go by the foreign key's cascade. Its history
    does not: log_entry is keyed by a plain register id with nothing to cascade
    from, so it is cleared here by hand, photographs first while there are still
    entries to find them by -- exactly as the two asset delete paths do it."""
    p = get_or_404(db, Project, aid)
    photos = _drop_log_photos(db, p.asset_id)
    db.query(LogEntry).filter(LogEntry.asset_id == p.asset_id).delete(
        synchronize_session=False)
    db.delete(p)
    db.commit()  # the rows first: if this raises, the photographs are still there
    _purge_photos(photos)
    return RedirectResponse("/projects", status_code=303)


# --- what a project is about -------------------------------------------------
# Membership is written on both sides: the project's history says what it took on
# and the item's says what it was wanted for. Two entries rather than one because
# they are read in two different places, and somebody looking at a board wants to
# know why it is spoken for without having to find the project that spoke for it.


@app.post("/projects/{aid}/add-item", include_in_schema=False)
async def gui_project_add_item(aid: str, request: Request,
                               db: Session = Depends(get_db)):
    p = get_or_404(db, Project, aid)
    form = await request.form()
    asset_id = (form.get("asset_id", "") or "").strip().upper()
    note = (form.get("note", "") or "").strip()
    if projects.add_asset(db, p.asset_id, asset_id, note):
        what = _asset_named(db, asset_id)
        add_log(db, p.asset_id, f"took on {what}" + (f" — {note}" if note else ""))
        _member_log(db, p, asset_id)
        db.commit()
    return RedirectResponse(f"/projects/{p.asset_id}", status_code=303)


@app.post("/projects/{aid}/remove-item", include_in_schema=False)
async def gui_project_remove_item(aid: str, request: Request,
                                  db: Session = Depends(get_db)):
    p = get_or_404(db, Project, aid)
    form = await request.form()
    asset_id = (form.get("asset_id", "") or "").strip().upper()
    if projects.drop_asset(db, p.asset_id, asset_id):
        add_log(db, p.asset_id, f"let go of {_asset_named(db, asset_id)}")
        _member_log(db, p, asset_id, joining=False)
        db.commit()
    return RedirectResponse(f"/projects/{p.asset_id}", status_code=303)


def _member_log(db, project, asset_id, joining=True):
    """Write the item's side of a membership -- but only while the project is one
    anybody may read.

    An item page is public and so is its history, and the history is the part of the
    register nothing rewrites. A line reading "wanted for Recap the +2A (RH-J0Y7)"
    on a public page is the name of a private project, published, and published for
    good. So a private project does not write here; its own history, which is as
    private as it is, has the entry either way.

    This is the invariant the pair of functions keeps: an item's history names a
    project exactly while that project is public. _publish_log is the other half,
    for a project that changes its mind."""
    if project.private:
        return
    add_log(db, asset_id, (f"wanted for {_project_named(project)}" if joining
                           else f"no longer wanted for {_project_named(project)}"))


def _publish_log(db, project):
    """Bring the members' histories into line after a project's privacy changed.

    Publishing writes the lines that were held back; withdrawing deletes them. That
    delete is the one place the register rewrites its own log, and it is the whole
    point: a name taken out of publication cannot be left behind in the one public
    place it was written, or withdrawing it would mean nothing."""
    members = [row.asset_id for row in db.query(ProjectAsset)
               .filter(ProjectAsset.project_id == project.asset_id)]
    if project.private:
        # Matched on the tag rather than the name: the name may have been edited in
        # the same breath, and the tag is what makes the line this project's.
        for asset_id in members:
            (db.query(LogEntry)
             .filter(LogEntry.asset_id == asset_id,
                     LogEntry.message.like(f"%({project.asset_id})%"))
             .delete(synchronize_session=False))
    else:
        for asset_id in members:
            add_log(db, asset_id, f"wanted for {_project_named(project)}")


def _asset_display(db, asset_id):
    """What a computer or part is called, or None if the register has no such
    thing. The name is a fact about the item and is asked for in two voices -- a
    sentence in a history, and the name of a project about it -- so it is read in
    one place."""
    for cls in (Computer, Part):
        if (obj := db.get(cls, asset_id)) is not None:
            return entry.display_name(to_dict(obj))
    return None


def _asset_named(db, asset_id):
    """A computer or part in a sentence written in a project's history: what it is
    called, and its id. Falls back to the bare id for something that has since
    gone, so a history line never reads as a blank."""
    name = _asset_display(db, asset_id)
    return f"{name} ({asset_id})" if name else asset_id


# --- work noted while checking something in -----------------------------------
# The quick box above is this gesture from a page that already exists. What follows
# is the same one from the two forms that make a page, which is where the thought
# actually arrives: what is wrong with a machine is seen while it is being unpacked,
# and the form that files it is on screen at the time. Asking for the item's tag
# first meant the note had to wait for a second visit to a page that did not exist
# yet, and a note that waits is a note that is lost -- which is the whole reason the
# flag on an item existed before 0031, and the reason this is not simply the quick
# box again.


def _work_project_name(db, asset_id):
    """What a project raised from an item's own form is called.

    The form asks for no name: what is being described is the work, and the only
    thing known about it at that moment is which item it is for. So the item names
    it -- what the thing is called, not its tag. "Work required by item: Amstrad
    PC1640" is a line somebody can read down a list and recognise; the same line
    ending RH-J8JA is one they have to look up, and a list of them is a list of
    lookups.

    The tag is the fallback, through display_name, for a thing entered with no
    maker, model or name of its own yet -- and the project's own tag is beside it on
    every list it appears in, which is what tells two machines of the same model
    apart. Rename it on its own form once it is a piece of work with a character of
    its own."""
    return f"Work required by item: {_asset_display(db, asset_id) or asset_id}"


def _work_lines(raw):
    """The jobs out of a work box, one to a line.

    Faults arrive as a list -- recap, belt, keyboard sticks -- and one box holding
    all three as a sentence would make a single task that can only ever be half
    ticked off. Blank lines go, so a trailing newline is not a job with nothing in
    it."""
    return [line.strip() for line in (raw or "").splitlines() if line.strip()]


def _take_on_work(db, asset_id, jobs, project=None, name=""):
    """Put an item and its jobs on a project, making one if none was given.

    The one path everything that notes work runs down -- the quick box, both entry
    forms, both edit forms and the API -- so the item lands on the project, the
    history is written from both ends and the same rules apply wherever the sentence
    was typed.

    Public, like everything else in the register. These started private, on the
    argument that a line typed at a bench in five seconds has not been considered
    for publication. In practice the register is a public catalogue of old machines,
    what is wrong with one is a good part of what is interesting about it, and a
    default that hides the work meant undoing it by hand on nearly every project.
    The tick on a project's own form still keeps one back; it is a decision now
    rather than a starting point (ADR-0004).

    Commits nothing. Every caller is in the middle of saving something else and owns
    the transaction; a commit here would be a half-saved machine with a project
    beside it if what follows fails."""
    if project is None:
        project = Project(asset_id=next_asset_id(db),
                          name=(name or _work_project_name(db, asset_id))[:255],
                          status="planned", private=False)
        db.add(project)
        add_log(db, project.asset_id, "created", "created")
    if asset_id and projects.add_asset(db, project.asset_id, asset_id):
        add_log(db, project.asset_id, f"took on {_asset_named(db, asset_id)}")
        _member_log(db, project, asset_id)
    for job in jobs:
        db.add(ProjectTask(project_id=project.asset_id, text=job))
        add_log(db, project.asset_id, f"to do: {_short(job)}")
    return project


def _work_from_form(db, obj, form):
    """The work box on an entry or edit form, acted on once the item itself is saved.

    Nothing typed and nothing picked makes nothing, which is the ordinary case: most
    things arrive with nothing wrong, and a project per arrival would turn the
    projects page from a list of work into a second copy of the register.

    A picked project that names nothing becomes a project of its own rather than an
    error. The menu cannot produce one -- only a hand-made post can -- and refusing
    at this point would throw away the entry being made, photographs and all, over
    the convenience half of the gesture. The sentence is the part worth keeping."""
    jobs = _work_lines(form.get("work_needed", ""))
    picked = (form.get("work_project", "") or "").strip().upper()
    project = db.get(Project, picked) if picked else None
    if not jobs and project is None:
        return None
    return _take_on_work(db, obj.asset_id, jobs, project)


def _work_from_api(db, fields):
    """`work_needed` / `work_project` off a create body: the jobs, and the project
    they go on, taken out of the fields on their way past.

    The project is checked here, before the item is written, and a tag that names
    nothing is a 404. Unlike the form, a caller here typed the tag -- and one that
    named a project meant that project, so filing the work somewhere else quietly
    would be a worse answer than being told. Checking first is what keeps the typo
    from leaving a half-entered machine behind it."""
    jobs = _work_lines(fields.pop("work_needed", "") or "")
    picked = (fields.pop("work_project", "") or "").strip().upper()
    project = None
    if picked:
        project = db.get(Project, picked)
        if project is None:
            raise HTTPException(404, f"projects {picked} not found")
    return jobs, project


# --- the jobs, and the things on order ---------------------------------------


def _task_or_404(db, p, tid):
    row = db.get(ProjectTask, tid)
    # The project id is checked rather than taken on trust, for the reason a history
    # entry's asset id is: a bare row id would otherwise let one project's task be
    # ticked from another project's page.
    if row is None or row.project_id != p.asset_id:
        raise HTTPException(404, f"no task {tid} in {p.asset_id}")
    return row


def _order_or_404(db, p, oid):
    row = db.get(ProjectOrder, oid)
    if row is None or row.project_id != p.asset_id:
        raise HTTPException(404, f"no order {oid} in {p.asset_id}")
    return row


@app.post("/projects/{aid}/task", include_in_schema=False)
async def gui_project_add_task(aid: str, request: Request,
                               db: Session = Depends(get_db)):
    p = get_or_404(db, Project, aid)
    form = await request.form()
    text = (form.get("text", "") or "").strip()
    if text:
        db.add(ProjectTask(project_id=p.asset_id, text=text))
        add_log(db, p.asset_id, f"to do: {_short(text)}")
        db.commit()
    return RedirectResponse(f"/projects/{p.asset_id}", status_code=303)


@app.post("/projects/{aid}/task/{tid}/toggle", include_in_schema=False)
def gui_project_toggle_task(aid: str, tid: int, db: Session = Depends(get_db)):
    """Tick a job, or put it back.

    Un-ticking clears the date rather than keeping it. A job that is not done has
    no day it was done on, and leaving the old one behind would mean a task showing
    as outstanding while still claiming a completion date."""
    p = get_or_404(db, Project, aid)
    row = _task_or_404(db, p, tid)
    row.done = not row.done
    row.done_at = date.today() if row.done else None
    add_log(db, p.asset_id, ("done: " if row.done else "back on the list: ")
            + _short(row.text))
    db.commit()
    return RedirectResponse(f"/projects/{p.asset_id}", status_code=303)


@app.post("/projects/{aid}/task/{tid}/delete", include_in_schema=False)
def gui_project_delete_task(aid: str, tid: int, db: Session = Depends(get_db)):
    p = get_or_404(db, Project, aid)
    row = _task_or_404(db, p, tid)
    add_log(db, p.asset_id, f"dropped: {_short(row.text)}")
    db.delete(row)
    db.commit()
    return RedirectResponse(f"/projects/{p.asset_id}", status_code=303)


@app.post("/projects/{aid}/order", include_in_schema=False)
async def gui_project_add_order(aid: str, request: Request,
                                db: Session = Depends(get_db)):
    """Something bought for this project. Only the description is required: an
    order written down the moment it is placed rarely has a delivery date yet, and
    a form that insisted on one would be filled in later or not at all."""
    p = get_or_404(db, Project, aid)
    form = await request.form()
    description = (form.get("description", "") or "").strip()
    if not description:
        return RedirectResponse(f"/projects/{p.asset_id}", status_code=303)
    qty = (form.get("qty", "") or "").strip()
    row = ProjectOrder(
        project_id=p.asset_id, description=description[:255],
        supplier=(form.get("supplier", "") or "").strip()[:255],
        url=(form.get("url", "") or "").strip(),
        qty=int(qty) if qty.isdigit() and int(qty) > 0 else 1,
        cost_p=projects.parse_money(form.get("cost", "")),
        ordered_at=_parse_date(form.get("ordered_at", "")) or date.today(),
        expected_at=_parse_date(form.get("expected_at", "")),
        note=(form.get("note", "") or "").strip()[:255])
    db.add(row)
    add_log(db, p.asset_id, f"ordered {_short(description)}"
            + (f" from {row.supplier}" if row.supplier else ""))
    db.commit()
    return RedirectResponse(f"/projects/{p.asset_id}", status_code=303)


@app.post("/projects/{aid}/order/{oid}/delivered", include_in_schema=False)
def gui_project_order_delivered(aid: str, oid: int,
                                db: Session = Depends(get_db)):
    """The tick. What arrives is added to the register the ordinary way -- this row
    is a note about a purchase, not a half-made asset -- so all that happens here is
    that it stops being one of the things still coming."""
    p = get_or_404(db, Project, aid)
    row = _order_or_404(db, p, oid)
    row.delivered = not row.delivered
    row.delivered_at = date.today() if row.delivered else None
    add_log(db, p.asset_id, ("arrived: " if row.delivered else "still coming: ")
            + _short(row.description))
    db.commit()
    return RedirectResponse(f"/projects/{p.asset_id}", status_code=303)


@app.post("/projects/{aid}/order/{oid}/delete", include_in_schema=False)
def gui_project_delete_order(aid: str, oid: int, db: Session = Depends(get_db)):
    p = get_or_404(db, Project, aid)
    row = _order_or_404(db, p, oid)
    add_log(db, p.asset_id, f"cancelled: {_short(row.description)}")
    db.delete(row)
    db.commit()
    return RedirectResponse(f"/projects/{p.asset_id}", status_code=303)


# --- JSON API: projects ------------------------------------------------------
# The same thing the pages do, for the tool server and for scripts. Full CRUD on
# the project, and endpoints of their own for the three lists it holds.
#
# The lists are not fields of the project on the way in, which is the one place
# this departs from how a computer's drives and memory are written. A drive row is
# a description of a machine and is rewritten wholesale every time the machine is
# described; a task is a row somebody ticks. A caller that read the list, changed
# one line and posted the lot back would silently drop whatever was added in
# between -- so each is added, changed and removed one at a time, by its own id.

PROJECT_TAGS = ["projects"]


def _project_out(db, p):
    """A project as it reads back: its own columns, the status in words, and its
    three lists. Four queries whatever it holds."""
    return to_dict(p) | {
        "status_label": projects.status_label(p.status),
        "items": [{"asset_id": obj.asset_id, "kind": kind,
                   "name": entry.display_name(to_dict(obj)), "note": row.note}
                  for kind, obj, row in projects.members(db, p.asset_id)],
        "tasks": projects.tasks(db, p.asset_id),
        "orders": projects.orders(db, p.asset_id),
    }


def _api_project(db, aid):
    return get_or_404(db, Project, aid)


def _api_task(db, p, tid):
    row = db.get(ProjectTask, tid)
    if row is None or row.project_id != p.asset_id:
        raise HTTPException(404, f"no task {tid} in {p.asset_id}")
    return row


def _api_order(db, p, oid):
    row = db.get(ProjectOrder, oid)
    if row is None or row.project_id != p.asset_id:
        raise HTTPException(404, f"no order {oid} in {p.asset_id}")
    return row


@app.get("/api/projects", response_model=list[ProjectOut], tags=PROJECT_TAGS)
def api_list_projects(status: str | None = None, open: bool | None = None,
                      db: Session = Depends(get_db)):
    """Every project, with what each is about, what is to be done and what is on
    order. `status` narrows it to one state; `open=true` to the ones not finished
    or abandoned, which is the question a list of projects is usually asked."""
    q = db.query(Project)
    if status:
        q = q.filter(Project.status == status)
    if open is not None:
        q = (q.filter(Project.status.notin_(projects.CLOSED)) if open
             else q.filter(Project.status.in_(projects.CLOSED)))
    return [_project_out(db, p) for p in q.order_by(Project.name,
                                                    Project.asset_id).all()]


@app.post("/api/projects", response_model=ProjectOut, tags=PROJECT_TAGS)
def api_create_project(data: ProjectIn, db: Session = Depends(get_db)):
    """Start a project. Only the name is required -- it is the only thing a
    project can be found by, having no manufacturer or model to fall back on."""
    fields = data.model_dump()
    fields["name"] = (fields.get("name") or "").strip()
    if not fields["name"]:
        raise HTTPException(422, "a project needs a name")
    fields["status"] = projects.clean_status(fields.get("status"))
    obj = Project(asset_id=next_asset_id(db), **fields)
    db.add(obj)
    add_log(db, obj.asset_id, "created", "created")
    db.commit()
    db.refresh(obj)
    return _project_out(db, obj)


@app.get("/api/projects/{aid}", response_model=ProjectOut, tags=PROJECT_TAGS)
def api_get_project(aid: str, db: Session = Depends(get_db)):
    return _project_out(db, _api_project(db, aid))


@app.patch("/api/projects/{aid}", response_model=ProjectOut, tags=PROJECT_TAGS)
def api_update_project(aid: str, data: ProjectIn, db: Session = Depends(get_db)):
    p = _api_project(db, aid)
    fields = data.model_dump(exclude_unset=True)
    if "name" in fields:
        fields["name"] = (fields["name"] or "").strip()
        if not fields["name"]:
            raise HTTPException(422, "a project needs a name")
    if "status" in fields:
        fields["status"] = projects.clean_status(fields["status"])
    old = to_dict(p)
    for k, v in fields.items():
        setattr(p, k, v)
    add_log(db, aid, _field_diffs(old, to_dict(p), list(fields)))
    if bool(old["private"]) != bool(p.private):
        _publish_log(db, p)
    db.commit()
    db.refresh(p)
    return _project_out(db, p)


@app.delete("/api/projects/{aid}", tags=PROJECT_TAGS)
def api_delete_project(aid: str, db: Session = Depends(get_db)):
    """Delete a project. Its tasks, orders and memberships go with it by the
    foreign key; its history goes by hand, log_entry having nothing to cascade
    from. The hardware it was about is untouched -- deleting the plan is not
    disposing of the machine."""
    p = _api_project(db, aid)
    photos = _drop_log_photos(db, aid)
    db.query(LogEntry).filter(LogEntry.asset_id == aid).delete(
        synchronize_session=False)
    db.delete(p)
    db.commit()
    _purge_photos(photos)
    return {"deleted": aid, "photos": len(photos)}


# --- JSON API: what a project is about ---------------------------------------


@app.post("/api/projects/{aid}/items", response_model=ProjectOut, tags=PROJECT_TAGS)
def api_project_add_item(aid: str, data: ProjectItemIn,
                         db: Session = Depends(get_db)):
    """Put a computer or part in a project. An asset id that is in neither table is
    refused rather than stored: a project is about things that exist, and a
    membership pointing at nothing would render as nothing for ever.

    Adding one already in it is not an error -- the project ends up in the state
    asked for, which is what a caller retrying a request wants."""
    p = _api_project(db, aid)
    asset_id = (data.asset_id or "").strip().upper()
    if not any(db.get(cls, asset_id) for cls in (Computer, Part)):
        raise HTTPException(404, f"no computer or part {data.asset_id}")
    if projects.add_asset(db, aid, asset_id, data.note):
        add_log(db, aid, f"took on {_asset_named(db, asset_id)}")
        _member_log(db, p, asset_id)
        db.commit()
    return _project_out(db, p)


@app.delete("/api/projects/{aid}/items/{asset_id}", response_model=ProjectOut,
            tags=PROJECT_TAGS)
def api_project_drop_item(aid: str, asset_id: str, db: Session = Depends(get_db)):
    p = _api_project(db, aid)
    asset_id = (asset_id or "").strip().upper()
    if projects.drop_asset(db, aid, asset_id):
        add_log(db, aid, f"let go of {_asset_named(db, asset_id)}")
        _member_log(db, p, asset_id, joining=False)
        db.commit()
    return _project_out(db, p)


# --- JSON API: the jobs and the things on order ------------------------------


@app.post("/api/projects/{aid}/tasks", response_model=ProjectTaskOut,
          tags=PROJECT_TAGS)
def api_project_add_task(aid: str, data: ProjectTaskIn,
                         db: Session = Depends(get_db)):
    p = _api_project(db, aid)
    text = (data.text or "").strip()
    if not text:
        raise HTTPException(422, "a task needs something written in it")
    db.add(row := ProjectTask(project_id=p.asset_id, text=text,
                              done=bool(data.done)))
    if row.done:
        row.done_at = date.today()
    add_log(db, aid, f"to do: {_short(text)}")
    db.commit()
    db.refresh(row)
    return row


@app.patch("/api/projects/{aid}/tasks/{tid}", response_model=ProjectTaskOut,
           tags=PROJECT_TAGS)
def api_project_update_task(aid: str, tid: int, data: ProjectTaskIn,
                            db: Session = Depends(get_db)):
    """Reword a job or tick it. Un-ticking clears the date as well: a job that is
    not done has no day it was done on."""
    p = _api_project(db, aid)
    row = _api_task(db, p, tid)
    fields = data.model_dump(exclude_unset=True)
    if "text" in fields and (text := (fields["text"] or "").strip()):
        row.text = text
    if "done" in fields and fields["done"] is not None:
        was = bool(row.done)
        row.done = bool(fields["done"])
        row.done_at = date.today() if row.done else None
        if was != row.done:
            add_log(db, aid, ("done: " if row.done else "back on the list: ")
                    + _short(row.text))
    db.commit()
    db.refresh(row)
    return row


@app.delete("/api/projects/{aid}/tasks/{tid}", tags=PROJECT_TAGS)
def api_project_delete_task(aid: str, tid: int, db: Session = Depends(get_db)):
    p = _api_project(db, aid)
    row = _api_task(db, p, tid)
    add_log(db, aid, f"dropped: {_short(row.text)}")
    db.delete(row)
    db.commit()
    return {"deleted": tid}


@app.post("/api/projects/{aid}/orders", response_model=ProjectOrderOut,
          tags=PROJECT_TAGS)
def api_project_add_order(aid: str, data: ProjectOrderIn,
                          db: Session = Depends(get_db)):
    """Record something bought for a project. Only the description is required: an
    order written down as it is placed rarely has a delivery date yet.

    Nothing here becomes a part. When it arrives it is added to the register the
    ordinary way and this row is ticked -- which keeps an order a note about a
    purchase rather than a half-made asset."""
    p = _api_project(db, aid)
    fields = data.model_dump(exclude_unset=True)
    description = (fields.get("description") or "").strip()
    if not description:
        raise HTTPException(422, "an order needs a description")
    delivered = bool(fields.pop("delivered", False))
    row = ProjectOrder(project_id=p.asset_id, **(fields | {
        "description": description,
        "ordered_at": fields.get("ordered_at") or date.today(),
        "delivered": delivered,
        "delivered_at": date.today() if delivered else None}))
    db.add(row)
    add_log(db, aid, f"ordered {_short(description)}"
            + (f" from {row.supplier}" if row.supplier else ""))
    db.commit()
    db.refresh(row)
    return row


@app.patch("/api/projects/{aid}/orders/{oid}", response_model=ProjectOrderOut,
           tags=PROJECT_TAGS)
def api_project_update_order(aid: str, oid: int, data: ProjectOrderIn,
                             db: Session = Depends(get_db)):
    """Change an order, or mark it in. Setting `delivered` dates it; clearing it
    clears the date, for the reason un-ticking a task does."""
    p = _api_project(db, aid)
    row = _api_order(db, p, oid)
    fields = data.model_dump(exclude_unset=True)
    delivered = fields.pop("delivered", None)
    for k, v in fields.items():
        setattr(row, k, v)
    if delivered is not None and bool(delivered) != bool(row.delivered):
        row.delivered = bool(delivered)
        row.delivered_at = date.today() if row.delivered else None
        add_log(db, aid, ("arrived: " if row.delivered else "still coming: ")
                + _short(row.description))
    db.commit()
    db.refresh(row)
    return row


@app.delete("/api/projects/{aid}/orders/{oid}", tags=PROJECT_TAGS)
def api_project_delete_order(aid: str, oid: int, db: Session = Depends(get_db)):
    p = _api_project(db, aid)
    row = _api_order(db, p, oid)
    add_log(db, aid, f"cancelled: {_short(row.description)}")
    db.delete(row)
    db.commit()
    return {"deleted": oid}
