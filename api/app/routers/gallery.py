"""The gallery: the wall of cards, the slice of it behind a figure on /stats, and
what the search bar offers while somebody is still typing.

All three render the same grid from the same rows -- they differ only in which rows
survive and what the page says it is showing. The matching itself is search.py's;
this is the page around it.
"""

import hashlib
import random
from collections.abc import Callable, Iterable
from datetime import datetime
from typing import TYPE_CHECKING
from urllib.parse import urlencode

from fastapi import APIRouter, Depends, HTTPException, Query, Request
from fastapi.responses import HTMLResponse
from sqlalchemy import func
from sqlalchemy.orm import Session

from .. import cards, entry, projects, settings, specdb
from ..auth import SORT_COOKIE
from ..common import folder_images, to_dict
from ..db import get_db
from ..models import Computer, LogEntry, Part
from ..photos import _favicon_for_rel, _storage_placeholder, is_reference, pick_images
from ..search import (
    SUGGEST_LIMIT,
    Card,
    _browse_view,
    _projects_matching,
    _search,
    _suggest,
)
from ..web import _og, _ui, templates

if TYPE_CHECKING:
    from _typeshed import SupportsRichComparison

router = APIRouter()


# --- GUI: index ------------------------------------------------------------


def _catalogue_rows(db: Session, authed: bool = False) -> list[Card]:
    """Every computer and part as one list of card rows. The gallery and /browse
    render the same grid from this; they differ only in which rows survive.

    Anonymously the recency sort keys carry the date alone, like the history does
    (`precise_times=False`). The rows come back newest-change-first regardless,
    which is what keeps a day's worth of edits in order once `order` sorts on dates
    that are all equal."""
    computers = db.query(Computer).order_by(Computer.asset_id).all()
    parts = db.query(Part).order_by(Part.asset_id).all()
    counts: dict[str, int] = {}
    for p in parts:
        if p.computer_id:
            counts[p.computer_id] = counts.get(p.computer_id, 0) + 1
    comp_ids = {c.asset_id for c in computers}

    # Newest/oldest log timestamp per asset, for the updated / added sorts.
    ts: dict[str | None, tuple[datetime | None, datetime | None]] = {}
    for aid, latest, first in db.query(
        LogEntry.asset_id, func.max(LogEntry.created_at), func.min(LogEntry.created_at)
    ).group_by(LogEntry.asset_id):
        ts[aid] = (latest, first)

    def stamp(when: datetime | None) -> str:
        if not when:
            return ""
        return when.isoformat() if authed else when.strftime("%Y-%m-%d")

    def stamps(aid: str) -> tuple[str, str]:
        latest, first = ts.get(aid, (None, None))
        return (stamp(latest), stamp(first))

    # Both folders read once for the whole page: scanning per row was the bulk of
    # this route's time (0.38s of 0.50s across 293 assets).
    listings = {kind: folder_images(kind) for kind in ("computers", "parts")}

    def primary_image(kind: str, aid: str) -> str:
        imgs = pick_images(kind, aid, listings[kind])
        return imgs[0] if imgs else ""

    # One query for every storage part's Kind, rather than re-parsing each specs
    # string (or a lookup per row) just to choose an icon.
    kinds = specdb.storage_kinds(db)

    rows: list[Card] = []
    for c in computers:
        rows.append(
            {
                "obj": c,
                "kind": "computer",
                "cat": "computer",
                "cat_label": "Computer",
                "parent": "",
                "year": c.year or "",
                "name": entry.display_name(to_dict(c)),
                "image": (cpi := primary_image("computers", c.asset_id)),
                "ref_photo": is_reference(cpi),
                "ref_icon": _favicon_for_rel(cpi),
                "placeholder": entry.placeholder_for("computer"),
                "updated": stamps(c.asset_id)[0],
                "added": stamps(c.asset_id)[1],
                "maker": (c.manufacturer or "").lower(),
                "acquired": str(c.acquired_date or ""),
                "catsort": 0,
                "sub": f"{counts.get(c.asset_id, 0)} part(s)",
            }
        )
    for p in parts:
        ptype = p.type or "other"
        rows.append(
            {
                "obj": p,
                "kind": "part",
                "cat": ptype,
                "cat_label": entry.type_label(ptype),
                "year": p.year or "",
                "parent": p.computer_id if p.computer_id in comp_ids else "",
                "name": entry.display_name(to_dict(p)),
                "image": (ppi := primary_image("parts", p.asset_id)),
                "ref_photo": is_reference(ppi),
                "ref_icon": _favicon_for_rel(ppi),
                "placeholder": (
                    _storage_placeholder(kinds.get(p.asset_id))
                    if ptype == "storage"
                    else entry.placeholder_for(ptype)
                ),
                "updated": stamps(p.asset_id)[0],
                "added": stamps(p.asset_id)[1],
                "maker": (p.manufacturer or "").lower(),
                "acquired": str(p.acquired_date or ""),
                "catsort": entry.type_sort_key(ptype) + 1,
                "sub": (p.computer_id if p.computer_id else "standalone"),
            }
        )

    def changed(row: Card) -> datetime:
        return ts.get(row["obj"].asset_id, (None, None))[0] or datetime.min

    # Newest change first. `order` re-sorts anyway, but its sort is stable, so this
    # is the order items updated on the same day keep -- the whole of what the
    # dropped clock time used to settle.
    rows.sort(key=changed, reverse=True)
    return rows


