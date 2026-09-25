"""The pages of a part: its own page, its form, its photographs, and the machine or
board it is fitted to."""

from collections.abc import Collection, Iterable
from typing import Literal

from sqlalchemy import func


# --- GUI: parts (guided, typed entry) --------------------------------------

from ..assets import _bezel_ctx, _machine_ctx
from ..pages import _datalists
from ..photos import _storage_placeholder
from datetime import date

from fastapi import APIRouter, Depends, File, HTTPException, Request, Response, UploadFile
from fastapi.responses import HTMLResponse, RedirectResponse
from sqlalchemy.orm import Session

from .. import drivedb, entry, filesdb, labels, locations, machinedb, projects, settings, specdb
from ..assets import (
    DUP_EXCLUDE,
    PART_DERIVED_FIELDS,
    PART_FIELDS,
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
    delete_part,
    part_thumbs,
)
from ..common import to_dict
from ..db import get_db
from ..disposal import _disposal_log
from ..forms import Posted, _coerce, _field_diffs, _parse_date, posted
from ..history import _history, add_log
from ..ids import next_asset_id
from ..models import ComputerDrive, Computer, Part, StorageSpec, StoredFile
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
from ..web import _dot, _jsonld, _og, _safe_next, png_label, templates

from .. import specstruct
from fastapi import Query


def _apply_drive_picks(form: Posted, rows: list[drivedb.Drive]) -> None:
    """Put what the pickers chose on drives just read from a typed description.

    A picker is a deliberate answer, so it wins over the same thing said in the
    text; a blank one leaves what the text said. Two drives typed at once get the
    same answers, which is the only reading a single set of pickers can have.

    And the kind, where the description named none. drivedb infers "floppy" from a
    size or a form factor only a floppy has, but it infers it while reading the
    text -- so a description like "Sony MPF920", which names neither, used to leave
    a row with no kind, and picking the size rather than typing it does not reach
    that rule. The menu that routed the drive here has already said which kind it
    is, so let it answer: read through drivedb's own vocabulary rather than a
    second mapping of the same words, and only where the text did not say.
    """
    picks: dict[DrivePick, str] = {
        col: _picked_ask(form, key) or "" for key, (_f, col) in DRIVE_PICKS.items()
    }
    picks["colour"] = form.get("drive_colour", "") or ""
    picks["yellowing"] = form.get("drive_yellowing", "") or ""
    # The make and model, from the fields that ask for them. A routed drive never
    # becomes a Part, so what was typed under Identity used to be dropped on the
    # floor and the description was the only way to name the thing -- survivable
    # while the description was always on screen, not now that a floppy the pickers
    # have described does without one. Filled in where the description named
    # nothing, not over the top of it: what is left of a description after the
    # pickers have taken their share is the words they could not say (a "SS/DD"),
    # and those are the last thing to overwrite.
    named = " ".join(
        x
        for x in (
            entry.deshout((form.get("manufacturer", "") or "").strip()),
            entry.deshout((form.get("model", "") or "").strip()),
        )
        if x
    )
    # The first word of the menu's label: "Floppy/Gotek" and "SD/CF card" are pairs
    # of alternatives that drivedb reads as neither, and a Gotek names itself.
    menu = (form.get("kind", "") or "").split("/")[0]
    parsed = drivedb.parse_segment(menu)
    from_menu = parsed["kind"] if parsed else ""
    for row in rows:
        for col, picked in picks.items():
            row[col] = picked.strip() or row[col]
        row["kind"] = row["kind"] or from_menu
        row["model"] = row["model"] or named


def _part_form_ctx(
    db: Session,
    obj: Part | None,
    ptype: str,
    computer_id: str,
    parent_id: str = "",
    action: str | None = None,
) -> dict[str, object]:
    # Existing values come from the typed tables, not from re-parsing the string.
    mb_slots: dict[str, int | None] = {}
    mb_ram: dict[str, int | None] = {}
    mb_ports: dict[str, int | None] = {}
    mb_cpufams: list[str] = []
    spec_keys: dict[str, str] = {}
    if obj:
        st = specdb.read(db, obj)
        # The form's text inputs are keyed by display name, and want the same
        # rendering the item page shows ('256 KiB', not 256).
        spec_keys = {k: v for k, v in specstruct.pairs(obj.type or "other", st) if k}
        if (obj.type or "") == "motherboard":
            mb_slots = dict(st.slots)
            mb_ram = dict(st.ram_slots)
            mb_ports = dict(st.ports)
            # str(): a scalar is whatever its column holds, a number as readily as
            # a word; the families are a written list.
            mb_cpufams = [
                x.strip() for x in str(st.scalars.get("cpu_family") or "").split(",") if x.strip()
            ]
    # A stored CPU family that is not in the pick list (older rows say '486'
    # where the vocabulary says '486-class') still needs a checkbox, or saving the
    # form would silently drop it.
    cpu_families = list(entry.CPU_FAMILIES)
    cpu_families += [f for f in mb_cpufams if f not in cpu_families]
    makes, models, known = _known_makes(db)
    # A board is the one part that can answer the catalogue: it is the thing the
    # board issue and the chip sockets were always about, and a bare one on a shelf
    # is an Amiga 500 board rather than an unidentified green rectangle. Nothing
    # else is offered it -- a SIMM is not a model of machine -- and the catalogue is
    # a quarter of a megabyte of JSON, which is not shipped to a form that cannot
    # use it.
    catalogue = _machine_ctx(obj, db, board=True) if ptype == "motherboard" else {}
    return {
        **catalogue,
        "p": obj,
        "ptype": ptype,
        "computer_id": computer_id,
        "parent_id": parent_id,
        "spec_keys": spec_keys,
        "action": action or (f"/parts/{obj.asset_id}/edit" if obj else "/parts/new"),
        "makes": makes,
        "models": models,
        "known": known,
        "conditions": entry.CONDITIONS,
        "work_projects": projects.open_projects(db),
        "dl": _datalists(db),
        "vocab": {
            "form_factors": entry.MOBO_FORM_FACTORS,
            "cpu_families": cpu_families,
            "ram_slots": entry.RAM_SLOT_TYPES,
            "card_interfaces": entry.CARD_INTERFACES,
            "video_connectors": entry.VIDEO_CONNECTORS,
            "storage_interfaces": entry.STORAGE_INTERFACES,
            "storage_kinds": entry.STORAGE_KINDS,
            "storage_protocols": entry.STORAGE_PROTOCOLS,
            "peripheral_interfaces": entry.PERIPHERAL_INTERFACES,
        },
        # Every question a drive is asked, for the form to build itself from.
        "storage_asks": _storage_asks_ctx(),
        # And every question a screen is asked, the same way.
        "display_asks": _display_asks_ctx(),
        "bezel_kinds": list(entry.BEZEL_KINDS),
        "disk_image_kinds": list(entry.DISK_IMAGE_KINDS),
        "row_kinds": [k for k in entry.STORAGE_KINDS if k not in entry.PART_STORAGE_KINDS],
        "floppy_kind": entry.FLOPPY_KIND,
        "optical_kind": entry.OPTICAL_KIND,
        **_bezel_ctx(),
        "slot_names": entry.SLOT_NAMES,
        "port_names": entry.PORT_NAMES,
        "mb_slots": mb_slots,
        "mb_ram": mb_ram,
        "mb_ports": mb_ports,
        "mb_cpufams": mb_cpufams,
        # The letters the Ports box takes, a pair at a time, for the key printed
        # under it -- the one hint on the form that is not a tooltip.
        "port_codes": entry.PORT_CODES,
        "type_labels": entry.TYPE_LABELS,
        "type_order": entry.TYPE_ORDER,
    }


