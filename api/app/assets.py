"""What a machine's page and a part's page do the same way.

The two are different things and read differently, but almost everything done *to*
one is done to the other: a photograph hung on it, a note written under it, a form
read back into its columns, a disposal, a deletion, the work it is wanted for. Those
are here, so that the two page modules hold what differs and not what does not --
and so that the JSON API, which deletes and edits the same rows, is not a third copy.
"""

from collections.abc import Collection, Iterable, Sequence
from typing import Literal, TypedDict
from urllib.parse import urlparse


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


# --- work noted while checking something in -----------------------------------
# The quick box above is this gesture from a page that already exists. What follows
# is the same one from the two forms that make a page, which is where the thought
# actually arrives: what is wrong with a machine is seen while it is being unpacked,
# and the form that files it is on screen at the time. Asking for the item's tag
# first meant the note had to wait for a second visit to a page that did not exist
# yet, and a note that waits is a note that is lost -- which is the whole reason the
# flag on an item existed before 0031, and the reason this is not simply the quick
# box again.

from fastapi import HTTPException, Request
from fastapi.responses import RedirectResponse

from sqlalchemy import func
from sqlalchemy.orm import Session
from starlette.datastructures import UploadFile

from . import entry, filesdb, machinedb, machines, projects, specdb
from .common import folder_images, to_dict
from .disposal import _parts_in_computer
from .forms import Posted, posted
from .history import add_log
from .models import (
    AssetChip,
    AssetVariant,
    Computer,
    ComputerDrive,
    ComputerRamChip,
    ComputerRamModule,
    LogEntry,
    Part,
    Project,
)
from .photos import (
    _asset_log_photos,
    _crop_op,
    _drop_log_photos,
    _edit_image,
    _favicon_for_rel,
    _purge_photos,
    _restore_original,
    _rotate_op,
    _save_photo,
    _storage_placeholder,
    _tuneup_op,
    detect_images,
    has_original,
    is_reference,
    pick_images,
)
from .register import get_or_404
from .web import _abs_url
from .work import _take_on_work, _work_lines


# What a typed answer to one of the catalogue pickers may be as long as: the column
# it lands in. The same rule the drive pickers follow (see _ASK_WIDTHS) -- a box that
# accepted more than the column holds would fail on save rather than at the keyboard.
_MACHINE_WIDTHS = {
    "issue": AssetVariant.issue.type.length,
    "style": AssetVariant.style.type.length,
    "region": AssetVariant.region.type.length,
    "chip": AssetChip.variant.type.length,
}


def _bezel_ctx() -> dict[str, object]:
    """The bezel vocabularies and their swatches, for any form that records one:
    a machine's drive rows, a storage part and a display all do."""
    return {
        "bezel_colours": entry.BEZEL_COLOURS,
        "yellowing": entry.YELLOWING,
        "bezel_colour_labels": entry.BEZEL_COLOUR_LABELS,
        "yellowing_labels": entry.YELLOWING_LABELS,
        "bezel_swatches": entry.bezel_swatch_map(),
    }


def _machine_ctx(
    obj: Computer | Part | None, db: Session | None = None, board: bool = False
) -> dict[str, object]:
    """The catalogue and this asset's place in it, for the edit form of a machine or
    of a board.

    The whole catalogue goes to the browser as JSON because the variation fields are
    built from whichever model is picked: sixty models' worth of menus rendered at
    once would be most of the page, and all but one set of them would be wrong."""
    saved = (
        machinedb.read(db, obj) if (obj is not None and db is not None) else dict(machinedb.BLANK)
    )
    # What the catalogue names, plus what the register has since been told: a chip
    # somebody had to type once is a radio button from then on. Boards teach it the
    # same as machines do -- the query behind this reads the whole register.
    catalogue = machines.with_recorded(
        machines.form_catalogue(), machinedb.recorded(db) if db is not None else {}
    )
    return {
        "machine_groups": machines.grouped(),
        "machine_saved": saved,
        "machine_catalogue": catalogue,
        "machine_widths": _MACHINE_WIDTHS,
        "machine_board": board,
    }


