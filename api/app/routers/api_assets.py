"""The JSON API for the things on the shelf: computers and parts.

The same rows the pages edit, read and written by something that is not a browser
-- the command-line tools and the MCP server. What it offers is the register's
shape rather than a page's: a machine with its memory, its drives and the catalogue
model it answers to, flattened into one document.
"""

from fastapi import APIRouter, Depends, HTTPException, Request
from sqlalchemy.orm import Session


# --- JSON API: parts -------------------------------------------------------

from .. import drivedb, entry, locations, machinedb, machines, projects, ramdb, specdb, tree
from ..assets import delete_computer, delete_part
from ..common import to_dict
from ..db import get_db
from ..disposal import _and_parts, _dispose_contents, _restore_contents, out_of_the_disposed
from ..forms import _field_diffs
from ..history import add_log
from ..ids import next_asset_id
from ..models import Computer, Part, Project
from ..register import get_or_404
from ..schemas import (
    BoardIn,
    ComputerCreate,
    ComputerIn,
    ComputerOut,
    MachineIn,
    PartCreate,
    PartIn,
    PartOut,
)
from ..work import _take_on_work, _work_lines

router = APIRouter()


def _drives_from_api(db: Session, computer: Computer, text: str) -> None:
    """drives over the wire is what a person would type, ';'-separated, and is
    parsed into rows the way the specs string is -- anything a segment does not
    yield is kept verbatim in drives_note."""
    drives, note = drivedb.from_string(text)
    drivedb.write(db, computer, drives, note)


def _ram_from_api(db: Session, computer: Computer, text: str) -> None:
    """installed_ram over the wire is a plain amount ('640KiB') or free text, never
    a module breakdown -- that has its own grids in the GUI. A caller sending one
    replaces any note and total but leaves the fitted modules and chips alone."""
    total_kb, note = ramdb.from_string(text)
    ramdb.write(db, computer, note=note, total_kb=total_kb)


def _machine_from_api(
    db: Session, asset: Computer | Part, machine: MachineIn | BoardIn | None
) -> None:
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
        raise HTTPException(422, f"no such machine model: {key} -- GET /api/machines lists them")
    # Which model the chips are being checked against: the one this request sets, or
    # the one the asset is already filed as.
    against = key if key is not None else machinedb.read(db, asset)["model_key"]
    for role in {*(fields.get("chips") or {}), *(fields.get("sockets") or {})}:
        if role not in machines.roles(against):
            raise HTTPException(
                422,
                f"{against or 'a machine with no model'} has no {role} socket to record a chip in",
            )
    machinedb.write(db, asset, **fields)


def _board_from_api(db: Session, part: Part, machine: BoardIn | None) -> None:
    """The same for a part, which only a motherboard may have. Every other kind is
    refused rather than quietly ignored: a card or a SIMM filed as a Commodore 64 is
    a mistake the caller wants to hear about, and the register would have no way to
    show what it had been told.

    Null is the exception, because null asks for nothing to be there -- and anything
    may be asked to forget a catalogue identity it has not got."""
    if machine is not None and (part.type or "") != "motherboard":
        raise HTTPException(
            422,
            f"a {entry.type_label(part.type) or 'part'} cannot be a catalogue "
            "machine -- only a motherboard is filed against the catalogue",
        )
    _machine_from_api(db, part, machine)


def _machine_out(
    db: Session, asset: Computer | Part, identity: machinedb.Identity | None = None
) -> dict[str, object] | None:
    """An asset's catalogue identity for the wire: what is stored, plus the
    catalogue's own name for the model, or None for one that is not filed as a
    catalogue machine at all."""
    v = machinedb.read(db, asset) if identity is None else identity
    if not any(v.values()):
        return None
    m = machines.model(v["model_key"])
    return v | {"model": m["model"] if m else "", "family": m["family"] if m else ""}