async def _part_from_form(
    form: Posted, ptype: str, extra: Iterable[tuple[str, str]] = ()
) -> dict[str, object]:
    data: dict[str, object] = {
        "type": ptype,
        "computer_id": form.get("computer_id", "") or None,
        "parent_id": form.get("parent_id", "") or None,
    }
    for f in (
        "manufacturer",
        "model",
        "name",
        "year",
        "serial",
        "condition",
        "source",
        "acquired_date",
        "location",
        "url",
        "summary",
        "notes",
        "disk_image",
    ):
        data[f] = _coerce(f, form.get(f, ""))
    for f in ("manufacturer", "model"):
        # str(): the dict carries a row's worth of columns and is typed as widely,
        # but a name is what was typed into a text box.
        data[f] = entry.deshout(str(data[f]))
    data["specs"] = _assemble_specs(ptype, form, extra)
    return data


def _part_placeholder(db: Session, part: Part) -> str:
    """The stand-in drawing for one part, routed exactly as the gallery routes it.

    One row read rather than the whole table: the gallery wants every storage part's
    Kind at once and this wants one, and asking the same question two ways is how
    a card and the page it opens come to disagree about what a thing looks like."""
    if (part.type or "") != "storage":
        return entry.placeholder_for(part.type or "other")
    kind = specdb.scalars(db, part).get("kind")
    return _storage_placeholder(kind if isinstance(kind, str) else None)


def _require_storage_interface(ptype: str, form: Posted) -> None:
    """A storage part has to say how it attaches, so that "every SCSI drive" stays a
    question the collection can answer. The radios are marked required, so this is
    the backstop for anything posting straight to the endpoint. A drive folded into a
    machine's drive row never reaches here: it is a field on that machine rather than
    a part, and has no interface column of its own to fill."""
    if ptype != "storage":
        return
    # Read exactly as the value that gets saved is read, or the two could disagree and
    # let a part through with an interface that is then dropped for not being one.
    picked = _picked_ask(form, "Interface")
    if picked is None:
        return
    if not picked:
        raise HTTPException(
            400,
            "a storage part needs an interface: one of "
            + ", ".join(entry.STORAGE_INTERFACES)
            + ", or custom",
        )


# The pick-or-type groups, and the drive row column each becomes where the drive is
# folded into a machine. Which kinds are asked, and what each picks from, is not
# repeated here: it comes from entry.STORAGE_ASKS, the one table the form is built
# from, so a group cannot be on screen for a kind the server reads past.
# Named as the literals they are, so that writing one into a drive row is checked
# against the row's own columns (drivedb.Drive) rather than being a string that
# happens to match one.
DrivePick = Literal["form_factor", "size", "media", "speed", "colour", "yellowing"]

DRIVE_PICKS: dict[str, tuple[str, DrivePick]] = {
    "Form factor": ("drive_form", "form_factor"),
    "Size": ("drive_size", "size"),
    "Media": ("drive_media", "media"),
    "Speed": ("drive_speed", "speed"),
}


# The form field each ask's radio group is named for: the four above keep the
# drive_-prefixed names a machine's own form posts, and the rest are named for their
# spec key like every other field on the part form.
PICK_FIELDS = {
    ask["key"]: (
        DRIVE_PICKS[ask["key"]][0]
        if ask["key"] in DRIVE_PICKS
        else "spec_" + ask["key"].lower().replace(" ", "_")
    )
    for ask in entry.STORAGE_ASKS
    if ask["options"]
}


# Which kinds each ask is offered for, straight off the table the form is built
# from, so a group cannot be on screen for a kind the server reads past.
ASK_KINDS = {ask["key"]: ask["kinds"] for ask in entry.STORAGE_ASKS}


