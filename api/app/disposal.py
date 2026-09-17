"""Disposing of a thing, and bringing it back.

Disposal keeps the record and says the thing has gone, which is the opposite of
deletion and the reason both exist. What makes it more than a flag is the
machine: disposing of one disposes of what was fitted inside it, and restoring it
brings back only those that went with it and not the ones disposed of separately
beforehand. That bookkeeping is here.
"""

from .history import add_log
from .models import Part


def _disposal_log(obj, with_machine=None):
    """The history line for a disposal: when, and why if a reason was given."""
    when = obj.disposed_at.isoformat() if obj.disposed_at else "date unknown"
    who = f" with {with_machine}" if with_machine else ""
    return f"marked disposed{who} ({when})" + (
        f": {obj.disposed_note}" if obj.disposed_note else ""
    )


def _parts_in_computer(db, aid):
    """Everything inside a machine: the parts installed in it, and then whatever
    is mounted on those in turn. A disk on a controller card carries the card's
    id rather than the machine's, so following computer_id alone would miss it."""
    found, seen = [], set()
    ids, first = [aid], True
    while ids:
        q = (
            db.query(Part).filter(Part.computer_id == aid)
            if first
            else db.query(Part).filter(Part.parent_id.in_(ids))
        )
        rows = [p for p in q.order_by(Part.asset_id).all() if p.asset_id not in seen]
        seen.update(p.asset_id for p in rows)
        found.extend(rows)
        ids, first = [p.asset_id for p in rows], False
    return found


def _dispose_contents(db, c):
    """A machine goes to the tip with what is in it. A part already disposed keeps
    the record it has -- it did not go with this machine -- and so is left alone,
    which is also what lets a restore tell the two apart."""
    n = 0
    for p in _parts_in_computer(db, c.asset_id):
        if p.disposed:
            continue
        p.disposed, p.disposed_at = True, c.disposed_at
        p.disposed_note = c.disposed_note
        add_log(db, p.asset_id, _disposal_log(p, c.asset_id))
        n += 1
    return n


def _restore_contents(db, c, was_at, was_note):
    """The other half of the cascade: the parts that went out with this machine --
    still in it, and still carrying its disposal record -- come back with it."""
    n = 0
    for p in _parts_in_computer(db, c.asset_id):
        if not (
            p.disposed and p.disposed_at == was_at and (p.disposed_note or "") == (was_note or "")
        ):
            continue
        p.disposed, p.disposed_at, p.disposed_note = False, None, ""
        add_log(db, p.asset_id, f"restored with {c.asset_id}")
        n += 1
    return n


def _and_parts(n, went="went with it"):
    """The tail of a machine's history line when the cascade touched anything."""
    return f"\n{n} part{'' if n == 1 else 's'} in it {went}" if n else ""
