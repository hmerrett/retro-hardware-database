"""Retro Hardware Database — FastAPI backend.

Two surfaces over the same MariaDB:
  * JSON API under /api  (used by scripts, the MCP wrapper, and the GUI)
  * a bespoke server-rendered GUI that mirrors the flat-file add.py workflow:
    the guided build walk (computer -> link/create motherboard -> parts by
    category), storage-kind routing, CPU/RAM as computer fields, photo upload,
    a disposed toggle, print-label PDFs, and a searchable/filterable index.

Interactive API docs live at /docs (OpenAPI).
"""
from datetime import date
from urllib.parse import parse_qs

from fastapi import (Depends, FastAPI, HTTPException, Request)
from fastapi.responses import (JSONResponse)
from fastapi.staticfiles import StaticFiles
from sqlalchemy import text
from sqlalchemy.orm import Session

from . import __version__
from . import (drivedb, entry, machinedb, machines,
               projects, ramdb, specdb)
from .common import (  # shared foundations; re-exported here so existing call-sites resolve
    BRANDING_DIR, IMAGES_DIR, STATIC_DIR, to_dict)
from .common import _all_years  # noqa: F401 -- re-exported for the tests, unused here
from .db import get_db
from .assets import delete_computer, delete_part
from .routers import (catalogue, computers as computer_pages, files as file_pages,
                      images, items, parts as part_pages,
                      projects as project_pages, seo)
from .work import (_api_task, _asset_named, _member_log, _publish_log, _take_on_work,
                   _task_asset, _work_lines)
from . import auth
from .routers import gallery
from .routers import stats as stats_routes
from .common import (  # noqa: F401 -- re-exported for the tests, unused here
    RELIABILITY_MIN, _maker_reliability, branded)
from .pages import _answers_given  # noqa: F401 -- re-exported for the tests
from .photos import (  # noqa: F401 -- re-exported for the tests, unused here
    detect_images, has_original, img_url, pick_images, tuned_photos)
from .web import templates  # noqa: F401 -- re-exported for the tests, unused here
from .ids import next_asset_id
from .stats import FACTS_SHOWN, _collection_stats, _facts, _facts_projects, _facts_register  # noqa: F401
from .disposal import (  # disposing of a thing, and what goes with it
    _and_parts, _dispose_contents, _restore_contents)
from .forms import _field_diffs  # what was typed -> what a column holds
from .register import (  # the register as one thing: a computer and a part in one id space
    get_or_404)
from .history import (  # the change log: writing a line and reading them back
    _short, add_log)
from .photos import (  # photo/image helpers, lifted out of this module
    _drop_log_photos, _purge_photos)
from .photos import (  # noqa: F401 -- re-exported for the tests, unused here
    WM_CACHE, WM_SRC, WM_SCALE, WM_MIN_PX, WM_BUILD, _watermarked_file, _wm_forget,
    _is_own_photo, _image_size, _ref_sidecar, _write_atomically, _original_of,
)
from .search import search_terms  # noqa: F401 -- re-exported for the tests, unused here
from .models import (Computer, LogEntry, Part, Project, ProjectOrder, ProjectTask)
from .schemas import (ComputerCreate, ComputerIn, ComputerOut, PartCreate,
                      PartIn, PartOut, ProjectIn, ProjectItemIn, ProjectOrderIn,
                      ProjectOrderOut, ProjectOut, ProjectTaskIn, ProjectTaskOut)

# Schema is owned by Alembic now (entrypoint.sh runs `alembic upgrade head` on
# start); no create_all here.

app = FastAPI(title="Retro Hardware Database API", version=__version__)


@app.middleware("http")
async def no_stale_pages(request: Request, call_next):
    """Every page, freshly asked for.

    The pages carried no cache headers at all, and a response with neither
    freshness nor a validator is one a browser may cache for as long as it
    likes -- Safari does, and does it hardest on a phone. The site was
    deployed, the code was on the server, and the reader had yesterday's
    Javascript. `no-cache` is not "do not store": it is "ask me first", which
    is what a page whose whole point is that it changes wants.

    Only the pages. Photographs and static files carry their own headers, and
    those say the opposite on purpose -- they are stamped with a version, so
    they may be kept for a year (see `img_url` and `_static_headers`).
    """
    response = await call_next(request)
    if response.headers.get("content-type", "").startswith("text/html"):
        response.headers.setdefault("Cache-Control", "no-cache")
    return response


# Registered after no_stale_pages and so outside it, which is the order the two
# decorators gave when both lived here: the gate runs first on the way in and last
# on the way out.
app.middleware("http")(auth.auth_gate)
app.include_router(auth.router)







