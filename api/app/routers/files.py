"""The files kept beside the register: drivers, manuals, ROM dumps, receipts.

What a file is for is the list of asset ids it is linked to, made by hand
(ADR-0028), and whether a visitor may see it is a tick somebody made (ADR-0009).
Both are asked on the way in and on the way out: the list, a file's page and the
download put the same question to the same column, because a file kept off a page
and still fetchable at its URL is not private.

Everything done to a file is done on its own page. The lists that show files -- this
module's /files and the panel on an item page -- are read-only rows, which is what
keeps a phone's screen for the files rather than for the boxes around them.
"""

from urllib.parse import quote, urlencode

from fastapi import APIRouter, Depends, File, HTTPException, Request, UploadFile
from fastapi.responses import FileResponse, HTMLResponse, RedirectResponse
from sqlalchemy.orm import Session

from .. import filekinds, filesdb
from ..common import to_dict
from ..db import get_db
from ..forms import posted
from ..history import add_log
from ..models import Computer, Part, Project, StoredFile
from ..register import _register_order
from ..web import _og, _safe_next, templates

router = APIRouter()


def _file_or_404(db: Session, fid: int) -> StoredFile:
    row = db.get(StoredFile, fid)
    if row is None:
        raise HTTPException(404, f"file {fid} not found")
    return row


def _seen_or_404(db: Session, fid: int, request: Request) -> StoredFile:
    """The file, if this reader may know it exists. An unpublished file is a 404 to
    a visitor rather than a 401, and the same 404 a missing id gets. There is
    nothing to log in *for* here -- the login is the owner's, not an account a
    reader could hold -- so an invitation to authenticate would only confirm that
    the file exists, which for the receipt this flag was added to cover is most of
    what was being kept back."""
    row = _file_or_404(db, fid)
    if not row.public and not request.state.authed:
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
    is opened -- the id is."""
    row = _seen_or_404(db, fid, request)
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


def _item_for_link(db: Session, aid: str | None) -> dict[str, object] | None:
    """The machine, part or project an asset id names, as the dict filesdb reads,
    or None for an id that names nothing."""
    aid = (aid or "").strip().upper()
    if not aid:
        return None
    obj = db.get(Computer, aid) or db.get(Part, aid) or db.get(Project, aid)
    return to_dict(obj) if obj else None


def _linkable(db: Session) -> list[tuple[str, str]]:
    """Everything a file can be linked to, as (asset id, name), for the box on a
    file's page to offer: the register's machines and parts in its own order, then
    the projects."""
    out = [(aid, name) for aid, _kind, name in _register_order(db)]
    out += [
        (aid, name or aid)
        for aid, name in db.query(Project.asset_id, Project.name).order_by(Project.asset_id)
    ]
    return out


# What a PDF shown in the browser may load (ADR-0030). The viewer is the browser's
# own and draws the document with its own resources, so nothing of the site's is
# wanted: no script, no style, no frame, no form. Objects are allowed from here and
# only here, because the site's `object-src 'none'` is right for its pages and
# blanks the viewer in the browsers that show a PDF as a plugin in a page they make
# themselves. The middleware sets the site's policy only where a response has none,
# which is what lets this one say its own.
PDF_POLICY = "; ".join(
    (
        "default-src 'none'",
        "object-src 'self'",
        "frame-ancestors 'self'",
        "base-uri 'none'",
        "form-action 'none'",
    )
)


@router.get("/files/{fid}/view/{name}", include_in_schema=False, response_model=None)
def view_file(
    fid: int, name: str, request: Request, db: Session = Depends(get_db)
) -> FileResponse | RedirectResponse:
    """Show a PDF in the browser rather than hand it over to be saved.

    Only a file that is a PDF by its name and by its bytes, and served as one by
    the server's say-so -- the type is never the upload's, and `nosniff` stops the
    browser second-guessing it. Anything else is sent to its download, so a page
    called invoice.pdf is saved rather than shown whatever is in it. Who may see
    it, and how long it may be kept, are the download's rules exactly."""
    row = _seen_or_404(db, fid, request)
    path = filesdb.path_of(row)
    if not path.is_file():
        raise HTTPException(404)
    if not filesdb.is_pdf(row):
        return RedirectResponse(f"/files/{row.id}/{quote(row.filename)}", status_code=303)
    return FileResponse(
        path,
        media_type="application/pdf",
        headers={
            "Content-Disposition": f'inline; filename="{_ascii_filename(row.filename)}"',
            "X-Content-Type-Options": "nosniff",
            "Cache-Control": ("public, max-age=3600" if row.public else "private, no-store"),
            "Content-Security-Policy": PDF_POLICY,
        },
    )


@router.post("/files", include_in_schema=False)
async def gui_upload_files(
    request: Request, uploads: list[UploadFile] = File(...), db: Session = Depends(get_db)
) -> RedirectResponse:
    """Take one or more files and link them to the item the upload started on --
    and to its same-model siblings as well, where the tick for them was ticked.

    The siblings are worked out here again rather than read from the form, so the
    tick can only ever mean "the others of this model still held": a list of ids
    posted from a page would be a way to link a file to anything at all."""
    form = await posted(request)
    note = form.get("note", "")
    public = bool(form.get("public"))
    nxt = _safe_next(form.get("next") or "/files")
    item = _item_for_link(db, form.get("aid"))
    targets: list[str] = []
    if item is not None:
        # str(): the dict is a row read column by column, so every value in it is
        # typed as wide as a column can be; an asset id is the primary key.
        targets.append(str(item["asset_id"]))
        if form.get("siblings"):
            targets += [link.asset_id for link in filesdb.siblings(db, item, held=True)]
    saved = 0
    errors: list[str] = []
    for up in uploads:
        if not (up.filename or "").strip():
            continue
        try:
            row = filesdb.save(db, up, note, public)
        except ValueError as exc:
            errors.append(str(exc))
            continue
        if row is not None:
            saved += 1
            for aid in targets:
                filesdb.link(db, row.id, aid)
    if saved and item is not None:
        add_log(db, str(item["asset_id"]), f"added {saved} file(s)")
    db.commit()
    return RedirectResponse(nxt + ("?fileerr=1" if errors else ""), status_code=303)


