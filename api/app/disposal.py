"""Disposing of a thing, and bringing it back.

Disposal keeps the record and says the thing has gone, which is the opposite of
deletion and the reason both exist. What makes it more than a flag is what is inside
a thing: disposing of a machine, or of a part with others mounted on it, disposes of
everything inside it, all the way down (ADR-0036), and restoring it brings back only
those that went with it and not the ones disposed of separately beforehand. A part
brought back on its own, out of something still gone, comes out of it, since nothing
is kept inside something that has left. That bookkeeping is here, and so is the one
question the owner answers on an item page that drives it: where the thing stands.
"""

from datetime import date
from typing import Final

from sqlalchemy.orm import Session

from . import tree
from .history import add_log
from .models import Computer, Part


# The three answers on an item page's Status panel, as its radio buttons send them.
HELD: Final = "held"
MIGHT_SELL: Final = "might-sell"
DISPOSED: Final = "disposed"
STATUSES: Final = (HELD, MIGHT_SELL, DISPOSED)


def _disposal_log(
    obj: Computer | Part, with_machine: str | None = None, what: str = "marked disposed"
) -> str:
    """The history line for a disposal: when, and why if a reason was given."""
    when = obj.disposed_at.isoformat() if obj.disposed_at else "date unknown"
    who = f" with {with_machine}" if with_machine else ""
    return f"{what}{who} ({when})" + (f": {obj.disposed_note}" if obj.disposed_note else "")


def inside(db: Session, aid: str, r: tree.Tree | None = None) -> list[Part]:
    """Everything inside a machine or a part, however far down, nearest first: the
    cards in it, then the drives on those cards. Read off the tree, so that what a
    delete calls "in the machine" is exactly what disposal called it."""
    r = r or tree.load(db)
    tags = r.within(aid.upper())
    found = (
        {p.asset_id.upper(): p for p in db.query(Part).filter(Part.asset_id.in_(tags))}
        if tags
        else {}
    )
    return [found[tag] for tag in tags if tag in found]


def _dispose_contents(db: Session, c: Computer | Part) -> int:
    """A machine goes to the tip with what is in it, and a card with what is mounted
    on it. A part already disposed keeps the record it has -- it did not go with this
    one -- and so is left alone, which is also what lets a restore tell the two
    apart."""
    n = 0
    for p in inside(db, c.asset_id):
        if p.disposed:
            continue
        p.disposed, p.disposed_at = True, c.disposed_at
        p.disposed_note = c.disposed_note
        add_log(db, p.asset_id, _disposal_log(p, c.asset_id))
        n += 1
    return n


def _went_with(p: Part, was_at: date | None, was_note: str | None) -> bool:
    """Whether a part inside something went out with it: nothing records that but the
    part carrying the same disposal, date and why, which is why a correction has to
    reach the parts too."""
    return p.disposed and p.disposed_at == was_at and (p.disposed_note or "") == (was_note or "")


def _restore_contents(
    db: Session, c: Computer | Part, was_at: date | None, was_note: str | None
) -> int:
    """The other half of the cascade: the parts that went out with this one -- still
    in it, and still carrying its disposal record -- come back with it."""
    n = 0
    for p in inside(db, c.asset_id):
        if not _went_with(p, was_at, was_note):
            continue
        p.disposed, p.disposed_at, p.disposed_note = False, None, ""
        add_log(db, p.asset_id, f"restored with {c.asset_id}")
        n += 1
    return n


def _correct_contents(
    db: Session, c: Computer | Part, was_at: date | None, was_note: str | None
) -> int:
    """A disposal's date or why corrected: the parts that went out with it are
    corrected with it, or the restore that finds them by that record would leave them
    behind. A part disposed of on its own beforehand keeps its own record."""
    n = 0
    for p in inside(db, c.asset_id):
        if not _went_with(p, was_at, was_note):
            continue
        p.disposed_at, p.disposed_note = c.disposed_at, c.disposed_note
        add_log(db, p.asset_id, _disposal_log(p, c.asset_id, "disposal corrected"))
        n += 1
    return n


def set_status(
    db: Session, obj: Computer | Part, to: str, note: str, when: date | None, who: str
) -> None:
    """The Status panel's answer, carried out: In the collection, Might sell or
    Disposed. One question with one answer, so disposing of a thing takes it off the
    shortlist, and choosing either of the others brings a disposed thing back.

    Disposed again, on something already gone, corrects the date and why rather than
    disposing of it twice. A blank date is today for a disposal being made, and
    unknown for one being corrected: emptying the box on a record says the date is not
    known, where a new disposal is ordinarily happening now."""
    if to == DISPOSED:
        obj.for_sale = False
        if not obj.disposed:
            obj.disposed, obj.disposed_at, obj.disposed_note = True, when or date.today(), note
            n = _dispose_contents(db, obj)
            add_log(db, obj.asset_id, _disposal_log(obj) + _and_parts(n))
        elif (obj.disposed_at, obj.disposed_note or "") != (when, note):
            was_at, was_note = obj.disposed_at, obj.disposed_note
            obj.disposed_at, obj.disposed_note = when, note
            n = _correct_contents(db, obj, was_at, was_note)
            add_log(
                db,
                obj.asset_id,
                _disposal_log(obj, what="disposal corrected") + _and_parts(n, "corrected too"),
            )
        return
    if obj.disposed:
        was_at, was_note = obj.disposed_at, obj.disposed_note
        obj.disposed, obj.disposed_at, obj.disposed_note = False, None, ""
        n = _restore_contents(db, obj, was_at, was_note)
        add_log(db, obj.asset_id, "restored" + _and_parts(n, "came back too"))
        if isinstance(obj, Part):
            # Back on its own, out of something still gone: it comes out of it (ADR-0036).
            out_of_the_disposed(db, obj, who)
    obj.for_sale = to == MIGHT_SELL


def out_of_the_disposed(db: Session, p: Part, who: str) -> bool:
    """A part restored on its own, from inside something still disposed of, comes
    out of it and is left nowhere: nothing is kept inside something that has left the
    collection (ADR-0036). Whether it had to."""
    r = tree.load(db)
    for up in r.up(p.asset_id.upper()):
        if r.what(up) not in (tree.COMPUTER, tree.PART):
            break
        holder = tree.item(db, up)
        if holder is not None and holder.disposed:
            tree.put(db, p, None, tree.EDIT, who, r)
            return True
    return False


def _and_parts(n: int, went: str = "went with it") -> str:
    """The tail of a machine's history line when the cascade touched anything."""
    return f"\n{n} part{'' if n == 1 else 's'} in it {went}" if n else ""