def _picked_ask(form: Posted, key: str) -> str | None:
    """What one of those groups chose: one of the standard answers, or whatever was
    typed beside "custom" for the hardware the list does not name (a 3" Amstrad, a
    Floptical). Blank when nothing was picked, which leaves the description to say
    it.

    None -- not blank -- for a kind the group is not offered for, which is the
    difference between "asked, and the answer is nothing" and "never asked". A radio
    left checked from a kind since changed must not be saved against a drive it never
    described, and a value already on a record must not be thrown away by a group
    that was never on screen to replace it.
    """
    kind = form.get("kind", "") or ""
    if kind not in ASK_KINDS.get(key, ()):
        return None
    field = PICK_FIELDS[key]
    raw = (form.get(field, "") or "").strip()
    if raw == "custom":
        return " ".join((form.get(field + "_custom", "") or "").split())
    # Against this kind's own list, not just any of them. Media and Speed are asked
    # of more than one kind and each kind has its own vocabulary, so the groups share
    # a field name -- which means a radio left checked from a kind since changed
    # arrives here looking like an answer. A CD-RW is not something a floppy takes.
    return raw if raw in _ask_options(key, kind) else ""


def _assemble_specs(ptype: str, form: Posted, extra: Iterable[tuple[str, str]] = ()) -> str:
    """Build a part's specs string from the typed form fields, running the same
    quick-entry expanders the guided flow has always used. `extra` carries the
    (key, value) pairs the form does not manage -- read from part_attribute, which
    is where anything unrecognised or unparseable already lives -- so editing a
    part never silently drops them."""
    if ptype == "motherboard":
        return _assemble_motherboard_specs(form, extra)
    managed = {
        "motherboard": [
            "Chipset",
            "CPU family",
            "Form factor",
            "RAM slots",
            "Onboard RAM",
            "Slots",
            "Cache",
            "BIOS",
            "Onboard video",
            "Ports",
        ],
        "cpu": ["Socket", "Speed", "FSB", "Cores", "Cache"],
        "ram": ["Type", "Size", "Speed"],
        "video": ["Chip", "Interface", "Connector", "Memory", "Type"],
        "sound": ["Chip", "Interface", "FM", "Ports"],
        "network": ["Chip", "Interface", "Connector"],
        "io": ["Chip", "Interface", "Ports"],
        "storage": [
            "Kind",
            "Description",
            "Form factor",
            "Size",
            "Interface",
            "Protocol",
            "Capacity",
            "CHS",
            "Media",
            "Speed",
            "Role",
            "Colour",
            "Yellowing",
        ],
        "display": [
            "Type",
            "Panel",
            "Screen size",
            "Aspect",
            "Resolution",
            "Refresh",
            "Sync",
            "Dot pitch",
            "Interface",
            "Picture",
            "Colour",
            "Yellowing",
        ],
    }.get(ptype)
    # 'other' / 'peripheral' keep a free-text specs box (no data loss).
    if managed is None:
        return " ".join((form.get("specs", "") or "").split())
    # One managed key whose box is not named for it: the drive description is
    # typed into the same field that feeds a machine's drive row, so it is named
    # for that job. Routed to a machine it becomes the row and never reaches
    # here; kept as a part, this is what stops it being dropped on the floor.
    fields = {"Description": "drive_desc"}
    specs = ""
    for key in managed:
        # spec_ prefix keeps these clear of the part's own columns (a RAM
        # 'Type' spec vs the part type, etc.).
        field = fields.get(key) or _spec_field(key)
        raw: str | None = None
        if ptype == "display" and key in DISPLAY_ASK_BY_KEY:
            # Picked from a group rather than typed into one box. Its answer stands,
            # blank included -- that is how a value is taken back off.
            raw = _picked_display(form, DISPLAY_ASK_BY_KEY[key])
        elif ptype == "storage" and key in PICK_FIELDS:
            # Picked from a radio group with a box beside it, not typed into one
            # input, and read only for the kinds the group is offered for. Where it
            # is offered its answer stands, blank included -- that is how a value is
            # taken back off -- and where it is not, nothing here replaces what the
            # record already said.
            raw = _picked_ask(form, key)
        if raw is None:
            raw = (form.get(field, "") or "").strip()
        if not raw:
            continue
        if key == "Ports":
            raw = entry.expand_ports(raw)
        elif key == "Slots":
            raw = entry.expand_slots(raw)
        elif key in ("Size", "Memory") and ptype != "storage":
            # A memory amount is a quantity, and normalises to KiB so it sorts and
            # compares. A drive's size is a media designation and must not: 1.44MB
            # is 1475 KiB only by convention, and nobody calls that disk a 1475 KiB.
            raw = entry.normalise_amount(key, raw)
        specs = entry.merge_spec(specs, key, raw)
    return _append_unmanaged(specs, extra, managed)


def _storage_asks_ctx() -> list[dict[str, object]]:
    """entry.STORAGE_ASKS dressed for the form: the field each group posts, how long a
    custom answer may be, and whether the answer has anywhere to go on a machine's
    drive row -- the four that do are the only ones still asked once a drive is folded
    into a machine, the rest being fields on a part that will not exist."""
    return [
        ask
        | {
            "field": PICK_FIELDS.get(ask["key"], _spec_field(ask["key"])),
            "max": _ASK_WIDTHS.get(ask["key"], 255),
            "row": ask["key"] in DRIVE_PICKS,
            "kinds": list(ask["kinds"]),
        }
        for ask in entry.STORAGE_ASKS
    ]


def _display_asks_ctx() -> list[dict[str, object]]:
    """entry.DISPLAY_ASKS dressed for the form: the field each group posts."""
    return [ask | {"field": DISPLAY_FIELDS[ask["key"]]} for ask in entry.DISPLAY_ASKS]


def _known_makes(db: Session) -> tuple[list[str], list[str], list[dict[str, str | None]]]:
    """The manufacturers and (make, model) pairs already recorded, for the new-part
    form's pick lists and for spotting that a part being entered is a second of
    something already here. One representative asset id per pair, so the form can
    offer to start from it.

    The makes come from both tables. A part's maker and a machine's are the same
    kind of fact and often the same company -- the Amstrad that made the machine
    made the board in it -- so a make used only on computers is still worth
    offering here; the (make, model) pairs stay parts-only, because what they are
    for is starting a new part from an identical one."""
    makes = _answers_given(db, Part.manufacturer, Computer.manufacturer)
    pairs = (
        db.query(Part.manufacturer, Part.model, Part.type, func.max(Part.asset_id))
        .filter(Part.manufacturer != "", Part.model != "")
        .group_by(Part.manufacturer, Part.model, Part.type)
        .all()
    )
    known = [{"m": mk, "d": md, "t": t, "id": aid} for mk, md, t, aid in pairs]
    models = sorted({p["d"] for p in known})
    return makes, models, known


