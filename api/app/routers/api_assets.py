"""The JSON API for the things on the shelf: computers and parts.

The same rows the pages edit, read and written by something that is not a browser
-- the command-line tools and the MCP server. What it offers is the register's
shape rather than a page's: a machine with its memory, its drives and the catalogue
model it answers to, flattened into one document.
"""
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session


# --- JSON API: parts -------------------------------------------------------

from .. import drivedb, entry, machinedb, machines, projects, ramdb, specdb
from ..assets import delete_computer, delete_part
from ..common import to_dict
from ..db import get_db
from ..disposal import _and_parts, _dispose_contents, _restore_contents
from ..forms import _field_diffs
from ..history import add_log
from ..ids import next_asset_id
from ..models import Computer, Part, Project
from ..register import get_or_404
from ..schemas import (ComputerCreate, ComputerIn, ComputerOut, PartCreate, PartIn,
                       PartOut)
from ..work import _take_on_work, _work_lines

router = APIRouter()


def _drives_from_api(db, computer, text):
    """drives over the wire is what a person would type, ';'-separated, and is
    parsed into rows the way the specs string is -- anything a segment does not
    yield is kept verbatim in drives_note."""
    drives, note = drivedb.from_string(text)
    drivedb.write(db, computer, drives, note)


def _ram_from_api(db, computer, text):
    """installed_ram over the wire is a plain amount ('640KiB') or free text, never
    a module breakdown -- that has its own grids in the GUI. A caller sending one
    replaces any note and total but leaves the fitted modules and chips alone."""
    total_kb, note = ramdb.from_string(text)
    ramdb.write(db, computer, note=note, total_kb=total_kb)


def _machine_from_api(db, asset, machine):
    """An asset's catalogue identity as the wire gives it: an object naming a
    catalogue model and any of the variations it was built in, or null to forget the
    catalogue for it.

    A key or a chip socket the catalogue does not have is refused rather than stored.
    Everything else here takes what it is given and the register keeps it -- but the
    point of a catalogue is that it is the thing being filed against, and a `sid` on
    an Amiga or a model key with a typo in it is a mistake the caller wants to hear
    about rather than a fact about anyone's hardware.
    """
    if machine is None:
        machinedb.clear(db, asset)
        return
    fields = machine.model_dump(exclude_unset=True)
    key = fields.get("model_key")
    if key and machines.model(key) is None:
        raise HTTPException(422, f"no such machine model: {key} -- "
                                 "GET /api/machines lists them")
    # Which model the chips are being checked against: the one this request sets, or
    # the one the asset is already filed as.
    against = key if key is not None else machinedb.read(db, asset)["model_key"]
    for role in {*(fields.get("chips") or {}), *(fields.get("sockets") or {})}:
        if role not in machines.roles(against):
            raise HTTPException(422, f"{against or 'a machine with no model'} has no "
                                     f"{role} socket to record a chip in")
    machinedb.write(db, asset, **fields)


def _board_from_api(db, part, machine):
    """The same for a part, which only a motherboard may have. Every other kind is
    refused rather than quietly ignored: a card or a SIMM filed as a Commodore 64 is
    a mistake the caller wants to hear about, and the register would have no way to
    show what it had been told.

    Null is the exception, because null asks for nothing to be there -- and anything
    may be asked to forget a catalogue identity it has not got."""
    if machine is not None and (part.type or "") != "motherboard":
        raise HTTPException(
            422, f"a {entry.type_label(part.type) or 'part'} cannot be a catalogue "
                 "machine -- only a motherboard is filed against the catalogue")
    _machine_from_api(db, part, machine)


def _machine_out(db, asset, identity=None):
    """An asset's catalogue identity for the wire: what is stored, plus the
    catalogue's own name for the model, or None for one that is not filed as a
    catalogue machine at all."""
    v = machinedb.read(db, asset) if identity is None else identity
    if not any(v.values()):
        return None
    m = machines.model(v["model_key"]) or {}
    return v | {"model": m.get("model", ""), "family": m.get("family", "")}


def _project_id(db, asset_id, prefetched=None):
    """The project an item is on, as a tag, or None. One of them (ADR-0016): this
    was a list of tags while a thing could be on several, and a list that can only
    ever hold one entry asks every caller to unpack a question that has one answer.

    `prefetched` is the whole page's answer in one query, which is what the list
    endpoints hand in: asking per row would be a query per machine on the page that
    would notice, the same reason machinedb.read_many exists.

    Nothing is hidden here. A private project is kept back from the public pages,
    and the API is behind the login entire -- there is nobody on this side of it to
    keep anything from."""
    found = (prefetched.get(asset_id) if prefetched is not None
             else projects.project_for(db, asset_id))
    return found.asset_id if found is not None else None


