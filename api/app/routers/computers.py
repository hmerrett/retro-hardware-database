"""The pages of a machine: its own page, its form, its photographs, and what is
fitted inside it."""

from .. import machines
from ..assets import _bezel_ctx, _machine_ctx
from ..pages import _datalists
from datetime import date


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

from collections.abc import Sequence

from fastapi import APIRouter, Depends, File, HTTPException, Request, Response, UploadFile
from fastapi.responses import HTMLResponse, RedirectResponse
from sqlalchemy.orm import Session

from .. import drivedb, entry, filesdb, labels, machinedb, projects, specdb
from ..assets import (
    COMPUTER_DIFF_FIELDS,
    COMPUTER_FIELDS,
    DERIVED_FIELDS,
    DUP_EXCLUDE,
    _attach_photos,
    _confirms_url,
    _delete_ctx,
    _do_photo_crop,
    _do_photo_revert,
    _do_photo_rotate,
    _do_photo_tuneup,
    _machine_from_form,
    _machine_page,
    _require_disposed,
    _set_for_sale,
    _work_from_form,
    delete_computer,
    part_thumbs,
)
from ..common import to_dict
from ..db import get_db
from ..disposal import _and_parts, _disposal_log, _dispose_contents, _restore_contents
from ..forms import Posted, _coerce, _field_diffs, _parse_date, posted
from ..history import _history, add_log
from ..ids import next_asset_id
from ..models import Computer, Part, StoredFile
from ..pages import _answers_given, _note_with_photos
from ..photos import (
    _chosen_photos,
    _delete_image,
    _fetch_reference_photo,
    _mark_reference,
    _photo_edit_redirect,
    _save_photo,
    _set_primary_photo,
    detect_images,
    reference_marks,
    tuned_photos,
)
from ..register import _change_token, _item_nav, get_or_404
from ..web import _dot, _jsonld, _og, _safe_next, templates

from .. import ramdb


def _board_out_of(db: Session, c: Computer) -> machinedb.Identity:
    """The machine's catalogue identity, if a board can be lifted out of it -- or a
    400 naming which of the two conditions it fails.

    It has to be a machine the catalogue names, because what this verb moves is the
    machine's catalogue answers and a PC has none: a PC's board is already an object
    with its own chipset and slot counts written on it.

    And nothing of type motherboard may be linked to it, because a machine has one
    board. Without that, the button is one press per object rather than one object
    per separation, which is the difference between recording what happened and
    inventing hardware."""
    v = machinedb.read(db, c)
    if not v["model_key"]:
        raise HTTPException(
            400,
            f"{c.asset_id} is not a catalogue machine, so it has no board "
            f"issue and no chips to move onto one. A PC's board is entered as "
            f"a part in the ordinary way.",
        )
    fitted = (
        db.query(Part).filter(Part.computer_id == c.asset_id, Part.type == "motherboard").first()
    )
    if fitted is not None:
        raise HTTPException(
            400,
            f"{c.asset_id} already has board {fitted.asset_id} linked to it. "
            f"A machine has one board.",
        )
    return v


def _computer_form_ctx(
    c: Computer | None, title: str, db: Session | None = None
) -> dict[str, object]:
    mods, chips = ramdb.read(db, c) if (c is not None and db is not None) else ([], [])
    free = c.installed_ram_note if c else ""
    if c is not None and not (mods or chips) and not free and c.installed_ram_kb:
        free = entry.fmt_kb(c.installed_ram_kb)
    drives = drivedb.read(db, c) if (c is not None and db is not None) else []
    blanks = max(2, MAX_DRIVE_ROWS - len(drives))
    return {
        "c": c,
        "conditions": entry.CONDITIONS,
        "title": title,
        "ram_modules": entry.RAM_MODULES,
        "ram_mod_counts": dict(mods),
        "ram_chips": entry.RAM_CHIPS,
        "ram_counts": dict(chips),
        "ram_free": free,
        "drives": drives + [{}] * blanks,
        "drive_kinds": drivedb.KINDS,
        "drive_forms": drivedb.FORM_FACTORS,
        "drive_sizes": drivedb.SIZES,
        "drive_media": drivedb.MEDIA,
        "drive_speeds": drivedb.SPEEDS,
        **_bezel_ctx(),
        **_machine_ctx(c, db),
        # The projects in hand, for the work box at the foot of the form.
        "work_projects": projects.open_projects(db) if db is not None else [],
        "dl": _datalists(db, computer=True) if db is not None else {},
        **_boardparts_ctx(db, c),
    }


