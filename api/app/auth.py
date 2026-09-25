"""The login, first-run setup, and the gate every request passes through.

One module, on purpose. Who is asking, what their role lets them reach, the rate
limiter, the gate that reads all of them, and the doors somebody comes in and out
by: each of those is only meaningful in terms of the others, and splitting them
would leave two copies of the question "may this reader see this?" to be kept in
step. What an account *is* -- its password, its sessions, its tokens, its role --
is `accounts/` (ADR-0032).

main registers the gate as middleware rather than this module doing it, because
middleware belongs to the app object and the order of the two matters: the gate is
registered last so that it sits outside the cache-header one.
"""

import base64
import logging
import os
import time
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from urllib.parse import quote, urlparse

from fastapi import APIRouter, Depends, FastAPI, HTTPException, Request
from fastapi.responses import HTMLResponse, RedirectResponse, Response
from sqlalchemy.orm import Session
from starlette.concurrency import run_in_threadpool
from starlette.middleware.base import RequestResponseEndpoint

from . import settings
from .accounts import firstrun, store
from .accounts.roles import ADMIN, EDIT, READ_PRIVATE, VISITOR, Principal, can
from .db import SessionLocal, get_db
from .forms import posted
from .web import _safe_next, templates

router = APIRouter()

# Nothing in the app configures logging: under uvicorn its config is already in
# place by the time this module is imported, and outside it a WARNING still reaches
# stderr through logging's last-resort handler. So a warning raised here is seen
# either way, which is the point of raising it here.
log = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(_app: FastAPI) -> AsyncIterator[None]:
    """At startup: seed the first account from the old single login if there is
    one to seed from, and say in the log which state the site came up in.

    The old pair is read here and nowhere else in the app. The tool server still
    reads it for itself, until it has a token."""
    firstrun.startup(
        os.getenv("RHDB_AUTH_USER", ""),
        os.getenv("RHDB_AUTH_PASSWORD", ""),
        os.getenv("RHDB_OPEN", ""),
    )
    yield


# The session cookie holds a random key the database keeps a digest of, so it signs
# nothing and needs no secret: RHDB_SECRET_KEY is no longer read.
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
SESSION_MAX_AGE = int(store.SESSION_LIFE.total_seconds())

# The setting that closes the site to visitors. Named once, here, beside the gate
# that reads it; settings.py holds its label and default.
CLOSED = "login_to_read"


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


def _is_api_path(path: str) -> bool:
    return path.startswith(("/api", "/docs")) or path == "/openapi.json"


# The one prefix a machine holding no password may knock on. Everything under it
# takes a print agent's own key, checked by the route rather than here -- the same
# shape ADR-0009 uses for files, where the door is open and the row decides. The
# gate cannot do it: it would have to know which agent, which is the route's answer
# and the whole of what the key is for.
AGENT_PREFIX = "/api/print/agent/"


def note_wrong_secret(request: Request) -> bool:
    """Count one wrong secret at the API's door against the address that sent it,
    and say whether to answer at all.

    The same limiter the login form and HTTP Basic use, for the same reason: a door
    a machine may knock on with no password is a door that can be knocked on all
    night. False means the caller has had its share of guesses.
    """
    ip = _client_ip(request)
    if not _login_limiter.check(ip):
        return False
    _login_limiter.record(ip)
    return True


def _always_open(path: str) -> bool:
    """What answers anybody, even on a site closed to visitors or not yet set up:
    the doors themselves, what they are drawn with, and the health check.

    The icons are here because a browser asks for them on the login page, and the
    stylesheets because the login page without them is a page nobody trusts with a
    password. robots.txt because a crawler reads it before anything else, and on a
    closed site it is where the crawler learns there is no sitemap to follow."""
    if path in (
        "/login",
        "/logout",
        "/setup",
        "/healthz",
        "/robots.txt",
        "/favicon.ico",
        "/apple-touch-icon.png",
        "/apple-touch-icon-precomposed.png",
    ):
        return True
    return path.startswith(("/static/", "/style/", AGENT_PREFIX))


# Pages that are not public, and that a viewer may read: they show what a visitor is
# not shown, and change nothing. Anything not listed here or public is an
# administrator's, so a new page nobody thought to list is kept from a viewer rather
# than shown to one.
VIEWER_PAGES = frozenset({"/for-sale"})

# A person's own account: their password, their sessions, their tokens. Anybody
# signed in, whatever their role, and every method -- changing your own password is
# a write a viewer is allowed.
OWN_ACCOUNT = "/settings/account"


