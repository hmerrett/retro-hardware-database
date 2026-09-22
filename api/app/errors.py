"""What a browser is shown when a request cannot be answered.

FastAPI's own answer to a 404 is `{"detail": "..."}`, which is the right answer to
a program and the wrong one to a person: the register's way in is a printed QR
label, and a label from another collection scans to an asset tag this one has
never issued. Whoever is holding the machine gets a line of JSON and reads it as
the site being broken, with no search box on the screen to try again from.

So three statuses -- nothing there, nothing for you, and something wrong at this
end -- are rendered as a page in the site's own chrome. Who asked is what decides:
the API keeps its JSON whoever asks for it, and so does anything that did not ask
for HTML, which leaves `curl`, the tool server and the command-line tools exactly
as they were.
"""

from fastapi import FastAPI, Request, Response
from fastapi.exception_handlers import http_exception_handler
from starlette.exceptions import HTTPException as StarletteHTTPException
from starlette.responses import PlainTextResponse

from .auth import _is_api_path
from .common import CONTENT_SECURITY_POLICY
from .web import templates

# The number, the line under it, and the heading between them. The wording is dry
# on purpose: the likeliest reader is somebody who scanned a label, and telling
# them the server's business helps nobody -- 500 in particular says what it can
# and leaves the rest in the log, where it belongs.
PAGES: dict[int, tuple[str, str]] = {
    403: (
        "Not for you",
        "This page is there, and is not open to you.",
    ),
    404: (
        "Nothing here",
        "Nothing is filed at this address. A label from another collection scans "
        "to a tag this register has never issued, and an address typed by hand is "
        "a character away from being nobody's.",
    ),
    500: (
        "Something went wrong",
        "The fault is at this end rather than in what you asked for. It has been "
        "written to the log.",
    ),
}


def _wants_page(request: Request) -> bool:
    """Whether this request is a person's, and so gets a page.

    Two questions, and both have to be yes. `/api` and the docs are a program's
    surface whatever a browser's Accept header says -- one opened in a browser
    still answers as the API. And an `Accept` without `text/html` is a program
    asking: the suite's own client sends `*/*`, as `curl` does, and keeps the JSON.
    """
    if _is_api_path(request.url.path):
        return False
    return "text/html" in request.headers.get("accept", "")


def _page(request: Request, status: int) -> Response:
    """The error page, in the site chrome, at the status that brought it here."""
    heading, line = PAGES[status]
    # The chrome reads two things off the request that the gate puts there, and a
    # fault raised before the gate ran -- or in the gate itself -- would leave them
    # missing and turn this page into a second error. Stated rather than assumed:
    # a stranger, and no cookie notice on a page that is already an apology.
    if not hasattr(request.state, "authed"):
        request.state.authed = False
    if not hasattr(request.state, "noticed"):
        request.state.noticed = True
    return templates.TemplateResponse(
        request,
        "error.html",
        {"status": status, "heading": heading, "line": line, "noindex": True},
        status_code=status,
    )


async def http_error(request: Request, exc: Exception) -> Response:
    """A raised `HTTPException`: a page for the three, the JSON for everything else.

    Registered for `HTTPException` alone, so the fallback is only ever reached with
    one; the check is what tells mypy that, and it costs nothing.
    """
    if isinstance(exc, StarletteHTTPException):
        if exc.status_code in PAGES and _wants_page(request):
            return _page(request, exc.status_code)
        return await http_exception_handler(request, exc)
    return await unhandled_error(request, exc)


async def unhandled_error(request: Request, exc: Exception) -> Response:
    """Anything that got out: the 500 page, and the exception goes on up.

    Starlette catches this outside every middleware -- by the time the exception
    arrives the response has passed the one that sends the content policy, so the
    page sends it itself rather than being the one page on the site without it.

    Returning a response rather than re-raising is what keeps the plain answer
    plain: Starlette re-raises after this either way, so the server still logs the
    traceback.
    """
    if not _wants_page(request):
        return PlainTextResponse("Internal Server Error", status_code=500)
    response = _page(request, 500)
    response.headers.setdefault("Content-Security-Policy", CONTENT_SECURITY_POLICY)
    return response


def install(app: FastAPI) -> None:
    """Put both handlers on the app. Called by `create_app`, with the wiring."""
    app.add_exception_handler(StarletteHTTPException, http_error)
    app.add_exception_handler(Exception, unhandled_error)
