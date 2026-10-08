"""The audit's routes: the screen, a scan, an undo, finishing, and the report
(MANUAL §14, "Audit"; ADR-0034).

The logic is storage.py's; this is the page around it. A scan is a form post, so
the audit works in a browser running no script -- the page posts, the round
records it, and the redirect draws the panel from the round's last scan. The page's
script sends the same post asking for JSON instead, and is answered with what the
scan did and the line it adds to the list, so a handheld scanner can be fired at
it as fast as its trigger goes.

For administrators: the audit moves things. The gate already says so, since no
path here is public and none is a viewer's.
"""

from collections.abc import Iterable

from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import HTMLResponse, JSONResponse, RedirectResponse, Response
from sqlalchemy.orm import Session

from .. import entry, storage, tree
from ..common import to_dict
from ..db import get_db
from ..forms import posted
from ..models import Location, StockCheck, StockCheckScan, Thing
from ..web import templates

router = APIRouter()


def _wants_json(request: Request) -> bool:
    return "application/json" in request.headers.get("accept", "")


def _user(request: Request) -> int:
    uid = request.state.principal.user_id
    if uid is None:
        raise HTTPException(403, "the audit is for a signed-in administrator")
    return int(uid)


def _names(db: Session, tags: Iterable[str | None]) -> dict[str, str]:
    """{tag: what to call it} for every tag a list or a report mentions."""
    out: dict[str, str] = {}
    for tag in tags:
        if not tag or tag in out:
            continue
        loc = db.get(Location, tag)
        if loc is not None:
            out[tag] = loc.name
            continue
        thing = tree.item(db, tag)
        out[tag] = entry.display_name(to_dict(thing)) if thing is not None else tag
    return out


def _tags(rows: Iterable[StockCheckScan]) -> list[str | None]:
    return [tag for row in rows for tag in (row.asset_id, row.at_id)]


HEADS = {
    storage.FOUND: "Found",
    storage.MOVED: "Moved in",
    storage.NESTED: "Moved in",
    storage.WHERE: "Where it is",
    storage.HELD: "Where it is",
    storage.AGAIN: "Already scanned",
    storage.REFUSED: "Not recognised",
    storage.CLOSED: "Next",
}


def _prompt(db: Session, opened: str | None) -> dict[str, str]:
    """What the prompt says of what is open, a location or a machine: its name, and
    where it is -- what it is inside, since the name is said in larger type above."""
    r = tree.load(db)
    found = db.get(Thing, opened) if opened else None
    if found is None or opened is None or opened.upper() not in r:
        return {"open_name": "", "open_path": ""}
    name = found.name if isinstance(found, Location) else storage.name_of(found)
    return {"open_name": name, "open_path": tree.words(db, r, r.holder(opened.upper()))}


def _answer(db: Session, said: storage.Said) -> JSONResponse:
    """A scan's answer to the script: what it did, the line it adds to the list, and
    what the prompt now says, so the page the script redraws is the page a reload
    would draw."""
    row = _row_html(db, db.get(StockCheckScan, said.scan))
    return JSONResponse(said.as_dict() | {"row": row} | _prompt(db, said.open))


def _line(row: StockCheckScan, names: dict[str, str]) -> dict[str, object]:
    """One scan as the list draws it."""
    tone = storage.TONES[row.result]
    head = names.get(row.asset_id or "", "") if row.result == storage.OPENED else HEADS[row.result]
    return {
        "id": row.id,
        "tone": tone,
        "icon": storage.ICONS[tone],
        "head": head,
        "words": row.said,
        "undone": row.undone,
        "undoable": row.result in (storage.MOVED, storage.NESTED) and not row.undone,
    }


def _row_html(db: Session, row: StockCheckScan | None) -> str:
    """The line a scan adds to the list, for the script to put at the top of it --
    drawn by the template the page draws its list with, so the two cannot differ."""
    if row is None:
        return ""
    line = _line(row, _names(db, _tags([row])))
    return templates.env.get_template("_storage_line.html").render(line=line)