DISPLAY_ASK_BY_KEY = {ask["key"]: ask for ask in entry.DISPLAY_ASKS}


def _spec_field(key: str) -> str:
    """The form field a spec key is asked with. The spec_ prefix keeps these clear of
    the part's own columns (a RAM 'Type' spec vs the part type, etc.)."""
    return "spec_" + key.lower().replace(" ", "_").replace("/", "_")


# The field each display ask posts, named for its spec key like every other field
# on this form. One mapping, used to build the form and to read it back.
DISPLAY_FIELDS = {ask["key"]: _spec_field(ask["key"]) for ask in entry.DISPLAY_ASKS}


# How long a typed "custom" answer may be: the column the answer lands in. The four
# that can become a machine's drive row are held to the row's width, because a picker
# that let you type more than the column holds would fail on save.
_ASK_WIDTHS = {
    "Form factor": ComputerDrive.form_factor.type.length,
    "Size": ComputerDrive.size.type.length,
    "Media": ComputerDrive.media.type.length,
    "Speed": ComputerDrive.speed.type.length,
    "Interface": StorageSpec.interface.type.length,
    "Protocol": StorageSpec.protocol.type.length,
}


def _append_unmanaged(
    specs: str, extra: Iterable[tuple[str, str]], managed: Collection[str]
) -> str:
    """Carry across the spec values the form does not manage. Keyed ones merge by
    key; keyless ones (bare values from the old CSV import, e.g. 'ES1869F') are
    appended verbatim -- they have no key to merge on and used to be dropped."""
    keyless: list[str] = []
    for k, v in extra:
        if not k:
            keyless.append(v)
        elif k not in managed:
            specs = entry.merge_spec(specs, k, v)
    for v in keyless:
        specs = f"{specs} | {v}" if specs else v
    return specs


def _ask_options(key: str, kind: str) -> Collection[str]:
    """The answers one kind is offered for one ask, () where it is asked with a text
    box instead."""
    for ask in entry.storage_asks(kind):
        if ask["key"] == key:
            return ask["options"] or ()
    return ()


def _assemble_motherboard_specs(form: Posted, extra: Iterable[tuple[str, str]] = ()) -> str:
    """Build a motherboard's specs from the structured grids (slot/RAM/port
    counts and CPU-family checkboxes) plus the plain text fields."""
    pairs = [
        ("Chipset", (form.get("spec_chipset", "") or "").strip()),
        ("CPU family", ", ".join(form.getlist("cpufam"))),
        ("Form factor", (form.get("spec_form_factor", "") or "").strip()),
        ("RAM slots", entry.format_counts(_counts_from_form(form, "ram", entry.RAM_SLOT_TYPES))),
        ("Onboard RAM", (form.get("spec_onboard_ram", "") or "").strip()),
        ("Slots", entry.format_counts(_counts_from_form(form, "slot", entry.SLOT_NAMES))),
        ("Cache", (form.get("spec_cache", "") or "").strip()),
        ("BIOS", (form.get("spec_bios", "") or "").strip()),
        ("Onboard video", (form.get("spec_onboard_video", "") or "").strip()),
        ("Ports", entry.format_counts(_counts_from_form(form, "port", entry.PORT_NAMES))),
    ]
    return _append_unmanaged(entry.build_specs(pairs), extra, [k for k, _ in pairs])


def _picked_display(form: Posted, ask: entry.DisplayAsk) -> str:
    """What one of a screen's groups chose.

    One of the offered answers, or whatever was typed beside "custom" for the
    hardware the list does not name. Blank when nothing was picked, which is how an
    answer is taken back off again.

    An answer is checked against the list it was offered from before it is kept, the
    same way a drive's is: a value posted straight to the endpoint that was never on
    the form is not an answer to the question that was asked.
    """
    field = DISPLAY_FIELDS[ask["key"]]
    custom = " ".join((form.get(field + "_custom", "") or "").split())
    if ask.get("multi"):
        # Several sockets, in the order the list offers them, and then whatever the
        # list could not name -- so the rendering is stable whichever order they
        # were ticked in.
        ticked = [v for v in form.getlist(field) if v in ask["options"]]
        return ", ".join([*ticked, *([custom] if custom else [])])
    raw = (form.get(field, "") or "").strip()
    if raw == "custom":
        return custom
    return raw if raw in ask["options"] else ""


def _counts_from_form(form: Posted, prefix: str, names: Iterable[str]) -> list[tuple[str, int]]:
    """Read a grid of per-name number inputs (name='<prefix>:<n>') into
    [(name, count), ...], skipping zeros/blanks."""
    out: list[tuple[str, int]] = []
    for name in names:
        raw = (form.get(f"{prefix}:{name}", "") or "").strip()
        try:
            n = int(raw)
        except ValueError:
            n = 0
        if n > 0:
            out.append((name, n))
    return out


router = APIRouter()


