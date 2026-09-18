"""The files kept beside the register: drivers, manuals, ROM dumps, receipts.

What a file is for is a link it carries rather than a guess made from its name
(ADR-0006, ADR-0020), and whether a visitor may see it is a tick somebody made
(ADR-0009). Both are asked on the way in and on the way out: the listing and the
download put the same question to the same column, because a file kept off a page
and still fetchable at its URL is not private.
"""

from urllib.parse import quote


# --- files kept beside the register -----------------------------------------
# Drivers, manuals, ROM dumps. Not hung off an asset id: a file is attached to what
# it is for, which is a model as often as it is a unit -- one driver for the three
# identical cards on the shelf and the fourth bought next year (ADR-0006,
# ADR-0020). app/filesdb.py owns the links and the bytes; these are the things a
# person does with one, of which publishing is its own, since a file is kept back
# from visitors until somebody says otherwise (ADR-0009).

from fastapi import APIRouter, Depends, File, HTTPException, Request, UploadFile
from fastapi.responses import FileResponse, HTMLResponse, RedirectResponse
from sqlalchemy.orm import Session

from .. import filesdb
from ..common import to_dict
from ..db import get_db
from ..forms import posted
from ..history import add_log
from ..models import Computer, Part, StoredFile
from ..register import _register_order
from ..web import _og, _safe_next, templates

router = APIRouter()


def _file_or_404(db: Session, fid: int) -> StoredFile:
    row = db.get(StoredFile, fid)
    if row is None:
        raise HTTPException(404, f"file {fid} not found")
    return row


@router.get("/files/{fid}/{name}", include_in_schema=False)
def serve_file(
    fid: int, name: str, request: Request, db: Session = Depends(get_db)
) -> FileResponse:
    """Hand over the bytes, always as a download and never as a page.

    An upload is whatever somebody sent, and some of what people send is HTML, or
    an SVG, which a browser asked to display would run as this site with this
    site's cookies. So: one content type for everything, an attachment
    disposition, and nosniff to stop the browser deciding it knows better. `name`
    is in the URL for the sake of the link reading like the file, and is not what
    is opened -- the id is.

    An unpublished file is a 404 to a visitor rather than a 401, and the same 404
    a missing id gets. There is nothing to log in *for* here -- the login is the
    owner's, not an account a reader could hold -- so an invitation to authenticate
    would only confirm that the file exists, which for the receipt this flag was
    added to cover is most of what was being kept back."""
    row = _file_or_404(db, fid)
    if not row.public and not request.state.authed:
        raise HTTPException(404, f"file {fid} not found")
    path = filesdb.path_of(row)
    if not path.is_file():
        raise HTTPException(404)
    return FileResponse(
        path,
        media_type="application/octet-stream",
        headers={
            "Content-Disposition": f'attachment; filename="{_ascii_filename(row.filename)}"',
            "X-Content-Type-Options": "nosniff",
            # A published file may be kept by anything that sees it; an unpublished one
            # may not be kept at all. The owner is the only person who can fetch one,
            # and the point of unticking the box is that the copy stops being handed
            # out -- which a shared cache holding it for the hour would carry on doing.
            "Cache-Control": ("public, max-age=3600" if row.public else "private, no-store"),
        },
    )


def _ascii_filename(name: str | None) -> str:
    """A filename safe to put in a header: no quotes, no control characters, no
    non-ASCII (which a header cannot carry). The stored name keeps the original."""
    cleaned = "".join(ch for ch in (name or "") if ch.isprintable() and ord(ch) < 128)
    return cleaned.replace('"', "").replace("\\", "").strip() or "download"


@router.post("/files", include_in_schema=False)
async def gui_upload_files(
    request: Request, uploads: list[UploadFile] = File(...), db: Session = Depends(get_db)
) -> RedirectResponse:
    """Take one or more files, label them with the tags the form carries, and attach
    them to whatever the upload started on.

    `aid` is that item. A driver found while looking at the card it is for is about
    the card as a model, so that is what it is attached to; an item with no model to
    speak of gets the file attached to itself (ADR-0020). Either way the panel says
    which it did and offers the other."""
    form = await posted(request)
    tags = filesdb.parse_tags(form.get("tags", ""))
    note = form.get("note", "")
    nxt = _safe_next(form.get("next") or "/files")
    aid = (form.get("aid") or "").strip().upper()
    saved = 0
    errors: list[str] = []
    for up in uploads:
        if not (up.filename or "").strip():
            continue
        try:
            row = filesdb.save(db, up, tags, note)
            if row is not None:
                saved += 1
                _attach_where_it_belongs(db, row.id, aid)
        except ValueError as exc:
            errors.append(str(exc))
    if saved and aid:
        add_log(db, aid, f"added {saved} file(s)")
    db.commit()
    return RedirectResponse(nxt + ("?fileerr=1" if errors else ""), status_code=303)


def _item_for_link(db: Session, aid: str | None) -> dict[str, object] | None:
    """The computer or part an asset id names, as the dict filesdb reads. None for
    a project, or an id that names nothing: a file is about hardware."""
    aid = (aid or "").strip().upper()
    if not aid:
        return None
    obj = db.get(Computer, aid) or db.get(Part, aid)
    return to_dict(obj) if obj else None


def _attach_where_it_belongs(db: Session, file_id: int, aid: str) -> None:
    """What uploading from an item's page means: the model where the item has one,
    since a driver is a fact about a model, and the item itself where it has none --
    a custom build, or a card whose model was left blank."""
    item = _item_for_link(db, aid)
    if item is None:
        return
    models = filesdb.model_ids_for(db, item)
    if models:
        kind, key, label = models[0]
        filesdb.attach_model(db, file_id, kind, key, label)
    else:
        # str(): the dict is a row read column by column, so every value in it is
        # typed as wide as a column can be; an asset id is the primary key.
        filesdb.attach_asset(db, file_id, str(item["asset_id"]))