def _detach_ctx(db: Session, c: Computer, v: machinedb.Identity) -> dict[str, object]:
    """What lifting the board out will do, for the page that asks first.

    Read through the catalogue's current words, exactly as _machine_page reads the
    panel this was picked from, so the page names what is about to move in the same
    language it was recorded in."""
    return {
        "c": c,
        "aid": c.asset_id,
        "name": entry.display_name(to_dict(c)),
        "model": machines.full_name(v["model_key"]),
        "issue_label": machines.ISSUE_KEY,
        "issue": v["issue"],
        "chips": [
            {
                "label": machines.chip_label(v["model_key"], role),
                "variant": variant,
                "socketed": v["sockets"].get(role),
            }
            for role, variant in v["chips"].items()
        ],
        "staying": [
            (label, value)
            for label, value in (
                (machines.STYLE_KEY, v["style"]),
                (machines.REGION_KEY, v["region"]),
            )
            if value
        ],
        "noindex": True,
    }


def _drives_from_form(form: Posted) -> list[drivedb.Drive]:
    """[drive dict] from the numbered drive rows, skipping the empty ones -- so
    clearing a row's fields is how a drive is removed."""
    out: list[drivedb.Drive] = []
    for i in range(MAX_DRIVE_ROWS):
        # The eight text answers on their own, because whether the row was filled in
        # at all is read off them: a count is one whether anybody typed it or not.
        said = {
            k: (form.get(f"drive{i}_{k}", "") or "").strip()
            for k in (
                "kind",
                "form_factor",
                "size",
                "media",
                "speed",
                "model",
                "colour",
                "yellowing",
            )
        }
        if not any(said.values()):
            continue
        count = (form.get(f"drive{i}_count", "") or "").strip()
        out.append(
            drivedb.Drive(
                count=int(count) if count.isdigit() and int(count) > 0 else 1,
                kind=said["kind"],
                form_factor=said["form_factor"],
                size=said["size"],
                media=said["media"],
                speed=said["speed"],
                model=said["model"],
                colour=said["colour"],
                yellowing=said["yellowing"],
            )
        )
    return out


def _ram_from_form(
    form: Posted,
) -> tuple[list[tuple[str, int]], list[tuple[str, int]], str, int | None]:
    """A computer's memory as the form gives it: the SIMM/SIPP module grid, the
    direct-DRAM-chip grid, and the free-text box read as a total or kept as a
    note. Nothing is parsed back out of a rendered string."""
    mods = _grid_counts(form, "rammod", entry.RAM_MODULES)
    chips = _grid_counts(form, "ramchip", entry.RAM_CHIPS)
    total_kb, note = ramdb.from_string(form.get("installed_ram", ""))
    return mods, chips, note, total_kb


MAX_DRIVE_ROWS = 8


def _boardparts_ctx(db: Session | None, c: Computer | None) -> dict[str, object]:
    """The motherboard and parts sections, for the edit form of the one machine
    whose own page does not carry them: a catalogue machine with nothing fitted.

    Empty for every other machine, because the page it is read on already has them
    and offering the same two sections twice would be two places to add the same
    drive. The queries are the page's own, and only run for the machine that needs
    them."""
    if c is None or db is None or not machinedb.read(db, c)["model_key"]:
        return {}
    parts = db.query(Part).filter(Part.computer_id == c.asset_id).all()
    if parts:
        return {}
    return {
        "boardparts": True,
        "motherboard": None,
        "parts": [],
        "card_steps": entry.CARD_STEPS,
        "free_boards": (
            db.query(Part)
            .filter(Part.type == "motherboard", Part.computer_id.is_(None))
            .order_by(Part.asset_id)
            .all()
        ),
        "link_candidates": (
            db.query(Part)
            .filter(
                Part.type != "motherboard", Part.computer_id.is_(None), Part.parent_id.is_(None)
            )
            .order_by(Part.type, Part.asset_id)
            .all()
        ),
    }