@router.get("/parts/new", response_class=HTMLResponse, include_in_schema=False)
def gui_new_part(
    request: Request,
    type: str = "",
    computer_id: str = "",
    parent_id: str = "",
    db: Session = Depends(get_db),
    source: str = Query("", alias="from"),
) -> HTMLResponse:
    """The new-part form. `from` starts it filled in from an existing part -- the
    same fields duplicating one copies, so a second of something already recorded
    is a couple of clicks rather than retyping its specs. Nothing is saved until
    the form is submitted, so it can be edited first, which is the difference
    between this and the duplicate button."""
    src = db.get(Part, source.upper()) if source else None
    if src is None:
        # No type given is the machine page's one "add part" button: the form opens
        # on "other" and the heading does not claim a type nobody has chosen yet.
        ctx = _part_form_ctx(db, None, type or "other", computer_id, parent_id)
        ctx["title"] = f"New {entry.type_label(type)}" if type else "New part"
        return templates.TemplateResponse(request, "part_form.html", ctx)

    ptype = src.type or type or "other"
    ctx = _part_form_ctx(db, src, ptype, computer_id, parent_id, action="/parts/new")
    # A transient Part, never added to the session: the descriptive fields of the
    # source with everything belonging to that particular object left out.
    ctx["p"] = Part(
        **{
            k: getattr(src, k)
            for k in PART_FIELDS
            if k not in DUP_EXCLUDE and k not in PART_DERIVED_FIELDS
        }
    )
    ctx["title"] = f"New {entry.type_label(ptype)}"
    ctx["from_part"] = src.asset_id
    # The same rule the duplicate button follows: another board of this model is
    # another board of this model, but which revision it is and what is in its
    # sockets are found by looking at the board in your hand.
    saved = ctx.get("machine_saved")
    if saved and isinstance(saved, dict):
        ctx["machine_saved"] = dict(machinedb.BLANK) | {"model_key": saved["model_key"]}
    return templates.TemplateResponse(request, "part_form.html", ctx)


@router.post("/parts/new", include_in_schema=False)
async def gui_create_part(request: Request, db: Session = Depends(get_db)) -> RedirectResponse:
    form = await posted(request)
    photos = _chosen_photos(form)
    ptype = form.get("type", "other") or "other"
    computer_id = form.get("computer_id", "") or ""
    # Storage routing: floppy / optical / SD-CF live on the computer's drives
    # field; only hard disks and tape become their own tagged parts.
    if ptype == "storage":
        kind = form.get("kind", "") or ""
        if kind and kind not in entry.PART_STORAGE_KINDS:
            # With nothing typed, the kind names the drive -- but the menu's label
            # is a pair of alternatives ("Floppy/Gotek", "SD/CF card") that the
            # parser reads as neither, and files as a model. Hand it the first
            # word, which is a word it knows. Picking only a capacity and typing
            # no description is an ordinary gesture now the picker exists.
            desc = (form.get("drive_desc", "") or "").strip() or kind.split("/")[0]
            if computer_id:
                c = get_or_404(db, Computer, computer_id)
                # Append a row, not text: drives is rendered from the rows, so
                # anything written straight to it would vanish on the next save.
                added = drivedb.from_string(desc)[0]
                _apply_drive_picks(form, added)
                drivedb.write(db, c, drivedb.read(db, c) + added)
                # The canonical rendering rather than what was typed, so the history
                # names the bezel that was picked from the menus as well.
                add_log(db, computer_id, f"added drive: {drivedb.render(added) or desc}")
                # This drive is a field on the machine rather than an asset of its
                # own, so it has no tag of its own to file a photo under: any that
                # were chosen belong to the machine the drive went into.
                if photos:
                    _attach_photos(db, c, "computers", photos)
                # And for the same reason, work noted while adding it is the
                # machine's: the drive is a field on that record and has no tag of
                # its own for a project to be about.
                _work_from_form(db, c, form)
                db.commit()
                return RedirectResponse(f"/computers/{computer_id}?build=1", status_code=303)
    _require_storage_interface(ptype, form)
    data = await _part_from_form(form, ptype)
    if ptype == "storage":
        data["specs"] = entry.merge_spec(str(data["specs"]), "Kind", form.get("kind", "") or "")
        # A routed kind with no machine to route to becomes a part after all, so a
        # bezel picked on that path comes with it rather than being dropped on the
        # floor -- the part's own menus were not on screen to say otherwise.
        for key, routed, own in (
            ("Colour", "drive_colour", "spec_colour"),
            ("Yellowing", "drive_yellowing", "spec_yellowing"),
        ):
            picked = (form.get(routed, "") or "").strip()
            if picked and not (form.get(own, "") or "").strip():
                data["specs"] = entry.merge_spec(str(data["specs"]), key, picked)
    obj = Part(asset_id=next_asset_id(db), **data)
    db.add(obj)
    db.flush()
    specdb.write(db, obj)
    # Only a board is filed against the catalogue, whatever a hand-made post claims:
    # the pickers are on no other type's form, and a SIMM filed as a Commodore 64
    # would be a record of nothing anybody owns.
    if ptype == "motherboard" and (mach := _machine_from_form(form, board=True)) is not None:
        machinedb.write(db, obj, **mach)
    add_log(db, obj.asset_id, "created", "created")
    locations.remember(db, obj.location)
    _work_from_form(db, obj, form)
    db.commit()
    if photos:
        _attach_photos(db, obj, "parts", photos)
        db.commit()
    parent_id = form.get("parent_id", "") or ""
    dest = (
        f"/computers/{computer_id}?build=1"
        if computer_id
        else f"/parts/{parent_id}"
        if parent_id
        else f"/parts/{obj.asset_id}"
    )
    return RedirectResponse(dest, status_code=303)


