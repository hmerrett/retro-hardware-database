"""Retro Hardware Database — FastAPI backend.

Two surfaces over the same MariaDB:
  * JSON API under /api  (used by scripts, the MCP wrapper, and the GUI)
  * a bespoke server-rendered GUI that mirrors the flat-file add.py workflow:
    the guided build walk (computer -> link/create motherboard -> parts by
    category), storage-kind routing, CPU/RAM as computer fields, photo upload,
    a disposed toggle, print-label PDFs, and a searchable/filterable index.

Interactive API docs live at /docs (OpenAPI).
"""
from urllib.parse import parse_qs

from fastapi import (Depends, FastAPI, Request)
from fastapi.responses import (JSONResponse)
from fastapi.staticfiles import StaticFiles
from sqlalchemy import text
from sqlalchemy.orm import Session

from . import __version__
from .common import to_dict  # noqa: F401 -- re-exported for the tests
from .common import (  # shared foundations; re-exported here so existing call-sites resolve
    BRANDING_DIR, IMAGES_DIR, STATIC_DIR)
from .common import _all_years  # noqa: F401 -- re-exported for the tests, unused here
from .db import get_db
from .routers import (catalogue, computers as computer_pages, files as file_pages,
                      images, items, parts as part_pages,
                      projects as project_pages, seo)
from . import auth
from .routers import gallery
from .routers import rest
from .routers import stats as stats_routes
from .common import (  # noqa: F401 -- re-exported for the tests, unused here
    RELIABILITY_MIN, _maker_reliability, branded)
from .pages import _answers_given  # noqa: F401 -- re-exported for the tests
from .photos import (  # noqa: F401 -- re-exported for the tests, unused here
    detect_images, has_original, img_url, pick_images, tuned_photos)
from .web import templates  # noqa: F401 -- re-exported for the tests, unused here
from .stats import FACTS_SHOWN, _collection_stats, _facts, _facts_projects, _facts_register  # noqa: F401
from .photos import (  # noqa: F401 -- re-exported for the tests, unused here
    WM_CACHE, WM_SRC, WM_SCALE, WM_MIN_PX, WM_BUILD, _watermarked_file, _wm_forget,
    _is_own_photo, _image_size, _ref_sidecar, _write_atomically, _original_of,
)
from .search import search_terms  # noqa: F401 -- re-exported for the tests, unused here

# Schema is owned by Alembic now (entrypoint.sh runs `alembic upgrade head` on
# start); no create_all here.

app = FastAPI(title="Retro Hardware Database API", version=__version__)


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


# Registered after no_stale_pages and so outside it, which is the order the two
# decorators gave when both lived here: the gate runs first on the way in and last
# on the way out.
app.middleware("http")(auth.auth_gate)
app.include_router(auth.router)







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





@app.get("/healthz", include_in_schema=False)
def healthz(db: Session = Depends(get_db)):
    """Liveness plus database reachability, for a deploy's smoke check and any
    uptime monitor. Deliberately public and content-free: it says up or down and
    nothing else, so it needs no login and gives nothing away.

    It touches the database rather than only answering, because a box that is up
    but cannot reach MariaDB serves nothing but errors, and a check that called
    that healthy would let a broken deploy through."""
    try:
        db.execute(text("SELECT 1"))
    except Exception:
        return JSONResponse({"status": "unhealthy"}, status_code=503)
    return {"status": "ok"}







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


# The route groups that have moved out of this module. Each is an APIRouter in
# api/app/routers/, included here in the order it was declared in, so that lifting
# the lot into a create_app() at the end of the split is mechanical.
app.include_router(seo.router)
app.include_router(images.router)
app.include_router(catalogue.router)
app.include_router(stats_routes.router)
app.include_router(gallery.router)
app.include_router(items.router)
app.include_router(file_pages.router)
app.include_router(rest.router)
app.include_router(computer_pages.router)
app.include_router(part_pages.router)
app.include_router(project_pages.router)
