"""The JSON API for projects: the work, its jobs and what it has on order."""

from datetime import date


# --- JSON API: projects ------------------------------------------------------
# The same thing the pages do, for the tool server and for scripts. Full CRUD on
# the project, and endpoints of their own for the three lists it holds.
#
# The lists are not fields of the project on the way in, which is the one place
# this departs from how a computer's drives and memory are written. A drive row is
# a description of a machine and is rewritten wholesale every time the machine is
# described; a task is a row somebody ticks. A caller that read the list, changed
# one line and posted the lot back would silently drop whatever was added in
# between -- so each is added, changed and removed one at a time, by its own id.


# --- JSON API: what a project is about ---------------------------------------


# --- JSON API: the jobs and the things on order ------------------------------

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from .. import entry, filesdb, projects
from ..common import to_dict
from ..db import get_db
from ..forms import _field_diffs
from ..history import _short, add_log
from ..ids import next_asset_id
from ..models import Computer, LogEntry, Part, Project, ProjectOrder, ProjectTask
from ..photos import _drop_log_photos, _purge_photos
from ..register import get_or_404
from ..schemas import (
    ProjectIn,
    ProjectItemIn,
    ProjectOrderIn,
    ProjectOrderOut,
    ProjectOut,
    ProjectTaskIn,
    ProjectTaskOut,
)
from ..work import PROJECT_TAGS, _api_task, _asset_named, _member_log, _publish_log, _task_asset

router = APIRouter()


def _project_out(db: Session, p: Project) -> dict[str, object]:
    """A project as it reads back: its own columns, the status in words, and its
    three lists. Four queries whatever it holds."""
    return to_dict(p) | {
        "status_label": projects.status_label(p.status),
        "items": [
            {
                "asset_id": obj.asset_id,
                "kind": kind,
                "name": entry.display_name(to_dict(obj)),
                "note": row.note,
            }
            for kind, obj, row in projects.members(db, p.asset_id)
        ],
        "tasks": projects.tasks(db, p.asset_id),
        "orders": projects.orders(db, p.asset_id),
    }


def _api_project(db: Session, aid: str) -> Project:
    return get_or_404(db, Project, aid)


def _api_order(db: Session, p: Project, oid: int) -> ProjectOrder:
    row = db.get(ProjectOrder, oid)
    if row is None or row.project_id != p.asset_id:
        raise HTTPException(404, f"no order {oid} in {p.asset_id}")
    return row


@router.get("/api/projects", response_model=list[ProjectOut], tags=PROJECT_TAGS)
def api_list_projects(
    status: str | None = None, open: bool | None = None, db: Session = Depends(get_db)
) -> list[dict[str, object]]:
    """Every project, with what each is about, what is to be done and what is on
    order. `status` narrows it to one state; `open=true` to the ones not finished
    or abandoned, which is the question a list of projects is usually asked."""
    q = db.query(Project)
    if status:
        q = q.filter(Project.status == status)
    if open is not None:
        q = (
            q.filter(Project.status.notin_(projects.CLOSED))
            if open
            else q.filter(Project.status.in_(projects.CLOSED))
        )
    return [_project_out(db, p) for p in q.order_by(Project.name, Project.asset_id).all()]


@router.post("/api/projects", response_model=ProjectOut, tags=PROJECT_TAGS)
def api_create_project(data: ProjectIn, db: Session = Depends(get_db)) -> dict[str, object]:
    """Start a project. Only the name is required -- it is the only thing a
    project can be found by, having no manufacturer or model to fall back on."""
    fields = data.model_dump()
    fields["name"] = (fields.get("name") or "").strip()
    if not fields["name"]:
        raise HTTPException(422, "a project needs a name")
    fields["status"] = projects.clean_status(fields.get("status"))
    obj = Project(asset_id=next_asset_id(db), **fields)
    db.add(obj)
    add_log(db, obj.asset_id, "created", "created")
    db.commit()
    db.refresh(obj)
    return _project_out(db, obj)


@router.get("/api/projects/{aid}", response_model=ProjectOut, tags=PROJECT_TAGS)
def api_get_project(aid: str, db: Session = Depends(get_db)) -> dict[str, object]:
    return _project_out(db, _api_project(db, aid))