def _computer_out(db, computer, identity=None, in_projects=None):
    """One computer as the API returns it: its own columns, the catalogue identity
    read from its rows rather than from the line rendered off them, and the project
    it is on."""
    return to_dict(computer) | {
        "machine": _machine_out(db, computer, identity),
        "project": _project_id(db, computer.asset_id, in_projects)}


def _part_out(db, part, identity=None, in_projects=None):
    """One part as the API returns it. The same pieces as a computer's, and for a
    part that is not a board `machine` is simply null."""
    return to_dict(part) | {
        "machine": _machine_out(db, part, identity),
        "project": _project_id(db, part.asset_id, in_projects)}


def _check_links(db, fields):
    """A part's links must point at something that exists. The foreign keys
    refuse a bad one anyway; this says which id was wrong."""
    cid = fields.get("computer_id")
    if cid and not db.get(Computer, cid):
        raise HTTPException(404, f"no computer {cid}")
    pid = fields.get("parent_id")
    if pid and not db.get(Part, pid):
        raise HTTPException(404, f"no part {pid}")


def _work_from_api(db, fields):
    """`work_needed` / `work_project` off a create body: the jobs, and the project
    they go on, taken out of the fields on their way past.

    The project is checked here, before the item is written, and a tag that names
    nothing is a 404. Unlike the form, a caller here typed the tag -- and one that
    named a project meant that project, so filing the work somewhere else quietly
    would be a worse answer than being told. Checking first is what keeps the typo
    from leaving a half-entered machine behind it."""
    jobs = _work_lines(fields.pop("work_needed", "") or "")
    picked = (fields.pop("work_project", "") or "").strip().upper()
    project = None
    if picked:
        project = db.get(Project, picked)
        if project is None:
            raise HTTPException(404, f"projects {picked} not found")
    return jobs, project


@router.get("/api/computers", response_model=list[ComputerOut], tags=["computers"])
def api_list_computers(db: Session = Depends(get_db)):
    rows = db.query(Computer).order_by(Computer.asset_id).all()
    # One pair of queries for the whole list rather than a pair per machine, and the
    # memberships in one more for the same reason.
    identities = machinedb.read_many(db, rows)
    in_projects = projects.project_by_asset(db, [c.asset_id for c in rows])
    return [_computer_out(db, c, identities.get(c.asset_id, dict(machinedb.BLANK)),
                          in_projects)
            for c in rows]


@router.post("/api/computers", response_model=ComputerOut, tags=["computers"])
def api_create_computer(data: ComputerCreate, db: Session = Depends(get_db)):
    fields = data.model_dump()
    # Read before anything is written, so a project tag that names nothing is a 404
    # rather than a machine entered and a note dropped.
    jobs, work = _work_from_api(db, fields)
    ram = fields.pop("installed_ram", "")
    drives = fields.pop("drives", "")
    machine = data.machine
    fields.pop("machine", None)
    obj = Computer(asset_id=next_asset_id(db), **fields)
    db.add(obj)
    db.flush()
    _ram_from_api(db, obj, ram)
    _drives_from_api(db, obj, drives)
    if machine is not None:
        _machine_from_api(db, obj, machine)
    add_log(db, obj.asset_id, "created", "created")
    if jobs or work is not None:
        _take_on_work(db, obj.asset_id, jobs, work)
    db.commit()
    db.refresh(obj)
    return _computer_out(db, obj)


@router.get("/api/computers/{aid}", response_model=ComputerOut, tags=["computers"])
def api_get_computer(aid: str, db: Session = Depends(get_db)):
    obj = get_or_404(db, Computer, aid)
    return _computer_out(db, obj)


@router.patch("/api/computers/{aid}", response_model=ComputerOut, tags=["computers"])
def api_update_computer(aid: str, data: ComputerIn, db: Session = Depends(get_db)):
    obj = get_or_404(db, Computer, aid)
    fields = data.model_dump(exclude_unset=True)
    ram = fields.pop("installed_ram", None)
    drives = fields.pop("drives", None)
    # An omitted machine leaves the catalogue rows alone; an explicit null forgets
    # them. Both arrive here as None, so which was meant is read from what the
    # request set rather than from the value.
    sent_machine = "machine" in fields
    fields.pop("machine", None)
    derived = ("installed_ram", "drives", "variant")
    old = {k: getattr(obj, k) for k in fields} | {k: getattr(obj, k) for k in derived}
    for k, v in fields.items():
        setattr(obj, k, v)
    if ram is not None:
        _ram_from_api(db, obj, ram)
    if drives is not None:
        _drives_from_api(db, obj, drives)
    if sent_machine:
        _machine_from_api(db, obj, data.machine)
    new = {k: getattr(obj, k) for k in fields} | {k: getattr(obj, k) for k in derived}
    diff = _field_diffs(old, new, list(fields) + list(derived))
    # The contents follow the machine whichever door the change came in by, so
    # that the API and the GUI cannot leave the register in different states.
    n = 0
    if "disposed" in fields and bool(old["disposed"]) != bool(obj.disposed):
        if obj.disposed:
            n = _dispose_contents(db, obj)
        else:
            # A patch that clears the flag need not clear the date and note as
            # well, so the record to match the parts against is whichever of the
            # two the request left behind.
            n = _restore_contents(
                db, obj,
                old["disposed_at"] if "disposed_at" in fields else obj.disposed_at,
                old["disposed_note"] if "disposed_note" in fields else obj.disposed_note)
    if diff or n:
        add_log(db, aid, (diff + _and_parts(
            n, "went with it" if obj.disposed else "came back too")).strip())
    db.commit()
    db.refresh(obj)
    return _computer_out(db, obj)