def _cats_for(rows: list[Card]) -> list[tuple[str, str]]:
    """Options for the toolbar's category menu: only the kinds actually present, so
    a filtered page does not offer to filter down to nothing."""
    cats: list[tuple[str, str]] = (
        [("computer", "Computers")] if any(r["kind"] == "computer" for r in rows) else []
    )
    present = {r["cat"] for r in rows if r["kind"] == "part"}
    for t in sorted(present, key=entry.type_sort_key):
        cats.append((t, entry.type_label(t)))
    return cats


# Two, three and four across all fill their last row.
PAGE_SIZE = 48


def _photo_first(r: Card) -> int:
    return 0 if r["image"] else 1


def _blank_last(value: object) -> int:
    return 0 if value else 1


def _name(r: Card) -> str:
    return r["name"].casefold()


def _shuffle_key(deal: int) -> Callable[[Card], bytes]:
    """Where the hand dealt as `deal` puts each item. A hash of the deal and the tag
    rather than a shuffle of the list, so an item keeps its place relative to every
    other whatever is filtered out around it: picking a category mid-shuffle narrows
    the hand instead of dealing a new one. blake2b rather than hash(), which is
    salted per process and would give each worker a different hand."""

    def key(r: Card) -> bytes:
        return hashlib.blake2b(f"{deal}:{r['obj'].asset_id}".encode(), digest_size=8).digest()

    return key


# Each sort as the keys it applies, least significant first: Python's sort is
# stable, so sorting on the tie-breaker and then on the main key leaves ties in the
# tie-breaker's order -- and ties in both in the order the rows came, which is
# newest change first. That last is the whole of what orders a day's edits for an
# anonymous visitor, whose recency keys are the date alone.
_Key = tuple[Callable[[Card], "SupportsRichComparison"], bool]
_SORTS: dict[str, list[_Key]] = {
    "updated": [(lambda r: r["updated"], True), (_photo_first, False)],
    "added": [
        (lambda r: r["updated"], True),
        (lambda r: r["added"], True),
        (_photo_first, False),
    ],
    "acquired": [
        (_name, False),
        (lambda r: r["acquired"], True),
        (lambda r: _blank_last(r["acquired"]), False),
    ],
    "yearnew": [
        (_name, False),
        (lambda r: str(r["year"]), True),
        (lambda r: _blank_last(r["year"]), False),
    ],
    "yearold": [
        (_name, False),
        (lambda r: str(r["year"]), False),
        (lambda r: _blank_last(r["year"]), False),
    ],
    "name": [(_name, False)],
    "maker": [
        (_name, False),
        (lambda r: r["maker"], False),
        (lambda r: _blank_last(r["maker"]), False),
    ],
    "cat": [(_name, False), (lambda r: r["catsort"], False)],
    "aid": [(lambda r: r["obj"].asset_id, False)],
}
SORTS = ("random", *_SORTS)


