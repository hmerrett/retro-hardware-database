"""The Surveys page, each survey's page, and what surveys have seen (MANUAL §23;
ADR-0043).

Read by anybody signed in, a viewer included (auth.VIEWER_PAGES); everything done to a
survey is a POST, and so an administrator's. A refusal comes back as the survey's own
page with the reason at the top and a 400, as a refused form does.
"""

import json
from datetime import datetime

from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import HTMLResponse, RedirectResponse, Response
from sqlalchemy.orm import Session

from .. import entry, surveys
from ..common import to_dict
from ..db import get_db
from ..forms import posted
from ..models import Computer, Part, Survey, Thing
from ..web import templates

router = APIRouter()

# What each kind of thing a survey has seen is, in words.
SEEN_KINDS = {
    "disk": "Hard disk",
    "mac": "Ethernet address",
    "system": "Machine's serial number",
    "board": "Board's serial number",
}


def _when(at: datetime | None, time: bool = True) -> str:
    if at is None:
        return ""
    return at.strftime("%d/%m/%Y %H:%M" if time else "%d/%m/%Y")


def _names(db: Session, tags: set[str]) -> dict[str, str]:
    out: dict[str, str] = {}
    for tag in tags:
        found = db.get(Thing, tag)
        if isinstance(found, Computer | Part):
            out[tag] = entry.display_name(to_dict(found))
    return out


def _result(s: Survey) -> str:
    keys = surveys.keys_of(s)
    return surveys.tests_line(keys).capitalize()


def _survey(db: Session, sid: int) -> Survey:
    s = db.get(Survey, sid)
    if s is None:
        raise HTTPException(status_code=404, detail="No such survey")
    return s


@router.get("/surveys", response_class=HTMLResponse, include_in_schema=False)
def surveys_page(request: Request, db: Session = Depends(get_db)) -> HTMLResponse:
    rows = surveys.listing(db)
    names = _names(db, {s.machine for s in rows if s.machine})
    return templates.TemplateResponse(
        request,
        "surveys.html",
        {
            "waiting": [s for s in rows if s.waiting],
            "done": [s for s in rows if not s.waiting],
            "names": names,
            "when": _when,
            "result": _result,
        },
    )


@router.get("/surveys/seen", response_class=HTMLResponse, include_in_schema=False)
def seen_page(request: Request, db: Session = Depends(get_db)) -> HTMLResponse:
    rows = surveys.seen(db)
    tags = {r.asset_id for r in rows if r.asset_id} | {r.last_in for r in rows if r.last_in}
    return templates.TemplateResponse(
        request,
        "surveys_seen.html",
        {
            "rows": rows,
            "names": _names(db, {t.upper() for t in tags if t}),
            "kinds": SEEN_KINDS,
            "when": _when,
        },
    )


def _page(
    request: Request, db: Session, s: Survey, refusal: str = "", status: int = 200
) -> HTMLResponse:
    keys = surveys.keys_of(s)
    found = surveys.findings_of(s)
    tests = [
        (name[5:], value.strip().upper(), keys.get(f"DETAIL_{name[5:]}", ""))
        for name, value in keys.items()
        if name.startswith("TEST_")
    ]
    tags = {s.machine or "", s.bench_card or ""} | {f["part"] or "" for f in found}
    tags |= set(json.loads(s.missing or "[]"))
    return templates.TemplateResponse(
        request,
        "survey.html",
        {
            "s": s,
            "keys": keys,
            "found": found,
            "asked": [f for f in found if f["kind"] != surveys.MACHINE],
            "tests": tests,
            "filled": json.loads(s.filled or "[]"),
            "differs": json.loads(s.differs or "[]"),
            "missing": json.loads(s.missing or "[]"),
            "roms": surveys.roms_of(s),
            "names": _names(db, {t for t in tags if t}),
            "benches": surveys.benches(db),
            "when": _when,
            "result": _result(s),
            "refusal": refusal,
        },
        status_code=status,
    )


@router.get("/surveys/{sid}", response_class=HTMLResponse, include_in_schema=False)
def survey_page(sid: int, request: Request, db: Session = Depends(get_db)) -> HTMLResponse:
    return _page(request, db, _survey(db, sid))


def _who(request: Request) -> str:
    return str(request.state.principal.username or "")


def _labels(db: Session, s: Survey, filing: surveys.Filing) -> None:
    agent = surveys.agents().get(s.agent)
    if agent is not None:
        surveys.labels_for(db, agent, filing.made)


@router.post("/surveys/{sid}/file", include_in_schema=False)
async def file_survey(sid: int, request: Request, db: Session = Depends(get_db)) -> Response:
    """File a survey that waits for a machine against the one named. Where that would
    move a part out of another machine, the page says so first, and files it when the
    question comes back confirmed."""
    s = _survey(db, sid)
    form = await posted(request)
    tag = (form.get("tag", "") or "").strip().upper()
    machine = surveys.machine_for(db, tag)
    if machine is None:
        return _page(request, db, s, f"{tag or 'That'} is not a machine or a motherboard.", 400)
    moving = surveys.taken_out(db, s, machine)
    if moving and not form.get("confirm"):
        names = _names(db, {machine, *(p for p, _ in moving), *(m for _, m in moving)})
        return templates.TemplateResponse(
            request,
            "survey_file.html",
            {"s": s, "tag": tag, "machine": machine, "moving": moving, "names": names},
        )
    try:
        filing = surveys.file_against(db, s, tag, _who(request))
    except surveys.Refused as err:
        db.rollback()
        return _page(request, db, _survey(db, sid), str(err), 400)
    db.commit()
    _labels(db, s, filing)
    return RedirectResponse(f"/surveys/{sid}", status_code=303)


@router.post("/surveys/{sid}/answer", include_in_schema=False)
async def answer(sid: int, request: Request, db: Session = Depends(get_db)) -> Response:
    """An answer given on the page for one thing a survey found."""
    s = _survey(db, sid)
    form = await posted(request)
    try:
        surveys.answer_on_page(
            db,
            s,
            (form.get("thing", "") or "").strip().upper(),
            (form.get("answer", "") or "").strip().lower(),
            (form.get("tag", "") or "").strip().upper(),
            (form.get("bench", "") or "").strip().upper(),
            _who(request),
        )
    except surveys.Refused as err:
        db.rollback()
        return _page(request, db, _survey(db, sid), str(err), 400)
    db.commit()
    return RedirectResponse(f"/surveys/{sid}", status_code=303)


@router.post("/surveys/{sid}/delete", include_in_schema=False)
async def delete(sid: int, db: Session = Depends(get_db)) -> Response:
    surveys.delete(db, _survey(db, sid))
    db.commit()
    return RedirectResponse("/surveys", status_code=303)
