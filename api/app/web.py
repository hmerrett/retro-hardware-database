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

from collections.abc import Mapping, Sequence
from datetime import date
from pathlib import Path

from fastapi import HTTPException, Request, Response
from fastapi.templating import Jinja2Templates
from markupsafe import Markup

from . import entry, filekinds, filesdb, labels, projects, settings
from .common import PUBLIC_BASE_URL, STATIC_DIR, _file_ver, branded
from .datacss import DATA_CSS_VER
from .photos import _image_size, img_srcset, img_url


templates = Jinja2Templates(directory=str(Path(__file__).resolve().parent / "templates"))
templates.env.globals.update(
    display_name=entry.display_name,
    type_label=entry.type_label,
    bezel_css=entry.bezel_css,
    bezel_class=entry.bezel_class,
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
    money=projects.money,
    status_label=projects.status_label,
    # The statuses that mean a project is over, so the pages that dim a finished
    # one do not each keep their own idea of which those are.
    closed_states=projects.CLOSED,
    # The settings a page is rendered through (ADR-0023). Callables rather than
    # values: these are registered once at import and read on every render, so a
    # name saved a moment ago is the name the next page carries.
    site_name=settings.site_name,
    site_theme=lambda: settings.value("theme"),
    site_indexed=lambda: not settings.on("block_search_engines"),
    # Whether a reader who is not signed in is told where a thing is kept. The item
    # pages ask it beside `request.state.authed`, which is the other half of the
    # same question (ADR-0027).
    public_locations=lambda: settings.on("public_locations"),
)
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
# The design tokens every page's colours come from (ADR-0024), stamped the same way.
templates.env.globals["tokens_ver"] = _file_ver(STATIC_DIR / "css" / "tokens.css")
# The generated stylesheet has no file to hash, so its stamp comes from the text
# itself -- built at import, like the rules in it (datacss).
templates.env.globals["data_css_ver"] = DATA_CSS_VER
# One stamp per script, read once at import the way the stylesheet's is. The
# scripts are served with a year's cache (see _CachedStatic), so the stamp in the
# URL is what makes a change to one of them arrive at all.
templates.env.globals["js_ver"] = {p.name: _file_ver(p) for p in sorted(STATIC_DIR.glob("*.js"))}
# Social sites cache a card hard, so its URL carries the artwork's hash too.
SITE_CARD_VER = _file_ver(branded(SITE_CARD[0].removeprefix("/static/")))


def _abs_url(request: Request, path: str) -> str:
    base = PUBLIC_BASE_URL or str(request.base_url).rstrip("/")
    return base + path


def _dot(*parts: object) -> str:
    return " · ".join(str(p) for p in parts if p)


def _og(
    request: Request,
    title: str,
    description: str = "",
    image_rel: str | None = None,
    card: tuple[str, int, int] | None = None,
) -> dict[str, str | int]:
    """Open Graph / Twitter-card context for a page's social-share preview.

    Three ways a page can have a picture, in the order they are preferred.
    `image_rel` is one stored photograph, which is what a page about one thing has.
    `card` is a picture already made for this page -- the montage of the photographs
    on a grid page (cards.montage, ADR-0017) -- which is what a page about many
    things has. Neither, and the site's own card, which is what a page with no
    photographs on it has.
    """
    og: dict[str, str | int] = {
        "title": title,
        "url": _abs_url(request, request.url.path),
        "description": " ".join((description or "").split())[:280],
    }
    if image_rel:
        og["image"] = _abs_url(request, img_url(image_rel))
        og["image_alt"] = title
        size = _image_size(image_rel)
        if size:
            og["image_w"], og["image_h"] = size
    elif card:
        path, og["image_w"], og["image_h"] = card
        og["image"] = _abs_url(request, path)
        # The card is named by a hash of what went into it, so what is at that URL
        # can never change and needs no ?v= of its own.
        og["image_alt"] = "Photographs from this page"
    else:
        # An item with no photo, a page of figures, a page of files: the site's own
        # card, so a shared link is never the bare text preview it used to be.
        path, og["image_w"], og["image_h"] = SITE_CARD
        og["image"] = _abs_url(request, f"{path}?v={SITE_CARD_VER}")
        og["image_alt"] = settings.site_name()
    return og


def _jsonld(
    og: Mapping[str, str | int], asset_id: str, brand: str | None, category: str
) -> dict[str, str | int | dict[str, str]]:
    """schema.org Product data for an item, so search engines can show a richer
    result. Built from the same values as the social-share card."""
    d: dict[str, str | int | dict[str, str]] = {
        "@context": "https://schema.org",
        "@type": "Product",
        "name": og["title"],
        "sku": asset_id,
        "category": category,
    }
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


def png_label(
    row: Mapping[str, object],
    kind: str,
    media: str = "",
    dpi: int = 0,
    parts: Sequence[Mapping[str, object]] = (),
    form_factor: str = "",
    spec_pairs: list[tuple[str, str]] | None = None,
    small: bool = True,
) -> Response:
    """A label as the dots a printer burns, for the three routes that serve one.

    The stock is named in the query and looked up rather than measured from it: a
    name the register does not know is a 404 and not a guess, because a guess is
    discovered by peeling a label off something (ADR-0024).
    """
    name = media or (labels.SMALL if small else labels.FULL)
    stock = labels.MEDIA.get(name)
    if stock is None:
        raise HTTPException(status_code=404, detail="No such label stock")
    png = labels.render_png(
        row,
        parts,
        kind,
        stock,
        dpi,
        small=small,
        form_factor=form_factor,
        spec_pairs=spec_pairs,
    )
    aid = str(row.get("asset_id") or "label")
    return Response(
        png,
        media_type="image/png",
        headers={"Content-Disposition": f'inline; filename="{aid}-{name}.png"'},
    )


def label_send() -> dict[str, object]:
    """What the label button needs to know: where a label may go, where it goes
    here, and what stock the Bluetooth printer has.

    Worked out once per page rather than written into each template, and read from
    `settings` rather than kept beside it, so the menu on the settings page and the
    button on an item page cannot come to disagree about what exists (ADR-0026)."""
    destination = settings.BY_KEY["label_destination"]
    return {
        "destinations": [list(pair) for pair in settings.choices_for(destination)],
        "default": settings.value("label_destination"),
        "bluetoothMedia": settings.value("label_bluetooth_media"),
        # Versioned like every other script on the site, and for the same reason:
        # static files are served with an hour's cache, so a bare path is a file
        # somebody goes on running for an hour after it was fixed. This one is
        # loaded by `import()` from another script rather than by a tag in a
        # template, which is how it came to be the only one without a version --
        # and, for a printer driver being corrected against real hardware, the
        # worst possible file to have to wait an hour for.
        "driver": f"/static/niimbot.js?v={_file_ver(STATIC_DIR / 'niimbot.js')}",
    }


templates.env.globals["label_send"] = label_send
templates.env.globals["img_url"] = img_url
templates.env.globals["img_srcset"] = img_srcset
templates.env.globals["THUMB_CARD"] = 300
templates.env.globals["THUMB_MAIN"] = 1200
templates.env.globals["human_size"] = filekinds.human_size
templates.env.globals["max_file_mb"] = filesdb.MAX_BYTES // (1024 * 1024)