def _project_id(
    db: Session, asset_id: str, prefetched: dict[str, Project] | None = None
) -> str | None:
    """The project an item is on, as a tag, or None. One of them (ADR-0016): this
    was a list of tags while a thing could be on several, and a list that can only
    ever hold one entry asks every caller to unpack a question that has one answer.

    `prefetched` is the whole page's answer in one query, which is what the list
    endpoints hand in: asking per row would be a query per machine on the page that
    would notice, the same reason machinedb.read_many exists.

    Nothing is hidden here. A private project is kept back from the public pages,
    and the API is behind the login entire -- there is nobody on this side of it to
    keep anything from."""
    found = (
        prefetched.get(asset_id) if prefetched is not None else projects.project_for(db, asset_id)
    )
    return found.asset_id if found is not None else None


def _where_out(thing: Computer | Part, places: locations.Tree, r: tree.Tree) -> dict[str, object]:
    """Where a thing is, for the wire, read off the one link it has (ADR-0036): the
    location it is kept in, with its path as words, and for a part the machine it
    is fitted in or the part it is mounted on. At most one of the three is set,
    because a thing is in one place. A part fitted in a machine has no location of
    its own -- the API is the record, and the record is that it is in the machine."""
    holder = r.holder(thing.asset_id.upper())
    what = r.what(holder)
    out: dict[str, object] = {
        "location": holder if what == tree.LOCATION else "",
        "location_path": places.text(holder) if what == tree.LOCATION else "",
    }
    if isinstance(thing, Part):
        out["computer_id"] = holder if what == tree.COMPUTER else None
        out["parent_id"] = holder if what == tree.PART else None
    return out


def _computer_out(
    db: Session,
    computer: Computer,
    identity: machinedb.Identity | None = None,
    in_projects: dict[str, Project] | None = None,
    places: locations.Tree | None = None,
    r: tree.Tree | None = None,
) -> dict[str, object]:
    """One computer as the API returns it: its own columns, the catalogue identity
    read from its rows rather than from the line rendered off them, the project it
    is on, and where it is kept."""
    return (
        to_dict(computer)
        | {
            "machine": _machine_out(db, computer, identity),
            "project": _project_id(db, computer.asset_id, in_projects),
        }
        | _where_out(computer, places or locations.tree(db), r or tree.load(db))
    )


def _part_out(
    db: Session,
    part: Part,
    identity: machinedb.Identity | None = None,
    in_projects: dict[str, Project] | None = None,
    places: locations.Tree | None = None,
    r: tree.Tree | None = None,
) -> dict[str, object]:
    """One part as the API returns it. The same pieces as a computer's, and for a
    part that is not a board `machine` is simply null."""
    return (
        to_dict(part)
        | {
            "machine": _machine_out(db, part, identity),
            "project": _project_id(db, part.asset_id, in_projects),
        }
        | _where_out(part, places or locations.tree(db), r or tree.load(db))
    )


def _locate(db: Session, thing: Computer | Part, sent: object, who: str) -> None:
    """`location` off a body: a tag, or a name -- one location's, or a new one's at
    the top when it names none -- and the move recorded as made through the API.

    A name that names more than one location is refused with the tags it could have
    meant, rather than guessed at: a caller that typed `Box 14` meant a box, and
    the register cannot tell which."""
    places = locations.tree(db)
    try:
        found = locations.choose(db, sent if isinstance(sent, str) else "", places)
        tree.put(db, thing, found.asset_id if found else None, tree.API, who)
    except tree.Refused as err:
        raise HTTPException(422, str(err)) from err