def _grid_counts(
    form: Posted, prefix: str, items: Sequence[tuple[str, int, str]]
) -> list[tuple[str, int]]:
    """[(key, n), ...] for the count-grid inputs '<prefix>:<key>' that hold a
    positive integer."""
    out: list[tuple[str, int]] = []
    for key, *_ in items:
        raw = (form.get(f"{prefix}:{key}", "") or "").strip()
        if raw.isdigit() and int(raw) > 0:
            out.append((key, int(raw)))
    return out


router = APIRouter()


@router.get("/computers/new", response_class=HTMLResponse, include_in_schema=False)
def gui_new_computer(request: Request, db: Session = Depends(get_db)) -> HTMLResponse:
    # With a session, because the catalogue's pickers offer what other machines have
    # already been found to have as well as what the catalogue names -- and the form
    # for a machine being entered for the first time is where that matters most.
    return templates.TemplateResponse(
        request, "computer_form.html", _computer_form_ctx(None, "New computer", db)
    )


@router.post("/computers/new", include_in_schema=False)
async def gui_create_computer(request: Request, db: Session = Depends(get_db)) -> RedirectResponse:
    form = await posted(request)
    photos = _chosen_photos(form)
    # Everything the child tables render is left to them, as the edit path does: the
    # form's own installed_ram and drive fields are read by ramdb and drivedb below.
    data = {
        k: _coerce(k, form[k]) for k in COMPUTER_FIELDS if k in form and k not in DERIVED_FIELDS
    }
    for f in ("manufacturer", "model"):
        # _coerce hands these two back as the text they were typed as; the check
        # is for the type checker, which sees every column's type at once.
        if isinstance(text := data.get(f), str):
            data[f] = entry.deshout(text)
    obj = Computer(asset_id=next_asset_id(db), **data)
    db.add(obj)
    db.flush()
    ramdb.write(db, obj, *_ram_from_form(form))
    drivedb.write(db, obj, _drives_from_form(form), (form.get("drives_note", "") or "").strip())
    if (mach := _machine_from_form(form)) is not None:
        machinedb.write(db, obj, **mach)
    add_log(db, obj.asset_id, "created", "created")
    # After the flush above, because a membership is refused for an asset that is not
    # in the register yet -- and this one is being entered as we speak.
    _work_from_form(db, obj, form)
    db.commit()
    if photos:
        _attach_photos(db, obj, "computers", photos)
        db.commit()
    # Land on the build walk so the next step (motherboard) is front and centre.
    return RedirectResponse(f"/computers/{obj.asset_id}?build=1", status_code=303)