@router.post("/files/{fid}/attach", include_in_schema=False)
async def gui_file_attach(
    fid: int, request: Request, db: Session = Depends(get_db)
) -> RedirectResponse:
    """Attach a file that is already on file to this item, or to its model.

    `what` picks which: `unit` is that one machine or card, anything else is the
    model. Asking for a model an item does not have attaches the item instead
    rather than failing, because the answer to "every one of these" where there is
    only the one is the one."""
    row = _file_or_404(db, fid)
    form = await posted(request)
    item = _item_for_link(db, form.get("aid"))
    if item is None:
        raise HTTPException(404, "nothing here to attach a file to")
    models = filesdb.model_ids_for(db, item)
    if (form.get("what") or "model") == "unit" or not models:
        filesdb.attach_asset(db, row.id, str(item["asset_id"]))
    else:
        kind, key, label = models[0]
        filesdb.attach_model(db, row.id, kind, key, label)
    db.commit()
    return RedirectResponse(_safe_next(form.get("next") or "/files"), status_code=303)


@router.post("/files/{fid}/detach", include_in_schema=False)
async def gui_file_detach(
    fid: int, request: Request, db: Session = Depends(get_db)
) -> RedirectResponse:
    """Take a file off a unit or off a model.

    It never deletes anything. A file attached to nothing is unfiled, which the
    files page says out loud -- the disposal case ADR-0006 was right to worry
    about is a file quietly going in the bin with the last thing that pointed at
    it."""
    row = _file_or_404(db, fid)
    form = await posted(request)
    aid = (form.get("aid") or "").strip().upper()
    kind, key = (form.get("kind") or "").strip(), (form.get("key") or "").strip()
    if aid:
        filesdb.detach_asset(db, row.id, aid)
    if kind and key:
        filesdb.detach_model(db, row.id, kind, key)
    db.commit()
    return RedirectResponse(_safe_next(form.get("next") or "/files"), status_code=303)


@router.post("/files/{fid}/tags", include_in_schema=False)
async def gui_file_tags(
    fid: int, request: Request, db: Session = Depends(get_db)
) -> RedirectResponse:
    """Relabel one: what the box says is the whole list, so a tag taken out of it is
    gone. A tag is a label now and decides nothing about where the file appears --
    that is what attach and detach are for."""
    row = _file_or_404(db, fid)
    form = await posted(request)
    filesdb.set_tags(db, row, form.get("tags", ""))
    db.commit()
    return RedirectResponse(_safe_next(form.get("next") or "/files"), status_code=303)


@router.post("/files/{fid}/public", include_in_schema=False)
async def gui_file_public(
    fid: int, request: Request, db: Session = Depends(get_db)
) -> RedirectResponse:
    """Publish one, or take it back.

    The box on the page is the answer, so an absent field is "no": an unticked
    checkbox sends nothing at all, which is the one form control whose off state
    has to be read from its silence."""
    row = _file_or_404(db, fid)
    form = await posted(request)
    row.public = bool(form.get("public"))
    db.commit()
    return RedirectResponse(_safe_next(form.get("next") or "/files"), status_code=303)


@router.post("/files/{fid}/delete", include_in_schema=False)
async def gui_file_delete(
    fid: int, request: Request, db: Session = Depends(get_db)
) -> RedirectResponse:
    row = _file_or_404(db, fid)
    form = await posted(request)
    filesdb.remove(db, row)
    db.commit()
    return RedirectResponse(_safe_next(form.get("next") or "/files"), status_code=303)


@router.get("/files", response_class=HTMLResponse, include_in_schema=False)
def gui_files(request: Request, tag: str = "", db: Session = Depends(get_db)) -> HTMLResponse:
    """Everything on file, for finding the driver whose card is not in front of you,
    for seeing what a tag is spelled as before typing it again, and for filing the
    one that is attached to nothing.

    The register's ids ride along for the attach box to offer, owner only: what it
    is is a list of everything owned, which is not a thing to hand a visitor who
    cannot attach anything anyway."""
    return templates.TemplateResponse(
        request,
        "files.html",
        {
            "files": filesdb.all_files(db, tag, request.state.authed),
            "tag": tag,
            "assets": _register_order(db) if request.state.authed else [],
            "og": _og(
                request, "Files", "Drivers, manuals and disks kept with the hardware they belong to"
            ),
        },
    )


# response_model=None: the annotation is for the type checker. FastAPI would
# otherwise publish it as the response's shape, which the pinned contract
# (ADR-0010) leaves open.
@router.get("/api/files", tags=["files"], response_model=None)
def api_list_files(tag: str = "", db: Session = Depends(get_db)) -> list[dict[str, object]]:
    """Files kept beside the register, newest first, each with its tags and what it
    is attached to: `assets` are the units it is about and `models` the models every
    item of which it is about. `tag` narrows it to one tag, matched ignoring case
    and spacing."""
    return [
        {
            "id": f.id,
            "filename": f.filename,
            "size": f.size,
            "note": f.note,
            "tags": f.tags,
            "created_at": f.created_at,
            "public": f.public,
            "assets": f.assets,
            "models": [{"kind": k, "key": key, "label": label} for k, key, label in f.models],
            "url": f"/files/{f.id}/{quote(f.filename)}",
        }
        for f in filesdb.all_files(db, tag)
    ]