@router.get("/parts/{aid}", response_class=HTMLResponse, include_in_schema=False)
def gui_part(
    aid: str, request: Request, imgerr: int = 0, fileerr: int = 0, db: Session = Depends(get_db)
) -> HTMLResponse:
    p = get_or_404(db, Part, aid)
    parent = db.get(Computer, p.computer_id) if p.computer_id else None
    host = db.get(Part, p.parent_id) if p.parent_id else None
    children = db.query(Part).filter(Part.parent_id == aid).order_by(Part.asset_id).all()
    candidates, computers = [], []
    if request.state.authed:
        candidates = (
            db.query(Part)
            .filter(Part.type == "storage", Part.asset_id != aid, Part.parent_id.is_(None))
            .order_by(Part.asset_id)
            .all()
        )
        if not p.computer_id and not p.parent_id:
            computers = db.query(Computer).order_by(Computer.asset_id).all()
    images = detect_images("parts", aid)
    # Where this part is because of what it is fitted in. Asked only of a part that
    # holds no answer of its own -- its own always wins -- and only for a reader who
    # is shown locations, because working one out for a row that cannot be rendered
    # is two queries spent on nothing.
    placed = None
    if not p.location.strip() and (request.state.sees_private or settings.on("public_locations")):
        placed = locations.inherited(db).get(aid)
    spec_pairs = specdb.pairs(db, p, display=True)
    # The preview text and the structured data are read rather than parsed, so they
    # say the figures the page says -- not the stored string's exact-to-the-KiB ones.
    blurb = p.summary or _dot(
        entry.type_label(p.type),
        " ".join(x for x in (p.manufacturer, p.model, str(p.year or "")) if x),
        specstruct.join(spec_pairs),
    )
    return templates.TemplateResponse(
        request,
        "part.html",
        {
            "machine": _machine_page(db, p),
            "p": p,
            "parent": parent,
            "host": host,
            "children": children,
            "thumbs": part_thumbs(db, children),
            "item": (pdict := to_dict(p)),
            "kind": "parts",
            **filesdb.panel(db, pdict, request.state.authed, request.state.sees_private),
            "fileerr": bool(fileerr),
            "dl_filenotes": _answers_given(db, StoredFile.note),
            "on_project": (found := projects.project_for(db, aid, request.state.sees_private)),
            "item_tasks": projects.tasks_for_asset(db, aid, request.state.sees_private),
            "project_tasks": (
                projects.project_wide_tasks(db, found.asset_id) if found is not None else []
            ),
            # For the picker in that panel, which only an owner is shown -- so a
            # visitor's page does not ask the question at all.
            "work_projects": (projects.open_projects(db) if request.state.authed else []),
            "candidates": candidates,
            # None unless this part is placed by something it is fitted in (above).
            "placed": placed,
            "computers": computers,
            "images": images,
            "placeholder": _part_placeholder(db, p),
            "ref_marks": reference_marks("parts", aid),
            "tuned": tuned_photos("parts", aid),
            "spec_pairs": spec_pairs,
            "imgerr": bool(imgerr),
            "log": _history(db, aid),
            "nav": _item_nav(db, aid),
            "live_aid": aid,
            "live_v": _change_token(db, aid),
            "og": (
                og := _og(
                    request, entry.display_name(to_dict(p)), blurb, images[0] if images else None
                )
            ),
            "jsonld": _jsonld(
                og, p.asset_id, p.manufacturer, entry.type_label(p.type) or "Computer part"
            ),
        },
    )


@router.get("/parts/{aid}/edit", response_class=HTMLResponse, include_in_schema=False)
def gui_edit_part(
    aid: str, request: Request, type: str = "", db: Session = Depends(get_db)
) -> HTMLResponse:
    """The edit form. `type` builds it for a type other than the one the part is
    filed under, which is what the type menu asks for: what a part is asked depends
    on its type, so changing that has to fetch the form again to have the new
    type's fields on screen at all. Nothing is saved by looking -- the record still
    says what it always did until the form is submitted.

    Only a type the register knows. A made-up one would fall through to the
    free-text box and then become the part's type on save, which is a way to file a
    SIMM as a "gizmo" by editing a URL."""
    p = get_or_404(db, Part, aid)
    ptype = type if type in entry.TYPE_ORDER else (p.type or "other")
    ctx = _part_form_ctx(db, p, ptype, p.computer_id or "", p.parent_id or "")
    ctx["title"] = f"Edit {aid}"
    return templates.TemplateResponse(request, "part_form.html", ctx)


@router.post("/parts/{aid}/edit", include_in_schema=False)
async def gui_save_part(
    aid: str, request: Request, db: Session = Depends(get_db)
) -> RedirectResponse:
    p = get_or_404(db, Part, aid)
    form = await posted(request)
    ptype = form.get("type", p.type or "") or "other"
    _require_storage_interface(ptype, form)
    # Unmanaged keys live in part_attribute; carry them across the edit.
    #
    # Retyping is the case that needs more than those. A part's structured specs are
    # read from the table its old type owns, and only what would not fit there is an
    # attribute -- so on the way to a type with different questions, everything that
    # did fit was being dropped on the floor. Retyping a video card to a display kept
    # nothing but what the display form itself asked: the chip it was built round and
    # how much memory it had simply went.
    #
    # So when the type changes, everything the old type recorded comes across as
    # unmanaged, and _append_unmanaged keeps whatever the new form has no question
    # for. A key both types ask about is left to the form, because that is the answer
    # somebody has just given to a question they were actually shown.
    old_type = p.type or "other"
    carried = specdb.pairs(db, p) if ptype != old_type else specdb.read(db, p).attributes
    data = await _part_from_form(form, ptype, carried)
    if ptype == "storage" and (form.get("kind", "") or ""):
        data["specs"] = entry.merge_spec(str(data["specs"]), "Kind", form.get("kind", ""))
    old = {k: getattr(p, k) for k in data}
    for k, v in data.items():
        setattr(p, k, v)
    specdb.write(db, p)
    if ptype == "motherboard":
        if (mach := _machine_from_form(form, board=True)) is not None:
            machinedb.write(db, p, **mach)
    elif p.variant:
        # Retyped out of being a board, and the catalogue answer goes with it: a
        # record saying this RAM stick is an Amiga 500 board describes nothing
        # anybody owns. The same rule as filing a machine out of the catalogue.
        machinedb.clear(db, p)
    diff = _field_diffs(old, {k: getattr(p, k) for k in data}, list(data), semantic_specs=True)
    if diff:
        add_log(db, aid, diff)
    locations.remember(db, p.location)
    _work_from_form(db, p, form)
    db.commit()
    return RedirectResponse(f"/parts/{aid}", status_code=303)


