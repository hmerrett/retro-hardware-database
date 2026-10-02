"""The location pages: a shelf, a box or a bag as a page of its own, and the forms
that make and change one (MANUAL §14; ADR-0034).

A location is in the register like a machine is, so its page is built from the same
parts -- the photographs, the history, the label panel -- and its routes have the
same shape. Two things are its own. What is in it is the body of the page, because
"what's here?" is the question somebody scanning a shelf has. And who may see it is
the Show locations switch, asked at every route rather than at the gate: a visitor
kept out gets the 404 a private project gives, which is the same answer as for a
tag nothing has, so the label on a box says nothing about the box to a stranger.
"""

from fastapi import APIRouter, Depends, File, HTTPException, Request, Response, UploadFile
from fastapi.responses import HTMLResponse, RedirectResponse
from sqlalchemy.orm import Session

from .. import entry, labels, locations
from ..assets import (
    _do_photo_crop,
    _do_photo_revert,
    _do_photo_rotate,
    _do_photo_tuneup,
    refused,
)
from ..common import to_dict
from ..db import get_db
from ..forms import Posted, Refusal, posted
from ..history import _history, add_log
from ..ids import next_asset_id
from ..models import Computer, Location, Part
from ..pages import _note_with_photos
from ..photos import (
    _delete_image,
    _photo_edit_redirect,
    _purge_photos,
    _save_photo,
    _set_primary_photo,
    detect_images,
    reference_marks,
    tuned_photos,
)
from ..register import _change_token, get_or_404
from ..web import _og, _safe_next, png_label, templates

router = APIRouter()

KIND = "locations"


def _shown_or_404(request: Request, db: Session, aid: str) -> Location:
    """The location, for a reader who is told where things are kept; otherwise the
    404 a tag nothing has gets (ADR-0034)."""
    if not locations.shown(request.state.sees_private):
        raise HTTPException(404, f"no location {(aid or '').upper()}")
    return get_or_404(db, Location, aid)


def _card(thing: Computer | Part) -> dict[str, object]:
    """A thing kept here, as a gallery card draws one."""
    folder = "computers" if isinstance(thing, Computer) else "parts"
    images = detect_images(folder, thing.asset_id)
    if isinstance(thing, Computer):
        cat, ph = "Computer", entry.placeholder_for("computer")
    else:
        cat, ph = (
            entry.type_label(thing.type or "other"),
            entry.placeholder_for(thing.type or "other"),
        )
    return {
        "obj": thing,
        "kind": "computer" if isinstance(thing, Computer) else "part",
        "name": entry.display_name(to_dict(thing)),
        "image": images[0] if images else "",
        "placeholder": ph,
        "cat_label": cat,
        "year": thing.year or "",
    }


def _form_ctx(
    db: Session, loc: Location | None, title: str, tree: locations.Tree
) -> dict[str, object]:
    return {
        "loc": loc,
        "title": title,
        "kinds": locations.KINDS,
        # Where it is, as the Inside box holds it -- the path to the location it is
        # inside -- and every location it could be put inside, by path. Not itself
        # nor anything in it: a box cannot go in a bag that is in the box, and a list
        # that offered one would be offering a refusal.
        "inside_text": tree.text(loc.parent_id) if loc is not None else "",
        "inside_choices": [
            tree.text(tag)
            for tag in sorted(tree.rows, key=lambda t: tree.text(t).casefold())
            if loc is None or not (tag == loc.asset_id or tag in tree.within(loc.asset_id))
        ],
        "noindex": True,
    }


