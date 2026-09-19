"""The login, and the gate every request passes through.

One module, on purpose. Whether auth is on, the credentials, the cookie and its
signer, the rate limiter, the gate that reads all of them, and the two routes that
let somebody in and out: each of those is only meaningful in terms of the others,
and splitting them would leave two copies of the question "is this reader logged
in?" to be kept in step.

It also keeps a test honest. A test that forces AUTH_ENABLED patches it here, and
here is where the gate and the login route both read it -- one name, one live
value. main no longer carries a copy for a patch to land on harmlessly.

main registers the gate as middleware rather than this module doing it, because
middleware belongs to the app object and the order of the two matters: the gate is
registered last so that it sits outside the cache-header one.
"""

import base64
import logging
import os
import secrets
import time
from urllib.parse import quote, urlparse

from fastapi import APIRouter, Request
from fastapi.responses import HTMLResponse, RedirectResponse, Response
from itsdangerous import BadSignature, SignatureExpired, URLSafeTimedSerializer
from starlette.middleware.base import RequestResponseEndpoint
from .forms import posted
from .web import _safe_next, templates

router = APIRouter()


AUTH_USER = os.getenv("RHDB_AUTH_USER", "")
AUTH_PASS = os.getenv("RHDB_AUTH_PASSWORD", "")
AUTH_ENABLED = bool(AUTH_USER and AUTH_PASS)
templates.env.globals["auth_enabled"] = AUTH_ENABLED

# Nothing in the app configures logging: under uvicorn its config is already in
# place by the time this module is imported, and outside it a WARNING still reaches
# stderr through logging's last-resort handler. So a warning raised here is seen
# either way, which is the point of raising it here.
log = logging.getLogger(__name__)


def _open_on_purpose() -> bool:
    """Whether the operator has said that running with no login is deliberate.

    The mirror of RHDB_WATERMARK's reading in photos.py -- the same words, the other
    way up, because this one is off until asked for.
    """
    return os.getenv("RHDB_OPEN", "").strip().lower() in ("1", "true", "yes", "on")


def _announce_auth(enabled: bool, on_purpose: bool) -> bool:
    """Say which of the two states the app came up in, and answer whether the pages
    should carry the warning banner as well (ADR-0019).

    Blank credentials make `auth_gate` treat every visitor as the owner, able to
    edit and delete anything. That is a supported way to run -- a local copy, a
    read-only install on a trusted network -- and it is also what a `.env` that is
    missing or was left behind when the checkout moved produces, with nothing to
    show for it but the traffic link and the log out button quietly gone from a
    menu. Which is how the state was actually found, weeks later, by somebody asking
    where the traffic page had got to.

    So the app assumes the mistake and says so twice over, because a log line only
    reaches somebody who goes looking and nobody did. RHDB_OPEN is the operator
    saying they meant it, after which this goes quiet.

    A function of its two arguments rather than a side effect at import: the suite
    can then ask it what it says for each of the four states, instead of racing an
    import that has already happened by the time a test is collected.

    Nothing here reads a credential. It names the variables and never their values,
    which is what keeps a startup line safe to paste into a bug report.
    """
    if enabled:
        if on_purpose:
            log.warning(
                "RHDB_OPEN is set, but RHDB_AUTH_USER and RHDB_AUTH_PASSWORD are "
                "set too, so the login is on and RHDB_OPEN is doing nothing. Unset "
                "it, or clear the credentials if this site is meant to be open."
            )
        return False
    if on_purpose:
        log.info(
            "Running with no login (RHDB_OPEN is set): every visitor may edit "
            "and delete anything in the register."
        )
        return False
    log.warning(
        "NO LOGIN: RHDB_AUTH_USER and RHDB_AUTH_PASSWORD are not set, so every "
        "visitor may edit and delete anything in the register. If that is not what "
        "you meant, set them and RHDB_SECRET_KEY -- a .env that is missing or was "
        "left behind when the checkout moved looks exactly like this. If it is what "
        "you meant, set RHDB_OPEN=1 and this stops."
    )
    return True


