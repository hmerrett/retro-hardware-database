"""The project pages: what is being built, what it is waiting on, and what it cost.

A project is the third thing in the register and the only one that is a plan rather
than an object -- so it carries jobs, orders and the things it is about, and its
page is the one place all three are read together.
"""

import random
from datetime import date, datetime


# --- projects: the work, as against the things it is done to ------------------
# Everything above this line describes what is owned. A project describes what is
# intended, and it is the one kind of record here that can be about nothing yet:
# the idea comes months before the hardware, and a plan to build a 486 has to be
# writable on the evening it is had rather than on the day the board turns up.
#
# It is a register asset, which is what makes this section short. A project takes
# an id from the same allocator, so its history, its notes and the photographs on
# them are the code the machines already use, unaltered -- _history.html renders
# here word for word because the note bar posts to /<kind>/<id>/note and this is
# simply a third kind. app/projects.py owns the vocabulary, the money and the
# reading of the three child tables; what is here is what a person does with one.


# --- what a project is about -------------------------------------------------
# Membership is written on both sides: the project's history says what it took on
# and the item's says what it was wanted for. Two entries rather than one because
# they are read in two different places, and somebody looking at a board wants to
# know why it is spoken for without having to find the project that spoke for it.


# --- the jobs, and the things on order ---------------------------------------

from collections.abc import Iterable, Mapping, Sequence
from typing import NamedTuple, TypedDict

from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import HTMLResponse, RedirectResponse, Response
from sqlalchemy import func

from sqlalchemy.orm import Session

from .. import cards, entry, filesdb, labels, projects
from ..common import _visible, folder_images, to_dict
from ..db import get_db
from ..forms import Posted, Refusal, _coerce, _field_diffs, _parse_date, posted, refusals
from ..history import _history, _now, _short, add_log
from ..ids import next_asset_id
from ..models import (
    Computer,
    LogEntry,
    Part,
    Project,
    ProjectAsset,
    ProjectOrder,
    ProjectTask,
    StoredFile,
)
from ..pages import _answers_given, _note_with_photos
from ..photos import _drop_log_photos, _purge_photos
from ..photos import detect_images, pick_images
from ..register import FLAGGABLE, _asset_find, _register_order, get_or_404
from ..search import _projects_matching
from ..web import _og, _safe_next, png_label, templates
from ..work import (
    PROJECT_FIELDS,
    _api_task,
    _asset_display,
    _asset_named,
    _member_log,
    _publish_log,
    _take_on_work,
    _task_asset,
    _work_lines,
    _work_project_name,
)


def _task_or_404(db: Session, p: Project, tid: int) -> ProjectTask:
    row = db.get(ProjectTask, tid)
    # The project id is checked rather than taken on trust, for the reason a history
    # entry's asset id is: a bare row id would otherwise let one project's task be
    # ticked from another project's page.
    if row is None or row.project_id != p.asset_id:
        raise HTTPException(404, f"no task {tid} in {p.asset_id}")
    return row


def _projects_page(
    request: Request, db: Session, q: str = "", error: str = "", status: int = 200
) -> HTMLResponse:
    """The page, drawn.

    A function rather than the route's body because the quick box has to render it
    again when what was typed is not an asset tag, with the boxes still holding what
    was typed.

    One list, where there were two. A flag on an item and a project were two sizes
    of the same idea sharing a page, and the promotion from the smaller to the
    larger was a thing you did by hand and by retyping; now the quick box makes the
    larger one directly and there is nothing to promote. What the flag really
    carried, apart from a sentence, was privacy -- and that is a column on the
    project now, so the quick box can go on being the place you write something you
    have not decided to publish.

    A visitor is shown the public ones. This is the first of the five places that is
    kept (see _visible); the other four are the project's own page, the search, the
    suggestion list and the sitemap."""
    rows = projects.summaries(db, authed=request.state.sees_private)
    total = len(rows)
    if q.strip():
        rows = _projects_matching(db, rows, q, request.state.sees_private)
    live = [r for r in rows if r["p"].status not in projects.CLOSED]
    # Not while the page is a set of search results, and not while it is telling
    # somebody their asset tag was wrong: both of those are the page answering a
    # question that was asked, and a suggestion above the answer is an interruption.
    suggestion = (
        None
        if (q.strip() or error)
        else _today_panel(db, _project_of_the_day(db, request.state.sees_private))
    )
    return templates.TemplateResponse(
        request,
        "projects.html",
        {
            "rows": rows,
            "live": len(live),
            "q": q,
            "searched": bool(q.strip()),
            "suggestion": suggestion,
            "total": total,
            "error": error,
            "register": _register_order(db) if request.state.authed else [],
            "og": _og(
                request,
                "Projects",
                "Repairs, builds and things on order — the work, as against the collection",
                card=cards.montage(_projects_card(db, rows)),
            ),
        },
        status_code=status,
    )