def _read_form(
    db: Session, form: Posted, loc: Location | None, tree: locations.Tree
) -> tuple[dict[str, str], list[Refusal], Location | None]:
    """What the location form was given: the fields, what is wrong with them, and
    the location it is to go inside."""
    name = (form.get("name", "") or "").strip()
    kind = (form.get("kind", "") or "").strip().lower()
    notes = (form.get("notes", "") or "").strip()
    errors: list[Refusal] = []
    if not name:
        errors.append(("name", "Name", "A location needs a name."))
    if kind not in locations.KIND_NAMES:
        errors.append(("kind", "Kind", "Choose one of the kinds offered."))
    parent = None
    try:
        parent = locations.choose(db, form.get("parent", ""), tree)
    except locations.Refused as err:
        errors.append(("parent", "Inside", str(err)))
    if loc is not None and parent is not None and tree.would_loop(loc.asset_id, parent.asset_id):
        errors.append(
            ("parent", "Inside", f"{loc.name} cannot go inside itself, or inside anything in it.")
        )
    return {"name": name[:255], "kind": kind, "notes": notes}, errors, parent


@router.get("/locations", response_class=HTMLResponse, include_in_schema=False)
def gui_locations(request: Request, db: Session = Depends(get_db)) -> HTMLResponse:
    """Every location, as the tree it is (MANUAL §14, "Every location"). Behind the
    switch a location's page is behind, and kept from a visitor with the answer an
    address nothing is at gets."""
    if not locations.shown(request.state.sees_private):
        raise HTTPException(404, "Not Found")
    tree = locations.tree(db)
    return templates.TemplateResponse(
        request,
        "locations.html",
        {
            "outline": locations.outline(tree, locations.counts(db, tree)),
            "total": len(tree.rows),
            # Out of search engines whichever way the switch is set, as a location's
            # page is: a list of where everything is kept is an address book.
            "noindex": True,
        },
    )


@router.get("/locations/new", response_class=HTMLResponse, include_in_schema=False)
def gui_new_location(request: Request, inside: str = "", db: Session = Depends(get_db)) -> Response:
    tree = locations.tree(db)
    ctx = _form_ctx(db, None, "New location", tree)
    # Opened from a location's page, the new one starts inside it.
    if (inside := inside.strip().upper()) in tree:
        ctx["inside_text"] = tree.text(inside)
    return templates.TemplateResponse(request, "location_form.html", ctx)


@router.post("/locations/new", include_in_schema=False)
async def gui_create_location(request: Request, db: Session = Depends(get_db)) -> Response:
    form = await posted(request)
    tree = locations.tree(db)
    who = request.state.principal.username
    fields, errors, parent = _read_form(db, form, None, tree)
    if errors:
        return refused(
            request,
            db,
            "location_form.html",
            _form_ctx(db, None, "New location", tree),
            form,
            errors,
        )
    loc = Location(asset_id=next_asset_id(db), **fields)
    db.add(loc)
    db.flush()
    add_log(db, loc.asset_id, "created", "created")
    if parent is not None:
        locations.move(db, loc, parent.asset_id, locations.EDIT, who, tree)
    db.commit()
    return RedirectResponse(f"/locations/{loc.asset_id}", status_code=303)


def _page_ctx(request: Request, db: Session, loc: Location) -> dict[str, object]:
    """Everything a location's page draws: the path to it, what is in it, and the
    parts it shares with an item page -- photographs, history, label."""
    tag = loc.asset_id
    tree = locations.tree(db)
    held = locations.counts(db, tree)
    images = detect_images(KIND, tag)
    blurb = tree.text(loc.parent_id) or locations.KIND_NAMES.get(loc.kind, "")
    return {
        "loc": loc,
        "obj": loc,
        "kind": KIND,
        "one": labels.LOCATION,
        "item": to_dict(loc),
        "steps": tree.steps(loc.parent_id),
        "kind_name": locations.KIND_NAMES.get(loc.kind, loc.kind),
        # The locations inside it, each with how many things it holds all the way
        # down, so a shelf of boxes says which box to open.
        "inside": [
            (child, tree.rows[child][0], tree.rows[child][1], held.get(child, 0))
            for child in tree.children(tag)
        ],
        "things": [_card(t) for t in locations.kept_in(db, tag)],
        "images": images,
        "placeholder": "placeholders/location.svg",
        "ref_marks": reference_marks(KIND, tag),
        "tuned": tuned_photos(KIND, tag),
        "log": _history(db, tag),
        "live_aid": tag,
        "live_v": _change_token(db, tag),
        # Kept out of search engines whichever way the switch is set: a page of where
        # things are is an address, and one made public is still not one to index.
        "noindex": True,
        "og": _og(request, loc.name, blurb, images[0] if images else None),
        # What it could be merged into: anywhere but itself and what is in it.
        "merge_choices": [
            tree.text(t)
            for t in sorted(tree.rows, key=lambda t: tree.text(t).casefold())
            if not (t == tag or t in tree.within(tag))
        ],
    }