def may(principal: Principal, method: str, path: str, closed: bool) -> bool:
    """Whether this principal may make this request at all.

    The coarse answer, by path. The fine one -- which file, which project -- is the
    route's, as it always was (ADR-0009): the gate says the door is open and the
    row decides who comes through it."""
    if can(principal, EDIT):
        return True
    if principal.signed_in and (path == OWN_ACCOUNT or path.startswith(OWN_ACCOUNT + "/")):
        return True
    if method != "GET":
        return False
    if can(principal, READ_PRIVATE) and (path in VIEWER_PAGES or _is_api_path(path)):
        return True
    if closed and not principal.signed_in:
        return False
    return _public_page(path)


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
    # would be a lock on a door in a field. A model's own page is the same list
    # read one entry at a time, beside the units of it here, whose pages are
    # public already.
    if path in ("/machines", "/api/machines") or path.startswith("/machines/"):
        return True
    if path.startswith(("/images/", "/static/", "/style/")):
        return True
    # Folding the side rail away. A visitor has a rail too, and a link that answered
    # with the login page would fold nothing and lose them the page they were on.
    if path.startswith("/rail/"):
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


def _basic(db: Session, header: str) -> Principal | None:
    try:
        u, _, p = base64.b64decode(header[6:]).decode("utf-8").partition(":")
    except ValueError:
        return None
    user = store.authenticate(db, u, p)
    return store.principal(db, user, "basic") if user else None


def _who(path: str, cookie: str, header: str) -> tuple[Principal, bool]:
    """Who this request is from, and whether it offered a credential that was wrong.

    Browser paths trust the session cookie only, so logging out is reliable; the
    API and the docs also take a bearer token or HTTP Basic, for the tool server and
    the command-line tools. Run in a thread by the gate, because it reads the
    database and a Basic password is an argon2 verify.

    Not at the print agent's door, whose bearer is the agent's own key and is
    checked by the route: read here, every label collected would count as a wrong
    guess at an account's token."""
    offered = (
        _is_api_path(path)
        and not path.startswith(AGENT_PREFIX)
        and header.startswith(("Bearer ", "Basic "))
    )
    if not cookie and not offered:
        return VISITOR, False
    with SessionLocal() as db:
        if cookie and (p := store.from_session(db, cookie)):
            return p, False
        if not offered:
            return VISITOR, False
        if header.startswith("Bearer "):
            p = store.from_token(db, header[7:].strip())
        else:
            p = _basic(db, header)
        return (p, False) if p else (VISITOR, True)


def _forbidden(request: Request, api_path: bool) -> Response:
    """Somebody signed in, asking for something their role does not reach.

    403 and not the login: sending a signed-in viewer to log in would ask them to
    prove again who they are, which is not what is wrong."""
    if api_path:
        return Response("Your account may not do that", status_code=403)
    # Imported here: errors reads _is_api_path from this module, and the page it
    # draws is the site's one 403, so a second one of this module's own would be two
    # answers to the same question.
    from .errors import page

    return page(request, 403)


async def auth_gate(request: Request, call_next: RequestResponseEndpoint) -> Response:
    """Works out who is asking and whether they may, and answers for the route when
    they may not (ADR-0032).

    Sets `request.state.principal`, and the two questions nearly every page asks of
    it: `authed`, whether they may edit, and `sees_private`, whether they may see
    what a visitor is not shown."""
    path = request.url.path
    api_path = _is_api_path(path)
    principal, wrong = await run_in_threadpool(
        _who, path, request.cookies.get(COOKIE, ""), request.headers.get("authorization", "")
    )
    request.state.principal = principal
    request.state.authed = can(principal, EDIT)
    request.state.sees_private = can(principal, READ_PRIVATE)
    # Read here so the notice can be left out of the markup altogether once it has
    # been dismissed, rather than shipped on every page and hidden by a script.
    request.state.noticed = NOTICE_COOKIE in request.cookies
    # A wrong token or password is a guess at the API's door; rate-limit it as the
    # login form is. Only counted when one was actually sent and wrong, so ordinary
    # anonymous reads are untouched.
    if wrong:
        ip = _client_ip(request)
        if not _login_limiter.check(ip):
            return Response("Too many failed attempts, try again later", status_code=429)
        _login_limiter.record(ip)
    if not firstrun.ready():
        # Nothing but setup, and what it is drawn with, until there is an administrator.
        if path == "/login" or not _always_open(path):
            if api_path:
                return Response(
                    "This site has no accounts yet: finish setting it up at /setup",
                    status_code=503,
                )
            return RedirectResponse("/setup", status_code=303)
        return await call_next(request)
    if _always_open(path) or may(principal, request.method, path, settings.on(CLOSED)):
        return await call_next(request)
    if principal.signed_in:
        return _forbidden(request, api_path)
    if api_path:
        return Response(
            "Authentication required",
            status_code=401,
            headers={"WWW-Authenticate": 'Basic realm="Retro Hardware Database"'},
        )
    return RedirectResponse(f"/login?next={quote(path)}", status_code=303)