def _fit(db: Session, part: Part, fields: dict[str, object], who: str) -> bool:
    """`computer_id` and `parent_id` off a body, acted on: the part moved into the
    machine or onto the part named, as a move made through the API, or -- for an
    explicit blank -- taken out of whatever machine or card it is in (ADR-0036).
    Mounted on wins over fitted in when both are sent, as the upgrade read them.
    Whether either was sent, which is what decides that a `location` beside them is
    not used: the machine wins."""
    if "computer_id" not in fields and "parent_id" not in fields:
        return False
    sent = fields.get("parent_id") or fields.get("computer_id")
    into = sent.upper() if isinstance(sent, str) and sent else None
    r = tree.load(db)
    try:
        if into is not None:
            tree.put(db, part, into, tree.API, who, r)
        elif r.what(r.holder(part.asset_id.upper())) in (tree.COMPUTER, tree.PART):
            tree.put(db, part, None, tree.API, who, r)
    except tree.Refused as err:
        raise HTTPException(422, str(err)) from err
    return into is not None


def _tick(obj: Computer | Part, fields: dict[str, object]) -> None:
    """`location_public` off a body: set when sent, and when it is null or left out of
    a create, the default -- what Show locations says a new thing starts with."""
    sent = fields.pop("location_public", None)
    if isinstance(sent, bool):
        obj.location_public = sent


def _fitted_in(r: tree.Tree, part: Part) -> str:
    """The machine a part is directly fitted in, or "": its `computer_id` on the wire."""
    holder = r.holder(part.asset_id.upper())
    return holder if holder and r.what(holder) == tree.COMPUTER else ""


def _require_gone(obj: Computer | Part, noun: str) -> None:
    """The page's rule, at the API's door too (ADR-0036): something still in the
    collection is disposed of before it is deleted, because deleting it now takes
    everything inside it, and one call from a script should not be able to empty a
    working machine of its cards."""
    if not obj.disposed:
        raise HTTPException(
            409,
            f"{obj.asset_id} is still in the collection. Dispose of the {noun} first: "
            "deleting it deletes everything inside it.",
        )


def _check_links(db: Session, fields: dict[str, object]) -> None:
    """A part's links must point at something that exists. The foreign keys
    refuse a bad one anyway; this says which id was wrong."""
    cid = fields.get("computer_id")
    if cid and not db.get(Computer, cid):
        raise HTTPException(404, f"no computer {cid}")
    pid = fields.get("parent_id")
    if pid and not db.get(Part, pid):
        raise HTTPException(404, f"no part {pid}")


def _work_from_api(db: Session, fields: dict[str, object]) -> tuple[list[str], Project | None]:
    """`work_needed` / `work_project` off a create body: the jobs, and the project
    they go on, taken out of the fields on their way past.

    The project is checked here, before the item is written, and a tag that names
    nothing is a 404. Unlike the form, a caller here typed the tag -- and one that
    named a project meant that project, so filing the work somewhere else quietly
    would be a worse answer than being told. Checking first is what keeps the typo
    from leaving a half-entered machine behind it."""
    # The fields are a body's model_dump, so they are typed as widely as the body
    # is; both of these are declared str on WorkIn and are checked rather than
    # assumed, an absent one reading as blank exactly as a null one does.
    needed = fields.pop("work_needed", "")
    tag = fields.pop("work_project", "")
    jobs = _work_lines(needed if isinstance(needed, str) else "")
    picked = (tag if isinstance(tag, str) else "").strip().upper()
    project = None
    if picked:
        project = db.get(Project, picked)
        if project is None:
            raise HTTPException(404, f"projects {picked} not found")
    return jobs, project


@router.get("/api/computers", response_model=list[ComputerOut], tags=["computers"])
def api_list_computers(db: Session = Depends(get_db)) -> list[dict[str, object]]:
    rows = db.query(Computer).order_by(Computer.asset_id).all()
    # One pair of queries for the whole list rather than a pair per machine, and the
    # memberships in one more for the same reason.
    identities = machinedb.read_many(db, rows)
    in_projects = projects.project_by_asset(db, [c.asset_id for c in rows])
    places, r = locations.tree(db), tree.load(db)
    return [
        _computer_out(
            db, c, identities.get(c.asset_id, machinedb.BLANK.copy()), in_projects, places, r
        )
        for c in rows
    ]