@router.get("/files/{fid}", response_class=HTMLResponse, include_in_schema=False)
def gui_file(fid: int, request: Request, db: Session = Depends(get_db)) -> HTMLResponse:
    """One file: what it is, what it is linked to, and the download -- and, for the
    owner, everything that can be done to it, since this is the only place any of
    it is done.

    The register's ids ride along for the link box to offer, owner only: what it is
    is a list of everything owned, which is not a thing to hand a visitor who cannot
    link anything anyway."""
    row = _seen_or_404(db, fid, request)
    authed = request.state.authed
    [row] = filesdb.with_links(db, [row], authed)
    return templates.TemplateResponse(
        request,
        "file.html",
        {
            "f": row,
            "assets": _linkable(db) if authed else [],
            "linkerr": request.query_params.get("linkerr", "")[:40] if authed else "",
            "note_max": filesdb.NOTE_MAX,
            "og": _og(
                request,
                row.filename,
                row.note or f"{row.what.size} · a file kept with the hardware it is for",
            ),
        },
    )


@router.post("/files/{fid}/link", include_in_schema=False)
async def gui_file_link(
    fid: int, request: Request, db: Session = Depends(get_db)
) -> RedirectResponse:
    """Link a file to one more machine, part or project, by its asset id.

    An id that is not in the register is a typo rather than a broken link, so the
    answer is the page again with a line saying so, not a 404 to find the way back
    from."""
    row = _file_or_404(db, fid)
    form = await posted(request)
    nxt = _safe_next(form.get("next") or f"/files/{row.id}")
    typed = (form.get("aid") or "").strip().upper()
    item = _item_for_link(db, typed)
    if item is None:
        joiner = "&" if "?" in nxt else "?"
        return RedirectResponse(
            nxt + joiner + urlencode({"linkerr": typed or "?"}), status_code=303
        )
    filesdb.link(db, row.id, str(item["asset_id"]))
    db.commit()
    return RedirectResponse(nxt, status_code=303)


@router.post("/files/{fid}/unlink", include_in_schema=False)
async def gui_file_unlink(
    fid: int, request: Request, db: Session = Depends(get_db)
) -> RedirectResponse:
    """Take a file off one thing. It never deletes anything: a file linked to
    nothing is unlinked, which the files page says out loud -- the disposal case
    ADR-0006 was right to worry about is a file quietly going in the bin with the
    last thing that pointed at it."""
    row = _file_or_404(db, fid)
    form = await posted(request)
    aid = (form.get("aid") or "").strip()
    if aid:
        filesdb.unlink(db, row.id, aid)
    db.commit()
    return RedirectResponse(_safe_next(form.get("next") or f"/files/{row.id}"), status_code=303)


@router.post("/files/{fid}/note", include_in_schema=False)
async def gui_file_note(
    fid: int, request: Request, db: Session = Depends(get_db)
) -> RedirectResponse:
    """Say what a file is, in a line. What the box holds is the whole of the note,
    so emptying it clears it."""
    row = _file_or_404(db, fid)
    form = await posted(request)
    row.note = (form.get("note") or "").strip()[: filesdb.NOTE_MAX]
    db.commit()
    return RedirectResponse(_safe_next(form.get("next") or f"/files/{row.id}"), status_code=303)


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
    return RedirectResponse(_safe_next(form.get("next") or f"/files/{row.id}"), status_code=303)


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
def gui_files(
    request: Request,
    kind: str = "",
    q: str = "",
    show: str = "",
    db: Session = Depends(get_db),
) -> HTMLResponse:
    """Everything on file, for finding the driver whose card is not in front of you
    -- and, for the owner, the two lists that want attention: what is linked to
    nothing, and what visitors cannot see.

    The kinds are counted over the files this reader can see before any of them is
    chosen, so a filter says how many it holds rather than how many it is showing."""
    authed = request.state.authed
    seen = filesdb.all_files(db, authed)
    kind = kind if kind in filekinds.GROUPS else ""
    show = show if authed and show in filesdb.SHOWS else ""
    return templates.TemplateResponse(
        request,
        "files.html",
        {
            "files": filesdb.all_files(db, authed, kind, q, show),
            "groups": filesdb.groups(seen),
            "counts": {
                "all": len(seen),
                "unlinked": sum(1 for f in seen if f.unlinked),
                "private": sum(1 for f in seen if not f.public),
            },
            "kind": kind,
            "q": q,
            "show": show,
            "og": _og(
                request, "Files", "Drivers, manuals and disks kept with the hardware they belong to"
            ),
        },
    )


# response_model=None: the annotation is for the type checker. FastAPI would
# otherwise publish it as the response's shape, which the pinned contract
# (ADR-0010) leaves open.
@router.get("/api/files", tags=["files"], response_model=None)
def api_list_files(db: Session = Depends(get_db)) -> list[dict[str, object]]:
    """Files kept beside the register, newest first, each with the asset ids of the
    machines, parts and projects it is linked to."""
    return [
        {
            "id": f.id,
            "filename": f.filename,
            "size": f.size,
            "note": f.note,
            "created_at": f.created_at,
            "public": f.public,
            "assets": f.assets,
            "url": f"/files/{f.id}/{quote(f.filename)}",
        }
        for f in filesdb.all_files(db)
    ]
