"""Work: the jobs on a project, and the things a project is about.

A project is a plan, and what makes it more than a note is that it names things in
the register and jobs against them. Those links are read from three directions --
the project's own page, the page of a thing it is about, and the JSON API -- so
they are here rather than in any one of them.
"""

from collections.abc import Iterable
from enum import Enum

from fastapi import HTTPException
from sqlalchemy.orm import Session

from . import entry, projects
from .common import to_dict
from .history import _short, add_log
from .ids import next_asset_id
from .models import Computer, LogEntry, Part, Project, ProjectAsset, ProjectTask


# Typed as FastAPI types a route's tags: a list is invariant, so a bare list[str]
# is not one of these however obviously it ought to be.
PROJECT_TAGS: list[str | Enum] = ["projects"]


def _asset_display(db: Session, asset_id: str) -> str | None:
    """What a computer or part is called, or None if the register has no such
    thing. The name is a fact about the item and is asked for in two voices -- a
    sentence in a history, and the name of a project about it -- so it is read in
    one place."""
    for cls in (Computer, Part):
        if (obj := db.get(cls, asset_id)) is not None:
            return entry.display_name(to_dict(obj))
    return None


def _project_named(p: Project) -> str:
    """A project in a sentence written in another item's history. The name, because
    that is what it is known by, with the id so the line still points somewhere when
    two projects are called nearly the same thing."""
    return f"{p.name or 'a project'} ({p.asset_id})"


PROJECT_FIELDS = (
    "name",
    "status",
    "summary",
    "notes",
    "started_at",
    "target_date",
    "finished_at",
    "private",
)


def _asset_named(db: Session, asset_id: str) -> str:
    """A computer or part in a sentence written in a project's history: what it is
    called, and its id. Falls back to the bare id for something that has since
    gone, so a history line never reads as a blank."""
    name = _asset_display(db, asset_id)
    return f"{name} ({asset_id})" if name else asset_id


def _task_asset(db: Session, project_id: str, raw: str | None) -> str | None:
    """The thing a job names, checked against the project it is written on. None for
    a job about no one thing in particular -- 'order the caps', 'find a manual' --
    which is most of what a project-wide list holds."""
    aid = (raw or "").strip().upper()
    if not aid:
        return None
    if not projects.holds(db, project_id, aid):
        raise HTTPException(422, f"{aid} is not on {project_id}")
    return aid


def _member_log(db: Session, project: Project, asset_id: str, joining: bool = True) -> None:
    """Write the item's side of a membership -- but only while the project is one
    anybody may read.

    An item page is public and so is its history, and the history is the part of the
    register nothing rewrites. A line reading "wanted for Recap the +2A (RH-J0Y7)"
    on a public page is the name of a private project, published, and published for
    good. So a private project does not write here; its own history, which is as
    private as it is, has the entry either way.

    This is the invariant the pair of functions keeps: an item's history names a
    project exactly while that project is public. _publish_log is the other half,
    for a project that changes its mind."""
    if project.private:
        return
    add_log(
        db,
        asset_id,
        (
            f"wanted for {_project_named(project)}"
            if joining
            else f"no longer wanted for {_project_named(project)}"
        ),
    )


def _work_project_name(db: Session, asset_id: str) -> str:
    """What a project raised from an item's own form is called.

    The form asks for no name: what is being described is the work, and the only
    thing known about it at that moment is which item it is for. So the item names
    it -- what the thing is called, not its tag. "Amstrad PC1640" is a line somebody
    can read down a list and recognise; RH-J8JA is one they have to look up, and a
    list of them is a list of lookups.

    The item's name is the whole of it. It carried "Work required by item: " in
    front until 0036 -- a phrase that read the same on every row it appeared on, and
    so told a reader nothing, while pushing the only part that varies to where a
    narrow column cuts it off. What the project is for is already said by the item
    beside it and by its status, on every list it appears in.

    The tag is the fallback, through display_name, for a thing entered with no
    maker, model or name of its own yet -- and the project's own tag is beside it on
    every list it appears in, which is what tells two machines of the same model
    apart. Rename it on its own form once it is a piece of work with a character of
    its own."""
    return _asset_display(db, asset_id) or asset_id