# The two answers a board is not asked for. A case or keyboard style and the market
# a machine was built for are facts about a whole computer in a case, so a board's
# form leaves them off -- and the save reads only what the form asked.
_MACHINE_ONLY: tuple[Literal["style", "region"], ...] = ("style", "region")


def _machine_pick(form: Posted, field: str) -> str:
    """What one of the catalogue's radio groups chose: one of the answers it offered,
    or whatever was typed beside "custom" for the machine the catalogue has not met
    yet. Blank is a deliberate answer too -- it is how a socket nobody has looked at
    is left unrecorded, and how a chip written down by mistake is taken back off."""
    picked = (form.get(field, "") or "").strip()
    if picked == "custom":
        return " ".join((form.get(f"{field}_custom", "") or "").split())
    return picked


def _clear_computer_rows(db: Session, c: Computer, with_parts: Iterable[Part] = ()) -> list[str]:
    """The same for a computer: its drive and memory rows, its history, and either
    the parts inside it or the link they hold to it. `with_parts` is the parts to
    delete along with it; the rest are unlinked and kept."""
    aid = c.asset_id
    going = {p.asset_id for p in with_parts}
    photos: list[str] = []
    # The same walk disposal uses, so that what a delete calls "in the machine" is
    # what disposal called it: a disk on a controller card carries the card's id,
    # not the machine's. A kept part only needs the link it holds to the machine
    # cleared here -- one held to a part that is going is cleared by that part.
    for p in _parts_in_computer(db, aid):
        if p.asset_id in going:
            photos += _clear_part_rows(db, p, also_going=going)
        elif p.computer_id == aid:
            p.computer_id = None
            add_log(db, p.asset_id, f"came out of {aid}, which was deleted")
    for model in (ComputerDrive, ComputerRamModule, ComputerRamChip):
        db.query(model).filter(model.computer_id == aid).delete(synchronize_session=False)
    photos += _drop_log_photos(db, aid)
    projects.forget_asset(db, aid)
    filesdb.forget_asset(db, aid)
    for table in (AssetChip, AssetVariant, LogEntry):
        db.query(table).filter(table.asset_id == aid).delete(synchronize_session=False)
    photos += detect_images("computers", aid)
    db.delete(c)
    return photos


def _clear_part_rows(db: Session, part: Part, also_going: Collection[str] = ()) -> list[str]:
    """Everything in the database belonging to one part, and the links other parts
    hold to it. Returns its photos, for the caller to delete once the transaction
    is safe. `also_going` names assets being deleted in the same breath, which are
    not told they have lost a link they are about to stop having."""
    aid = part.asset_id
    for child in db.query(Part).filter(Part.parent_id == aid).all():
        if child.asset_id in also_going:
            continue
        child.parent_id = None
        add_log(db, child.asset_id, f"came off {aid}, which was deleted")
    for model in specdb.SPEC_TABLES:
        db.query(model).filter(model.part_id == aid).delete(synchronize_session=False)
    # By hand rather than by cascade, for the reason log_entry is: these are keyed
    # by an asset id from the shared register, which no one table can own. The
    # log's own photographs go first, while there are still entries to find them by.
    photos = _drop_log_photos(db, aid)
    # A project that was about this part stops being about it. By hand for the same
    # reason: project_asset.asset_id is a plain register id with no foreign key
    # behind it, so nothing in the database will clear it. A file attached to this
    # one unit goes the same way, and the bytes stay: a file left attached to
    # nothing is unfiled, which the files page says rather than bins (ADR-0006).
    projects.forget_asset(db, aid)
    filesdb.forget_asset(db, aid)
    for table in (AssetChip, AssetVariant, LogEntry):
        db.query(table).filter(table.asset_id == aid).delete(synchronize_session=False)
    photos += detect_images("parts", aid)
    db.delete(part)
    return photos