# Whether a project is one of the private ones, asked as a query rather than as a
# column filter. This replaced PRIVATE_COLUMNS, which kept two columns of an
# otherwise public record back from a visitor; a project is private as a whole or
# not at all, so what is hidden is the row, and hiding a row is done where rows are
# chosen rather than where their fields are read.
#
# Five places, and it is only private with all five shut: the list leaves them out,
# the project's own page refuses them, the search and the suggestion list drop them,
# the sitemap does not name them, and the panel on an item's page does not say the
# item is wanted for one. Miss any one and the other four are decoration.


# Container paths by default (the `images` volume and the goaccess report mount);
# overridable so the app can be imported and run outside Docker for local
# development, which the hardcoded absolute paths used to make impossible.





@app.get("/healthz", include_in_schema=False)
def healthz(db: Session = Depends(get_db)):
    """Liveness plus database reachability, for a deploy's smoke check and any
    uptime monitor. Deliberately public and content-free: it says up or down and
    nothing else, so it needs no login and gives nothing away.

    It touches the database rather than only answering, because a box that is up
    but cannot reach MariaDB serves nothing but errors, and a check that called
    that healthy would let a broken deploy through."""
    try:
        db.execute(text("SELECT 1"))
    except Exception:
        return JSONResponse({"status": "unhealthy"}, status_code=503)
    return {"status": "ok"}







class _CachedStatic(StaticFiles):
    """The static files, with a Cache-Control on them.

    StaticFiles sends an ETag and a Last-Modified and no Cache-Control at all,
    which means the browser asks about every one of them on every page: ten
    conditional requests for the logo, the icons and the placeholder drawings,
    each answered 304 Not Modified, each a round trip. On a phone on a slow link
    that is most of what a second page view costs.

    Every one of them is linked with ?v=<hash of the file>, so the URL already
    says which version it wants and cannot go stale -- change the file and the
    markup asks for a different URL. Those may be kept for a year and never asked
    about again. A request without the stamp is somebody typing the path, and
    keeps a short life so it cannot pin an old copy in a cache for a year.
    """

    def file_response(self, full_path, stat_result, scope, status_code=200):
        response = super().file_response(full_path, stat_result, scope, status_code)
        query = parse_qs(scope.get("query_string", b"").decode("latin-1"))
        response.headers["Cache-Control"] = (
            "public, max-age=31536000, immutable" if query.get("v")
            else "public, max-age=3600")
        return response


for sub in ("computers", "parts"):
    (IMAGES_DIR / sub).mkdir(parents=True, exist_ok=True)
_static = _CachedStatic(directory=str(STATIC_DIR))
# The deployment's own artwork first, the shipped placeholders behind it. This is
# StaticFiles' own search list, so a name that is not overridden falls through to
# what ships, and the traversal checks are the ones it already makes on every
# request -- a directory in front of another is exactly what `packages` does.
if BRANDING_DIR.is_dir():
    _static.all_directories = [str(BRANDING_DIR), *_static.all_directories]
app.mount("/static", _static, name="static")





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


@app.get("/api/computers", response_model=list[ComputerOut], tags=["computers"])
def api_list_computers(db: Session = Depends(get_db)):
    rows = db.query(Computer).order_by(Computer.asset_id).all()
    # One pair of queries for the whole list rather than a pair per machine, and the
    # memberships in one more for the same reason.
    identities = machinedb.read_many(db, rows)
    in_projects = projects.project_by_asset(db, [c.asset_id for c in rows])
    return [_computer_out(db, c, identities.get(c.asset_id, dict(machinedb.BLANK)),
                          in_projects)
            for c in rows]


@app.post("/api/computers", response_model=ComputerOut, tags=["computers"])
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


@app.get("/api/computers/{aid}", response_model=ComputerOut, tags=["computers"])
def api_get_computer(aid: str, db: Session = Depends(get_db)):
    obj = get_or_404(db, Computer, aid)
    return _computer_out(db, obj)


@app.patch("/api/computers/{aid}", response_model=ComputerOut, tags=["computers"])
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


@app.delete("/api/computers/{aid}", tags=["computers"])
def api_delete_computer(aid: str, db: Session = Depends(get_db)):
    """Delete a computer. The parts inside it are unlinked, not deleted; its
    photos, drive/memory rows and history go with it (see delete_computer). The
    API deletes any computer -- the disposed-only rule and the confirmation are
    the GUI's, where a delete is a click rather than a deliberate request."""
    obj = get_or_404(db, Computer, aid)
    return {"deleted": aid, "photos": len(delete_computer(db, obj))}