def _signed_in(request: Request, resp: Response, key: str) -> Response:
    resp.set_cookie(
        COOKIE,
        key,
        max_age=SESSION_MAX_AGE,
        httponly=True,
        samesite="lax",
        secure=request.headers.get("x-forwarded-proto") == "https",
    )
    return resp


def _login_page(request: Request, status: int = 200, **context: object) -> Response:
    return templates.TemplateResponse(
        request,
        "login.html",
        {"error": False, "noindex": True, "closed": settings.on(CLOSED)} | context,
        status_code=status,
    )


@router.get("/login", response_class=HTMLResponse, include_in_schema=False)
def gui_login(request: Request, next: str = "/") -> Response:
    if request.state.principal.signed_in:
        return RedirectResponse(_safe_next(next), status_code=303)
    return _login_page(request, next=_safe_next(next))


@router.post("/login", include_in_schema=False)
async def gui_do_login(request: Request, db: Session = Depends(get_db)) -> Response:
    form = await posted(request)
    nxt = _safe_next(form.get("next", "/") or "/")
    ip = _client_ip(request)
    if not _login_limiter.check(ip):
        return _login_page(request, next=nxt, error=True, rate_limited=True, status=429)
    user = await run_in_threadpool(
        store.authenticate, db, form.get("username", ""), form.get("password", "")
    )
    if user is None:
        _login_limiter.record(ip)
        return _login_page(request, next=nxt, error=True, status=401)
    _login_limiter.reset(ip)
    return _signed_in(request, RedirectResponse(nxt, status_code=303), store.open_session(db, user))


def _setup_page(
    request: Request, error: str = "", username: str = "", status: int = 200
) -> Response:
    firstrun.code()
    return templates.TemplateResponse(
        request,
        "setup.html",
        {"error": error, "username": username, "noindex": True},
        status_code=status,
    )


@router.get("/setup", response_class=HTMLResponse, include_in_schema=False)
def gui_setup(request: Request) -> Response:
    """The first administrator, made by whoever can read the log (ADR-0032). Gone,
    as a 404, once there is an account: a page that could make an administrator
    must not exist a moment longer than it is needed."""
    if firstrun.ready():
        raise HTTPException(404)
    return _setup_page(request)


@router.post("/setup", include_in_schema=False)
async def gui_do_setup(request: Request, db: Session = Depends(get_db)) -> Response:
    if firstrun.ready():
        raise HTTPException(404)
    form = await posted(request)
    username = form.get("username", "").strip()
    ip = _client_ip(request)
    if not _login_limiter.check(ip):
        return _setup_page(request, "Too many wrong codes. Try again later.", username, 429)
    if not firstrun.code_matches(form.get("code", "")):
        _login_limiter.record(ip)
        return _setup_page(request, "That is not the setup code.", username, 400)
    password = form.get("password", "")
    if password != form.get("password2", ""):
        return _setup_page(request, "The two passwords were not the same.", username, 400)
    try:
        user = await run_in_threadpool(store.create, db, username, password, ADMIN)
    except store.AccountError as e:
        return _setup_page(request, str(e), username, 400)
    _login_limiter.reset(ip)
    firstrun.mark_ready()
    log.warning("Setup finished: %s is the first administrator.", user.username)
    return _signed_in(request, RedirectResponse("/", status_code=303), store.open_session(db, user))


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
async def gui_logout(request: Request, db: Session = Depends(get_db)) -> Response:
    """Ends the session on the server, not only in the browser: a copy of the cookie
    taken before now stops working too."""
    form = await posted(request)
    if key := request.cookies.get(COOKIE):
        store.end_session(db, key)
    resp = RedirectResponse(_way_out(form.get("next", "") or ""), status_code=303)
    resp.delete_cookie(COOKIE)
    return resp