def _project_from_form(form: Posted) -> dict[str, str | int | bool | date | None]:
    data = {k: _coerce(k, form.get(k, "")) for k in PROJECT_FIELDS}
    # _coerce hands a project's name and status back as the text they were typed
    # as; the two checks are for the type checker, which sees every column's type
    # at once rather than the two being read here.
    name, status = data["name"], data["status"]
    data["name"] = (name if isinstance(name, str) else "").strip()
    data["status"] = projects.clean_status(status if isinstance(status, str) else "")
    # A tickbox that is not ticked sends nothing at all, so its absence is the
    # answer rather than a missing one.
    data["private"] = bool(form.get("private"))
    return data


def _order_or_404(db: Session, p: Project, oid: int) -> ProjectOrder:
    row = db.get(ProjectOrder, oid)
    if row is None or row.project_id != p.asset_id:
        raise HTTPException(404, f"no order {oid} in {p.asset_id}")
    return row


def _project_card(members: Iterable[tuple[str, Computer | Part, ProjectAsset]]) -> str | None:
    """The photograph a project's shared link shows: the first of its things that
    has one, or None to fall back to the site's own card.

    A project had no picture of its own and so always showed the logo, which made
    every project posted anywhere look like every other one. It is about things,
    and those things have been photographed -- so the machine is what a link to the
    work on it should show.

    The first with a photo rather than a chosen one: the items are in the order they
    were put on the project, so the first is the thing it was raised about, which is
    the one somebody means. Nothing is added to the schema to say otherwise, because
    a "card photo" column would be a second way of saying what the order already
    says.

    detect_images returns placeholders for a thing with no photograph of its own --
    a drive icon, a blank machine -- and those are worse than the site card in a
    share preview: a generic outline of a computer reads as a broken image rather
    than as a machine. So only a real upload counts."""
    for _kind, obj, _row in members:
        kind = "computers" if isinstance(obj, Computer) else "parts"
        for rel in detect_images(kind, obj.asset_id):
            if "/placeholders/" not in rel:
                return rel
    return None


def _today_panel(db: Session, project: Project | None) -> dict[str, object] | None:
    """What the suggestion shows: the project, a photograph or three of the things
    it is about, the jobs still to do, and how long it has been quiet.

    The photographs are the items', because a project has none of its own -- it is a
    piece of work, and what can be photographed is the hardware it is about. One
    each from as many items as there are, then more from the first, so a project
    about three machines shows the three rather than three views of one."""
    if project is None:
        return None
    members = projects.members(db, project.asset_id)
    shots, seen = [], set()
    for wanted in (1, TODAY_PHOTOS):
        for kind, obj, _row in members:
            for rel in detect_images(kind, obj.asset_id)[:wanted]:
                if rel in seen:
                    continue
                seen.add(rel)
                # Each picture is a way through to the thing it is of, not to the
                # project: somebody looking at a photograph of a drive wants the
                # drive's page, and the project's name above it is already a link.
                shots.append(
                    {
                        "rel": rel,
                        "url": f"/{kind}/{obj.asset_id}",
                        "alt": entry.display_name(to_dict(obj)),
                    }
                )
                if len(shots) == TODAY_PHOTOS:
                    break
            if len(shots) == TODAY_PHOTOS:
                break
        if len(shots) == TODAY_PHOTOS:
            break
    tasks = [t for t in projects.tasks(db, project.asset_id) if not t.done]
    orders_out = sum(1 for o in projects.orders(db, project.asset_id) if not o.delivered)
    last = (
        db.query(func.max(LogEntry.created_at))
        .filter(LogEntry.asset_id == project.asset_id)
        .scalar()
    )
    return {
        "p": project,
        "members": [
            {"url": f"/{kind}/{obj.asset_id}", "name": entry.display_name(to_dict(obj))}
            for kind, obj, _row in members
        ],
        "photos": shots,
        "tasks": tasks[:TODAY_TASKS],
        "tasks_left": len(tasks),
        "orders_out": orders_out,
        # Whole days, and None for a project nothing has ever been written about --
        # which cannot happen through the app (creating one writes a line) but can
        # through a restore, and "quiet for 20361 days" would be a strange thing for
        # a page to say about it.
        "quiet_days": (_now() - last).days if last else None,
    }