@router.post("/parts/{aid}/duplicate", include_in_schema=False)
def gui_duplicate_part(aid: str, db: Session = Depends(get_db)) -> RedirectResponse:
    """A second identical part. On a board the catalogue model comes across for the
    same reason the model field does -- another Amiga 500 board is another Amiga 500
    board -- and the revision and the chips do not, because those are read off the
    board in your hand rather than off the one it was copied from."""
    src = get_or_404(db, Part, aid)
    data = {
        k: getattr(src, k)
        for k in PART_FIELDS
        if k not in DUP_EXCLUDE and k not in PART_DERIVED_FIELDS
    }
    obj = Part(asset_id=next_asset_id(db), **data)
    db.add(obj)
    db.flush()
    specdb.write(db, obj)
    machinedb.duplicated_from(db, src, obj)
    add_log(db, obj.asset_id, f"created as a duplicate of {aid}", kind="created")
    add_log(db, aid, f"duplicated to {obj.asset_id}", kind="duplicate")
    db.commit()
    return RedirectResponse(f"/parts/{obj.asset_id}", status_code=303)


@router.post("/parts/{aid}/for-sale", include_in_schema=False)
async def gui_part_for_sale(
    aid: str, request: Request, db: Session = Depends(get_db)
) -> RedirectResponse:
    return await _set_for_sale(db, Part, aid, request)


@router.post("/parts/{aid}/dispose", include_in_schema=False)
async def gui_dispose_part(
    aid: str, request: Request, db: Session = Depends(get_db)
) -> RedirectResponse:
    p = get_or_404(db, Part, aid)
    form = await posted(request)
    p.disposed = True
    p.disposed_at = _parse_date(form.get("date", "")) or date.today()
    p.disposed_note = form.get("note", "") or ""
    add_log(db, aid, _disposal_log(p))
    db.commit()
    return RedirectResponse(f"/parts/{aid}", status_code=303)


@router.post("/parts/{aid}/restore", include_in_schema=False)
def gui_restore_part(aid: str, db: Session = Depends(get_db)) -> RedirectResponse:
    p = get_or_404(db, Part, aid)
    p.disposed = False
    p.disposed_at = None
    p.disposed_note = ""
    add_log(db, aid, "restored")
    db.commit()
    return RedirectResponse(f"/parts/{aid}", status_code=303)


@router.get("/parts/{aid}/delete", response_class=HTMLResponse, include_in_schema=False)
def gui_delete_part_form(aid: str, request: Request, db: Session = Depends(get_db)) -> HTMLResponse:
    p = get_or_404(db, Part, aid)
    _require_disposed(p, "part")
    return templates.TemplateResponse(request, "delete.html", _delete_ctx(request, db, "parts", p))


@router.post("/parts/{aid}/delete", include_in_schema=False)
async def gui_delete_part(aid: str, request: Request, db: Session = Depends(get_db)) -> Response:
    p = get_or_404(db, Part, aid)
    _require_disposed(p, "part")
    form = await posted(request)
    if not _confirms_url(form.get("confirm", ""), "parts", p.asset_id):
        return templates.TemplateResponse(
            request,
            "delete.html",
            _delete_ctx(
                request, db, "parts", p, error="That is not this item's URL. Nothing was deleted."
            ),
            status_code=400,
        )
    # Back to the machine it was in if it was in one, since that page is now a
    # part short and is the thing worth looking at; otherwise to the gallery.
    where = f"/computers/{p.computer_id}" if p.computer_id else "/"
    delete_part(db, p)
    return RedirectResponse(where, status_code=303)


@router.post("/parts/{aid}/note", include_in_schema=False)
async def gui_part_note(
    aid: str, request: Request, db: Session = Depends(get_db)
) -> RedirectResponse:
    get_or_404(db, Part, aid)
    _note_with_photos(db, aid, await posted(request))
    return RedirectResponse(f"/parts/{aid}", status_code=303)


@router.post("/parts/{aid}/photo", include_in_schema=False)
async def gui_part_photo(
    aid: str, photos: list[UploadFile] = File(...), db: Session = Depends(get_db)
) -> RedirectResponse:
    p = get_or_404(db, Part, aid)
    first = None
    n = 0
    for up in photos:
        if (up.filename or "").strip():
            rel = _save_photo("parts", aid, up)
            n += 1
            if first is None:
                first = rel
    if first and not p.image:
        p.image = first
    if n:
        add_log(db, aid, f"added {n} photo(s)")
    db.commit()
    return RedirectResponse(f"/parts/{aid}", status_code=303)


@router.post("/parts/{aid}/fetch-image", include_in_schema=False)
def gui_part_fetch_image(aid: str, db: Session = Depends(get_db)) -> RedirectResponse:
    p = get_or_404(db, Part, aid)
    rel = _fetch_reference_photo("parts", aid, p.url or "") if p.url else None
    if rel:
        if not p.image:
            p.image = rel
        add_log(db, aid, "fetched a photo from the reference")
        db.commit()
    return RedirectResponse(f"/parts/{aid}" + ("" if rel else "?imgerr=1"), status_code=303)


@router.post("/parts/{aid}/unlink", include_in_schema=False)
async def gui_unlink_part(
    aid: str, request: Request, db: Session = Depends(get_db)
) -> RedirectResponse:
    p = get_or_404(db, Part, aid)
    form = await posted(request)
    nxt = form.get("next", "") or f"/parts/{aid}"
    old_cid = p.computer_id
    p.computer_id = None
    if old_cid:
        add_log(db, aid, f"unlinked from computer {old_cid}")
    db.commit()
    return RedirectResponse(_safe_next(nxt), status_code=303)


@router.post("/parts/{aid}/link", include_in_schema=False)
async def gui_link_part_to_computer(
    aid: str, request: Request, db: Session = Depends(get_db)
) -> RedirectResponse:
    """Install this part into an existing computer (chosen from the part page)."""
    p = get_or_404(db, Part, aid)
    form = await posted(request)
    cid = form.get("computer_id", "") or ""
    if cid:
        get_or_404(db, Computer, cid)
        p.computer_id = cid
        p.parent_id = None
        add_log(db, aid, f"installed in {cid}")
        add_log(db, cid, f"linked part {aid}")
        db.commit()
    return RedirectResponse(f"/parts/{aid}", status_code=303)