@router.get("/locations/{aid}", response_class=HTMLResponse, include_in_schema=False)
def gui_location(
    aid: str, request: Request, imgerr: int = 0, db: Session = Depends(get_db)
) -> HTMLResponse:
    loc = _shown_or_404(request, db, aid)
    ctx = _page_ctx(request, db, loc) | {"imgerr": bool(imgerr)}
    return templates.TemplateResponse(request, "location.html", ctx)


@router.get("/locations/{aid}/edit", response_class=HTMLResponse, include_in_schema=False)
def gui_edit_location(aid: str, request: Request, db: Session = Depends(get_db)) -> HTMLResponse:
    loc = get_or_404(db, Location, aid)
    tree = locations.tree(db)
    return templates.TemplateResponse(
        request, "location_form.html", _form_ctx(db, loc, f"Edit {loc.name}", tree)
    )


@router.post("/locations/{aid}/edit", include_in_schema=False)
async def gui_save_location(aid: str, request: Request, db: Session = Depends(get_db)) -> Response:
    loc = get_or_404(db, Location, aid)
    form = await posted(request)
    tree = locations.tree(db)
    who = request.state.principal.username
    fields, errors, parent = _read_form(db, form, loc, tree)
    if errors:
        ctx = _form_ctx(db, loc, f"Edit {loc.name}", tree)
        return refused(request, db, "location_form.html", ctx, form, errors)
    changed = []
    if fields["name"] != loc.name:
        changed.append(f"name: {loc.name} → {fields['name']}")
    if fields["kind"] != loc.kind:
        changed.append(
            f"kind: {locations.KIND_NAMES.get(loc.kind, loc.kind)} → {locations.KIND_NAMES[fields['kind']]}"
        )
    if fields["notes"] != loc.notes:
        changed.append("notes changed")
    for key, value in fields.items():
        setattr(loc, key, value)
    tree.rows[loc.asset_id] = (loc.name, loc.kind, loc.parent_id)
    if changed:
        add_log(db, loc.asset_id, "; ".join(changed))
    locations.move(db, loc, parent.asset_id if parent else None, locations.EDIT, who, tree)
    db.commit()
    return RedirectResponse(f"/locations/{loc.asset_id}", status_code=303)


def _refused_here(request: Request, db: Session, loc: Location, message: str) -> HTMLResponse:
    """The location's page again, saying why what was asked of it was not done --
    for the buttons on it that change what it holds. 400, as a refused form is."""
    ctx = _page_ctx(request, db, loc) | {"refusal": message, "imgerr": False}
    return templates.TemplateResponse(request, "location.html", ctx, status_code=400)


@router.post("/locations/{aid}/delete", include_in_schema=False)
def gui_delete_location(aid: str, request: Request, db: Session = Depends(get_db)) -> Response:
    """Refused while anything is in it, a thing or a location, which is the rule
    the page states: move what is in it first, or empty it into the location above."""
    loc = get_or_404(db, Location, aid)
    if not locations.empty(db, loc.asset_id, locations.tree(db)):
        return _refused_here(
            request, db, loc, f"{loc.name} is not empty. Move what is in it first."
        )
    up = loc.parent_id
    rels = locations.forget(db, loc)
    db.commit()  # the rows first: a file cannot be rolled back
    _purge_photos(rels)
    return RedirectResponse(f"/locations/{up}" if up else "/", status_code=303)