# Read once at import, beside the flag it is about, so there is no window in which
# the app is configured open and has not said so.
templates.env.globals["auth_open_warning"] = _announce_auth(AUTH_ENABLED, _open_on_purpose())


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
        return secrets.compare_digest(u, AUTH_USER) and secrets.compare_digest(p, AUTH_PASS)
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
    if path in (
        "/",
        "/stats",
        "/browse",
        "/suggest",
        "/robots.txt",
        "/sitemap.xml",
        "/favicon.ico",
        "/apple-touch-icon.png",
        "/apple-touch-icon-precomposed.png",
    ):
        return True
    # The deploy smoke check and any uptime monitor hit this with no credentials
    # at all -- it must answer before a login is possible, not redirect to one.
    if path == "/healthz":
        return True
    # The catalogue, in both the shapes it is offered in. This is the one corner of
    # the JSON API that is public, and it is public because there is nothing of the
    # register in it: /api/machines answers with what was made rather than with what
    # is here, the same list that is in the repository as machines.yaml and
    # catalogue.txt. Putting the page behind the login and not the data behind it
    # would be a lock on a door in a field.
    if path in ("/machines", "/api/machines"):
        return True
    if path.startswith(("/images/", "/static/", "/style/")):
        return True
    # The share card a grid page's link previews as (ADR-0017), and it has to be
    # public or the feature does not exist: a preview is fetched *anonymously* --
    # the chat service reads the page as a stranger and then fetches the og:image it
    # names -- so behind the login every card would answer with a redirect to it and
    # no preview would ever render. Nothing is given away by that: the route opens a
    # file by hash and the photographs in it are already served to anybody from
    # /images.
    if path.startswith("/og/"):
        return True
    # The files kept beside the register read like the photographs do: a driver or
    # a manual is part of what the catalogue is for. Downloading one is public;
    # putting one there, re-filing it and deleting it are all POSTs, so they are
    # already behind the login by the rule above.
    #
    # Which file, though, is not a question a path can answer: the same route
    # serves a manual and a receipt, and only the row knows which. So this says
    # the door is open and `serve_file` asks who may come through it -- see
    # ADR-0009. The list at /files is public for the same reason and thins itself
    # the same way.
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
        return not (path.endswith(("/new", "/delete")) or "/edit" in path or "/label." in path)
    return False


async def auth_gate(request: Request, call_next: RequestResponseEndpoint) -> Response:
    """Public read-only browsing; login required to edit. Browsers use a session
    cookie (login page + logout); the API and tools use HTTP Basic."""
    path = request.url.path
    api_path = _is_api_path(path)
    # Browser paths trust the session cookie only, so logout is reliable; the API
    # and docs also accept HTTP Basic for the MCP server and command-line tools.
    has_basic = request.headers.get("authorization", "").startswith("Basic ")
    basic_ok = api_path and has_basic and _check_basic(request)
    request.state.authed = not AUTH_ENABLED or _check_cookie(request) or basic_ok
    # A wrong Basic credential is a guess at the API's door; rate-limit it as the
    # login form is. Only counted when a Basic header was actually sent and wrong,
    # so ordinary anonymous reads are untouched.
    if AUTH_ENABLED and api_path and has_basic and not basic_ok:
        ip = _client_ip(request)
        if not _login_limiter.check(ip):
            return Response("Too many failed attempts, try again later", status_code=429)
        _login_limiter.record(ip)
    # Read here so the notice can be left out of the markup altogether once it has
    # been dismissed, rather than shipped on every page and hidden by a script.
    request.state.noticed = NOTICE_COOKIE in request.cookies
    if path in ("/login", "/logout"):
        return await call_next(request)
    if not request.state.authed and not _is_public_read(request):
        if api_path:
            return Response(
                "Authentication required",
                status_code=401,
                headers={"WWW-Authenticate": 'Basic realm="Retro Hardware Database"'},
            )
        return RedirectResponse(f"/login?next={quote(path)}", status_code=303)
    return await call_next(request)


@router.get("/login", response_class=HTMLResponse, include_in_schema=False)
def gui_login(request: Request, next: str = "/") -> Response:
    if request.state.authed:
        return RedirectResponse(_safe_next(next), status_code=303)
    return templates.TemplateResponse(
        request, "login.html", {"next": _safe_next(next), "error": False, "noindex": True}
    )


@router.post("/login", include_in_schema=False)
async def gui_do_login(request: Request) -> Response:
    form = await posted(request)
    nxt = _safe_next(form.get("next", "/") or "/")
    ip = _client_ip(request)
    if not _login_limiter.check(ip):
        return templates.TemplateResponse(
            request,
            "login.html",
            {"next": nxt, "error": True, "rate_limited": True, "noindex": True},
            status_code=429,
        )
    ok = (
        AUTH_ENABLED
        and secrets.compare_digest(form.get("username", ""), AUTH_USER)
        and secrets.compare_digest(form.get("password", ""), AUTH_PASS)
    )
    if not ok:
        _login_limiter.record(ip)
        return templates.TemplateResponse(
            request, "login.html", {"next": nxt, "error": True, "noindex": True}, status_code=401
        )
    _login_limiter.reset(ip)
    resp = RedirectResponse(nxt, status_code=303)
    resp.set_cookie(
        COOKIE,
        _signer.dumps("ok"),
        max_age=SESSION_MAX_AGE,
        httponly=True,
        samesite="lax",
        secure=request.headers.get("x-forwarded-proto") == "https",
    )
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


@router.post("/logout", include_in_schema=False)
async def gui_logout(request: Request) -> Response:
    form = await posted(request)
    resp = RedirectResponse(_way_out(form.get("next", "") or ""), status_code=303)
    resp.delete_cookie(COOKIE)
    return resp