def _projects_card(
    db: Session, rows: Sequence[projects.Summary], limit: int = cards.MAX_TILES
) -> list[str]:
    """The photographs the projects *list* tiles its share card from: the first
    photograph of each project on the page, in the order the page reads (ADR-0017).

    One photograph per project rather than four off the first one, because this page
    is a list of projects and a card of four views of one machine would describe it
    as a page about that machine.

    `rows` is what the page is showing, which is what makes this safe to put on a
    picture an anonymous crawler fetches: a private project is already absent from a
    visitor's rows, so it is absent from the card without a second rule that could
    come to disagree with the first.

    One query and the two folder listings however many projects there are, rather
    than projects.members per row -- this is the page that would notice, which is why
    summaries() is written the way it is.
    """
    ids = [r["p"].asset_id for r in rows]
    if not ids:
        return []
    owned: dict[str, list[str]] = {}
    for pid, aid in (
        db.query(ProjectAsset.project_id, ProjectAsset.asset_id)
        .filter(ProjectAsset.project_id.in_(ids))
        .order_by(ProjectAsset.id)
    ):
        owned.setdefault(pid, []).append(aid)
    listing = {kind: folder_images(kind) for kind in ("computers", "parts")}
    out = []
    for pid in ids:
        for aid in owned.get(pid, []):
            found = next(
                (
                    rel
                    for kind in ("computers", "parts")
                    for rel in pick_images(kind, aid, listing[kind])
                ),
                None,
            )
            if found:
                out.append(found)
                break
        if len(out) == limit:
            break
    return out


router = APIRouter()


class _ItemRow(TypedDict):
    asset_id: str
    name: str
    moves_from: Project | None


class _FormItems(NamedTuple):
    """The Items fieldset as posted: the tags it now lists, and what was typed into
    the box if it could not be added, with why."""

    ids: list[str]
    typed: str
    error: str


NO_NAME = 'Needs a name, like "recap the +2A".'

# The project form's boxes that take one shape of answer (forms.SHAPES).
DATES = ("started_at", "target_date", "finished_at")


def _form_items(db: Session, form: Posted) -> _FormItems:
    """The list the form carries, with its Remove and its box applied.

    The list rides in hidden inputs, so it is checked as it comes back: a tag that
    is not a computer or part is dropped rather than trusted, as the add route drops
    one. What is typed in the box is added whichever button was pressed -- a tag left
    there when Save is pressed was meant, and losing it would be the form deciding
    it was not."""
    ids: list[str] = []
    for raw in form.getlist("items"):
        aid = raw.strip().upper()
        if aid and aid not in ids and any(db.get(cls, aid) for cls in (Computer, Part)):
            ids.append(aid)
    drop = (form.get("drop") or "").strip().upper()
    if drop in ids:
        ids.remove(drop)
    typed = (form.get("add_item") or "").strip()
    if not typed:
        return _FormItems(ids, "", "")
    found, error = projects.find_item(db, typed)
    if found is None:
        return _FormItems(ids, typed, error)
    if found not in ids:
        ids.append(found)
    return _FormItems(ids, "", "")


def _item_rows(db: Session, ids: Iterable[str], project_id: str | None) -> list[_ItemRow]:
    """Each listed thing as the form shows it: its name, and the project it is on now
    if that is another one -- saving moves it, and the form says so first."""
    rows: list[_ItemRow] = []
    for aid in ids:
        held = projects.holder(db, aid)
        rows.append(
            {
                "asset_id": aid,
                "name": _asset_display(db, aid) or aid,
                "moves_from": held if held is not None and held.asset_id != project_id else None,
            }
        )
    return rows


def _project_form_ctx(
    p: Project | Mapping[str, object] | None,
    title: str,
    items: Sequence[_ItemRow] = (),
    add_item: str = "",
    item_error: str = "",
    errors: Sequence[Refusal] = (),
) -> dict[str, object]:
    return {
        "p": p,
        "title": title,
        "statuses": projects.STATUSES,
        "items": items,
        "add_item": add_item,
        "item_error": item_error,
        "errors": errors,
        "field_errors": {f: message for f, _, message in errors},
    }


def _form_back(
    form: Posted, data: Mapping[str, object], chosen: _FormItems
) -> tuple[dict[str, object], list[Refusal]] | None:
    """What the form comes back with, or None when the save can go ahead.

    It comes back for Add item and Remove, which change the list on the page and
    save nothing, and for a save it refuses. Only a save is refused: adding to the
    list is not the moment to be told the name is missing. Either way a date that
    could not be read is shown as typed, since its column could not hold it."""
    shaped = refusals(form, DATES)
    typed = {f: form.get(f, "") for f, _, _ in shaped}
    if "add" in form or "drop" in form:
        return {**data, **typed}, []
    errors = ([] if data["name"] else [("name", "Name", NO_NAME)]) + shaped
    if chosen.error:
        errors.append(("add_item", "Add a computer or part", chosen.error))
    return ({**data, **typed}, errors) if errors else None


def _take_on(db: Session, p: Project, asset_id: str, note: str = "") -> None:
    """Put a thing on a project and say so in both histories. The one way in, for
    the project page's add box and the form's Save alike."""
    if projects.add_asset(db, p.asset_id, asset_id, note):
        what = _asset_named(db, asset_id)
        add_log(db, p.asset_id, f"took on {what}" + (f" — {note}" if note else ""))
        _member_log(db, p, asset_id)


