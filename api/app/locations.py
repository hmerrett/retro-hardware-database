"""Where things are kept: the memory of the places used, and the list a form offers.

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
"""

from collections.abc import Sequence
from datetime import UTC, datetime

from sqlalchemy.orm import Session

from . import settings
from .models import Location


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