@router.post("/parts/{aid}/attach", include_in_schema=False)
async def gui_attach_part(
    aid: str, request: Request, db: Session = Depends(get_db)
) -> RedirectResponse:
    """Mount another part onto this one (e.g. a hard disk on a controller card)."""
    get_or_404(db, Part, aid)
    form = await posted(request)
    pid = form.get("part_id", "") or ""
    if not pid:
        return RedirectResponse(f"/parts/{aid}", status_code=303)
    child = get_or_404(db, Part, pid)
    child.parent_id = aid
    child.computer_id = None
    add_log(db, aid, f"mounted {child.asset_id}")
    add_log(db, child.asset_id, f"mounted on {aid}")
    db.commit()
    return RedirectResponse(f"/parts/{aid}", status_code=303)


@router.post("/parts/{aid}/detach", include_in_schema=False)
async def gui_detach_part(
    aid: str, request: Request, db: Session = Depends(get_db)
) -> RedirectResponse:
    p = get_or_404(db, Part, aid)
    form = await posted(request)
    old_host = p.parent_id
    p.parent_id = None
    if old_host:
        add_log(db, aid, f"unmounted from {old_host}")
    db.commit()
    return RedirectResponse(_safe_next(form.get("next", "") or f"/parts/{aid}"), status_code=303)


@router.post("/parts/{aid}/primary-photo", include_in_schema=False)
async def gui_part_primary(
    aid: str, request: Request, db: Session = Depends(get_db)
) -> RedirectResponse:
    p = get_or_404(db, Part, aid)
    form = await posted(request)
    p.image = _set_primary_photo("parts", aid, form.get("image", ""))
    add_log(db, aid, "changed the default photo")
    db.commit()
    return RedirectResponse(f"/parts/{aid}", status_code=303)


@router.post("/parts/{aid}/photo-delete", include_in_schema=False)
async def gui_part_photo_delete(
    aid: str, request: Request, db: Session = Depends(get_db)
) -> RedirectResponse:
    p = get_or_404(db, Part, aid)
    form = await posted(request)
    was_primary, new_primary = _delete_image("parts", aid, form.get("image", ""))
    if was_primary:
        p.image = new_primary or ""
    add_log(db, aid, "deleted a photo")
    db.commit()
    return RedirectResponse(f"/parts/{aid}", status_code=303)


@router.post("/parts/{aid}/photo-reference", include_in_schema=False)
async def gui_part_photo_reference(
    aid: str, request: Request, db: Session = Depends(get_db)
) -> RedirectResponse:
    p = get_or_404(db, Part, aid)
    form = await posted(request)
    rel = form.get("image", "")
    if rel not in detect_images("parts", aid):
        raise HTTPException(404, "no such photo for this item")
    on = form.get("set", "1") == "1"
    _mark_reference(rel, on, (form.get("note", "") or "").strip(), p.url or "")
    add_log(
        db, aid, "flagged a photo as a reference image" if on else "unflagged a reference photo"
    )
    db.commit()
    return RedirectResponse(f"/parts/{aid}", status_code=303)


@router.get("/parts/{aid}/edit-photo", response_class=HTMLResponse, include_in_schema=False)
def gui_part_edit_photo(aid: str, image: str = "") -> RedirectResponse:
    return _photo_edit_redirect("parts", aid, image)


@router.post("/parts/{aid}/photo-rotate", include_in_schema=False)
async def gui_part_photo_rotate(
    aid: str, request: Request, db: Session = Depends(get_db)
) -> RedirectResponse:
    form = await posted(request)
    _do_photo_rotate(db, Part, "parts", aid, form)
    return RedirectResponse(_safe_next(form.get("next") or f"/parts/{aid}"), status_code=303)


@router.post("/parts/{aid}/photo-tuneup", include_in_schema=False)
async def gui_part_photo_tuneup(
    aid: str, request: Request, db: Session = Depends(get_db)
) -> RedirectResponse:
    form = await posted(request)
    _do_photo_tuneup(db, Part, "parts", aid, form)
    return RedirectResponse(_safe_next(form.get("next") or f"/parts/{aid}"), status_code=303)


@router.post("/parts/{aid}/photo-revert", include_in_schema=False)
async def gui_part_photo_revert(
    aid: str, request: Request, db: Session = Depends(get_db)
) -> RedirectResponse:
    form = await posted(request)
    _do_photo_revert(db, Part, "parts", aid, form)
    return RedirectResponse(_safe_next(form.get("next") or f"/parts/{aid}"), status_code=303)


@router.post("/parts/{aid}/photo-crop", include_in_schema=False)
async def gui_part_photo_crop(
    aid: str, request: Request, db: Session = Depends(get_db)
) -> RedirectResponse:
    form = await posted(request)
    _do_photo_crop(db, Part, "parts", aid, form)
    return RedirectResponse(_safe_next(form.get("next") or f"/parts/{aid}"), status_code=303)


@router.get("/parts/{aid}/label.png", include_in_schema=False)
def gui_part_label_png(
    aid: str, media: str = "", dpi: int = 0, db: Session = Depends(get_db)
) -> Response:
    p = get_or_404(db, Part, aid)
    return png_label(
        to_dict(p), labels.PART, media, dpi, spec_pairs=specdb.pairs(db, p, display=True)
    )


@router.get("/parts/{aid}/label.pdf", include_in_schema=False)
def gui_part_label(aid: str, small: int = 1, db: Session = Depends(get_db)) -> Response:
    p = get_or_404(db, Part, aid)
    pdf = labels.render_pdf(
        to_dict(p), [], labels.PART, small=bool(small), spec_pairs=specdb.pairs(db, p, display=True)
    )
    return Response(
        pdf,
        media_type="application/pdf",
        headers={"Content-Disposition": f'inline; filename="{aid}{"-small" if small else ""}.pdf"'},
    )