def _let_go(db: Session, p: Project, asset_id: str) -> None:
    """Take a thing off a project, and say so in both histories."""
    if projects.drop_asset(db, p.asset_id, asset_id):
        add_log(db, p.asset_id, f"let go of {_asset_named(db, asset_id)}")
        _member_log(db, p, asset_id, joining=False)


def _project_of_the_day(db: Session, authed: bool) -> Project | None:
    """One project to suggest, drawn now, or None if there is nothing in hand.

    Weighted towards the neglected, because the point of a nudge is the thing you
    had forgotten and not the one you were doing yesterday. A project's weight is
    how long its history has been quiet, capped, doubled if its status says stalled;
    a project touched today weighs one, which keeps it in the draw rather than
    excluding it -- what was worked on this morning is still a reasonable answer to
    what to do this afternoon.

    Drawn on every visit rather than once a day. It is a suggestion and not a queue:
    looking again for another one is a thing somebody will want to do, and the
    weighting means the same project coming up twice running is unlikely rather than
    impossible.

    A visitor is offered only the public ones, for the reason the list below them
    is filtered (see _visible)."""
    q = _visible(db.query(Project).filter(Project.status.notin_(projects.CLOSED)), authed)
    pool = q.all()
    if not pool:
        return None
    # The last thing written about each of them, in one query: a project's history
    # is what says when it was last thought about at all.
    last: dict[str | None, datetime | None] = dict(
        db.query(LogEntry.asset_id, func.max(LogEntry.created_at))
        .filter(LogEntry.asset_id.in_([p.asset_id for p in pool]))
        .group_by(LogEntry.asset_id)
        .tuples()
    )
    now = _now()
    weights = []
    for p in pool:
        seen = last.get(p.asset_id)
        quiet = (now - seen).days if seen else TODAY_QUIET_CAP
        weight = min(max(quiet, 0), TODAY_QUIET_CAP) + 1
        if p.status == "stalled":
            weight *= TODAY_STALLED_WEIGHT
        weights.append(weight)
    return random.choices(pool, weights=weights, k=1)[0]


# How many photographs the suggestion at the top of the projects page carries, and
# how many of the project's jobs it lists. Enough to say what the thing is and what
# is left to do on it; more would be the project's own page, drawn twice.
TODAY_PHOTOS = 3


TODAY_TASKS = 3


# The longest a silence counts for in the draw. A project nobody has touched for
# three years is not thirty times more overdue than one left a month ago -- past
# some point it is simply "not for a while", and without a ceiling the oldest
# project would win every draw and the feature would be a fixture.
TODAY_QUIET_CAP = 180


# What being stalled is worth, as against merely being quiet. Stalled is the state
# somebody chose to record: it says out loud that this one is waiting on a part, the
# weather or the will, and those are exactly the ones that never come up again on
# their own.
TODAY_STALLED_WEIGHT = 2


@router.get("/projects", response_class=HTMLResponse, include_in_schema=False)
def gui_projects(request: Request, q: str = "", db: Session = Depends(get_db)) -> HTMLResponse:
    """Everything planned, in hand or finished. `q` narrows it, and is a box of its
    own rather than the banner's: the banner searches the register and lands on the
    gallery, and a page of projects wants to be siftable without leaving it."""
    return _projects_page(request, db, q)


@router.post("/projects/quick", include_in_schema=False)
async def gui_project_quick(request: Request, db: Session = Depends(get_db)) -> Response:
    """A project in one gesture, from the list's own page.

    This is what the flag on an item used to be, and it is here for the same
    reason: you are at the bench, you have just seen what is wrong with something,
    and finding its page to write it down is how the second thing you noticed gets
    lost. What is different is that what you get is a project -- with the item on
    it and the sentence as its first job -- rather than a flag that has to be
    turned into one by hand later.

    Public, like everything else in the register: the tick on a project's own form
    is what keeps one back, and it is a decision rather than a starting point (see
    _take_on_work, which this goes through, and ADR-0004).

    The asset tag is optional. A project need own nothing -- the idea comes before
    the hardware -- and the commonest thing to want at a bench is both: this drive,
    this fault.

    `project` names one already going for the item and the jobs to go on instead of
    raising another. The panel on an item's page offers it as a menu; the box on the
    projects page does not, because a list of projects is not where you are standing
    when you find out a part is for one of them.

    One route for both boxes and for the entry forms, so what gets made does not
    depend on which of them was to hand."""
    form = await posted(request)
    jobs = _work_lines(form.get("job"))
    asset_id = (form.get("aid") or "").strip().upper()
    name = (form.get("name") or "").strip()
    found = _asset_find(db, asset_id, FLAGGABLE) if asset_id else None
    if asset_id and found is None:
        # Back to the list saying so, rather than a 404 page. A mistyped tag is the
        # ordinary way to get this wrong and the answer to it is the box to type it
        # in again, which is on the page that was already open.
        return _projects_page(request, db, error=asset_id, status=400)
    picked = (form.get("project") or "").strip().upper()
    project = db.get(Project, picked) if picked else None
    if not name:
        # Named after what it is about, where you did not say -- the same name the
        # entry forms give one, because this is the same gesture and a project
        # should not be called two different things depending on which box raised
        # it. Where there is no item, the job names it: a project called nothing is
        # a row nobody will recognise again.
        name = (
            _work_project_name(db, asset_id)
            if found
            else (jobs[0][:60] if jobs else "") or "Untitled project"
        )
    obj = _take_on_work(db, asset_id if found is not None else "", jobs, project, name=name)
    db.commit()
    return RedirectResponse(f"/projects/{obj.asset_id}", status_code=303)


