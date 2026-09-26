"""What the side rail holds besides links: the counts, and the owner's last three.

The rail is navigation and nothing else would need a module -- but two of the
things it carries are facts about the register rather than markup, and both have a
reader in them. A count is what *this* reader may see: a visitor's Projects figure
leaves out the private ones and their Files figure leaves out the unpublished ones,
or the rail would be announcing the existence of exactly what those two switches
keep back (ADR-0009, ADR-0004). Hiding a row and publishing its number is half a
decision.

`Recent` is the owner's alone, and is read from the history rather than from a
column: the history is what already records that somebody touched a thing, and a
`last_seen` column would be a second answer to the same question for the rail's
sake.

The queries run on every page a rail is drawn on, which is why they are counts and
a short slice rather than rows fetched and measured. There is no cache: a count
that lags is a count that argues with the page beside it, and these are small
tables on a register one person is editing.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, NamedTuple

from sqlalchemy import func
from sqlalchemy.exc import SQLAlchemyError

from . import machines
from .common import _held, _visible, to_dict
from .db import SessionLocal
from .entry import display_name
from .models import Computer, LogEntry, Part, Project, StoredFile

if TYPE_CHECKING:
    from fastapi import Request

# The device's own answer, kept in a cookie because it is the device's: the wide
# screen in the workshop can hold the rail open while the laptop folds it away. A
# link writes it, so the whole thing works with no script at all.
COOKIE = "rhdb_rail"
OPEN, SHUT = "open", "collapsed"

# Three, because it is the rail's argument and not a second gallery: at a bench you
# go back to the same two machines all afternoon, and a list long enough to search
# is a list nobody glances at.
RECENT = 3

# How far back the history is read to find them. A change is a row, so three items
# can be a great many rows -- forty covers a long session on one machine, and taking
# a slice is what keeps this off a group-by over the whole table.
_HISTORY_SLICE = 40


class Item(NamedTuple):
    """One of the owner's recent things: what to call it and where it lives."""

    href: str
    tag: str
    name: str


def collapsed(request: Request) -> bool:
    return request.cookies.get(COOKIE) == SHUT


def counts(authed: bool) -> dict[str, int]:
    """The figure beside each section, for this reader, keyed by the section's path.

    Numbers has none: the page is figures about the collection, and a count of
    those is a fact about the software.

    Nothing at all if the database cannot answer. The error page is drawn in this
    same chrome, and the likeliest reason it is being drawn is that the database
    did not answer -- so a rail that raised here would put a second error on top of
    the first, which is the fault errors.py is already careful about. A rail with
    no figures beside its sections is still a rail.
    """
    try:
        with SessionLocal() as db:
            files = db.query(func.count(StoredFile.id))
            if not authed:
                files = files.filter(StoredFile.public.is_(True))
            return {
                "/": sum(
                    _held(db.query(func.count(model.asset_id)), model).scalar() or 0
                    for model in (Computer, Part)
                ),
                "/projects": _visible(db.query(func.count(Project.asset_id)), authed).scalar() or 0,
                "/machines": len(machines.keys()),
                "/files": files.scalar() or 0,
            }
    except SQLAlchemyError:
        return {}


def recent(limit: int = RECENT) -> list[Item]:
    """The last few things the owner edited, newest first.

    The history names an asset and not a kind, so the rows are looked up in both
    registers and whichever answers is what it was. A change to something since
    deleted simply does not come back, which is the right answer to "take me back
    to what I was doing": there is nothing to go back to.

    Empty rather than raising when the database cannot answer, for the reason
    `counts` above gives.
    """
    try:
        return _recent(limit)
    except SQLAlchemyError:
        return []


def _recent(limit: int) -> list[Item]:
    with SessionLocal() as db:
        seen: list[str] = []
        for (aid,) in (
            db.query(LogEntry.asset_id)
            .filter(LogEntry.asset_id.isnot(None))
            .order_by(LogEntry.created_at.desc(), LogEntry.id.desc())
            .limit(_HISTORY_SLICE)
        ):
            if aid and aid not in seen:
                seen.append(aid)
        if not seen:
            return []
        found: dict[str, Item] = {}
        # The two queries written out rather than a loop over the pair of classes:
        # a variable holding either of them widens to the base they share, and the
        # rows read from it lose the columns this reads off them.
        for where, rows in (
            ("/computers", db.query(Computer).filter(Computer.asset_id.in_(seen))),
            ("/parts", db.query(Part).filter(Part.asset_id.in_(seen))),
        ):
            for row in rows:
                aid = str(row.asset_id)
                found[aid] = Item(f"{where}/{aid}", aid, display_name(to_dict(row)))
        return [found[aid] for aid in seen if aid in found][:limit]
