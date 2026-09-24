"""The Content-Security-Policy: that it is sent, and that the pages still fit it.

Two halves, and the second is the one that earns its keep. Sending the header is
a line of middleware and it either works or every page breaks at once. What no
browser will tell you until a reader hits it is that a template has grown an
inline handler, or a script tag with its code in the tag, or a link to somebody
else's CDN -- each of which the policy blocks silently, on that page, for
everybody, months after the change that did it.

So these read the policy off a real response, and then read the rendered pages
against it. They are markup tests in the same spirit as test_keyboard_and_motion:
the browser is not here, so the assertion is made against what would be sent to
one. ADR-0021.
"""

import re

import pytest

from app import main

# Loaded without `src`, a <script> is code, and `script-src 'self'` blocks it --
# but only if the browser would run it. A `type` the browser does not recognise
# as JavaScript makes the element a data block, which it parses as nothing and
# hands to whoever asks for it by id. Both kinds are here and both are wanted:
# `application/json` carries the values the templates used to interpolate into
# the script, and `application/ld+json` is the structured data the item pages
# publish for search engines.
SCRIPT_TAG = re.compile(r"<script\b([^>]*)>", re.I)
HAS_SRC = re.compile(r"\bsrc\s*=", re.I)
TYPE = re.compile(r"""\btype\s*=\s*["']?([^"'\s>]+)""", re.I)
# The types a browser executes: the legacy and current JavaScript MIME types, and
# `module`. Everything else, including no type at all being absent, is decided below.
JAVASCRIPT = re.compile(r"^(?:module|(?:text|application)/(?:x-)?(?:java|ecma)script)$", re.I)


def executable(attributes: str) -> bool:
    """Whether the browser would run this <script>'s contents -- which is the
    only case `script-src` has an opinion about."""
    if HAS_SRC.search(attributes):
        return False  # a file, and the policy judges it by its origin
    declared = TYPE.search(attributes)
    return declared is None or bool(JAVASCRIPT.match(declared.group(1)))


# on* as an attribute name only: `ondisk="..."` in a form field is not a handler,
# and neither is the word "online" in prose.
INLINE_HANDLER = re.compile(
    r"""[\s"'](on(?:click|change|submit|input|load|error|"""
    r"""focus|blur|keydown|keyup|mouseover|mouseout|"""
    r"""select|reset|drop|dragover))\s*=""",
    re.I,
)

# Anything the browser is told to fetch. A scheme and a host means another origin;
# `/images/...` and `/static/...` mean this one.
#
# <link> is deliberately not in here. Whether one fetches anything depends on its
# `rel`: a stylesheet or an icon does, and `canonical` -- which every page carries,
# at the site's real public address -- is metadata for a search engine that the
# browser never requests. Judging those by their URL flags the canonical link on
# every page and says the policy is broken when it is not.
FETCHED = re.compile(
    r"""<(?:script|img|iframe|source|video|audio|embed|object)\b[^>]*"""
    r"""\b(?:src|data)\s*=\s*["']([^"']+)["']""",
    re.I,
)
LINK_TAG = re.compile(r"<link\b([^>]*)>", re.I)
REL = re.compile(r"""\brel\s*=\s*["']?([^"'>]+)""", re.I)
HREF = re.compile(r"""\bhref\s*=\s*["']([^"']+)["']""", re.I)
FETCHING_RELS = {
    "stylesheet",
    "icon",
    "shortcut",
    "apple-touch-icon",
    "manifest",
    "preload",
    "prefetch",
    "preconnect",
}
OFF_SITE = re.compile(r"^(?:[a-z][a-z0-9+.-]*:)?//", re.I)


def link_fetches(attributes: str) -> str | None:
    """The URL a <link> actually requests, or None if its `rel` requests nothing.
    Read in either attribute order, because markup is written both ways."""
    rel = REL.search(attributes)
    href = HREF.search(attributes)
    if not rel or not href:
        return None
    if FETCHING_RELS & {word.lower() for word in rel.group(1).split()}:
        return href.group(1)
    return None


# A link that runs script instead of going somewhere. `script-src 'self'` blocks
# a javascript: URL, so one of these is a dead control, not a slow one.
SCRIPT_URL = re.compile(r"""\bhref\s*=\s*["']\s*javascript:""", re.I)

STYLE_ATTRIBUTE = re.compile(r"""[\s"']style\s*=\s*["']""", re.I)

# What ADR-0021 records. Stated here rather than imported so that changing the
# policy means changing it in two places on purpose: the middleware sends it, and
# this says it is the one that was decided on.
EXPECTED = {
    "default-src": ("'self'",),
    "script-src": ("'self'",),
    "style-src": ("'self'",),
    "img-src": ("'self'",),
    "font-src": ("'self'",),
    "connect-src": ("'self'",),
    "form-action": ("'self'",),
    "frame-ancestors": ("'self'",),
    "base-uri": ("'none'",),
    "object-src": ("'none'",),
}


def directives(header: str) -> dict:
    """The header as {name: (source, ...)}, so an assertion names one directive."""
    out = {}
    for part in header.split(";"):
        if part.strip():
            name, *sources = part.split()
            out[name.lower()] = tuple(sources)
    return out


@pytest.mark.parametrize(
    "path",
    [
        "/",  # a rendered page
        "/api/assets",  # the JSON API
        "/static/app.js",  # a static file, served by the mount
        "/healthz",  # the health check
        "/computers/RH-9999",  # a 404: an error is a response somebody sees
    ],
)
def test_every_response_carries_the_policy(client, path):
    """Including the ones nobody thinks of as pages. A 404 renders markup and a
    static file is script; both are places an injection would like to land."""
    response = client.get(path)
    assert "Content-Security-Policy" in response.headers, (
        f"{path} ({response.status_code}) was sent with no policy"
    )


