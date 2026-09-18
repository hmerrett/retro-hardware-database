"""Retro Hardware Database — FastAPI backend.

Two surfaces over the same MariaDB:
  * JSON API under /api  (used by scripts, the MCP wrapper, and the GUI)
  * a bespoke server-rendered GUI that mirrors the flat-file add.py workflow:
    the guided build walk (computer -> link/create motherboard -> parts by
    category), storage-kind routing, CPU/RAM as computer fields, photo upload,
    a disposed toggle, print-label PDFs, and a searchable/filterable index.

Interactive API docs live at /docs (OpenAPI).
"""

import os
from urllib.parse import parse_qs

from fastapi import FastAPI, Request, Response
from fastapi.staticfiles import StaticFiles
from starlette.middleware.base import RequestResponseEndpoint
from starlette.staticfiles import PathLike
from starlette.types import Scope

from . import __version__
from .common import (  # shared foundations; re-exported here so existing call-sites resolve
    BRANDING_DIR,
    IMAGES_DIR,
    STATIC_DIR,
)
from .common import (  # noqa: F401 -- re-exported for the tests, unused here
    _all_years,
    to_dict,
)
from .routers import (
    api_assets,
    api_projects,
    catalogue,
    computers as computer_pages,
    files as file_pages,
    gallery,
    health,
    images,
    items,
    parts as part_pages,
    projects as project_pages,
    seo,
    styles,
)
from . import auth
from .routers import stats as stats_routes
from .common import (  # noqa: F401 -- re-exported for the tests, unused here
    RELIABILITY_MIN,
    _maker_reliability,
    branded,
)
from .pages import _answers_given  # noqa: F401 -- re-exported for the tests
from .photos import (  # noqa: F401 -- re-exported for the tests, unused here
    detect_images,
    has_original,
    img_url,
    pick_images,
    tuned_photos,
)
from .web import templates  # noqa: F401 -- re-exported for the tests, unused here
from .stats import FACTS_SHOWN, _collection_stats, _facts, _facts_projects, _facts_register  # noqa: F401
from .photos import (  # noqa: F401 -- re-exported for the tests, unused here
    WM_CACHE,
    WM_SRC,
    WM_SCALE,
    WM_MIN_PX,
    WM_BUILD,
    _watermarked_file,
    _wm_forget,
    _is_own_photo,
    _image_size,
    _ref_sidecar,
    _write_atomically,
    _original_of,
)
from .search import search_terms  # noqa: F401 -- re-exported for the tests, unused here

# Schema is owned by Alembic now (entrypoint.sh runs `alembic upgrade head` on
# start); no create_all here.


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


async def content_security_policy(request: Request, call_next: RequestResponseEndpoint) -> Response:
    """Say what the page is allowed to load, on every response.

    The other security headers -- HSTS, nosniff, the referrer policy -- are
    Caddy's, because they are facts about transport and hold whatever the app
    renders. This one is a fact about *this app's* markup and static files, so it
    lives with them, where a test can read it and where it applies to an install
    that is not behind Caddy. Caddy does not send one too: two policies drift
    apart, and the stricter of the pair wins in ways nobody predicted.

    `setdefault`, not assignment, so a route that needs its own policy can say so
    and keep it -- nothing does today, and the tests would notice if one started.
    """
    response = await call_next(request)
    response.headers.setdefault("Content-Security-Policy", CONTENT_SECURITY_POLICY)
    return response


async def no_stale_pages(request: Request, call_next: RequestResponseEndpoint) -> Response:
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


# Container paths by default (the `images` volume and the goaccess report mount);
# overridable so the app can be imported and run outside Docker for local
# development, which the hardcoded absolute paths used to make impossible.


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

    def file_response(
        self,
        full_path: PathLike,
        stat_result: os.stat_result,
        scope: Scope,
        status_code: int = 200,
    ) -> Response:
        response = super().file_response(full_path, stat_result, scope, status_code)
        query = parse_qs(scope.get("query_string", b"").decode("latin-1"))
        response.headers["Cache-Control"] = (
            "public, max-age=31536000, immutable" if query.get("v") else "public, max-age=3600"
        )
        return response


def _static_files() -> _CachedStatic:
    """The static mount, with this installation's own artwork in front of it."""
    for sub in ("computers", "parts"):
        (IMAGES_DIR / sub).mkdir(parents=True, exist_ok=True)
    _static = _CachedStatic(directory=str(STATIC_DIR))
    # The deployment's own artwork first, the shipped placeholders behind it. This is
    # StaticFiles' own search list, so a name that is not overridden falls through to
    # what ships, and the traversal checks are the ones it already makes on every
    # request -- a directory in front of another is exactly what `packages` does.
    if BRANDING_DIR.is_dir():
        _static.all_directories = [str(BRANDING_DIR), *_static.all_directories]
    return _static


def create_app() -> FastAPI:
    """Build the application: the middlewares, the static mount, and every router.

    The routes live in api/app/routers/ and the helpers they call in modules beside
    them; what is left here is the wiring, which is the one thing that cannot move
    because it is what there is to wire.

    The order of the middlewares is load-bearing. Starlette puts each new one
    outside the last, so the gate is registered after the cache header and
    therefore runs first on the way in and last on the way out -- the order the
    decorators gave when both of them lived in this file.

    The policy is registered last of all, which puts it outside the gate. That
    matters: a gate that turns a stranger away answers without ever calling the
    stack inside it, so a policy registered further in would miss the login
    redirect -- the one response an unauthenticated stranger is most likely to get.
    """
    app = FastAPI(title="Retro Hardware Database API", version=__version__)
    app.middleware("http")(no_stale_pages)
    app.middleware("http")(auth.auth_gate)
    app.middleware("http")(content_security_policy)
    app.mount("/static", _static_files(), name="static")
    for router in (
        auth.router,
        seo.router,
        styles.router,
        images.router,
        catalogue.router,
        stats_routes.router,
        gallery.router,
        items.router,
        file_pages.router,
        computer_pages.router,
        part_pages.router,
        project_pages.router,
        api_assets.router,
        api_projects.router,
        health.router,
    ):
        app.include_router(router)
    return app


app = create_app()