def _log_count(db: Session, asset_ids: Sequence[str]) -> int:
    if not asset_ids:
        return 0
    counted: int | None = (
        db.query(func.count(LogEntry.id)).filter(LogEntry.asset_id.in_(asset_ids)).scalar()
    )
    return counted or 0


COMPUTER_FIELDS = [c.name for c in Computer.__table__.columns if c.name != "asset_id"]


COMPUTER_DIFF_FIELDS = [f for f in COMPUTER_FIELDS if f != "installed_ram_kb"]


# These are rendered from the memory, drive and catalogue child tables, so the form
# loop must not write them, and the change log need not repeat the derived total.
DERIVED_FIELDS = {"installed_ram", "installed_ram_kb", "drives", "drives_note", "variant"}


PART_FIELDS = [c.name for c in Part.__table__.columns if c.name != "asset_id"]


# The same for a part: its variant line is rendered from the catalogue rows, so
# nothing that copies or writes a part's columns wholesale may set it.
PART_DERIVED_FIELDS = {"variant"}


# A duplicate is a second identical unit, so it copies what describes the model --
# the fields, the specs, a machine's fitted memory and drives -- and nothing that
# belongs to the original object: its photos, its disposal, its provenance
# (source / acquired date / notes), its serial number, and where it sits. A second
# card is a second card, not another card in the same slot, so the copy starts
# unplaced -- and no two objects ever wore the same serial.
#
# A plan used to be on that list too, when one was a column here. It is a project of
# its own now, and a project is attached to an asset rather than copied with one --
# so a duplicate is simply not in it, and there is nothing to leave out.
DUP_EXCLUDE = {
    "image",
    "disposed",
    "disposed_at",
    "disposed_note",
    "source",
    "acquired_date",
    "notes",
    "serial",
    "computer_id",
    "parent_id",
}


def _attach_photos(
    db: Session, obj: Computer | Part, kind: str, uploads: Sequence[UploadFile]
) -> None:
    """Store photos against an item that has only just been created. Nothing can
    upload while a create form is still being filled in -- there is no asset id to
    file a photo under yet -- so they come with the form and are written here."""
    first: str | None = None
    for up in uploads:
        rel = _save_photo(kind, obj.asset_id, up)
        if first is None:
            first = rel
    if first and not obj.image:
        obj.image = first
    if uploads:
        add_log(db, obj.asset_id, f"added {len(uploads)} photo(s)")


def _confirms_url(text: str | None, kind: str, aid: str) -> bool:
    """The safety net: the item's own URL, pasted in. Nothing about this asks the
    database a question it does not already know the answer to -- the point is to
    make deleting the wrong thing take a deliberate act, so that a delete cannot
    be a stray click on a page somebody landed on by accident.

    What the address bar holds is accepted from any host, with any query or
    fragment, and so is the bare path, because all three are the same act of
    fetching the thing's identity. The asset id itself has to be right."""
    path = urlparse((text or "").strip()).path.rstrip("/")
    return path.upper() == f"/{kind}/{aid}".upper()