@router.post("/locations/{aid}/empty", include_in_schema=False)
def gui_empty_location(aid: str, request: Request, db: Session = Depends(get_db)) -> Response:
    loc = get_or_404(db, Location, aid)
    locations.empty_into_parent(db, loc, request.state.principal.username, locations.tree(db))
    db.commit()
    return RedirectResponse(f"/locations/{loc.asset_id}", status_code=303)


@router.post("/locations/{aid}/merge", include_in_schema=False)
async def gui_merge_location(aid: str, request: Request, db: Session = Depends(get_db)) -> Response:
    loc = get_or_404(db, Location, aid)
    form = await posted(request)
    tree = locations.tree(db)
    try:
        into = locations.find(db, form.get("into", ""), tree)
        if into is None:
            raise locations.Refused("Choose the location to merge it into.")
        rels = locations.merge(db, loc, into, request.state.principal.username, tree)
    except locations.Refused as err:
        db.rollback()
        return _refused_here(request, db, get_or_404(db, Location, aid), str(err))
    target = into.asset_id
    db.commit()
    _purge_photos(rels)
    return RedirectResponse(f"/locations/{target}", status_code=303)


@router.post("/locations/{aid}/note", include_in_schema=False)
async def gui_location_note(
    aid: str, request: Request, db: Session = Depends(get_db)
) -> RedirectResponse:
    get_or_404(db, Location, aid)
    _note_with_photos(db, aid, await posted(request))
    return RedirectResponse(f"/locations/{aid}", status_code=303)


# --- photographs, the shape the item pages' have --------------------------------


@router.post("/locations/{aid}/photo", include_in_schema=False)
async def gui_location_photo(
    aid: str, photos: list[UploadFile] = File(...), db: Session = Depends(get_db)
) -> RedirectResponse:
    loc = get_or_404(db, Location, aid)
    first = None
    n = 0
    for up in photos:
        if (up.filename or "").strip():
            rel = _save_photo(KIND, loc.asset_id, up)
            n += 1
            first = first or rel
    if first and not loc.image:
        loc.image = first
    if n:
        add_log(db, loc.asset_id, f"added {n} photo(s)")
    db.commit()
    return RedirectResponse(f"/locations/{loc.asset_id}", status_code=303)


@router.post("/locations/{aid}/primary-photo", include_in_schema=False)
async def gui_location_primary(
    aid: str, request: Request, db: Session = Depends(get_db)
) -> RedirectResponse:
    loc = get_or_404(db, Location, aid)
    form = await posted(request)
    loc.image = _set_primary_photo(KIND, loc.asset_id, form.get("image", ""))
    add_log(db, loc.asset_id, "changed the default photo")
    db.commit()
    return RedirectResponse(f"/locations/{loc.asset_id}", status_code=303)


@router.post("/locations/{aid}/photo-delete", include_in_schema=False)
async def gui_location_photo_delete(
    aid: str, request: Request, db: Session = Depends(get_db)
) -> RedirectResponse:
    loc = get_or_404(db, Location, aid)
    form = await posted(request)
    was_primary, new_primary = _delete_image(KIND, loc.asset_id, form.get("image", ""))
    if was_primary:
        loc.image = new_primary or ""
    add_log(db, loc.asset_id, "deleted a photo")
    db.commit()
    return RedirectResponse(f"/locations/{loc.asset_id}", status_code=303)


@router.get("/locations/{aid}/edit-photo", response_class=HTMLResponse, include_in_schema=False)
def gui_location_edit_photo(aid: str, image: str = "") -> RedirectResponse:
    return _photo_edit_redirect(KIND, aid, image)