def test_a_response_the_gate_makes_itself_carries_it_too(client, monkeypatch):
    """The middleware is registered last, so it wraps the auth gate rather than
    sitting inside it. Were it the other way round, every redirect to the login
    page -- the one response an unauthenticated stranger is most likely to get --
    would go out bare."""
    monkeypatch.setattr(main.auth, "AUTH_ENABLED", True)
    response = client.get("/computers/new", follow_redirects=False)
    assert response.status_code in (302, 303, 307, 401), (
        f"expected the gate to turn this away, got {response.status_code}"
    )
    assert "Content-Security-Policy" in response.headers, (
        "the gate's own response went out with no policy"
    )


def test_the_policy_is_the_one_recorded(client):
    """ADR-0021 states the directives; this is that statement as an assertion.
    A change here should be a change to the ADR first."""
    sent = directives(client.get("/").headers["Content-Security-Policy"])
    assert sent == EXPECTED


def test_a_pdf_shown_in_the_browser_carries_a_policy_of_its_own(client):
    """The one response that says its own (ADR-0030). A PDF is drawn by the
    browser's viewer, which the site's object-src 'none' can blank, so it may load
    objects from the site -- and nothing else at all: no script, no frame, no form."""
    r = client.post(
        "/files",
        files={"uploads": ("manual.pdf", b"%PDF-1.4\n%%EOF\n")},
        follow_redirects=False,
    )
    assert r.status_code == 303, r.text
    fid = client.get("/api/files").json()[0]["id"]
    sent = directives(
        client.get(f"/files/{fid}/view/manual.pdf").headers["Content-Security-Policy"]
    )
    assert sent["default-src"] == ("'none'",)
    assert sent["object-src"] == ("'self'",)
    assert "script-src" not in sent and "style-src" not in sent
    for directive in ("form-action", "frame-ancestors", "base-uri"):
        assert directive in sent, f"{directive} does not fall back to default-src"


def test_the_directives_that_do_not_fall_back_are_stated(client):
    """`form-action`, `frame-ancestors` and `base-uri` ignore `default-src`. Left
    out they are simply absent, which reads as a tight policy and is not one."""
    sent = directives(client.get("/").headers["Content-Security-Policy"])
    for directive in ("form-action", "frame-ancestors", "base-uri"):
        assert directive in sent, f"{directive} does not fall back to default-src"


def test_no_page_carries_a_script_the_policy_would_block(client, a_page_of_everything):
    """A <script> with no `src` is code in the page, which is what the policy is
    for. The one exception is a data island, which the browser never executes."""
    inline = []
    for path in a_page_of_everything:
        page = client.get(path)
        assert page.status_code == 200, f"{path} did not render: {page.status_code}"
        for attributes in SCRIPT_TAG.findall(page.text):
            if executable(attributes):
                inline.append(f"{path}: <script{attributes}>")
    assert inline == [], (
        "script-src 'self' blocks these; give the code a file or the data a type: "
        + "; ".join(inline[:8])
    )


def test_no_page_carries_an_inline_event_handler(client, a_page_of_everything):
    """`onclick="..."` is script in an attribute, and the policy blocks it as
    surely as a script tag. The delegated listeners in app.js are the shape that
    survives: `data-confirm` and `data-back` are markup, read by code in a file."""
    handlers = []
    for path in a_page_of_everything:
        page = client.get(path)
        for match in INLINE_HANDLER.finditer(page.text):
            handlers.append(f"{path}: {match.group(1)}=")
    assert handlers == [], "these would not fire under the policy: " + "; ".join(
        sorted(set(handlers))[:8]
    )


def test_no_link_runs_script_instead_of_going_somewhere(client, a_page_of_everything):
    """`href="javascript:history.back()"` is a control that does nothing at all
    under the policy, and says nothing about it. The three form pages each had
    one."""
    dead = []
    for path in a_page_of_everything:
        if SCRIPT_URL.search(client.get(path).text):
            dead.append(path)
    assert dead == [], "a javascript: link is blocked by script-src 'self': " + ", ".join(dead)


def test_nothing_is_loaded_from_another_origin(client, a_page_of_everything):
    """Every directive is `'self'`, which is a description and not a wish: the
    photographs are served from the images volume, reference pictures are fetched
    into it server-side rather than hot-linked, and the QR decoder is vendored.
    A CDN link added later would be blocked, and the page would half-work."""
    external = []
    for path in a_page_of_everything:
        markup = client.get(path).text
        requested = FETCHED.findall(markup)
        requested += [url for url in map(link_fetches, LINK_TAG.findall(markup)) if url]
        for url in requested:
            if OFF_SITE.match(url.strip()):
                external.append(f"{path}: {url}")
    assert external == [], "the policy allows this origin only: " + "; ".join(external[:8])


def test_no_page_carries_a_style_attribute(client, a_page_of_everything):
    """The policy allows none (ADR-0022), so one written into a template would not
    be applied -- silent in the browser and easy to miss in review, because the
    markup looks right and the page merely comes out wrong.

    The token went with the attributes in one change, which is the only order that
    works: the attributes without the token lose their layout, and the token
    without the attributes is a hole kept open for nothing."""
    style_src = directives(client.get("/").headers["Content-Security-Policy"])["style-src"]
    assert "'unsafe-inline'" not in style_src
    attributed = [
        path for path in a_page_of_everything if STYLE_ATTRIBUTE.search(client.get(path).text)
    ]
    assert attributed == [], (
        "style-src no longer allows these, so they have no effect: " + ", ".join(attributed)
    )