@router.delete("/api/computers/{aid}", tags=["computers"])
def api_delete_computer(aid: str, db: Session = Depends(get_db)):
    """Delete a computer. The parts inside it are unlinked, not deleted; its
    photos, drive/memory rows and history go with it (see delete_computer). The
    API deletes any computer -- the disposed-only rule and the confirmation are
    the GUI's, where a delete is a click rather than a deliberate request."""
    obj = get_or_404(db, Computer, aid)
    return {"deleted": aid, "photos": len(delete_computer(db, obj))}


@router.get("/api/parts", response_model=list[PartOut], tags=["parts"])
def api_list_parts(computer_id: str | None = None, type: str | None = None,
                   db: Session = Depends(get_db)):
    q = db.query(Part)
    if computer_id is not None:
        q = q.filter(Part.computer_id.is_(None) if computer_id == ""
                     else Part.computer_id == computer_id)
    if type is not None:
        q = q.filter(Part.type == type)
    rows = q.order_by(Part.asset_id).all()
    identities = machinedb.read_many(db, rows)
    in_projects = projects.project_by_asset(db, [p.asset_id for p in rows])
    return [_part_out(db, p, identities.get(p.asset_id, dict(machinedb.BLANK)),
                      in_projects)
            for p in rows]


@router.post("/api/parts", response_model=PartOut, tags=["parts"])
def api_create_part(data: PartCreate, db: Session = Depends(get_db)):
    fields = data.model_dump()
    jobs, work = _work_from_api(db, fields)
    machine = fields.pop("machine")
    _check_links(db, fields)
    obj = Part(asset_id=next_asset_id(db), **fields)
    db.add(obj)
    db.flush()
    specdb.write(db, obj)
    if machine is not None:
        _board_from_api(db, obj, data.machine)
    add_log(db, obj.asset_id, "created", "created")
    if jobs or work is not None:
        _take_on_work(db, obj.asset_id, jobs, work)
    db.commit()
    db.refresh(obj)
    return _part_out(db, obj)


@router.get("/api/parts/{aid}", response_model=PartOut, tags=["parts"])
def api_get_part(aid: str, db: Session = Depends(get_db)):
    return _part_out(db, get_or_404(db, Part, aid))


@router.patch("/api/parts/{aid}", response_model=PartOut, tags=["parts"])
def api_update_part(aid: str, data: PartIn, db: Session = Depends(get_db)):
    obj = get_or_404(db, Part, aid)
    fields = data.model_dump(exclude_unset=True)
    machine = fields.pop("machine", ...)
    _check_links(db, fields)
    old = {k: getattr(obj, k) for k in fields}
    for k, v in fields.items():
        setattr(obj, k, v)
    specdb.write(db, obj)
    # After the columns are set, so a request that renames the type and files the
    # board in one go is checked against the type it is being given.
    if machine is not ...:
        _board_from_api(db, obj, data.machine)
    elif "type" in fields and obj.type != "motherboard" and obj.variant:
        # Retyped out of being a board, and the catalogue answer goes with it -- the
        # same rule the edit form follows.
        machinedb.clear(db, obj)
    new = {k: getattr(obj, k) for k in fields}
    diff = _field_diffs(old, new, list(fields), semantic_specs=True)
    if diff:
        add_log(db, aid, diff)
    db.commit()
    db.refresh(obj)
    return _part_out(db, obj)


@router.delete("/api/parts/{aid}", tags=["parts"])
def api_delete_part(aid: str, db: Session = Depends(get_db)):
    """Delete a part, with its typed spec rows, photos and history. Anything
    mounted on it is unlinked, not deleted."""
    obj = get_or_404(db, Part, aid)
    return {"deleted": aid, "photos": len(delete_part(db, obj))}
