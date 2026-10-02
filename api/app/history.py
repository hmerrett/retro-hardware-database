"""The change log: writing a line, reading them back, and folding the noise.

Every page that changes something writes a line here, and an item's page reads them
back as its history. The folding is the part worth knowing about: eleven
photographs added in one gesture are one line saying so, not eleven, and the window
that decides "one gesture" lives here rather than in whatever wrote them.

Held apart from the routes because everything writes to it -- an edit, a disposal,
a photograph, a job ticked off -- so a route group cannot leave main while add_log
is defined there.
"""

import re
from collections.abc import Sequence
from datetime import UTC, datetime, timedelta
from types import SimpleNamespace

from sqlalchemy.orm import Session

from .models import LogEntry, LogPhoto, Move
from .web import templates


def _now() -> datetime:
    """Naive UTC, matching the column and every row already in it. utcnow() is
    deprecated, and an aware value here would be inconsistent with the history
    written before this."""
    return datetime.now(UTC).replace(tzinfo=None)


# An entry whose content is the photographs on it rather than any words. A kind of
# its own rather than a note that happens to be blank, so that everything which asks
# what an entry is gets an answer: the page draws it its own chip, the fold leaves it
# alone, and add_log knows where the rule about empty messages stops.
PHOTO_ENTRY = "photo"

# The entries that say where something is kept: a move, drawn from its row with a
# link at each end, and a stock check's "not found here" (ADR-0034). Kinds of their
# own because they go behind the same switch the Location row does -- an item's
# history is public, and a line reading "moved from the loft to the garage" is the
# address the row was keeping back -- and because they stay out of the search, which
# is for where a thing is now and not every place it has been.
MOVE_ENTRY = "move"
CHECK_ENTRY = "check"
KEPT_ENTRIES = frozenset({MOVE_ENTRY, CHECK_ENTRY})


def add_log(
    db: Session, asset_id: str | None, message: str, kind: str = "change"
) -> LogEntry | None:
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
    db.add(row := LogEntry(asset_id=asset_id, created_at=_now(), kind=kind, message=message))
    return row


def item_log(db: Session, asset_id: str) -> list[LogEntry]:
    return (
        db.query(LogEntry)
        .filter(LogEntry.asset_id == asset_id)
        .order_by(LogEntry.created_at.desc(), LogEntry.id.desc())
        .all()
    )


# How far apart two of the same thing can be and still be one sitting. Long enough
# to cover picking the next photo out of a folder, short enough that coming back to
# the same machine after tea is a separate line.
FOLD_WINDOW = timedelta(minutes=5)

# "deleted a photo" ten times over is "deleted 10 photos", which is the sentence a
# person would have written. Where a message does not name a single thing that way,
# the count is appended instead rather than guessed at.
_ONE_OF = re.compile(r"\ba (photo|file)\b")


def _folded_message(message: str | None, n: int) -> str | None:
    # The column is nullable, and a row from a restored dump can hold a null the
    # app itself would never write. Nothing to pluralise is nothing to fold.
    if n < 2 or not message:
        return message
    plural, hit = _ONE_OF.subn(lambda m: f"{n} {m.group(1)}s", message, count=1)
    return plural if hit else f"{message} ×{n}"


def log_photos(db: Session, log_ids: Sequence[int]) -> dict[int, list[str]]:
    """{log entry id: [photo path]} for a page's worth of entries, in one query and
    in the order they were attached."""
    if not log_ids:
        return {}
    out: dict[int, list[str]] = {}
    for log_id, rel in (
        db.query(LogPhoto.log_id, LogPhoto.rel)
        .filter(LogPhoto.log_id.in_(log_ids))
        .order_by(LogPhoto.id)
    ):
        out.setdefault(log_id, []).append(rel)
    return out


def _fold_log(
    entries: Sequence[LogEntry], photos: dict[int, list[str]] | None = None
) -> list[SimpleNamespace]:
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
    out: list[SimpleNamespace] = []
    for e in entries:
        last = out[-1] if out else None
        mine = photos.get(e.id) or []
        if (
            last is not None
            and not mine
            and not last.photos
            and e.kind != "note"
            and last.kind == e.kind
            and last.message == e.message
            and last.created_at
            and e.created_at
            and last.oldest - e.created_at <= FOLD_WINDOW
        ):
            last.count += 1
            last.oldest = e.created_at
            # Every row the one line stands for, so that deleting it removes what it
            # says it is rather than one twentieth of it.
            last.ids.append(e.id)
            continue
        out.append(
            SimpleNamespace(
                id=e.id,
                created_at=e.created_at,
                kind=e.kind,
                message=e.message,
                count=1,
                photos=mine,
                oldest=e.created_at,
                ids=[e.id],
            )
        )
    # Newest first, so a run's own stamp is the last time it was done; the count in
    # the message says the rest.
    for line in out:
        line.message = _folded_message(line.message, line.count)
    return out


def _history(db: Session, asset_id: str, kept: bool = True) -> list[SimpleNamespace]:
    """One item's history as its page wants it: folded, with each entry's
    photographs on it, and a move's row on the line it is drawn as. Three queries
    whatever the history is long.

    `kept` is whether this reader is told where things are kept (locations.shown).
    Without it the moves and the stock-check lines are left out, rather than drawn
    with the places blanked: a line saying something moved and not where is a line
    saying there is somewhere to know about."""
    entries = item_log(db, asset_id)
    if not kept:
        entries = [e for e in entries if e.kind not in KEPT_ENTRIES]
    lines = _fold_log(entries, log_photos(db, [e.id for e in entries]))
    ids = [e.id for e in entries if e.kind == MOVE_ENTRY]
    moves = {m.log_id: m for m in db.query(Move).filter(Move.log_id.in_(ids))} if ids else {}
    for line in lines:
        line.move = moves.get(line.id)
    return lines


def log_stamp(created_at: datetime | None, authed: bool) -> str:
    """A history line's date, with the clock time only for whoever is signed in.
    Editing wants the minute -- it is how you tell apart two corrections to the same
    photo -- but a visitor is reading about the machine, and the time of day says
    more about the owner's evenings than about the hardware."""
    if not created_at:
        return ""
    return created_at.strftime("%Y-%m-%d %H:%M" if authed else "%Y-%m-%d")


templates.env.globals["log_stamp"] = log_stamp


def _short(v: object, limit: int = 80) -> str:
    v = "" if v is None else str(v).strip()
    if not v:
        return "(empty)"
    return v if len(v) <= limit else v[: limit - 1] + "…"