@router.post("/api/computers", response_model=ComputerOut, tags=["computers"])
def api_create_computer(
    data: ComputerCreate, request: Request, db: Session = Depends(get_db)
) -> dict[str, object]:
    fields = data.model_dump()
    where = fields.pop("location", "")
    # Read before anything is written, so a project tag that names nothing is a 404
    # rather than a machine entered and a note dropped.
    jobs, work = _work_from_api(db, fields)
    ram = fields.pop("installed_ram", "")
    drives = fields.pop("drives", "")
    machine = data.machine
    fields.pop("machine", None)
    tick = fields.pop("location_public", None)
    obj = Computer(asset_id=next_asset_id(db), **fields)
    _tick(obj, {"location_public": tick})
    db.add(obj)
    db.flush()
    _ram_from_api(db, obj, ram)
    _drives_from_api(db, obj, drives)
    if machine is not None:
        _machine_from_api(db, obj, machine)
    add_log(db, obj.asset_id, "created", "created")
    _locate(db, obj, where, request.state.principal.username)
    if jobs or work is not None:
        _take_on_work(db, obj.asset_id, jobs, work)
    db.commit()
    db.refresh(obj)
    return _computer_out(db, obj)


@router.get("/api/computers/{aid}", response_model=ComputerOut, tags=["computers"])
def api_get_computer(aid: str, db: Session = Depends(get_db)) -> dict[str, object]:
    obj = get_or_404(db, Computer, aid)
    return _computer_out(db, obj)


@router.patch("/api/computers/{aid}", response_model=ComputerOut, tags=["computers"])
def api_update_computer(
    aid: str, data: ComputerIn, request: Request, db: Session = Depends(get_db)
) -> dict[str, object]:
    obj = get_or_404(db, Computer, aid)
    fields = data.model_dump(exclude_unset=True)
    where = fields.pop("location", None)
    ram = fields.pop("installed_ram", None)
    drives = fields.pop("drives", None)
    # An omitted machine leaves the catalogue rows alone; an explicit null forgets
    # them. Both arrive here as None, so which was meant is read from what the
    # request set rather than from the value.
    sent_machine = "machine" in fields
    fields.pop("machine", None)
    _tick(obj, fields)
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
                db,
                obj,
                old["disposed_at"] if "disposed_at" in fields else obj.disposed_at,
                old["disposed_note"] if "disposed_note" in fields else obj.disposed_note,
            )
    if diff or n:
        add_log(
            db,
            aid,
            (diff + _and_parts(n, "went with it" if obj.disposed else "came back too")).strip(),
        )
    if where is not None:
        _locate(db, obj, where, request.state.principal.username)
    db.commit()
    db.refresh(obj)
    return _computer_out(db, obj)


# response_model=None: the annotation is for the type checker. FastAPI would
# otherwise publish it as the response's shape, which the pinned contract
# (ADR-0010) leaves open.
@router.delete("/api/computers/{aid}", tags=["computers"], response_model=None)
def api_delete_computer(aid: str, db: Session = Depends(get_db)) -> dict[str, object]:
    """Delete a computer that has been disposed of, and everything inside it, all the
    way down: its parts, their photos, drive/memory rows and history (see
    delete_computer). One still in the collection is refused with 409, as the page
    refuses it (ADR-0036)."""
    obj = get_or_404(db, Computer, aid)
    _require_gone(obj, "machine")
    return {"deleted": aid, "photos": len(delete_computer(db, obj))}


@router.get("/api/parts", response_model=list[PartOut], tags=["parts"])
def api_list_parts(
    computer_id: str | None = None, type: str | None = None, db: Session = Depends(get_db)
) -> list[dict[str, object]]:
    q = db.query(Part)
    if type is not None:
        q = q.filter(Part.type == type)
    rows = q.order_by(Part.asset_id).all()
    places, r = locations.tree(db), tree.load(db)
    if computer_id is not None:
        # As the field reads: the machine a part is fitted in, "" for none.
        rows = [p for p in rows if _fitted_in(r, p) == computer_id.upper()]
    identities = machinedb.read_many(db, rows)
    in_projects = projects.project_by_asset(db, [p.asset_id for p in rows])
    return [
        _part_out(db, p, identities.get(p.asset_id, machinedb.BLANK.copy()), in_projects, places, r)
        for p in rows
    ]


