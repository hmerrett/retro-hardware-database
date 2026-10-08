"""Disposing of a thing, and bringing it back.

Disposal keeps the record and says the thing has gone, which is the opposite of
deletion and the reason both exist. What makes it more than a flag is what is inside
a thing: disposing of a machine, or of a part with others mounted on it, disposes of
everything inside it, all the way down (ADR-0036), and restoring it brings back only
those that went with it and not the ones disposed of separately beforehand. A part
brought back on its own, out of something still gone, comes out of it, since nothing
is kept inside something that has left. That bookkeeping is here.
"""

from datetime import date

from sqlalchemy.orm import Session

from . import tree
from .history import add_log
from .models import Computer, Part


def _disposal_log(obj: Computer | Part, with_machine: str | None = None) -> str:
    """The history line for a disposal: when, and why if a reason was given."""
    when = obj.disposed_at.isoformat() if obj.disposed_at else "date unknown"
    who = f" with {with_machine}" if with_machine else ""
    return f"marked disposed{who} ({when})" + (
        f": {obj.disposed_note}" if obj.disposed_note else ""
    )


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


def _restore_contents(
    db: Session, c: Computer | Part, was_at: date | None, was_note: str | None
) -> int:
    """The other half of the cascade: the parts that went out with this one -- still
    in it, and still carrying its disposal record -- come back with it."""
    n = 0
    for p in inside(db, c.asset_id):
        if not (
            p.disposed and p.disposed_at == was_at and (p.disposed_note or "") == (was_note or "")
        ):
            continue
        p.disposed, p.disposed_at, p.disposed_note = False, None, ""
        add_log(db, p.asset_id, f"restored with {c.asset_id}")
        n += 1
    return n


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