@router.get("/projects/new", response_class=HTMLResponse, include_in_schema=False)
def gui_new_project(request: Request) -> HTMLResponse:
    return templates.TemplateResponse(
        request, "project_form.html", _project_form_ctx(None, "New project")
    )


@router.post("/projects/new", include_in_schema=False)
async def gui_create_project(request: Request, db: Session = Depends(get_db)) -> Response:
    """A project needs a name and nothing else.

    A name because it is the only thing a project can be found by: a machine
    falls back to its manufacturer and model and then to its asset id, and a
    project has neither -- an untitled one is a row nobody will ever recognise
    again. Everything else can be filled in later or never."""
    form = await posted(request)
    data = _project_from_form(form)
    chosen = _form_items(db, form)
    if (back := _form_back(form, data, chosen)) is not None:
        shown, errors = back
        return templates.TemplateResponse(
            request,
            "project_form.html",
            _project_form_ctx(
                shown,
                "New project",
                _item_rows(db, chosen.ids, None),
                chosen.typed,
                chosen.error,
                errors,
            ),
            status_code=400 if errors else 200,
        )
    obj = Project(asset_id=next_asset_id(db), **data)
    db.add(obj)
    add_log(db, obj.asset_id, "created", "created")
    for aid in chosen.ids:
        _take_on(db, obj, aid)
    db.commit()
    return RedirectResponse(f"/projects/{obj.asset_id}", status_code=303)


@router.get("/projects/{aid}", response_class=HTMLResponse, include_in_schema=False)
def gui_project(aid: str, request: Request, db: Session = Depends(get_db)) -> HTMLResponse:
    p = get_or_404(db, Project, aid)
    # The second of the five. Not a 403 and not a redirect to the login: a visitor
    # who guessed the tag of a private project should not be told there is one to
    # guess at, and 404 is what every id that is nothing else answers.
    if p.private and not request.state.sees_private:
        raise HTTPException(404, f"projects {aid} not found")
    order_rows = projects.orders(db, p.asset_id)
    spent, unpriced = projects.spend(order_rows)
    task_rows = projects.tasks(db, p.asset_id)
    # Offered in the "add an item" box: everything in the register that is not
    # already in this project. Only for whoever is signed in -- it is the contents
    # of a form nobody else is shown -- and only as (id, name) pairs, because a
    # menu of a few hundred assets should not be a few hundred loaded rows.
    choices = []
    if request.state.authed:
        here = {
            a
            for (a,) in db.query(ProjectAsset.asset_id).filter(
                ProjectAsset.project_id == p.asset_id
            )
        }
        for cls in (Computer, Part):
            for row in db.query(cls.asset_id, cls.name, cls.manufacturer, cls.model).order_by(
                cls.asset_id
            ):
                if row.asset_id in here:
                    continue
                choices.append(
                    (
                        row.asset_id,
                        entry.display_name(
                            {
                                "asset_id": row.asset_id,
                                "name": row.name,
                                "manufacturer": row.manufacturer,
                                "model": row.model,
                            }
                        ),
                    )
                )
        choices.sort(key=lambda c: c[1].lower())
    members = projects.members(db, p.asset_id)
    return templates.TemplateResponse(
        request,
        "project.html",
        {
            "p": p,
            "item": (pdict := to_dict(p)),
            "kind": "projects",
            # The same Files panel an item has (ADR-0028): a receipt for what was
            # ordered, the schematic the job was done from.
            **filesdb.panel(db, pdict, request.state.authed, request.state.sees_private),
            "fileerr": bool(request.query_params.get("fileerr")),
            "dl_filenotes": _answers_given(db, StoredFile.note),
            # Who things have been bought from before: the same kind of field as an
            # item's source, and answered the same few ways.
            "dl_suppliers": _answers_given(db, ProjectOrder.supplier),
            "members": members,
            "tasks": task_rows,
            "tasks_done": sum(1 for t in task_rows if t.done),
            "orders": order_rows,
            "orders_out": sum(1 for o in order_rows if not o.delivered),
            "spent": spent,
            "unpriced": unpriced,
            "choices": choices,
            "log": _history(db, p.asset_id),
            "og": _og(
                request,
                p.name or p.asset_id,
                p.summary or projects.status_label(p.status),
                _project_card(members),
            ),
        },
    )