@router.post("/api/parts", response_model=PartOut, tags=["parts"])
def api_create_part(
    data: PartCreate, request: Request, db: Session = Depends(get_db)
) -> dict[str, object]:
    fields = data.model_dump()
    where = fields.pop("location", "")
    jobs, work = _work_from_api(db, fields)
    machine = fields.pop("machine")
    _check_links(db, fields)
    links: dict[str, object] = {k: fields.pop(k) for k in ("computer_id", "parent_id")}
    tick = fields.pop("location_public", None)
    obj = Part(asset_id=next_asset_id(db), **fields)
    _tick(obj, {"location_public": tick})
    db.add(obj)
    db.flush()
    specdb.write(db, obj)
    if machine is not None:
        _board_from_api(db, obj, data.machine)
    add_log(db, obj.asset_id, "created", "created")
    who = request.state.principal.username
    # A thing is in one place: one sent into a machine or onto a part goes there, and
    # a location sent beside that is not used -- the machine wins (ADR-0036).
    if not _fit(db, obj, {k: v for k, v in links.items() if v}, who):
        _locate(db, obj, where, who)
    if jobs or work is not None:
        _take_on_work(db, obj.asset_id, jobs, work)
    db.commit()
    db.refresh(obj)
    return _part_out(db, obj)


@router.get("/api/parts/{aid}", response_model=PartOut, tags=["parts"])
def api_get_part(aid: str, db: Session = Depends(get_db)) -> dict[str, object]:
    return _part_out(db, get_or_404(db, Part, aid))


@router.patch("/api/parts/{aid}", response_model=PartOut, tags=["parts"])
def api_update_part(
    aid: str, data: PartIn, request: Request, db: Session = Depends(get_db)
) -> dict[str, object]:
    obj = get_or_404(db, Part, aid)
    fields = data.model_dump(exclude_unset=True)
    where = fields.pop("location", None)
    machine = fields.pop("machine", ...)
    _check_links(db, fields)
    links: dict[str, object] = {
        k: fields.pop(k) for k in ("computer_id", "parent_id") if k in fields
    }
    _tick(obj, fields)
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
    # What is mounted on it follows it out and back, as a machine's parts do.
    n = 0
    if "disposed" in fields and bool(old["disposed"]) != bool(obj.disposed):
        if obj.disposed:
            n = _dispose_contents(db, obj)
        else:
            n = _restore_contents(
                db,
                obj,
                old["disposed_at"] if "disposed_at" in fields else obj.disposed_at,
                old["disposed_note"] if "disposed_note" in fields else obj.disposed_note,
            )
    if diff or n:
        add_log(
            db,
            aid,
            (diff + _and_parts(n, "went with it" if obj.disposed else "came back too")).strip(),
        )
    who = request.state.principal.username
    if "disposed" in fields and not obj.disposed:
        out_of_the_disposed(db, obj, who)
    fitted = _fit(db, obj, links, who)
    if where is not None and not fitted:
        _locate(db, obj, where, who)
    db.commit()
    db.refresh(obj)
    return _part_out(db, obj)


# response_model=None, as above: the annotation is for the type checker.
@router.delete("/api/parts/{aid}", tags=["parts"], response_model=None)
def api_delete_part(aid: str, db: Session = Depends(get_db)) -> dict[str, object]:
    """Delete a part that has been disposed of, with its typed spec rows, photos and
    history, and everything mounted on it, all the way down. One still in the
    collection is refused with 409, as for a machine (ADR-0036)."""
    obj = get_or_404(db, Part, aid)
    _require_gone(obj, "part")
    return {"deleted": aid, "photos": len(delete_part(db, obj))}