def _delete_ctx(
    request: Request,
    db: Session,
    kind: str,
    obj: Computer | Part,
    error: str = "",
    with_parts: bool = False,
) -> dict[str, object]:
    """What deleting this would take with it, for the confirmation page. Read with
    the same queries the deletion itself runs, so the page cannot promise one
    thing and the button do another.

    The item's own figures and the contents' are kept apart rather than summed
    against the tick, so both are on the page whichever way the tick is set and
    neither needs a script to keep them honest."""
    aid = obj.asset_id
    inside: list[Part]
    children: list[Part]
    inside = children = []
    if kind == "computers":
        inside = _parts_in_computer(db, aid)
    else:
        children = db.query(Part).filter(Part.parent_id == aid).order_by(Part.asset_id).all()
    # A part inside the machine that is not itself disposed is not deleted even
    # when the box is ticked: it is still in the collection, and the rule here is
    # that only what has already been marked as gone can go.
    deletable = [p for p in inside if p.disposed]
    # The photographs hung on the history count here too. They are not shown in the
    # gallery and are not the portrait, but they are files, they go when the record
    # goes, and the page's promise is "deleted from disk" -- so leaving them out
    # would be under-promising what the button does.
    return {
        "kind": kind,
        "obj": obj,
        "aid": aid,
        "name": entry.display_name(to_dict(obj)),
        "url": _abs_url(request, f"/{kind}/{aid}"),
        "photos": detect_images(kind, aid) + _asset_log_photos(db, aid),
        "logs": _log_count(db, [aid]),
        "inside": inside,
        "deletable": deletable,
        "kept": [p for p in inside if not p.disposed],
        "parts_photos": sum(
            len(detect_images("parts", p.asset_id)) + len(_asset_log_photos(db, p.asset_id))
            for p in deletable
        ),
        "parts_logs": _log_count(db, [p.asset_id for p in deletable]),
        "children": children,
        "with_parts": with_parts,
        "error": error,
        "noindex": True,
    }


def _do_photo_crop(
    db: Session, model: type[Computer] | type[Part], kind: str, aid: str, form: Posted
) -> None:
    get_or_404(db, model, aid)
    try:
        x, y, w, h = (float(form.get(k, "")) for k in ("x", "y", "w", "h"))
    except ValueError as err:
        raise HTTPException(400, "bad crop box") from err
    _edit_image(kind, aid, form.get("image", ""), _crop_op(x, y, w, h))
    add_log(db, aid, "cropped a photo")
    db.commit()


def _do_photo_revert(
    db: Session, model: type[Computer] | type[Part], kind: str, aid: str, form: Posted
) -> None:
    get_or_404(db, model, aid)
    rel = form.get("image", "")
    if rel not in detect_images(kind, aid):
        raise HTTPException(404, "no such photo for this item")
    _restore_original(rel)
    add_log(db, aid, "reverted a tuned photo")
    db.commit()


def _do_photo_rotate(
    db: Session, model: type[Computer] | type[Part], kind: str, aid: str, form: Posted
) -> None:
    get_or_404(db, model, aid)
    _edit_image(kind, aid, form.get("image", ""), _rotate_op(form.get("dir", "cw")))
    add_log(db, aid, "rotated a photo")
    db.commit()


def _do_photo_tuneup(
    db: Session, model: type[Computer] | type[Part], kind: str, aid: str, form: Posted
) -> None:
    get_or_404(db, model, aid)
    rel = form.get("image", "")
    # Pressing it twice is the accident this guards: the file is re-encoded on
    # every edit, so a second tuneup costs another generation of JPEG for a
    # picture that has already had the fix. Nothing to do is not an error -- the
    # photograph is in the state the button asks for -- so it returns quietly
    # rather than sending back a failure for a button that appears to have worked.
    if has_original(rel) and rel in detect_images(kind, aid):
        return
    _edit_image(kind, aid, rel, _tuneup_op(), revertible=True)
    add_log(db, aid, "tuned a photo")
    db.commit()


class MachineAnswers(TypedDict, total=False):
    """What the catalogue pickers answered, as machinedb.write's keyword arguments.
    Every key is optional because a question the form never put is left unnamed
    rather than blanked -- which is what machinedb reads an absent field as."""

    model_key: str
    issue: str
    style: str
    region: str
    chips: dict[str, str]
    sockets: dict[str, bool]