@router.get("/computers/{aid}", response_class=HTMLResponse, include_in_schema=False)
def gui_computer(
    aid: str,
    request: Request,
    build: int = 0,
    imgerr: int = 0,
    fileerr: int = 0,
    db: Session = Depends(get_db),
) -> HTMLResponse:
    c = get_or_404(db, Computer, aid)
    parts = db.query(Part).filter(Part.computer_id == aid).all()
    parts.sort(key=lambda p: (entry.type_sort_key(p.type or ""), entry.display_name(to_dict(p))))
    motherboard = next((p for p in parts if p.type == "motherboard"), None)
    # Unlinked boards that could be linked to this machine.
    free_boards, link_candidates = [], []
    if request.state.authed:
        free_boards = (
            db.query(Part)
            .filter(Part.type == "motherboard", Part.computer_id.is_(None))
            .order_by(Part.asset_id)
            .all()
        )
        link_candidates = (
            db.query(Part)
            .filter(
                Part.type != "motherboard", Part.computer_id.is_(None), Part.parent_id.is_(None)
            )
            .order_by(Part.type, Part.asset_id)
            .all()
        )
    images = detect_images("computers", aid)
    blurb = c.summary or _dot(
        " ".join(x for x in (c.manufacturer, c.model, str(c.year or "")) if x), c.cpu, c.condition
    )
    # Form factor is a property of the board, shown on the machine -- which is
    # what the part form promises ("the computer's form factor is taken from
    # here"). Read it from the typed column rather than re-parsing the string.
    form_factor = specdb.scalars(db, motherboard).get("form_factor", "") if motherboard else ""
    # Whether a board can be lifted out of this machine, worked out from what the
    # page has already read rather than by asking again: a machine the catalogue
    # names, with no board linked to it yet. _board_out_of is the same two conditions
    # at the door, so the button and the route cannot disagree.
    machine = _machine_page(db, c)
    detachable = bool(request.state.authed and machine and machine["key"] and motherboard is None)
    return templates.TemplateResponse(
        request,
        "computer.html",
        {
            "machine": machine,
            "detachable": detachable,
            "item": (cdict := to_dict(c)),
            "kind": "computers",
            "files": filesdb.for_item(db, cdict, request.state.authed),
            "file_models": filesdb.model_ids_for(db, cdict),
            "fileerr": bool(fileerr),
            "dl_filenotes": _answers_given(db, StoredFile.note),
            "on_project": (found := projects.project_for(db, aid, request.state.authed)),
            "item_tasks": projects.tasks_for_asset(db, aid, request.state.authed),
            "project_tasks": (
                projects.project_wide_tasks(db, found.asset_id) if found is not None else []
            ),
            # For the picker in that panel, which only an owner is shown -- so a
            # visitor's page does not ask the question at all.
            "work_projects": (projects.open_projects(db) if request.state.authed else []),
            "c": c,
            "parts": [p for p in parts if p is not motherboard],
            "motherboard": motherboard,
            "form_factor": form_factor,
            # A picture for each of them, read once for the page rather than per card.
            "thumbs": part_thumbs(db, parts),
            "free_boards": free_boards,
            "link_candidates": link_candidates,
            "images": images,
            # The drawing to stand in for a photograph nobody has taken yet -- the same
            # one the gallery card for this item is already wearing, so the two places
            # it appears agree about what it is a picture of.
            "placeholder": entry.placeholder_for("computer"),
            "ref_marks": reference_marks("computers", aid),
            "tuned": tuned_photos("computers", aid),
            "card_steps": entry.CARD_STEPS,
            "build": bool(build),
            "imgerr": bool(imgerr),
            "log": _history(db, aid),
            "nav": _item_nav(db, aid),
            "live_aid": aid,
            "live_v": _change_token(db, aid),
            "og": (
                og := _og(
                    request, entry.display_name(to_dict(c)), blurb, images[0] if images else None
                )
            ),
            "jsonld": _jsonld(og, c.asset_id, c.manufacturer, "Vintage computer"),
        },
    )


@router.get("/computers/{aid}/edit", response_class=HTMLResponse, include_in_schema=False)
def gui_edit_computer(aid: str, request: Request, db: Session = Depends(get_db)) -> HTMLResponse:
    c = get_or_404(db, Computer, aid)
    return templates.TemplateResponse(
        request, "computer_form.html", _computer_form_ctx(c, f"Edit {aid}", db)
    )


@router.post("/computers/{aid}/edit", include_in_schema=False)
async def gui_save_computer(
    aid: str, request: Request, db: Session = Depends(get_db)
) -> RedirectResponse:
    c = get_or_404(db, Computer, aid)
    form = await posted(request)
    old = {k: getattr(c, k) for k in COMPUTER_FIELDS}
    for k in COMPUTER_FIELDS:
        if k not in form:
            continue
        if k in DERIVED_FIELDS:
            continue
        v = _coerce(k, form[k])
        if k in ("manufacturer", "model") and isinstance(v, str):
            v = entry.deshout(v)
        setattr(c, k, v)
    mods, chips, note, total_kb = _ram_from_form(form)
    ramdb.write(db, c, mods, chips, note, total_kb)
    drivedb.write(db, c, _drives_from_form(form), (form.get("drives_note", "") or "").strip())
    if (mach := _machine_from_form(form)) is not None:
        machinedb.write(db, c, **mach)
    diff = _field_diffs(old, {k: getattr(c, k) for k in COMPUTER_FIELDS}, COMPUTER_DIFF_FIELDS)
    if diff:
        add_log(db, aid, diff)
    _work_from_form(db, c, form)
    db.commit()
    return RedirectResponse(f"/computers/{aid}", status_code=303)