@router.get("/projects/{aid}/edit", response_class=HTMLResponse, include_in_schema=False)
def gui_edit_project(aid: str, request: Request, db: Session = Depends(get_db)) -> HTMLResponse:
    p = get_or_404(db, Project, aid)
    here = [obj.asset_id for _kind, obj, _row in projects.members(db, p.asset_id)]
    return templates.TemplateResponse(
        request,
        "project_form.html",
        _project_form_ctx(p, "Edit project", items=_item_rows(db, here, p.asset_id)),
    )


@router.post("/projects/{aid}/edit", include_in_schema=False)
async def gui_update_project(aid: str, request: Request, db: Session = Depends(get_db)) -> Response:
    p = get_or_404(db, Project, aid)
    form = await posted(request)
    data = _project_from_form(form)
    chosen = _form_items(db, form)
    if (back := _form_back(form, data, chosen)) is not None:
        # What was typed rather than what is on file, so a refusal or a change to
        # the list costs nothing already written.
        shown, errors = back
        return templates.TemplateResponse(
            request,
            "project_form.html",
            _project_form_ctx(
                {**shown, "asset_id": p.asset_id},
                "Edit project",
                _item_rows(db, chosen.ids, p.asset_id),
                chosen.typed,
                chosen.error,
                errors,
            ),
            status_code=400 if errors else 200,
        )
    before = to_dict(p)
    for k, v in data.items():
        setattr(p, k, v)
    add_log(db, p.asset_id, _field_diffs(before, to_dict(p), PROJECT_FIELDS))
    if bool(before["private"]) != bool(p.private):
        _publish_log(db, p)
    # After the publishing, so a thing added in the same save as the project goes
    # public is written into its history once, by _take_on, rather than twice. Only
    # when the form drew its list: a post that never carried one says nothing about
    # what the project is about, and must not be read as "about nothing".
    if "items_listed" in form:
        here = [obj.asset_id for _kind, obj, _row in projects.members(db, p.asset_id)]
        for gone in (a for a in here if a not in chosen.ids):
            _let_go(db, p, gone)
        for new in (a for a in chosen.ids if a not in here):
            _take_on(db, p, new)
    db.commit()
    return RedirectResponse(f"/projects/{p.asset_id}", status_code=303)


@router.post("/projects/{aid}/complete", include_in_schema=False)
def gui_complete_project(aid: str, db: Session = Depends(get_db)) -> RedirectResponse:
    """The button that ends a project, with nothing in front of it.

    Finishing is one fact, and saying it through the edit form meant opening a
    page, changing a menu, typing today into a date box and saving -- four
    gestures for one statement, which is how a register comes to be full of
    projects that are over and do not say so.

    A finish date already written down is kept. It says when the work actually
    stopped, and a click that may come a fortnight later is in no position to
    correct it; none of a project's three dates is worked out from another (see
    the Project model) and this does not start. Today is written only into a blank.

    A sentence rather than a field diff, as the tick on an order leaves: what
    happened is that the project was finished, and a reader of the history wants
    that rather than the two columns it moved."""
    p = get_or_404(db, Project, aid)
    p.status = "done"
    if p.finished_at is None:
        p.finished_at = date.today()
    add_log(db, p.asset_id, "finished")
    db.commit()
    return RedirectResponse(f"/projects/{p.asset_id}", status_code=303)


@router.get("/projects/{aid}/label.png", include_in_schema=False)
def gui_project_label_png(
    aid: str, media: str = "", dpi: int = 0, db: Session = Depends(get_db)
) -> Response:
    p = get_or_404(db, Project, aid)
    return png_label(to_dict(p), labels.PROJECT, media, dpi)


@router.get("/projects/{aid}/label.pdf", include_in_schema=False)
def gui_project_label(aid: str, small: int = 1, db: Session = Depends(get_db)) -> Response:
    """A printable label for a project, so a thing bought for one can carry a
    sticker saying what it is for.

    The same label the machines and the parts get, made by the same code and
    carrying the same /items/<id> code -- which is the whole reason a project was
    given a register id in the first place. Scanning the sticker on a parcel opens
    the project it was bought for, with its orders on it.

    Small by default, as a part's is. A machine gets the 6x4 by default because it
    is filed on a shelf and read across a room; this is going on a jiffy bag."""
    p = get_or_404(db, Project, aid)
    pdf = labels.render_pdf(to_dict(p), [], labels.PROJECT, small=bool(small))
    return Response(
        pdf,
        media_type="application/pdf",
        headers={"Content-Disposition": f'inline; filename="{aid}{"-small" if small else ""}.pdf"'},
    )