@router.post("/locations/{aid}/photo-rotate", include_in_schema=False)
async def gui_location_photo_rotate(
    aid: str, request: Request, db: Session = Depends(get_db)
) -> RedirectResponse:
    form = await posted(request)
    _do_photo_rotate(db, Location, KIND, aid, form)
    return RedirectResponse(_safe_next(form.get("next") or f"/locations/{aid}"), status_code=303)


@router.post("/locations/{aid}/photo-tuneup", include_in_schema=False)
async def gui_location_photo_tuneup(
    aid: str, request: Request, db: Session = Depends(get_db)
) -> RedirectResponse:
    form = await posted(request)
    _do_photo_tuneup(db, Location, KIND, aid, form)
    return RedirectResponse(_safe_next(form.get("next") or f"/locations/{aid}"), status_code=303)


@router.post("/locations/{aid}/photo-revert", include_in_schema=False)
async def gui_location_photo_revert(
    aid: str, request: Request, db: Session = Depends(get_db)
) -> RedirectResponse:
    form = await posted(request)
    _do_photo_revert(db, Location, KIND, aid, form)
    return RedirectResponse(_safe_next(form.get("next") or f"/locations/{aid}"), status_code=303)


@router.post("/locations/{aid}/photo-crop", include_in_schema=False)
async def gui_location_photo_crop(
    aid: str, request: Request, db: Session = Depends(get_db)
) -> RedirectResponse:
    form = await posted(request)
    _do_photo_crop(db, Location, KIND, aid, form)
    return RedirectResponse(_safe_next(form.get("next") or f"/locations/{aid}"), status_code=303)


# --- labels ---------------------------------------------------------------------


def _labelled(request: Request, db: Session, aid: str) -> Location:
    """A location's labels are the owner's tools, as an item's are, and a visitor
    asking for one gets the 404 the page gives them."""
    if not request.state.sees_private:
        raise HTTPException(404, f"no location {(aid or '').upper()}")
    return get_or_404(db, Location, aid)


@router.get("/locations/{aid}/label.pdf", include_in_schema=False)
def gui_location_label(
    aid: str, request: Request, small: int = 1, db: Session = Depends(get_db)
) -> Response:
    loc = _labelled(request, db, aid)
    pdf = labels.render_pdf(
        locations.label_row(loc, locations.tree(db)), [], labels.LOCATION, small=bool(small)
    )
    return Response(
        pdf,
        media_type="application/pdf",
        headers={
            "Content-Disposition": f'inline; filename="{loc.asset_id}{"-small" if small else ""}.pdf"'
        },
    )


@router.get("/locations/{aid}/label.png", include_in_schema=False)
def gui_location_label_png(
    aid: str, request: Request, media: str = "", dpi: int = 0, db: Session = Depends(get_db)
) -> Response:
    loc = _labelled(request, db, aid)
    return png_label(locations.label_row(loc, locations.tree(db)), labels.LOCATION, media, dpi)


@router.get("/locations/{aid}/labels.pdf", include_in_schema=False)
def gui_location_labels(
    aid: str, request: Request, sheet: int = 0, db: Session = Depends(get_db)
) -> Response:
    """Labels for everything inside: the location's own, then one for each location
    inside it and each thing kept in it, all the way down (MANUAL §13). One to a
    page for a label printer, or laid out on an A4 sheet."""
    loc = _labelled(request, db, aid)
    tree = locations.tree(db)
    rows = []
    for tag in [
        loc.asset_id,
        *sorted(tree.within(loc.asset_id), key=lambda t: tree.text(t).casefold()),
    ]:
        here = db.get(Location, tag)
        if here is None:
            continue
        rows.append((locations.label_row(here, tree), labels.LOCATION))
        for thing in locations.kept_in(db, tag):
            kind = labels.COMPUTER if isinstance(thing, Computer) else labels.PART
            rows.append((to_dict(thing), kind))
    pdf = labels.render_many(rows, sheet=bool(sheet))
    return Response(
        pdf,
        media_type="application/pdf",
        headers={"Content-Disposition": f'inline; filename="{loc.asset_id}-labels.pdf"'},
    )