@router.patch("/api/projects/{aid}", response_model=ProjectOut, tags=PROJECT_TAGS)
def api_update_project(
    aid: str, data: ProjectIn, db: Session = Depends(get_db)
) -> dict[str, object]:
    p = _api_project(db, aid)
    fields = data.model_dump(exclude_unset=True)
    if "name" in fields:
        fields["name"] = (fields["name"] or "").strip()
        if not fields["name"]:
            raise HTTPException(422, "a project needs a name")
    if "status" in fields:
        fields["status"] = projects.clean_status(fields["status"])
    old = to_dict(p)
    for k, v in fields.items():
        setattr(p, k, v)
    add_log(db, aid, _field_diffs(old, to_dict(p), list(fields)))
    if bool(old["private"]) != bool(p.private):
        _publish_log(db, p)
    db.commit()
    db.refresh(p)
    return _project_out(db, p)


# response_model=None: the annotation is for the type checker. FastAPI would
# otherwise publish it as the response's shape, which the pinned contract
# (ADR-0010) leaves open.
@router.delete("/api/projects/{aid}", tags=PROJECT_TAGS, response_model=None)
def api_delete_project(aid: str, db: Session = Depends(get_db)) -> dict[str, object]:
    """Delete a project. Its tasks, orders and memberships go with it by the
    foreign key; its history goes by hand, log_entry having nothing to cascade
    from. The hardware it was about is untouched -- deleting the plan is not
    disposing of the machine."""
    p = _api_project(db, aid)
    photos = _drop_log_photos(db, aid)
    db.query(LogEntry).filter(LogEntry.asset_id == aid).delete(synchronize_session=False)
    # Its file links, and never the files (ADR-0028).
    filesdb.forget_asset(db, aid)
    db.delete(p)
    db.commit()
    _purge_photos(photos)
    return {"deleted": aid, "photos": len(photos)}


@router.post("/api/projects/{aid}/items", response_model=ProjectOut, tags=PROJECT_TAGS)
def api_project_add_item(
    aid: str, data: ProjectItemIn, db: Session = Depends(get_db)
) -> dict[str, object]:
    """Put a computer or part in a project. An asset id that is in neither table is
    refused rather than stored: a project is about things that exist, and a
    membership pointing at nothing would render as nothing for ever.

    Adding one already in it is not an error -- the project ends up in the state
    asked for, which is what a caller retrying a request wants."""
    p = _api_project(db, aid)
    asset_id = (data.asset_id or "").strip().upper()
    if not any(db.get(cls, asset_id) for cls in (Computer, Part)):
        raise HTTPException(404, f"no computer or part {data.asset_id}")
    if projects.add_asset(db, aid, asset_id, data.note):
        add_log(db, aid, f"took on {_asset_named(db, asset_id)}")
        _member_log(db, p, asset_id)
        db.commit()
    return _project_out(db, p)


@router.delete("/api/projects/{aid}/items/{asset_id}", response_model=ProjectOut, tags=PROJECT_TAGS)
def api_project_drop_item(
    aid: str, asset_id: str, db: Session = Depends(get_db)
) -> dict[str, object]:
    p = _api_project(db, aid)
    asset_id = (asset_id or "").strip().upper()
    if projects.drop_asset(db, aid, asset_id):
        add_log(db, aid, f"let go of {_asset_named(db, asset_id)}")
        _member_log(db, p, asset_id, joining=False)
        db.commit()
    return _project_out(db, p)


@router.post("/api/projects/{aid}/tasks", response_model=ProjectTaskOut, tags=PROJECT_TAGS)
def api_project_add_task(
    aid: str, data: ProjectTaskIn, db: Session = Depends(get_db)
) -> ProjectTask:
    p = _api_project(db, aid)
    text = (data.text or "").strip()
    if not text:
        raise HTTPException(422, "a task needs something written in it")
    db.add(
        row := ProjectTask(
            project_id=p.asset_id,
            text=text,
            done=bool(data.done),
            asset_id=_task_asset(db, p.asset_id, data.asset_id),
        )
    )
    if row.done:
        row.done_at = date.today()
    add_log(db, aid, f"to do: {_short(text)}")
    db.commit()
    db.refresh(row)
    return row


