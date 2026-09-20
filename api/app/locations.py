"""Where things are kept: the memory of the places used, the list a form offers,
and where a part is when it does not say for itself.

The pick lists everywhere else on this site are derived -- `pages._answers_given`
counts the spellings in a column and offers the commonest back -- and nothing is
stored, because a source is written once and goes on being true. A location does
not: it stops being true the moment the thing is moved, so the last item out of a
crate takes the crate's spelling out of the register with it, and the crate is
typed again a month later as something not quite the same.

This is the half that holds what the derived list loses. A row per place ever
saved, offered after the places something is actually kept in now, and written
only while the owner has asked for it. Turning that off deletes the rows rather
than hiding them (ADR-0027) -- somebody who has said stop remembering where my
things are has not asked for a list kept quietly out of sight.

The other half of the module is the question a part answers by being fitted in
something. Most parts are in a machine, and typing the loft onto each of forty
cards is both a morning's work and forty things to correct when the machine is
carried downstairs -- so a blank location on a fitted part is read off whatever
it is fitted in, worked out at the moment it is shown and never stored.
"""

from collections.abc import Sequence
from datetime import UTC, datetime
from typing import NamedTuple

from sqlalchemy.orm import Session

from . import settings
from .models import Computer, Location, Part


def remember(db: Session, value: str | None) -> None:
    """Note a location as one this collection uses, if the owner is having that.

    Called where an item is saved rather than where one is read, so the vocabulary
    is what has been written down rather than what happens to be on screen. Blank
    is not a place and writes nothing.

    No commit: this rides along with the write that prompted it, so a saved item
    and the location it taught the register arrive together or not at all."""
    if not settings.on("remember_locations"):
        return
    text = (value or "").strip()
    if not text:
        return
    # get() rather than a filtered query: MariaDB's collation folds case on the
    # primary key, so "Loft" finds the row written as "loft" and one crate stays
    # one row however it was capitalised on the day.
    now = datetime.now(UTC).replace(tzinfo=None)
    row = db.get(Location, text)
    if row is None:
        db.add(Location(name=text, used_at=now))
    else:
        row.used_at = now


def purge(db: Session) -> None:
    """Forget every remembered place.

    Run after every save made while the switch is off, not only on the save that
    turned it off: a delete of everything is the same act however many times it
    happens, and needing to know what the switch was a moment ago would make the
    promise depend on a transition nobody can see. Committed here, because the
    save that prompted it has already committed its own work."""
    db.query(Location).delete(synchronize_session=False)
    db.commit()


def suggestions(db: Session, in_use: Sequence[str]) -> list[str]:
    """The pick list for a location box: where things are now, then where things
    have been.

    `in_use` comes in already counted and ordered, because that half is the
    register answering a question about itself and belongs with the other derived
    lists. What is added here is only what that half can no longer say -- a place
    nothing is kept in at the moment -- most recently used first, since the crate
    filled last week is a likelier answer than one nothing has gone into for years.

    Switched off, the answer is the derived list on its own, which is what every
    other box on these forms offers.

    Capped for the reason the derived list is capped: this goes into the markup of
    every form that asks, and a hundred is already past what anybody scrolls
    through looking for a crate."""
    if not settings.on("remember_locations"):
        return list(in_use)
    seen = {text.casefold() for text in in_use}
    return list(in_use) + [
        row.name
        for row in db.query(Location).order_by(Location.used_at.desc(), Location.name).limit(100)
        if row.name.casefold() not in seen
    ]


class Placed(NamedTuple):
    """Where a part is because of what it is fitted in, and whose answer that is.

    `whose` and `kind` are carried with the value because the page has to say
    where the answer came from. A location shown against a part that does not hold
    one would otherwise read as something somebody typed there, and the first
    thing anybody would do about a wrong one is edit the part -- which is the one
    record that cannot fix it."""

    where: str
    whose: str
    kind: str


def inherited(db: Session) -> dict[str, Placed]:
    """Where each part is because of what it is fitted in, for the parts that do
    not say for themselves. Keyed by the part's asset id.

    A part's own answer is not in here: it is already in the column, and every
    reader of this map has that to hand. What is here is only the answer the part
    would have no way of giving -- which is why this is worked out and never
    written down. Storing it would mean rewriting a row of the parts table every
    time a machine was carried upstairs, and getting that wrong is how a register
    comes to say a card is in a loft the machine left two years ago.

    Mounted on before installed in: a chip on a board is wherever the board is,
    and the board is the nearer answer even when the machine it is in has one of
    its own. The first non-blank location up the chain wins, and a chain that
    runs out yields nothing rather than an empty string -- a part in a machine
    nobody has placed is a part nobody has placed.

    Two lean queries for the whole register rather than a walk per part, because
    every caller wants many at once: the gallery is building a card for each of
    them and the search is matching against each of them. The item page asks for
    the lot as well and reads one row out of it -- two queries of a few hundred
    short values is cheaper than the ORM loads that page already does, and one
    implementation cannot disagree with itself about where a part is.
    """
    parts = {
        aid: (parent, computer, (where or "").strip())
        for aid, parent, computer, where in db.query(
            Part.asset_id, Part.parent_id, Part.computer_id, Part.location
        )
    }
    computers = {
        aid: (where or "").strip() for aid, where in db.query(Computer.asset_id, Computer.location)
    }

    def answer(aid: str, seen: frozenset[str]) -> Placed | None:
        # Nothing in the register should be able to build a part mounted on itself
        # -- the forms do not offer it -- but a walk that trusts that is a page
        # that never finishes loading if one ever exists, and the cost of not
        # trusting it is a set.
        if aid in seen:
            return None
        # One pool of asset ids across the whole register (ADR-0007), so an id is a
        # machine or a part and never both, and asking the two maps in turn cannot
        # land on the wrong thing.
        if aid in computers:
            return Placed(computers[aid], aid, "computers") if computers[aid] else None
        row = parts.get(aid)
        if row is None:
            return None
        parent, computer, own = row
        if own:
            return Placed(own, aid, "parts")
        for up in (parent, computer):
            if up and (found := answer(up, seen | {aid})) is not None:
                return found
        return None

    out: dict[str, Placed] = {}
    for aid, (parent, computer, own) in parts.items():
        if own or not (parent or computer):
            continue
        if (found := answer(aid, frozenset())) is not None:
            out[aid] = found
    return out