@router.post("/projects/{aid}/note", include_in_schema=False)
async def gui_project_note(
    aid: str, request: Request, db: Session = Depends(get_db)
) -> RedirectResponse:
    """The same note bar the machines have, posting to the same shape of URL, which
    is why _history.html needed nothing said to it about projects."""
    get_or_404(db, Project, aid)
    _note_with_photos(db, aid, await posted(request))
    return RedirectResponse(f"/projects/{aid}", status_code=303)


@router.post("/projects/{aid}/delete", include_in_schema=False)
async def gui_delete_project(aid: str, db: Session = Depends(get_db)) -> RedirectResponse:
    """Delete a project outright, with no disposal step in front of it.

    A machine has to be marked disposed before it can be deleted, because deleting
    one is claiming a physical object has left the collection and that is a thing
    worth being sure about. A project is a plan. Abandoning one is already a status
    it can be put in and kept in, so the only reason left to delete is that it was
    written by mistake -- and a confirmation is enough for that.

    Its tasks, orders and memberships go by the foreign key's cascade. Its history
    does not: log_entry is keyed by a plain register id with nothing to cascade
    from, so it is cleared here by hand, photographs first while there are still
    entries to find them by -- exactly as the two asset delete paths do it."""
    p = get_or_404(db, Project, aid)
    photos = _drop_log_photos(db, p.asset_id)
    db.query(LogEntry).filter(LogEntry.asset_id == p.asset_id).delete(synchronize_session=False)
    # The links to its files, and never the files: one uploaded here may be linked
    # to a machine too, and one that is not is left unlinked rather than binned.
    filesdb.forget_asset(db, p.asset_id)
    db.delete(p)
    db.commit()  # the rows first: if this raises, the photographs are still there
    _purge_photos(photos)
    return RedirectResponse("/projects", status_code=303)


@router.post("/projects/{aid}/add-item", include_in_schema=False)
async def gui_project_add_item(
    aid: str, request: Request, db: Session = Depends(get_db)
) -> RedirectResponse:
    p = get_or_404(db, Project, aid)
    form = await posted(request)
    asset_id = (form.get("asset_id", "") or "").strip().upper()
    note = (form.get("note", "") or "").strip()
    _take_on(db, p, asset_id, note)
    db.commit()
    return RedirectResponse(f"/projects/{p.asset_id}", status_code=303)


@router.post("/projects/{aid}/remove-item", include_in_schema=False)
async def gui_project_remove_item(
    aid: str, request: Request, db: Session = Depends(get_db)
) -> RedirectResponse:
    p = get_or_404(db, Project, aid)
    form = await posted(request)
    asset_id = (form.get("asset_id", "") or "").strip().upper()
    _let_go(db, p, asset_id)
    db.commit()
    return RedirectResponse(f"/projects/{p.asset_id}", status_code=303)


@router.post("/projects/{aid}/task", include_in_schema=False)
async def gui_project_add_task(
    aid: str, request: Request, db: Session = Depends(get_db)
) -> RedirectResponse:
    p = get_or_404(db, Project, aid)
    form = await posted(request)
    text = (form.get("text", "") or "").strip()
    if text:
        db.add(
            ProjectTask(
                project_id=p.asset_id,
                text=text,
                asset_id=_task_asset(db, p.asset_id, form.get("asset", "")),
            )
        )
        add_log(db, p.asset_id, f"to do: {_short(text)}")
        db.commit()
    return RedirectResponse(f"/projects/{p.asset_id}", status_code=303)


@router.post("/projects/{aid}/task/{tid}/about", include_in_schema=False)
async def gui_project_task_about(
    aid: str, tid: int, request: Request, db: Session = Depends(get_db)
) -> RedirectResponse:
    """Say which of the project's things a job is about, from the project's page.

    Its own route rather than a field on the add form, because the jobs that need
    this most are the ones already written -- see api_project_update_task."""
    p = get_or_404(db, Project, aid)
    row = _api_task(db, p, tid)
    form = await posted(request)
    before = row.asset_id
    row.asset_id = _task_asset(db, p.asset_id, form.get("asset", ""))
    if before != row.asset_id:
        add_log(
            db,
            aid,
            (
                f"{_short(row.text)}: about {_asset_named(db, row.asset_id)}"
                if row.asset_id
                else f"{_short(row.text)}: about no one thing"
            ),
        )
    db.commit()
    return RedirectResponse(f"/projects/{p.asset_id}", status_code=303)