def order(rows: Iterable[Card], sort: str, deal: int) -> list[Card]:
    """The rows in the order the toolbar's sort names. Recency and random both put
    photographed items first, so neither opens on a screenful of placeholders; an
    undated item goes last whichever way round the dated ones are."""
    out = list(rows)
    if sort not in _SORTS:
        out.sort(key=lambda r: (_photo_first(r), _shuffle_key(deal)(r)))
        return out
    for key, reverse in _SORTS[sort]:
        out.sort(key=key, reverse=reverse)
    return out


def _grid_page(
    request: Request,
    rows: list[Card],
    show_disposed: bool = False,
    keep: dict[str, str] | None = None,
    **extra: object,
) -> HTMLResponse:
    """Render one page of the card grid, in the view the query string names.

    Counts come from the rows handed in rather than from the register, so a
    filtered view describes itself honestly, and from all of them rather than the
    page on screen. `keep` is what the route itself was asked for -- a search, a
    /browse figure -- which every link out of the toolbar and the pager has to
    carry, or changing the sort would drop the figure being looked at."""
    qp = request.query_params
    keep = keep or {}
    cats = _cats_for(rows)
    cat = qp.get("cat", "")
    if cat not in {k for k, _ in cats}:
        cat = ""
    sort = qp.get("sort") or request.cookies.get(SORT_COOKIE, "")
    if sort not in SORTS:
        sort = "random"
    try:
        deal = int(qp.get("deal", ""))
    except ValueError:
        # Arriving on Random, or choosing it from another sort: a new hand. Small,
        # because it is going to sit in an address bar.
        deal = random.randrange(1, 1_000_000)
    # An unticked box sends nothing, so an absent `disposed` means "unticked" only
    # when the form was used -- which the sort, sent by every submission and every
    # pager link, says. Arriving at the bare page takes the page's own default.
    if "disposed" in qp or "sort" in qp:
        show_disposed = qp.get("disposed") == "1"

    shown = [
        r for r in rows if (not cat or r["cat"] == cat) and (show_disposed or not r["obj"].disposed)
    ]
    shown = order(shown, sort, deal)
    pages = max(1, -(-len(shown) // PAGE_SIZE))
    try:
        page = min(max(1, int(qp.get("page", "1"))), pages)
    except ValueError:
        page = 1

    view = {**keep, "cat": cat, "sort": sort, "disposed": "1" if show_disposed else "0"}
    if sort == "random":
        view["deal"] = str(deal)
    n_computers = sum(1 for r in rows if r["kind"] == "computer")
    return templates.TemplateResponse(
        request,
        "index.html",
        {
            "rows": shown[(page - 1) * PAGE_SIZE : page * PAGE_SIZE],
            "cats": cats,
            "n_computers": n_computers,
            "n_parts": len(rows) - n_computers,
            "n_shown": len(shown),
            "n_all": len(rows),
            "cat": cat,
            "sort": sort,
            "deal": deal if sort == "random" else None,
            "keep": keep,
            "show_disposed": show_disposed,
            "page": page,
            "pages": pages,
            "pager_href": f"{request.url.path}?{urlencode(view)}&page=",
            # Every page of the list, not the one on screen, so an item page's next
            # walks off the end of this page into the first card of the next.
            "handoff": [
                [
                    f"/{'computers' if r['kind'] == 'computer' else 'parts'}/{r['obj'].asset_id}",
                    r["name"],
                ]
                for r in shown
            ],
            **extra,
        },
    )


@router.get("/suggest", include_in_schema=False)
def gui_suggest(
    request: Request,
    q: str = "",
    limit: int = Query(SUGGEST_LIMIT, ge=1),
    db: Session = Depends(get_db),
) -> dict[str, object]:
    # A phone asks for fewer, to keep the last row above its keyboard. Nobody gets
    # more: the whole answer is the results page's to give.
    items, total = _suggest(db, q, min(limit, SUGGEST_LIMIT), authed=request.state.sees_private)
    # The list's last row, worded here rather than by the script: it is a control,
    # so it follows the Button text setting, which only the server can read. One
    # result is not "all" of anything.
    said = q.strip()
    words = f'All {total} results for "{said}"' if total != 1 else f'1 result for "{said}"'
    return {
        "q": q,
        "items": items,
        "total": total,
        # Where Enter goes with nothing lit: the banner's form, a GET to / with q.
        "all": {"url": "/?" + urlencode({"q": said}), "text": _ui(words)},
    }


@router.get("/", response_class=HTMLResponse, include_in_schema=False)
def gui_index(request: Request, q: str = "", db: Session = Depends(get_db)) -> HTMLResponse:
    rows = _catalogue_rows(db, request.state.sees_private)
    total = len(rows)
    hit_projects = 0
    if q.strip():
        rows = _search(db, rows, q, request.state.sees_private)
        # Counted, not shown. The grid is a wall of photographs of things owned and
        # a project is not one of those, so it does not become a card here -- but a
        # search that quietly ignored a whole section of the site would be a search
        # bar that says "anything" and means "the shelf". The line the page draws
        # from this points at /projects with the same query.
        hit_projects = len(
            _projects_matching(
                db,
                projects.summaries(db, authed=request.state.sees_private),
                q,
                request.state.sees_private,
            )
        )
    n_computers = sum(1 for r in rows if r["kind"] == "computer")
    return _grid_page(
        request,
        rows,
        keep={"q": q} if q.strip() else None,
        q=q,
        searched=bool(q.strip()),
        total=total,
        # A register with nothing in it at all, which is not the same state as a
        # search that matched nothing: the front page has nothing to be until the
        # first item exists, so it is the three steps instead. Asked here and not
        # in `_grid_page`, because /browse and /for-sale draw the same grid from a
        # narrowed list and an empty one of those is a filter, not a new install.
        first_run=total == 0 and not q.strip(),
        named=settings.site_name() != settings.DEFAULT_SITE_NAME,
        hit_projects=hit_projects,
        og=_og(
            request,
            settings.site_name(),
            f"{n_computers} computers and {len(rows) - n_computers} parts in the collection.",
            # The photographs on the page, tiled, rather than the logo: this is
            # a wall of them, and a search is the page here most worth sending
            # somebody (ADR-0017). The rows are already in hand, and only the
            # first few of them that have a photograph are ever opened.
            card=cards.montage(r["image"] for r in rows),
        ),
    )


@router.get("/for-sale", response_class=HTMLResponse, include_in_schema=False)
def gui_for_sale(request: Request, db: Session = Depends(get_db)) -> HTMLResponse:
    """The owner's shortlist: everything ticked "might sell" (ADR-0018).

    In the same grid as the gallery, because deciding what could go is done by
    looking at the things -- a list of asset tags would not answer the question this
    page is opened to answer.

    It is here rather than as a /browse view, even though it is the same grid with a
    different test applied: /browse is a public page, so a view of it would be one
    filter away from being the shortlist on the open web. A route of its own is
    private by the auth gate's ordinary rule, with nothing to remember.

    No montage on the share card, and noindex: this is not a page to share, and the
    site's own card is what a page with nothing to advertise shows (ADR-0017).
    """
    rows = [r for r in _catalogue_rows(db, request.state.sees_private) if r["obj"].for_sale]
    return _grid_page(
        request,
        rows,
        heading="Might sell",
        note="things flagged as ones that could go — nobody else sees this",
        # Disposed items are shown: something on its way out can be both, and a
        # shortlist that silently dropped them would be answering a question that
        # was not asked.
        show_disposed=True,
        page_title=f"Might sell — {settings.site_name()}",
        noindex=True,
        og=_og(request, "Might sell"),
    )


@router.get("/browse", response_class=HTMLResponse, include_in_schema=False)
def gui_browse(
    request: Request, f: str = "", v: str = "", db: Session = Depends(get_db)
) -> HTMLResponse:
    """The items behind one figure on /stats, in the same grid as the gallery."""
    view = _browse_view(db, f, v)
    if view is None:
        raise HTTPException(404, f"no such view: {f or '(none)'}")
    heading, note, crumb, keep = view
    rows = [r for r in _catalogue_rows(db, request.state.sees_private) if keep(r)]
    return _grid_page(
        request,
        rows,
        keep={"f": f, "v": v},
        heading=heading,
        note=note,
        crumb=crumb,
        # The figures on /stats count disposed items too, so this page has to show
        # them by default or it would seem to contradict the number clicked on.
        show_disposed=True,
        page_title=f"{heading} — {settings.site_name()}",
        # A filtered slice of the gallery is not a page search engines want; the
        # items themselves are already indexed one by one.
        noindex=True,
        og=_og(request, heading, note, card=cards.montage(r["image"] for r in rows)),
    )