@router.post("/computers/{aid}/link-motherboard", include_in_schema=False)
async def gui_link_motherboard(
    aid: str, request: Request, db: Session = Depends(get_db)
) -> RedirectResponse:
    get_or_404(db, Computer, aid)
    form = await posted(request)
    pid = form.get("part_id", "") or ""
    if not pid:
        return RedirectResponse(f"/computers/{aid}?build=1", status_code=303)
    board = get_or_404(db, Part, pid)
    if board.type != "motherboard":
        raise HTTPException(400, f"{pid} is not a motherboard")
    board.computer_id = aid
    add_log(db, aid, f"linked motherboard {board.asset_id}")
    add_log(db, board.asset_id, f"linked to computer {aid}")
    db.commit()
    return RedirectResponse(f"/computers/{aid}?build=1", status_code=303)


@router.post("/computers/{aid}/link-part", include_in_schema=False)
async def gui_link_part(
    aid: str, request: Request, db: Session = Depends(get_db)
) -> RedirectResponse:
    """Install an existing standalone part into this computer."""
    get_or_404(db, Computer, aid)
    form = await posted(request)
    pid = form.get("part_id", "") or ""
    if not pid:
        return RedirectResponse(f"/computers/{aid}", status_code=303)
    part = get_or_404(db, Part, pid)
    part.computer_id = aid
    part.parent_id = None
    add_log(db, aid, f"linked part {part.asset_id}")
    add_log(db, part.asset_id, f"installed in {aid}")
    db.commit()
    return RedirectResponse(f"/computers/{aid}", status_code=303)


@router.get("/computers/{aid}/detach-board", response_class=HTMLResponse, include_in_schema=False)
def gui_detach_board_form(
    aid: str, request: Request, db: Session = Depends(get_db)
) -> HTMLResponse:
    c = get_or_404(db, Computer, aid)
    return templates.TemplateResponse(
        request, "detach.html", _detach_ctx(db, c, _board_out_of(db, c))
    )


@router.post("/computers/{aid}/detach-board", include_in_schema=False)
async def gui_detach_board(
    aid: str, request: Request, db: Session = Depends(get_db)
) -> RedirectResponse:
    """Make the board in this machine an object of its own.

    The identity move is a rewrite inside the two catalogue tables rather than a
    copy between a machine's and a part's, which is what keying them by a plain
    asset id bought: read the machine's answers, write the board's, blank the two
    the machine has stopped being able to answer. No schema knows this verb exists.

    The machine keeps its asset id, its model, its style, its region and every line
    of its history. It is still the machine on the shelf; what has changed is that
    one of the things it is made of is now on the shelf beside it.

    The photographs come with the form for the reason they do on any create form --
    there is no asset tag to file them under until the part exists -- but here they
    are also the point of the page. A board is photographable at the moment it is
    out and before it goes back in, and that moment does not come round again."""
    c = get_or_404(db, Computer, aid)
    v = _board_out_of(db, c)
    form = await posted(request)
    photos = _chosen_photos(form)
    # The maker and the model come across because the maker of the machine made the
    # board and it is the board for that model -- the same carry the duplicate
    # button makes, and without it the board is an asset id with no name in a list.
    # Nothing else does: the condition of a board out of a working machine, where it
    # came from and what it cost are its own answers now, and the machine's history
    # is where it came from.
    board = Part(
        asset_id=next_asset_id(db),
        type="motherboard",
        computer_id=aid,
        manufacturer=c.manufacturer,
        model=c.model,
    )
    db.add(board)
    db.flush()
    specdb.write(db, board)
    machinedb.write(
        db,
        board,
        model_key=v["model_key"],
        issue=v["issue"],
        chips=v["chips"],
        sockets=v["sockets"],
    )
    # Blanked, not cleared: clear() would take the model with it, and this machine is
    # still a Spectrum. The style and the region are not touched at all -- the form
    # never asked them of the board and the case did not go anywhere.
    machinedb.write(db, c, issue="", chips={})
    # The board's history opens with where it came from, because that is its birth:
    # it was not created out of nothing, it was taken out of RH-xxxx.
    add_log(db, board.asset_id, f"detached from computer {aid}", kind="created")
    add_log(db, aid, f"board detached as {board.asset_id}, and linked back in")
    db.commit()
    if photos:
        _attach_photos(db, board, "parts", photos)
        db.commit()
    return RedirectResponse(f"/parts/{board.asset_id}", status_code=303)


