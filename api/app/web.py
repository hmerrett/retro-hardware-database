"""The templates object, and what a page needs around one.

Everything a route reaches for in order to render: the Jinja environment with the
globals and the filter registered on it, the Open Graph card a shared link shows,
the schema.org data under an item page, and the small helpers a page's own text is
built from.

Here rather than in main so that a group of routes can move out of main without
taking a copy of the environment with it -- there is one environment, made once,
and whatever registers a global registers it on that one. What is not here yet is
what depends on something still in main: whether auth is on, the two cookie names,
and the history stamp. main registers those on this same object, and they will
follow their own helpers out when those move.
"""
from datetime import date
from pathlib import Path

from fastapi import Request
from fastapi.templating import Jinja2Templates
from markupsafe import Markup

from . import entry, filesdb, labels, projects
from .common import PUBLIC_BASE_URL, STATIC_DIR, _file_ver, branded
from .photos import _image_size, img_srcset, img_url


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

# The share card for a page with no photograph of its own: the logo on its own
# cream, opaque and at the 1.91:1 those slots want (tools/make_icons.py makes it).
# Several of the sites that show these composite a transparent PNG onto black,
# which is why this one is not transparent.
SITE_CARD = ("/static/og-image.png", 1200, 630)

templates.env.globals["icon_ver"] = _file_ver(branded("favicon.ico"))
templates.env.globals["css_ver"] = _file_ver(STATIC_DIR / "app.css")
# Social sites cache a card hard, so its URL carries the artwork's hash too.
SITE_CARD_VER = _file_ver(branded(SITE_CARD[0].removeprefix("/static/")))

def _abs_url(request: Request, path: str) -> str:
    base = PUBLIC_BASE_URL or str(request.base_url).rstrip("/")
    return base + path

def _dot(*parts) -> str:
    return " · ".join(str(p) for p in parts if p)

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

def _safe_next(nxt: str) -> str:
    return nxt if nxt.startswith("/") and not nxt.startswith("//") else "/"

templates.env.globals["img_url"] = img_url
templates.env.globals["img_srcset"] = img_srcset
templates.env.globals["THUMB_CARD"] = 300
templates.env.globals["THUMB_MAIN"] = 1200
templates.env.globals["human_size"] = filesdb.human_size
templates.env.globals["max_file_mb"] = filesdb.MAX_BYTES // (1024 * 1024)