def _machine_from_form(form: Posted, board: bool = False) -> MachineAnswers | None:
    """An asset's catalogue identity as the form gives it, as keyword arguments for
    machinedb.write -- or None where the form did not carry the question at all.

    The variation fields are built in the browser from the catalogue, and
    `mach_fields` is the marker the script sets once it has built them. Without it --
    no JavaScript, or a script that did not run -- only the model choice is read and
    the board issue, style, region and chips already on file are left alone: a form
    that could not draw them must not be able to erase them either.

    `board` is the board's form, which asks the model, the issue and the chips and
    not the two that belong to a whole machine. They are left unnamed rather than
    blanked, so a question this form never put cannot answer itself.

    Only the sockets the chosen model has are read, so fields left over from another
    model in the same browser tab cannot put a ULA in a Commodore 64."""
    if "mach_model" not in form:
        return None
    key = (form.get("mach_model", "") or "").strip()
    out: MachineAnswers = {"model_key": key}
    if not key or not (form.get("mach_fields", "") or "").strip():
        return out
    asked: list[Literal["issue", "style", "region"]] = (
        ["issue"] if board else ["issue", *_MACHINE_ONLY]
    )
    for field in asked:
        out[field] = _machine_pick(form, f"mach_{field}")
    out["chips"] = {role: _machine_pick(form, f"chip:{role}") for role in machines.roles(key)}
    # The tickbox beside each chip: on for a socket, off for soldered to the board.
    # A box that is off is only an answer for a chip that has one -- a socket left
    # at "not recorded" stores no row at all, so saving the form cannot quietly
    # decide that a chip nobody has looked at is soldered down.
    out["sockets"] = {
        role: bool(form.get(f"chip:{role}:socketed"))
        for role in machines.roles(key)
        if out["chips"].get(role)
    }
    return out


def _machine_page(db: Session, obj: Computer | Part) -> dict[str, object] | None:
    """An asset's catalogue identity for its page: what it is filed as, then what
    makes this one of them, then the chips in the order a board is read in. None for
    an asset outside the catalogue, so the section does not appear at all.

    The same shape for a machine and for a board, because it is the same answer: a
    board is filed as an Amiga 500 exactly as the Amiga 500 it came out of is, and a
    page that said it two ways would be inviting the reader to look for a difference
    that is not there. A board simply has nothing in the two rows a case answers.

    Every label is read from the catalogue rather than from the record, so a page
    shows the current words for what was recorded -- and a chip whose socket the
    catalogue has since dropped still shows, under the role's own name, because what
    was seen on the board is not wrong for having gone out of the catalogue. The
    catalogue's line about a socket stays on the form, where it helps decide what to
    look at; here it would be the same sentence under every machine of the model.

    The row keys are machines.ISSUE_KEY and the two beside it, so the page and the
    rendered line call the same three answers by the same names."""
    v = machinedb.read(db, obj)
    if not any(v.values()):
        return None
    m = machines.model(v["model_key"])
    return {
        # The stable key as well as the words, because a page that offers an action
        # on a filed asset has to ask whether it is filed -- and the rendered model
        # name falls back to the key, so it cannot answer that.
        "key": v["model_key"],
        "model": (m["model"] if m else v["model_key"]),
        "family": m["family"] if m else "",
        "year": m["year"] if m else None,
        # What the model is, where the catalogue has it written. Read from the
        # catalogue and not the record, like every label here: the paragraph is
        # about the model, so correcting it corrects every machine filed as one.
        "summary": m.get("summary", "") if m else "",
        "rows": [
            (label, value)
            for label, value in (
                (machines.ISSUE_KEY, v["issue"]),
                (machines.STYLE_KEY, v["style"]),
                (machines.REGION_KEY, v["region"]),
            )
            if value
        ],
        "chips": [
            {
                "label": machines.chip_label(v["model_key"], role),
                "variant": variant,
                "socketed": v["sockets"].get(role),
            }
            for role, variant in v["chips"].items()
        ],
    }


def _require_disposed(obj: Computer | Part, kind: str) -> None:
    """Only a disposed item can be deleted from the GUI. Disposal is reversible
    and deletion is not, so the reversible step is made a precondition of the
    other: whatever is about to go has already been marked as gone once, on
    purpose, on an earlier day."""
    if not obj.disposed:
        raise HTTPException(
            400,
            f"{obj.asset_id} is still in the collection. Mark it disposed "
            f"first -- only a disposed {kind} can be deleted.",
        )