def _work_lines(raw: str | None) -> list[str]:
    """The jobs out of a work box, one to a line.

    Faults arrive as a list -- recap, belt, keyboard sticks -- and one box holding
    all three as a sentence would make a single task that can only ever be half
    ticked off. Blank lines go, so a trailing newline is not a job with nothing in
    it."""
    return [line.strip() for line in (raw or "").splitlines() if line.strip()]


def _take_on_work(
    db: Session,
    asset_id: str,
    jobs: Iterable[str],
    project: Project | None = None,
    name: str = "",
) -> Project:
    """Put an item and its jobs on a project, making one if none was given.

    The one path everything that notes work runs down -- the quick box, both entry
    forms, both edit forms and the API -- so the item lands on the project, the
    history is written from both ends and the same rules apply wherever the sentence
    was typed.

    Public, like everything else in the register. These started private, on the
    argument that a line typed at a bench in five seconds has not been considered
    for publication. In practice the register is a public catalogue of old machines,
    what is wrong with one is a good part of what is interesting about it, and a
    default that hides the work meant undoing it by hand on nearly every project.
    The tick on a project's own form still keeps one back; it is a decision now
    rather than a starting point (ADR-0004).

    Commits nothing. Every caller is in the middle of saving something else and owns
    the transaction; a commit here would be a half-saved machine with a project
    beside it if what follows fails."""
    held = projects.project_for(db, asset_id) if asset_id else None
    # The thing's own project, where nobody picked one and the thing has one. A job
    # noted on an item's page belongs with the work already going on that item; a
    # thing is on one project (ADR-0016), so raising a second about the same thing
    # is the one answer that cannot be right.
    if project is None:
        project = held
    if project is None:
        project = Project(
            asset_id=next_asset_id(db),
            name=(name or _work_project_name(db, asset_id))[:255],
            status="planned",
            private=False,
        )
        db.add(project)
        add_log(db, project.asset_id, "created", "created")
    if asset_id and projects.add_asset(db, project.asset_id, asset_id):
        if held is not None:
            # Said on the project losing it too. A thing leaving is as much a fact
            # about the old project as arriving is about the new one, and the old
            # one's history is where somebody will look for where it went.
            add_log(
                db,
                held.asset_id,
                f"{_asset_named(db, asset_id)} moved to {_project_named(project)}",
            )
        add_log(db, project.asset_id, f"took on {_asset_named(db, asset_id)}")
        _member_log(db, project, asset_id)
    for job in jobs:
        # Against the thing, where there is one: an item's page lists its own jobs,
        # and a job typed on that page is about that item by definition.
        db.add(ProjectTask(project_id=project.asset_id, text=job, asset_id=asset_id or None))
        add_log(db, project.asset_id, f"to do: {_short(job)}")
    return project


def _publish_log(db: Session, project: Project) -> None:
    """Bring the members' histories into line after a project's privacy changed.

    Publishing writes the lines that were held back; withdrawing deletes them. That
    delete is the one place the register rewrites its own log, and it is the whole
    point: a name taken out of publication cannot be left behind in the one public
    place it was written, or withdrawing it would mean nothing."""
    members = [
        row.asset_id
        for row in db.query(ProjectAsset).filter(ProjectAsset.project_id == project.asset_id)
    ]
    if project.private:
        # Matched on the tag rather than the name: the name may have been edited in
        # the same breath, and the tag is what makes the line this project's.
        for asset_id in members:
            (
                db.query(LogEntry)
                .filter(
                    LogEntry.asset_id == asset_id, LogEntry.message.like(f"%({project.asset_id})%")
                )
                .delete(synchronize_session=False)
            )
    else:
        for asset_id in members:
            add_log(db, asset_id, f"wanted for {_project_named(project)}")


def _api_task(db: Session, p: Project, tid: int) -> ProjectTask:
    row = db.get(ProjectTask, tid)
    if row is None or row.project_id != p.asset_id:
        raise HTTPException(404, f"no task {tid} in {p.asset_id}")
    return row
