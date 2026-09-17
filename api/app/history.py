"""The register's history: the dated entries written against an asset, and how a
page reads them back.

Lifted out of main whole. It is one cohesive thing -- writing an entry, reading a
page of them with their photographs, and folding a run of the same action into the
one line a person would have written -- and it is wanted by nearly every route
group being lifted after it, which is why it comes out first (workflow-and-ci).

`get_or_404` rides along rather than living alone: every group that writes an entry
first fetches the thing it is about, and one more module holding one function
helps nobody.

The rows are never rewritten. Folding is how the page reads them out; the API's
log still lists them one per action, which is what makes the record a record.
"""
from datetime import UTC, datetime, timedelta
import re
from types import SimpleNamespace

from fastapi import HTTPException

from .models import LogEntry, LogPhoto
from .web import templates


def get_or_404(db, model, aid):
    obj = db.get(model, (aid or "").upper())
    if not obj:
        raise HTTPException(404, f"{model.__tablename__} {aid} not found")
    return obj




def _now():
    """Naive UTC, matching the column and every row already in it. utcnow() is
    deprecated, and an aware value here would be inconsistent with the history
    written before this."""
    return datetime.now(UTC).replace(tzinfo=None)


# An entry whose content is the photographs on it rather than any words. A kind of
# its own rather than a note that happens to be blank, so that everything which asks
# what an entry is gets an answer: the page draws it its own chip, the fold leaves it
# alone, and add_log knows where the rule about empty messages stops.
PHOTO_ENTRY = "photo"


def add_log(db, asset_id, message, kind="change"):
    """Record a dated history entry for an asset, and hand the row back for
    anything that wants to hang photographs on it. The caller commits.

    An empty message writes nothing and returns None: there is no such thing as an
    entry that does not say anything. Except a photograph entry, which says it
    without words -- a picture of the board with the capacitor missing is a thing
    said about the board, and it used to need a sentence typed beside it before the
    register would keep it.
    """
    if not message and kind != PHOTO_ENTRY:
        return None
    db.add(row := LogEntry(asset_id=asset_id, created_at=_now(),
                           kind=kind, message=message))
    return row


def item_log(db, asset_id):
    return (db.query(LogEntry).filter(LogEntry.asset_id == asset_id)
            .order_by(LogEntry.created_at.desc(), LogEntry.id.desc()).all())


# How far apart two of the same thing can be and still be one sitting. Long enough
# to cover picking the next photo out of a folder, short enough that coming back to
# the same machine after tea is a separate line.
FOLD_WINDOW = timedelta(minutes=5)

# "deleted a photo" ten times over is "deleted 10 photos", which is the sentence a
# person would have written. Where a message does not name a single thing that way,
# the count is appended instead rather than guessed at.
_ONE_OF = re.compile(r"\ba (photo|file)\b")


def _folded_message(message, n):
    if n < 2:
        return message
    plural, hit = _ONE_OF.subn(lambda m: f"{n} {m.group(1)}s", message, count=1)
    return plural if hit else f"{message} ×{n}"


def log_photos(db, log_ids):
    """{log entry id: [photo path]} for a page's worth of entries, in one query and
    in the order they were attached."""
    if not log_ids:
        return {}
    out = {}
    for log_id, rel in (db.query(LogPhoto.log_id, LogPhoto.rel)
                        .filter(LogPhoto.log_id.in_(log_ids))
                        .order_by(LogPhoto.id)):
        out.setdefault(log_id, []).append(rel)
    return out


def _fold_log(entries, photos=None):
    """The history as a page shows it, with a run of the same thing done over and
    over collapsed into one line.

    Clearing out a folder of photographs writes "deleted a photo" once per
    photograph, and twenty of those push the history the machine actually has --
    what it was fitted with, what was corrected -- off the bottom of the page. They
    are one action to the person who did them, so they read as one line.

    Only entries next to each other, saying exactly the same thing, and within
    FOLD_WINDOW of the one before: a chain, so a long tidying session is still one
    line, while the same thing done again next week is its own. A note is never
    folded -- it is a person's own words about the machine, and it stands as
    written, however like the last one it reads.

    The record itself is untouched: the rows stay one per action, and the API's log
    still lists them. This is how the page reads them out.

    An entry carrying photographs is never folded either, into or out of. Folding
    rewrites several entries as one sentence, and the photographs would then either
    be lost with the entries that are no longer shown or be gathered under a line
    that is not the one they were taken for. `photos` is what log_photos read, so
    an entry with none behaves exactly as it did before this existed.
    """
    photos = photos or {}
    out = []
    for e in entries:
        last = out[-1] if out else None
        mine = photos.get(e.id) or []
        if (last is not None and not mine and not last.photos
                and e.kind != "note" and last.kind == e.kind
                and last.message == e.message and last.created_at and e.created_at
                and last.oldest - e.created_at <= FOLD_WINDOW):
            last.count += 1
            last.oldest = e.created_at
            # Every row the one line stands for, so that deleting it removes what it
            # says it is rather than one twentieth of it.
            last.ids.append(e.id)
            continue
        out.append(SimpleNamespace(id=e.id, created_at=e.created_at, kind=e.kind,
                                   message=e.message, count=1, photos=mine,
                                   oldest=e.created_at, ids=[e.id]))
    # Newest first, so a run's own stamp is the last time it was done; the count in
    # the message says the rest.
    for e in out:
        e.message = _folded_message(e.message, e.count)
    return out


def _history(db, asset_id):
    """One item's history as its page wants it: folded, with each entry's
    photographs on it. Two queries whatever the history is long -- the entries, and
    the photographs of all of them at once."""
    entries = item_log(db, asset_id)
    return _fold_log(entries, log_photos(db, [e.id for e in entries]))


def log_stamp(created_at, authed):
    """A history line's date, with the clock time only for whoever is signed in.
    Editing wants the minute -- it is how you tell apart two corrections to the same
    photo -- but a visitor is reading about the machine, and the time of day says
    more about the owner's evenings than about the hardware."""
    if not created_at:
        return ""
    return created_at.strftime("%Y-%m-%d %H:%M" if authed else "%Y-%m-%d")


templates.env.globals["log_stamp"] = log_stamp