async def _set_for_sale(
    db: Session, model: type[Computer] | type[Part], aid: str, request: Request
) -> RedirectResponse:
    """Tick or untick "might sell" on one item (ADR-0018).

    The box on the page is the answer, so an absent field is "no": an unticked
    checkbox sends nothing at all, which is the one form control whose off state has
    to be read from its silence. The same reading gui_file_public takes of the same
    gesture, and for the same reason -- these two ticks are the same control.

    Nothing is written to the history. A shortlist is a thought about a thing, not
    something that happened to it, and a machine ticked and unticked over a month of
    Sundays would otherwise fill its own record with the owner changing their mind.
    """
    row = get_or_404(db, model, aid)
    form = await posted(request)
    row.for_sale = bool(form.get("for_sale"))
    db.commit()
    return RedirectResponse(
        f"/{'computers' if model is Computer else 'parts'}/{aid}", status_code=303
    )


def _work_from_form(db: Session, obj: Computer | Part, form: Posted) -> Project | None:
    """The work box on an entry or edit form, acted on once the item itself is saved.

    Nothing typed and nothing picked makes nothing, which is the ordinary case: most
    things arrive with nothing wrong, and a project per arrival would turn the
    projects page from a list of work into a second copy of the register.

    A picked project that names nothing becomes a project of its own rather than an
    error. The menu cannot produce one -- only a hand-made post can -- and refusing
    at this point would throw away the entry being made, photographs and all, over
    the convenience half of the gesture. The sentence is the part worth keeping."""
    jobs = _work_lines(form.get("work_needed", ""))
    picked = (form.get("work_project", "") or "").strip().upper()
    project = db.get(Project, picked) if picked else None
    if not jobs and project is None:
        return None
    return _take_on_work(db, obj.asset_id, jobs, project)


def part_thumbs(db: Session, parts: Iterable[Part]) -> dict[str, dict[str, object]]:
    """The picture to put on each part's card in a list of them, by asset id.

    A list of parts said what each one was and never showed it: "PT-0031 · storage /
    drive, Teac FD-235HF" names a floppy drive without saying whether the one in this
    machine is beige or grey, full-height or slim, or photographed at all. The
    picture is the fastest way to know which of four identical-sounding drives you
    are looking at, and the gallery card for the same part has been carrying it all
    along.

    The same reading the gallery makes of the same parts -- one folder scan and one
    query for every storage part's Kind, rather than either per row -- so a part's
    card in a machine and its card on the shelf cannot come to wear different
    pictures. Where nobody has photographed it, the drawing stands in, exactly as it
    does there; and a photograph of the model rather than of this unit says so, for
    the same reason it says so everywhere else it is shown.
    """
    listing = folder_images("parts")
    kinds = specdb.storage_kinds(db)
    thumbs: dict[str, dict[str, object]] = {}
    for p in parts:
        imgs = pick_images("parts", p.asset_id, listing)
        rel = imgs[0] if imgs else ""
        ptype = p.type or "other"
        thumbs[p.asset_id] = {
            "img": rel,
            "ref": is_reference(rel),
            "icon": _favicon_for_rel(rel),
            "ph": (
                _storage_placeholder(kinds.get(p.asset_id))
                if ptype == "storage"
                else entry.placeholder_for(ptype)
            ),
        }
    return thumbs


def delete_computer(db: Session, c: Computer, with_parts: Iterable[Part] = ()) -> list[str]:
    photos = _clear_computer_rows(db, c, with_parts)
    db.commit()
    _purge_photos(photos)
    return photos


def delete_part(db: Session, part: Part) -> list[str]:
    """Delete a part and commit. Returns the photos that went with it."""
    photos = _clear_part_rows(db, part)
    db.commit()  # the rows first: if this raises, the photos are still there
    _purge_photos(photos)
    return photos
