"""Everything reached at /items/<id>: the address a printed label carries, and the
history written under it.

An asset id names something in the register without saying which of the three
tables holds it, which is the whole point of the label: scan it and land on the
right page. The history routes are here rather than with the pages because a log
entry belongs to the id, not to whichever kind of thing wears it.
"""

from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import RedirectResponse
from sqlalchemy.orm import Session


# --- QR target: one stable /items/<id> URL for either kind ------------------


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

from ..db import get_db
from ..forms import posted
from ..history import PHOTO_ENTRY, item_log, log_photos
from ..models import LogEntry, LogPhoto
from ..photos import _attach_log_photos, _chosen_photos, _purge_photos
from ..register import _asset_page, _change_token

router = APIRouter()


@router.get("/api/items/{aid}/log", tags=["log"])
def api_item_log(aid: str, db: Session = Depends(get_db)):
    """One asset's history, entry by entry and unfolded -- the record as it was
    written, not as a page reads it out. `photos` are the paths of anything hung on
    the entry, to be fetched from /images/ like any other photograph."""
    entries = item_log(db, aid)
    photos = log_photos(db, [e.id for e in entries])
    return [
        {
            "created_at": e.created_at.isoformat() if e.created_at else None,
            "kind": e.kind,
            "message": e.message,
            "photos": photos.get(e.id, []),
        }
        for e in entries
    ]


@router.get("/items/{aid}/version", include_in_schema=False)
def gui_item_version(aid: str, db: Session = Depends(get_db)):
    """The token above, for a page to compare against the one it was built with.

    Public, like the page it belongs to: it says that something changed, never what.
    No 404 for an unknown asset -- a page whose item has been deleted asks this too,
    and the honest answer is a token that will not match, which sends it to reload
    and find out properly."""
    return {"v": _change_token(db, (aid or "").upper())}


@router.get("/items/{aid}", include_in_schema=False)
def gui_item(aid: str, db: Session = Depends(get_db)):
    """The URL printed on labels: resolve an asset id to its page, whichever of the
    three things in the register it turns out to name. Keeps the same /items/<id>
    scheme the old QR codes used.

    A project is in here despite never being printed on a label, because this is the
    register-wide address and a project holds a register id. Its history is written
    through /items/<id> like everything else's, and a route that could not find it
    would be a page whose note bar posted into nowhere."""
    return RedirectResponse(_asset_page(db, aid.upper()), status_code=307)


def _log_entry_or_404(db, aid, log_id):
    """One history entry, and the page to go back to. The asset id in the URL is
    checked against the entry's rather than taken on trust: an entry id on its own
    would let a photograph of one machine be hung on another machine's history."""
    aid = (aid or "").upper()
    where = _asset_page(db, aid)
    row = db.get(LogEntry, log_id)
    if row is None or row.asset_id != aid:
        raise HTTPException(404, f"no history entry {log_id} for {aid}")
    return row, where


@router.post("/items/{aid}/log/{log_id}/photo", include_in_schema=False)
async def gui_log_photo(aid: str, log_id: int, request: Request, db: Session = Depends(get_db)):
    row, where = _log_entry_or_404(db, aid, log_id)
    _attach_log_photos(db, row, _chosen_photos(await posted(request)))
    db.commit()
    return RedirectResponse(where, status_code=303)


@router.post("/items/{aid}/log/{log_id}/photo-delete", include_in_schema=False)
async def gui_log_photo_delete(
    aid: str, log_id: int, request: Request, db: Session = Depends(get_db)
):
    row, where = _log_entry_or_404(db, aid, log_id)
    form = await posted(request)
    photo = (
        db.query(LogPhoto)
        .filter(LogPhoto.log_id == row.id, LogPhoto.rel == form.get("image", ""))
        .first()
    )
    if photo is None:
        raise HTTPException(404, "no such photo on this history entry")
    rel = photo.rel
    db.delete(photo)
    # A photograph entry is its photographs. Take the last one off it and there is
    # nothing left that it said, so the entry goes too rather than standing in the
    # log as a chip with nothing beside it. An entry with words keeps its line: the
    # words are still what it said.
    if row.kind == PHOTO_ENTRY:
        db.flush()
        if not db.query(LogPhoto).filter(LogPhoto.log_id == row.id).count():
            db.delete(row)
    # Nothing is written to the history about this, either way round. An entry
    # gaining or losing a photograph is an edit to the record rather than something
    # that happened to the machine, and a history that logged its own editing would
    # grow a line for every line it already has.
    db.commit()  # the row first: a file cannot be rolled back
    _purge_photos([rel])
    return RedirectResponse(where, status_code=303)


@router.post("/items/{aid}/log/delete", include_in_schema=False)
async def gui_log_delete(aid: str, request: Request, db: Session = Depends(get_db)):
    """Remove history entries.

    Several ids rather than one, because a run of the same thing done in one sitting
    reads as a single line and has to delete as one: "deleted 10 photographs" that
    took one row away and came back saying nine would be a button that does not do
    what it says.

    Every id is checked against this asset before anything goes, the way hanging a
    photograph on an entry is -- an id on its own would let one machine's history be
    deleted from another machine's page.

    Nothing is written to the history about this, which is the rule a history entry
    losing a photograph already follows: editing the record is not something that
    happened to the machine, and a history that logged its own editing would grow a
    line for every line it lost.
    """
    aid = (aid or "").upper()
    where = _asset_page(db, aid)
    form = await posted(request)
    ids = [int(i) for i in form.getlist("id") if str(i).strip().isdigit()]
    rows = (
        db.query(LogEntry).filter(LogEntry.id.in_(ids), LogEntry.asset_id == aid).all()
        if ids
        else []
    )
    if not rows:
        raise HTTPException(404, f"no such history entry for {aid}")
    # The photographs hung on them go too, and their paths are read while the rows
    # are still there: a file is the one thing here that cannot be rolled back.
    found = [r.id for r in rows]
    rels = [
        rel
        for (rel,) in db.query(LogPhoto.rel)
        .filter(LogPhoto.log_id.in_(found))
        .order_by(LogPhoto.id)
    ]
    db.query(LogPhoto).filter(LogPhoto.log_id.in_(found)).delete(synchronize_session=False)
    for row in rows:
        db.delete(row)
    db.commit()  # the rows first, then the files
    _purge_photos(rels)
    return RedirectResponse(where, status_code=303)
