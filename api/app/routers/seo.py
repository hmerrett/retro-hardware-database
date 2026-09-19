"""The routes a crawler or a browser asks for by convention rather than by link:
robots.txt, the sitemap, and the icons requested at the domain root.

They have nothing to do with the register and nothing to do with each other beyond
that, which is why they are the first group out of main.py: the site's page routes
can move afterwards without this corner moving again.
"""

from datetime import datetime
from xml.sax.saxutils import escape

from fastapi import APIRouter, Depends, Request
from fastapi.responses import FileResponse, Response
from sqlalchemy import func
from sqlalchemy.orm import Session

from .. import settings
from ..common import PUBLIC_BASE_URL, branded
from ..db import get_db
from ..models import Computer, LogEntry, Part, Project

router = APIRouter()


@router.get("/robots.txt", include_in_schema=False)
def robots_txt(request: Request) -> Response:
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
        # The owner's shortlist. Already behind the login, so this is belt and
        # braces -- but a crawler that followed a link to it and filed the login
        # page under its name would be publishing that the list exists (ADR-0018).
        "Disallow: /for-sale\n"
        # Filtered slices of the gallery: the items in them are indexed already.
        "Disallow: /browse\n"
        # What the search bar reads while you type: JSON about pages already indexed.
        "Disallow: /suggest\n"
        "Disallow: /computers/new\n"
        "Disallow: /parts/new\n"
        "Disallow: /projects/new\n"
        "Disallow: /*/edit\n"
    )
    # A site that has asked not to be listed still lets the crawler in, and this is
    # the whole reason it can: refused here, a crawler never reads the page, never
    # meets the noindex that base.html now puts on every one of them, and files the
    # address anyway from whatever links to it. What does go is the sitemap --
    # asking not to be listed while handing over a list of everything to list is
    # two answers to one question (ADR-0023).
    if not settings.on("block_search_engines"):
        body += f"Sitemap: {base}/sitemap.xml\n"
    return Response(body, media_type="text/plain")


@router.get("/sitemap.xml", include_in_schema=False)
def sitemap_xml(request: Request, db: Session = Depends(get_db)) -> Response:
    base = PUBLIC_BASE_URL or str(request.base_url).rstrip("/")
    # Newest change per asset, for <lastmod>.
    last: dict[str | None, datetime | None] = dict(
        db.query(LogEntry.asset_id, func.max(LogEntry.created_at))
        .group_by(LogEntry.asset_id)
        .tuples()
    )
    urls: list[tuple[str, datetime | None]] = [
        (f"{base}/", None),
        (f"{base}/stats", None),
        (f"{base}/machines", None),
        (f"{base}/projects", None),
    ]
    for c in db.query(Computer.asset_id).order_by(Computer.asset_id):
        urls.append((f"{base}/computers/{c.asset_id}", last.get(c.asset_id)))
    for p in db.query(Part.asset_id).order_by(Part.asset_id):
        urls.append((f"{base}/parts/{p.asset_id}", last.get(p.asset_id)))
    # The projects read out of the same `last`, because a project's history is
    # log_entry keyed by its own register id -- the same rows, the same query.
    # A private project is not named here. The sitemap is the one of the five that
    # is read by machines rather than people, and a tag in it is an invitation.
    for pr in (
        db.query(Project.asset_id).filter(Project.private.is_(False)).order_by(Project.asset_id)
    ):
        urls.append((f"{base}/projects/{pr.asset_id}", last.get(pr.asset_id)))
    lines = [
        '<?xml version="1.0" encoding="UTF-8"?>',
        '<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">',
    ]
    for loc, ts in urls:
        lines.append("  <url>")
        lines.append(f"    <loc>{escape(loc)}</loc>")
        if ts:
            lines.append(f"    <lastmod>{ts.strftime('%Y-%m-%d')}</lastmod>")
        lines.append("  </url>")
    lines.append("</urlset>")
    return Response("\n".join(lines), media_type="application/xml")


_ICON_CACHE = {"Cache-Control": "public, max-age=86400"}


# Browsers and crawlers request these at the domain root regardless of markup.
@router.get("/favicon.ico", include_in_schema=False)
def favicon() -> FileResponse:
    return FileResponse(branded("favicon.ico"), headers=_ICON_CACHE)


@router.get("/apple-touch-icon.png", include_in_schema=False)
@router.get("/apple-touch-icon-precomposed.png", include_in_schema=False)
def apple_touch_icon() -> FileResponse:
    return FileResponse(branded("apple-touch-icon.png"), headers=_ICON_CACHE)