# --- JSON API: parts -------------------------------------------------------

@app.get("/api/parts", response_model=list[PartOut], tags=["parts"])
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


def _check_links(db, fields):
    """A part's links must point at something that exists. The foreign keys
    refuse a bad one anyway; this says which id was wrong."""
    cid = fields.get("computer_id")
    if cid and not db.get(Computer, cid):
        raise HTTPException(404, f"no computer {cid}")
    pid = fields.get("parent_id")
    if pid and not db.get(Part, pid):
        raise HTTPException(404, f"no part {pid}")


@app.post("/api/parts", response_model=PartOut, tags=["parts"])
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


@app.get("/api/parts/{aid}", response_model=PartOut, tags=["parts"])
def api_get_part(aid: str, db: Session = Depends(get_db)):
    return _part_out(db, get_or_404(db, Part, aid))


@app.patch("/api/parts/{aid}", response_model=PartOut, tags=["parts"])
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


@app.delete("/api/parts/{aid}", tags=["parts"])
def api_delete_part(aid: str, db: Session = Depends(get_db)):
    """Delete a part, with its typed spec rows, photos and history. Anything
    mounted on it is unlinked, not deleted."""
    obj = get_or_404(db, Part, aid)
    return {"deleted": aid, "photos": len(delete_part(db, obj))}















# --- deleting a record for good ---------------------------------------------
# Disposal says an item has left the collection and keeps its record; this is the
# other thing, for when the record itself should not exist -- a duplicate, a
# mistake, something scrapped that was never worth a line. Only a disposed item
# can be deleted through the GUI, so the ordinary way to lose something is still
# the reversible one.
#
# Everything pointing at the asset is cleared before its own row goes, rather
# than leaving it to the foreign keys. Three reasons: what another item's history
# should say about losing its link is a judgement no cascade can make; the
# confirmation page can only promise what this code actually does; and the
# cascades are MariaDB's, while the tests run on SQLite, where they hold only
# while a PRAGMA does.

























# --- QR target: one stable /items/<id> URL for either kind ------------------








# --- GUI: computers --------------------------------------------------------








































# --- detaching the board: the moment a description becomes an object ---------
#
# A machine the catalogue names is one object, and the board inside it is part of
# the description of that object: the board issue and the chips in its sockets are
# answers the machine gives about itself. Lift the board out and put it on a shelf
# and that stops being true -- it is now a thing that can be photographed, tagged,
# swapped into another machine and sold on its own, which is the register's whole
# test for what deserves an asset id. So this verb is the moment of physical
# separation written down, and nothing here happens speculatively: no machine grows
# a board object because the catalogue says it has one.
#
# What moves is exactly what stops being true of the machine. The board issue and
# the chips go, because they were always facts about the board. The model key is
# copied rather than moved -- the machine is still a Spectrum and the board is a
# Spectrum board -- and the style and the region stay behind, because a case and a
# market are facts about the assembled machine and a board has neither.
#
# One way only. Refitting a board, to this machine or to another, is setting
# computer_id like any other part: there is no re-absorb that would fold the object
# back into a description, because the object exists now and pretending otherwise
# would mean deleting a tagged, photographed thing.
#
# Two open questions, left open rather than guessed at:
#
#   * The memory tables (computer_ram_module, computer_ram_chip) are keyed to the
#     computer and stay there. DRAM soldered to the board arguably went with it,
#     but those rows count chips rather than identify them, they are half of how a
#     machine's installed RAM is rendered, and a machine that lost its memory
#     figure by having its board tagged would be a worse record than one whose
#     memory row is filed a level up. Deciding it needs a look at how a refitted
#     board should read, which nothing has asked for yet.
#   * A board detached and then unlinked leaves the machine looking detachable
#     again, and pressing it a second time would put a second object on the shelf
#     where there is one piece of hardware. The register cannot tell an empty case
#     from an unopened one -- both hold no board -- and the person holding the
#     machine can, so the guard below is the one it can make honestly and the
#     history says what happened either way.









# --- the GUI's delete, with its safety net ----------------------------------























# --- writing the history, and hanging photographs on it ----------------------
# A note and its photographs go in one gesture, because the entry's message is
# their caption and writing the caption is the same act as choosing them. The two
# routes below are the other half: a photograph for an entry that is already
# written -- the swap the register logged last week, photographed when the lid next
# came off -- and taking one back off again.
#
# Those two are under /items/, not under /computers/ or /parts/, because a history
# entry belongs to an asset id from the shared register rather than to either
# table, which is the whole reason log_entry has no foreign key. /items/<id> is
# already the register-wide address the QR codes print and the JSON log is read
# from. They are POSTs, so the auth gate has them whatever the prefix.




