@router.post("/computers/{aid}/dispose", include_in_schema=False)
async def gui_dispose_computer(
    aid: str, request: Request, db: Session = Depends(get_db)
) -> RedirectResponse:
    c = get_or_404(db, Computer, aid)
    form = await posted(request)
    c.disposed = True
    c.disposed_at = _parse_date(form.get("date", "")) or date.today()
    c.disposed_note = form.get("note", "") or ""
    # What was in the machine went out with the machine, on the same date and for
    # the same reason -- recording it any other way would leave the register
    # claiming we still hold parts that are in the same skip as their host.
    n = _dispose_contents(db, c)
    add_log(db, aid, _disposal_log(c) + _and_parts(n))
    db.commit()
    return RedirectResponse(f"/computers/{aid}", status_code=303)


@router.post("/computers/{aid}/for-sale", include_in_schema=False)
async def gui_computer_for_sale(
    aid: str, request: Request, db: Session = Depends(get_db)
) -> RedirectResponse:
    return await _set_for_sale(db, Computer, aid, request)


@router.post("/computers/{aid}/restore", include_in_schema=False)
def gui_restore_computer(aid: str, db: Session = Depends(get_db)) -> RedirectResponse:
    c = get_or_404(db, Computer, aid)
    was_at, was_note = c.disposed_at, c.disposed_note
    c.disposed = False
    c.disposed_at = None
    c.disposed_note = ""
    n = _restore_contents(db, c, was_at, was_note)
    add_log(db, aid, "restored" + _and_parts(n, "came back too"))
    db.commit()
    return RedirectResponse(f"/computers/{aid}", status_code=303)


@router.get("/computers/{aid}/delete", response_class=HTMLResponse, include_in_schema=False)
def gui_delete_computer_form(
    aid: str, request: Request, db: Session = Depends(get_db)
) -> HTMLResponse:
    c = get_or_404(db, Computer, aid)
    _require_disposed(c, "computer")
    return templates.TemplateResponse(
        request, "delete.html", _delete_ctx(request, db, "computers", c)
    )


@router.post("/computers/{aid}/delete", include_in_schema=False)
async def gui_delete_computer(
    aid: str, request: Request, db: Session = Depends(get_db)
) -> Response:
    c = get_or_404(db, Computer, aid)
    _require_disposed(c, "computer")
    form = await posted(request)
    with_parts = bool(form.get("with_parts"))
    if not _confirms_url(form.get("confirm", ""), "computers", c.asset_id):
        # Back to the page rather than an error: a paste that went wrong is the
        # ordinary way to arrive here, and the tick keeps whatever it was set to.
        return templates.TemplateResponse(
            request,
            "delete.html",
            _delete_ctx(
                request,
                db,
                "computers",
                c,
                with_parts=with_parts,
                error="That is not this item's URL. Nothing was deleted.",
            ),
            status_code=400,
        )
    ctx = _delete_ctx(request, db, "computers", c, with_parts=with_parts)
    # The list the confirmation page showed, and not one worked out again here: a
    # template's context is typed as loosely as a template needs, so what comes
    # back out of it is checked for being the parts it was put in as.
    listed = ctx["deletable"]
    going = [p for p in listed if isinstance(p, Part)] if isinstance(listed, list) else []
    delete_computer(db, c, with_parts=going if with_parts else ())
    return RedirectResponse("/", status_code=303)


