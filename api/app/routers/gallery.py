"""The gallery: the wall of cards, the slice of it behind a figure on /stats, and
what the search bar offers while somebody is still typing.

All three render the same grid from the same rows -- they differ only in which rows
survive and what the page says it is showing. The matching itself is search.py's;
this is the page around it.
"""

from datetime import datetime

from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import HTMLResponse
from sqlalchemy import func
from sqlalchemy.orm import Session

from .. import cards, entry, projects, specdb
from ..common import folder_images, to_dict
from ..db import get_db
from ..models import Computer, LogEntry, Part
from ..photos import _favicon_for_rel, _storage_placeholder, is_reference, pick_images
from ..search import _browse_view, _projects_matching, _search, _suggest
from ..web import _og, templates

router = APIRouter()


# --- GUI: index ------------------------------------------------------------


def _catalogue_rows(db, precise_times=True):
    """Every computer and part as one list of card rows. The gallery and /browse
    render the same grid from this; they differ only in which rows survive.

    The recency sort keys ride on the cards as data attributes, so anonymously they
    carry the date alone, like the history does (`precise_times=False`). The rows
    come back newest-change-first regardless, which is what keeps a day's worth of
    edits in order once the browser sorts on dates that are all equal."""
    computers = db.query(Computer).order_by(Computer.asset_id).all()
    parts = db.query(Part).order_by(Part.asset_id).all()
    counts = {}
    for p in parts:
        if p.computer_id:
            counts[p.computer_id] = counts.get(p.computer_id, 0) + 1
    comp_ids = {c.asset_id for c in computers}

    # Newest/oldest log timestamp per asset, for the updated / added sorts.
    ts = {}
    for aid, latest, first in db.query(
        LogEntry.asset_id, func.max(LogEntry.created_at), func.min(LogEntry.created_at)
    ).group_by(LogEntry.asset_id):
        ts[aid] = (latest, first)

    def stamp(when):
        if not when:
            return ""
        return when.isoformat() if precise_times else when.strftime("%Y-%m-%d")

    def stamps(aid):
        latest, first = ts.get(aid, (None, None))
        return (stamp(latest), stamp(first))

    # Both folders read once for the whole page: scanning per row was the bulk of
    # this route's time (0.38s of 0.50s across 293 assets).
    listings = {kind: folder_images(kind) for kind in ("computers", "parts")}

    def primary_image(kind, aid):
        imgs = pick_images(kind, aid, listings[kind])
        return imgs[0] if imgs else ""

    # One query for every storage part's Kind, rather than re-parsing each specs
    # string (or a lookup per row) just to choose an icon.
    kinds = specdb.storage_kinds(db)

    rows = []
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
                "search": " ".join(
                    [
                        c.asset_id,
                        c.name or "",
                        c.manufacturer or "",
                        c.model or "",
                        c.os or "",
                        c.cpu or "",
                        c.chassis or "",
                        c.installed_ram or "",
                        c.drives or "",
                        str(c.year or ""),
                        c.condition or "",
                        c.source or "",
                        str(c.acquired_date or ""),
                        c.disposed_note or "",
                    ]
                ).lower(),
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
                "search": " ".join(
                    [
                        p.asset_id,
                        p.name or "",
                        p.manufacturer or "",
                        p.model or "",
                        p.specs or "",
                        p.type or "",
                        entry.type_label(ptype),
                        str(p.year or ""),
                        p.condition or "",
                        p.source or "",
                        str(p.acquired_date or ""),
                        p.disk_image or "",
                        p.computer_id or "",
                        p.disposed_note or "",
                    ]
                ).lower(),
            }
        )
    # Newest change first. The browser re-sorts on load anyway, but its sort is
    # stable, so this is the order items updated on the same day keep -- the whole
    # of what the dropped clock time used to settle.
    rows.sort(
        key=lambda r: ts.get(r["obj"].asset_id, (datetime.min,))[0] or datetime.min, reverse=True
    )
    return rows