@router.post("/projects/{aid}/task/{tid}/toggle", include_in_schema=False)
async def gui_project_toggle_task(
    aid: str, tid: int, request: Request, db: Session = Depends(get_db)
) -> RedirectResponse:
    """Tick a job, or put it back.

    Un-ticking clears the date rather than keeping it. A job that is not done has
    no day it was done on, and leaving the old one behind would mean a task showing
    as outstanding while still claiming a completion date.

    Comes back to the page it was ticked from, which the form says in `next`. A job
    is shown in two places -- its project's list and the page of the thing it is
    about -- and always returning to the project meant ticking one off at the bench,
    where you are looking at the machine, threw you onto a different page. Through
    _safe_next, so the field cannot send anybody off this site.

    A tick on a page sends `set` with the box, and then the job becomes what the box
    shows rather than the opposite of what it is: a tab left open since the job was
    ticked, or a double press, would otherwise untick it. Nothing changes, and
    nothing is logged, when it is already that."""
    p = get_or_404(db, Project, aid)
    row = _task_or_404(db, p, tid)
    form = await posted(request)
    done = form.get("done") == "1" if form.get("set") else not row.done
    if done != row.done:
        row.done = done
        row.done_at = date.today() if done else None
        add_log(db, p.asset_id, ("done: " if done else "back on the list: ") + _short(row.text))
        db.commit()
    return RedirectResponse(
        _safe_next(form.get("next", "") or f"/projects/{p.asset_id}"), status_code=303
    )


@router.post("/projects/{aid}/task/{tid}/delete", include_in_schema=False)
def gui_project_delete_task(aid: str, tid: int, db: Session = Depends(get_db)) -> RedirectResponse:
    p = get_or_404(db, Project, aid)
    row = _task_or_404(db, p, tid)
    add_log(db, p.asset_id, f"dropped: {_short(row.text)}")
    db.delete(row)
    db.commit()
    return RedirectResponse(f"/projects/{p.asset_id}", status_code=303)


@router.post("/projects/{aid}/order", include_in_schema=False)
async def gui_project_add_order(
    aid: str, request: Request, db: Session = Depends(get_db)
) -> RedirectResponse:
    """Something bought for this project. Only the description is required: an
    order written down the moment it is placed rarely has a delivery date yet, and
    a form that insisted on one would be filled in later or not at all."""
    p = get_or_404(db, Project, aid)
    form = await posted(request)
    description = (form.get("description", "") or "").strip()
    if not description:
        return RedirectResponse(f"/projects/{p.asset_id}", status_code=303)
    qty = (form.get("qty", "") or "").strip()
    row = ProjectOrder(
        project_id=p.asset_id,
        description=description[:255],
        supplier=(form.get("supplier", "") or "").strip()[:255],
        url=(form.get("url", "") or "").strip(),
        qty=int(qty) if qty.isdigit() and int(qty) > 0 else 1,
        cost_p=projects.parse_money(form.get("cost", "")),
        ordered_at=_parse_date(form.get("ordered_at", "")) or date.today(),
        expected_at=_parse_date(form.get("expected_at", "")),
        note=(form.get("note", "") or "").strip()[:255],
    )
    db.add(row)
    add_log(
        db,
        p.asset_id,
        f"ordered {_short(description)}" + (f" from {row.supplier}" if row.supplier else ""),
    )
    db.commit()
    return RedirectResponse(f"/projects/{p.asset_id}", status_code=303)


@router.post("/projects/{aid}/order/{oid}/delivered", include_in_schema=False)
def gui_project_order_delivered(
    aid: str, oid: int, db: Session = Depends(get_db)
) -> RedirectResponse:
    """The tick. What arrives is added to the register the ordinary way -- this row
    is a note about a purchase, not a half-made asset -- so all that happens here is
    that it stops being one of the things still coming."""
    p = get_or_404(db, Project, aid)
    row = _order_or_404(db, p, oid)
    row.delivered = not row.delivered
    row.delivered_at = date.today() if row.delivered else None
    add_log(
        db,
        p.asset_id,
        ("arrived: " if row.delivered else "still coming: ") + _short(row.description),
    )
    db.commit()
    return RedirectResponse(f"/projects/{p.asset_id}", status_code=303)


@router.post("/projects/{aid}/order/{oid}/delete", include_in_schema=False)
def gui_project_delete_order(aid: str, oid: int, db: Session = Depends(get_db)) -> RedirectResponse:
    p = get_or_404(db, Project, aid)
    row = _order_or_404(db, p, oid)
    add_log(db, p.asset_id, f"cancelled: {_short(row.description)}")
    db.delete(row)
    db.commit()
    return RedirectResponse(f"/projects/{p.asset_id}", status_code=303)