@router.post("/computers/{aid}/note", include_in_schema=False)
async def gui_computer_note(
    aid: str, request: Request, db: Session = Depends(get_db)
) -> RedirectResponse:
    get_or_404(db, Computer, aid)
    _note_with_photos(db, aid, await posted(request))
    return RedirectResponse(f"/computers/{aid}", status_code=303)


@router.post("/computers/{aid}/photo", include_in_schema=False)
async def gui_computer_photo(
    aid: str, photos: list[UploadFile] = File(...), db: Session = Depends(get_db)
) -> RedirectResponse:
    c = get_or_404(db, Computer, aid)
    first = None
    n = 0
    for up in photos:
        if (up.filename or "").strip():
            rel = _save_photo("computers", aid, up)
            n += 1
            if first is None:
                first = rel
    if first and not c.image:
        c.image = first
    if n:
        add_log(db, aid, f"added {n} photo(s)")
    db.commit()
    return RedirectResponse(f"/computers/{aid}", status_code=303)


@router.post("/computers/{aid}/fetch-image", include_in_schema=False)
def gui_computer_fetch_image(aid: str, db: Session = Depends(get_db)) -> RedirectResponse:
    c = get_or_404(db, Computer, aid)
    rel = _fetch_reference_photo("computers", aid, c.url or "") if c.url else None
    if rel:
        if not c.image:
            c.image = rel
        add_log(db, aid, "fetched a photo from the reference")
        db.commit()
    return RedirectResponse(f"/computers/{aid}" + ("" if rel else "?imgerr=1"), status_code=303)


@router.post("/computers/{aid}/primary-photo", include_in_schema=False)
async def gui_computer_primary(
    aid: str, request: Request, db: Session = Depends(get_db)
) -> RedirectResponse:
    c = get_or_404(db, Computer, aid)
    form = await posted(request)
    c.image = _set_primary_photo("computers", aid, form.get("image", ""))
    add_log(db, aid, "changed the default photo")
    db.commit()
    return RedirectResponse(f"/computers/{aid}", status_code=303)


@router.post("/computers/{aid}/photo-delete", include_in_schema=False)
async def gui_computer_photo_delete(
    aid: str, request: Request, db: Session = Depends(get_db)
) -> RedirectResponse:
    c = get_or_404(db, Computer, aid)
    form = await posted(request)
    was_primary, new_primary = _delete_image("computers", aid, form.get("image", ""))
    if was_primary:
        c.image = new_primary or ""
    add_log(db, aid, "deleted a photo")
    db.commit()
    return RedirectResponse(f"/computers/{aid}", status_code=303)


@router.post("/computers/{aid}/photo-reference", include_in_schema=False)
async def gui_computer_photo_reference(
    aid: str, request: Request, db: Session = Depends(get_db)
) -> RedirectResponse:
    c = get_or_404(db, Computer, aid)
    form = await posted(request)
    rel = form.get("image", "")
    if rel not in detect_images("computers", aid):
        raise HTTPException(404, "no such photo for this item")
    on = form.get("set", "1") == "1"
    _mark_reference(rel, on, (form.get("note", "") or "").strip(), c.url or "")
    add_log(
        db, aid, "flagged a photo as a reference image" if on else "unflagged a reference photo"
    )
    db.commit()
    return RedirectResponse(f"/computers/{aid}", status_code=303)


@router.get("/computers/{aid}/edit-photo", response_class=HTMLResponse, include_in_schema=False)
def gui_computer_edit_photo(aid: str, image: str = "") -> RedirectResponse:
    return _photo_edit_redirect("computers", aid, image)