def _cats_for(rows):
    """Options for the toolbar's category menu: only the kinds actually present, so
    a filtered page does not offer to filter down to nothing."""
    cats = [("computer", "Computers")] if any(r["kind"] == "computer" for r in rows) else []
    present = {r["cat"] for r in rows if r["kind"] == "part"}
    for t in sorted(present, key=entry.type_sort_key):
        cats.append((t, entry.type_label(t)))
    return cats


def _grid_page(request, rows, **extra):
    """Render the card grid. Counts come from the rows on the page rather than from
    the register, so a filtered view describes itself honestly."""
    n_computers = sum(1 for r in rows if r["kind"] == "computer")
    return templates.TemplateResponse(
        request,
        "index.html",
        {
            "rows": rows,
            "cats": _cats_for(rows),
            "n_computers": n_computers,
            "n_parts": len(rows) - n_computers,
            **extra,
        },
    )


@router.get("/suggest", include_in_schema=False)
def gui_suggest(request: Request, q: str = "", db: Session = Depends(get_db)):
    items, total = _suggest(db, q, authed=request.state.authed)
    return {"q": q, "items": items, "total": total}


@router.get("/", response_class=HTMLResponse, include_in_schema=False)
def gui_index(request: Request, q: str = "", db: Session = Depends(get_db)):
    rows = _catalogue_rows(db, precise_times=request.state.authed)
    total = len(rows)
    hit_projects = 0
    if q.strip():
        rows = _search(db, rows, q, request.state.authed)
        # Counted, not shown. The grid is a wall of photographs of things owned and
        # a project is not one of those, so it does not become a card here -- but a
        # search that quietly ignored a whole section of the site would be a search
        # bar that says "anything" and means "the shelf". The line the page draws
        # from this points at /projects with the same query.
        hit_projects = len(
            _projects_matching(
                db, projects.summaries(db, authed=request.state.authed), q, request.state.authed
            )
        )
    n_computers = sum(1 for r in rows if r["kind"] == "computer")
    return _grid_page(
        request,
        rows,
        q=q,
        searched=bool(q.strip()),
        total=total,
        hit_projects=hit_projects,
        og=_og(
            request,
            "Retro Hardware Database",
            f"{n_computers} computers and {len(rows) - n_computers} parts in the collection.",
            # The photographs on the page, tiled, rather than the logo: this is
            # a wall of them, and a search is the page here most worth sending
            # somebody (ADR-0017). The rows are already in hand, and only the
            # first few of them that have a photograph are ever opened.
            card=cards.montage(r["image"] for r in rows),
        ),
    )


@router.get("/for-sale", response_class=HTMLResponse, include_in_schema=False)
def gui_for_sale(request: Request, db: Session = Depends(get_db)):
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
    rows = [r for r in _catalogue_rows(db, precise_times=request.state.authed) if r["obj"].for_sale]
    return _grid_page(
        request,
        rows,
        heading="Might sell",
        note="things flagged as ones that could go — nobody else sees this",
        # Disposed items are shown: something on its way out can be both, and a
        # shortlist that silently dropped them would be answering a question that
        # was not asked.
        show_disposed=True,
        page_title="Might sell — Retro Hardware Database",
        noindex=True,
        og=_og(request, "Might sell"),
    )


@router.get("/browse", response_class=HTMLResponse, include_in_schema=False)
def gui_browse(request: Request, f: str = "", v: str = "", db: Session = Depends(get_db)):
    """The items behind one figure on /stats, in the same grid as the gallery."""
    view = _browse_view(db, f, v)
    if view is None:
        raise HTTPException(404, f"no such view: {f or '(none)'}")
    heading, note, crumb, keep = view
    rows = [r for r in _catalogue_rows(db, precise_times=request.state.authed) if keep(r)]
    return _grid_page(
        request,
        rows,
        heading=heading,
        note=note,
        crumb=crumb,
        # The figures on /stats count disposed items too, so this page has to show
        # them by default or it would seem to contradict the number clicked on.
        show_disposed=True,
        page_title=f"{heading} — Retro Hardware Database",
        # A filtered slice of the gallery is not a page search engines want; the
        # items themselves are already indexed one by one.
        noindex=True,
        og=_og(request, heading, note, card=cards.montage(r["image"] for r in rows)),
    )