@router.patch("/api/projects/{aid}/tasks/{tid}", response_model=ProjectTaskOut, tags=PROJECT_TAGS)
def api_project_update_task(
    aid: str, tid: int, data: ProjectTaskIn, db: Session = Depends(get_db)
) -> ProjectTask:
    """Reword a job, tick it, or say which of the project's things it is about.

    `asset_id` takes one of the project's own members, or null to say the job is
    about the project rather than any one thing on it. It is here as well as on the
    create because the jobs written before a job could name anything are exactly the
    ones that most need saying -- without it the only way to attach one is to delete
    it and type it again, which loses the tick and the day it was done.

    Un-ticking clears the date as well: a job that is not done has no day it was
    done on."""
    p = _api_project(db, aid)
    row = _api_task(db, p, tid)
    fields = data.model_dump(exclude_unset=True)
    if "text" in fields and (text := (fields["text"] or "").strip()):
        row.text = text
    if "done" in fields and fields["done"] is not None:
        was = bool(row.done)
        row.done = bool(fields["done"])
        row.done_at = date.today() if row.done else None
        if was != row.done:
            add_log(db, aid, ("done: " if row.done else "back on the list: ") + _short(row.text))
    if "asset_id" in fields:
        before = row.asset_id
        row.asset_id = _task_asset(db, p.asset_id, fields["asset_id"])
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
    db.refresh(row)
    return row


# response_model=None, as above: the annotation is for the type checker.
@router.delete("/api/projects/{aid}/tasks/{tid}", tags=PROJECT_TAGS, response_model=None)
def api_project_delete_task(aid: str, tid: int, db: Session = Depends(get_db)) -> dict[str, int]:
    p = _api_project(db, aid)
    row = _api_task(db, p, tid)
    add_log(db, aid, f"dropped: {_short(row.text)}")
    db.delete(row)
    db.commit()
    return {"deleted": tid}


@router.post("/api/projects/{aid}/orders", response_model=ProjectOrderOut, tags=PROJECT_TAGS)
def api_project_add_order(
    aid: str, data: ProjectOrderIn, db: Session = Depends(get_db)
) -> ProjectOrder:
    """Record something bought for a project. Only the description is required: an
    order written down as it is placed rarely has a delivery date yet.

    Nothing here becomes a part. When it arrives it is added to the register the
    ordinary way and this row is ticked -- which keeps an order a note about a
    purchase rather than a half-made asset."""
    p = _api_project(db, aid)
    fields = data.model_dump(exclude_unset=True)
    description = (fields.get("description") or "").strip()
    if not description:
        raise HTTPException(422, "an order needs a description")
    delivered = bool(fields.pop("delivered", False))
    row = ProjectOrder(
        project_id=p.asset_id,
        **(
            fields
            | {
                "description": description,
                "ordered_at": fields.get("ordered_at") or date.today(),
                "delivered": delivered,
                "delivered_at": date.today() if delivered else None,
            }
        ),
    )
    db.add(row)
    add_log(
        db,
        aid,
        f"ordered {_short(description)}" + (f" from {row.supplier}" if row.supplier else ""),
    )
    db.commit()
    db.refresh(row)
    return row


@router.patch("/api/projects/{aid}/orders/{oid}", response_model=ProjectOrderOut, tags=PROJECT_TAGS)
def api_project_update_order(
    aid: str, oid: int, data: ProjectOrderIn, db: Session = Depends(get_db)
) -> ProjectOrder:
    """Change an order, or mark it in. Setting `delivered` dates it; clearing it
    clears the date, for the reason un-ticking a task does."""
    p = _api_project(db, aid)
    row = _api_order(db, p, oid)
    fields = data.model_dump(exclude_unset=True)
    delivered = fields.pop("delivered", None)
    for k, v in fields.items():
        setattr(row, k, v)
    if delivered is not None and bool(delivered) != bool(row.delivered):
        row.delivered = bool(delivered)
        row.delivered_at = date.today() if row.delivered else None
        add_log(
            db, aid, ("arrived: " if row.delivered else "still coming: ") + _short(row.description)
        )
    db.commit()
    db.refresh(row)
    return row


# response_model=None, as above: the annotation is for the type checker.
@router.delete("/api/projects/{aid}/orders/{oid}", tags=PROJECT_TAGS, response_model=None)
def api_project_delete_order(aid: str, oid: int, db: Session = Depends(get_db)) -> dict[str, int]:
    p = _api_project(db, aid)
    row = _api_order(db, p, oid)
    add_log(db, aid, f"cancelled: {_short(row.description)}")
    db.delete(row)
    db.commit()
    return {"deleted": oid}