# --- GUI: parts (guided, typed entry) --------------------------------------





































































































# --- files kept beside the register -----------------------------------------
# Drivers, manuals, ROM dumps. Not hung off an asset id: a file is attached to what
# it is for, which is a model as often as it is a unit -- one driver for the three
# identical cards on the shelf and the fourth bought next year (ADR-0006,
# ADR-0020). app/filesdb.py owns the links and the bytes; these are the things a
# person does with one, of which publishing is its own, since a file is kept back
# from visitors until somebody says otherwise (ADR-0009).




























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


















# --- work noted while checking something in -----------------------------------
# The quick box above is this gesture from a page that already exists. What follows
# is the same one from the two forms that make a page, which is where the thought
# actually arrives: what is wrong with a machine is seen while it is being unpacked,
# and the form that files it is on screen at the time. Asking for the item's tag
# first meant the note had to wait for a second visit to a page that did not exist
# yet, and a note that waits is a note that is lost -- which is the whole reason the
# flag on an item existed before 0031, and the reason this is not simply the quick
# box again.










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


# --- the jobs, and the things on order ---------------------------------------






















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

PROJECT_TAGS = ["projects"]


def _project_out(db, p):
    """A project as it reads back: its own columns, the status in words, and its
    three lists. Four queries whatever it holds."""
    return to_dict(p) | {
        "status_label": projects.status_label(p.status),
        "items": [{"asset_id": obj.asset_id, "kind": kind,
                   "name": entry.display_name(to_dict(obj)), "note": row.note}
                  for kind, obj, row in projects.members(db, p.asset_id)],
        "tasks": projects.tasks(db, p.asset_id),
        "orders": projects.orders(db, p.asset_id),
    }


def _api_project(db, aid):
    return get_or_404(db, Project, aid)




def _api_order(db, p, oid):
    row = db.get(ProjectOrder, oid)
    if row is None or row.project_id != p.asset_id:
        raise HTTPException(404, f"no order {oid} in {p.asset_id}")
    return row


@app.get("/api/projects", response_model=list[ProjectOut], tags=PROJECT_TAGS)
def api_list_projects(status: str | None = None, open: bool | None = None,
                      db: Session = Depends(get_db)):
    """Every project, with what each is about, what is to be done and what is on
    order. `status` narrows it to one state; `open=true` to the ones not finished
    or abandoned, which is the question a list of projects is usually asked."""
    q = db.query(Project)
    if status:
        q = q.filter(Project.status == status)
    if open is not None:
        q = (q.filter(Project.status.notin_(projects.CLOSED)) if open
             else q.filter(Project.status.in_(projects.CLOSED)))
    return [_project_out(db, p) for p in q.order_by(Project.name,
                                                    Project.asset_id).all()]


@app.post("/api/projects", response_model=ProjectOut, tags=PROJECT_TAGS)
def api_create_project(data: ProjectIn, db: Session = Depends(get_db)):
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


@app.get("/api/projects/{aid}", response_model=ProjectOut, tags=PROJECT_TAGS)
def api_get_project(aid: str, db: Session = Depends(get_db)):
    return _project_out(db, _api_project(db, aid))


@app.patch("/api/projects/{aid}", response_model=ProjectOut, tags=PROJECT_TAGS)
def api_update_project(aid: str, data: ProjectIn, db: Session = Depends(get_db)):
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


@app.delete("/api/projects/{aid}", tags=PROJECT_TAGS)
def api_delete_project(aid: str, db: Session = Depends(get_db)):
    """Delete a project. Its tasks, orders and memberships go with it by the
    foreign key; its history goes by hand, log_entry having nothing to cascade
    from. The hardware it was about is untouched -- deleting the plan is not
    disposing of the machine."""
    p = _api_project(db, aid)
    photos = _drop_log_photos(db, aid)
    db.query(LogEntry).filter(LogEntry.asset_id == aid).delete(
        synchronize_session=False)
    db.delete(p)
    db.commit()
    _purge_photos(photos)
    return {"deleted": aid, "photos": len(photos)}


# --- JSON API: what a project is about ---------------------------------------


@app.post("/api/projects/{aid}/items", response_model=ProjectOut, tags=PROJECT_TAGS)
def api_project_add_item(aid: str, data: ProjectItemIn,
                         db: Session = Depends(get_db)):
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