@router.get("/audit", response_class=HTMLResponse, include_in_schema=False)
def gui_storage(request: Request, db: Session = Depends(get_db)) -> HTMLResponse:
    check = storage.current(db, _user(request))
    rows = storage.scans(db, check) if check is not None else []
    names = _names(db, _tags(rows))
    opened = storage.open_location(rows)
    last = _line(rows[-1], names) if rows else None
    return templates.TemplateResponse(
        request,
        "storage.html",
        {
            "check": check,
            "lines": [_line(r, names) for r in reversed(rows)],
            "last": last,
            "opened": opened,
            # A round with a scan in it has been started, and is not asked again how
            # it is being scanned (MANUAL §14).
            "started": bool(rows),
            "noindex": True,
        }
        | _prompt(db, opened),
    )


@router.post("/audit/scan", include_in_schema=False)
async def gui_storage_scan(request: Request, db: Session = Depends(get_db)) -> Response:
    form = await posted(request)
    check = storage.round_for(db, _user(request))
    said = storage.scan(db, check, form.get("code", "") or "", request.state.principal.username)
    db.commit()
    if not _wants_json(request):
        return RedirectResponse("/audit", status_code=303)
    return _answer(db, said)


@router.post("/audit/close", include_in_schema=False)
def gui_storage_close(request: Request, db: Session = Depends(get_db)) -> Response:
    """**next** (MANUAL §14): what is open shut, and nothing opened, so the next scan
    opens whatever it is."""
    check = storage.current(db, _user(request))
    if check is None:
        raise HTTPException(404, "no location is open")
    said = storage.close(db, check)
    db.commit()
    if not _wants_json(request):
        return RedirectResponse("/audit", status_code=303)
    return _answer(db, said)


@router.post("/audit/undo", include_in_schema=False)
async def gui_storage_undo(request: Request, db: Session = Depends(get_db)) -> Response:
    form = await posted(request)
    check = storage.current(db, _user(request))
    raw = (form.get("scan", "") or "").strip()
    said = None
    if check is not None and raw.isdigit():
        said = storage.undo(db, check, int(raw), request.state.principal.username)
    if said is None:
        raise HTTPException(404, "nothing to undo there")
    db.commit()
    if not _wants_json(request):
        return RedirectResponse("/audit", status_code=303)
    return _answer(db, said)


@router.post("/audit/finish", include_in_schema=False)
def gui_storage_finish(request: Request, db: Session = Depends(get_db)) -> Response:
    check = storage.current(db, _user(request))
    if check is None:
        return RedirectResponse("/audit", status_code=303)
    storage.finish(check)
    db.commit()
    return RedirectResponse(f"/audit/rounds/{check.id}", status_code=303)


@router.get("/audit/rounds/{rid}", response_class=HTMLResponse, include_in_schema=False)
def gui_storage_report(
    rid: int, request: Request, recorded: int = -1, db: Session = Depends(get_db)
) -> HTMLResponse:
    check = db.get(StockCheck, rid)
    if check is None:
        raise HTTPException(404, f"no round {rid}")
    checked, refused = storage.report(db, check)
    names = _names(
        db,
        [
            t
            for part in checked
            for t in (*part.found, *(a for a, _ in part.moved), *part.unscanned)
        ],
    )
    return templates.TemplateResponse(
        request,
        "storage_report.html",
        {
            "check": check,
            "checked": checked,
            "refused": refused,
            "names": names,
            "recorded": recorded,
            "noindex": True,
        },
    )


@router.post("/audit/rounds/{rid}/missing", include_in_schema=False)
def gui_storage_missing(rid: int, request: Request, db: Session = Depends(get_db)) -> Response:
    check = db.get(StockCheck, rid)
    if check is None:
        raise HTTPException(404, f"no round {rid}")
    n = storage.record_missing(db, check)
    db.commit()
    return RedirectResponse(f"/audit/rounds/{rid}?recorded={n}", status_code=303)