@router.post("/computers/{aid}/photo-rotate", include_in_schema=False)
async def gui_computer_photo_rotate(
    aid: str, request: Request, db: Session = Depends(get_db)
) -> RedirectResponse:
    form = await posted(request)
    _do_photo_rotate(db, Computer, "computers", aid, form)
    return RedirectResponse(_safe_next(form.get("next") or f"/computers/{aid}"), status_code=303)


@router.post("/computers/{aid}/photo-tuneup", include_in_schema=False)
async def gui_computer_photo_tuneup(
    aid: str, request: Request, db: Session = Depends(get_db)
) -> RedirectResponse:
    form = await posted(request)
    _do_photo_tuneup(db, Computer, "computers", aid, form)
    return RedirectResponse(_safe_next(form.get("next") or f"/computers/{aid}"), status_code=303)


@router.post("/computers/{aid}/photo-revert", include_in_schema=False)
async def gui_computer_photo_revert(
    aid: str, request: Request, db: Session = Depends(get_db)
) -> RedirectResponse:
    form = await posted(request)
    _do_photo_revert(db, Computer, "computers", aid, form)
    return RedirectResponse(_safe_next(form.get("next") or f"/computers/{aid}"), status_code=303)


@router.post("/computers/{aid}/photo-crop", include_in_schema=False)
async def gui_computer_photo_crop(
    aid: str, request: Request, db: Session = Depends(get_db)
) -> RedirectResponse:
    form = await posted(request)
    _do_photo_crop(db, Computer, "computers", aid, form)
    return RedirectResponse(_safe_next(form.get("next") or f"/computers/{aid}"), status_code=303)


@router.get("/computers/{aid}/label.pdf", include_in_schema=False)
def gui_computer_label(aid: str, small: int = 0, db: Session = Depends(get_db)) -> Response:
    c = get_or_404(db, Computer, aid)
    installed = db.query(Part).filter(Part.computer_id == aid).all()
    board = next((p for p in installed if p.type == "motherboard"), None)
    rows = []
    for p in installed:
        d = to_dict(p)
        d["spec_pairs"] = specdb.pairs(db, p, display=True)
        rows.append(d)
    # Form factor is a text column; the check is for the type checker, which sees
    # the typed spec columns as the strings and the integers together.
    form_factor = specdb.scalars(db, board).get("form_factor", "") if board else ""
    pdf = labels.render_pdf(
        to_dict(c),
        rows,
        labels.COMPUTER,
        small=bool(small),
        form_factor=form_factor if isinstance(form_factor, str) else "",
    )
    return Response(
        pdf,
        media_type="application/pdf",
        headers={"Content-Disposition": f'inline; filename="{aid}{"-small" if small else ""}.pdf"'},
    )


@router.post("/computers/{aid}/duplicate", include_in_schema=False)
def gui_duplicate_computer(aid: str, db: Session = Depends(get_db)) -> RedirectResponse:
    """A second machine of the same model. Its memory and drives come across --
    they describe the build -- but its parts do not: those are tagged objects
    fitted to the original, and the copy starts as an empty chassis to fill. The
    catalogue model comes across for the same reason the model field does; the
    board issue and the chips do not, because those are found by opening this
    machine rather than the one it was copied from."""
    src = get_or_404(db, Computer, aid)
    data = {
        k: getattr(src, k)
        for k in COMPUTER_FIELDS
        if k not in DUP_EXCLUDE and k not in DERIVED_FIELDS
    }
    obj = Computer(asset_id=next_asset_id(db), **data)
    db.add(obj)
    db.flush()
    mods, chips = ramdb.read(db, src)
    ramdb.write(db, obj, mods, chips, src.installed_ram_note or "", src.installed_ram_kb)
    drivedb.write(db, obj, drivedb.read(db, src), src.drives_note or "")
    machinedb.duplicated_from(db, src, obj)
    add_log(db, obj.asset_id, f"created as a duplicate of {aid}", kind="created")
    add_log(db, aid, f"duplicated to {obj.asset_id}", kind="duplicate")
    db.commit()
    return RedirectResponse(f"/computers/{obj.asset_id}", status_code=303)