@app.delete("/api/projects/{aid}/items/{asset_id}", response_model=ProjectOut,
            tags=PROJECT_TAGS)
def api_project_drop_item(aid: str, asset_id: str, db: Session = Depends(get_db)):
    p = _api_project(db, aid)
    asset_id = (asset_id or "").strip().upper()
    if projects.drop_asset(db, aid, asset_id):
        add_log(db, aid, f"let go of {_asset_named(db, asset_id)}")
        _member_log(db, p, asset_id, joining=False)
        db.commit()
    return _project_out(db, p)


# --- JSON API: the jobs and the things on order ------------------------------


@app.post("/api/projects/{aid}/tasks", response_model=ProjectTaskOut,
          tags=PROJECT_TAGS)
def api_project_add_task(aid: str, data: ProjectTaskIn,
                         db: Session = Depends(get_db)):
    p = _api_project(db, aid)
    text = (data.text or "").strip()
    if not text:
        raise HTTPException(422, "a task needs something written in it")
    db.add(row := ProjectTask(project_id=p.asset_id, text=text,
                              done=bool(data.done),
                              asset_id=_task_asset(db, p.asset_id, data.asset_id)))
    if row.done:
        row.done_at = date.today()
    add_log(db, aid, f"to do: {_short(text)}")
    db.commit()
    db.refresh(row)
    return row


@app.patch("/api/projects/{aid}/tasks/{tid}", response_model=ProjectTaskOut,
           tags=PROJECT_TAGS)
def api_project_update_task(aid: str, tid: int, data: ProjectTaskIn,
                            db: Session = Depends(get_db)):
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
            add_log(db, aid, ("done: " if row.done else "back on the list: ")
                    + _short(row.text))
    if "asset_id" in fields:
        before = row.asset_id
        row.asset_id = _task_asset(db, p.asset_id, fields["asset_id"])
        if before != row.asset_id:
            add_log(db, aid, (f"{_short(row.text)}: about "
                              f"{_asset_named(db, row.asset_id)}" if row.asset_id
                              else f"{_short(row.text)}: about no one thing"))
    db.commit()
    db.refresh(row)
    return row


@app.delete("/api/projects/{aid}/tasks/{tid}", tags=PROJECT_TAGS)
def api_project_delete_task(aid: str, tid: int, db: Session = Depends(get_db)):
    p = _api_project(db, aid)
    row = _api_task(db, p, tid)
    add_log(db, aid, f"dropped: {_short(row.text)}")
    db.delete(row)
    db.commit()
    return {"deleted": tid}


@app.post("/api/projects/{aid}/orders", response_model=ProjectOrderOut,
          tags=PROJECT_TAGS)
def api_project_add_order(aid: str, data: ProjectOrderIn,
                          db: Session = Depends(get_db)):
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
    row = ProjectOrder(project_id=p.asset_id, **(fields | {
        "description": description,
        "ordered_at": fields.get("ordered_at") or date.today(),
        "delivered": delivered,
        "delivered_at": date.today() if delivered else None}))
    db.add(row)
    add_log(db, aid, f"ordered {_short(description)}"
            + (f" from {row.supplier}" if row.supplier else ""))
    db.commit()
    db.refresh(row)
    return row


@app.patch("/api/projects/{aid}/orders/{oid}", response_model=ProjectOrderOut,
           tags=PROJECT_TAGS)
def api_project_update_order(aid: str, oid: int, data: ProjectOrderIn,
                             db: Session = Depends(get_db)):
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
        add_log(db, aid, ("arrived: " if row.delivered else "still coming: ")
                + _short(row.description))
    db.commit()
    db.refresh(row)
    return row


@app.delete("/api/projects/{aid}/orders/{oid}", tags=PROJECT_TAGS)
def api_project_delete_order(aid: str, oid: int, db: Session = Depends(get_db)):
    p = _api_project(db, aid)
    row = _api_order(db, p, oid)
    add_log(db, aid, f"cancelled: {_short(row.description)}")
    db.delete(row)
    db.commit()
    return {"deleted": oid}


# The route groups that have moved out of this module. Each is an APIRouter in
# api/app/routers/, included here in the order it was declared in, so that lifting
# the lot into a create_app() at the end of the split is mechanical.
app.include_router(seo.router)
app.include_router(images.router)
app.include_router(catalogue.router)
app.include_router(stats_routes.router)
app.include_router(gallery.router)
app.include_router(items.router)
app.include_router(file_pages.router)
app.include_router(computer_pages.router)
app.include_router(part_pages.router)
app.include_router(project_pages.router)
