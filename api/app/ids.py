"""Allocate an asset id, unique across every table in the register, and read one
back out of what somebody typed or scanned.

The register is computers, parts, projects and locations. The last two are not
objects anybody owns, but they draw from the same pool because an id is what
/items/<id> resolves and what the history is keyed by: two things sharing one
would put one's notes on the other's page. A location's label is scanned like a
machine's for the same reason (ADR-0034).

Historic ids are sequential (RH-0001); newly created ones are RH- followed by
four random uppercase alphanumeric characters, e.g. RH-K7Q2. Ids are treated
case-insensitively (lookups uppercase the id), so RH-k7q2 finds RH-K7Q2.

The alphabet drops characters that are easily confused when read off a label
and typed back in: the letters I, L, O (which look like 1 / 0) are excluded, so
each confusable pair keeps a single form.
"""

import re
import secrets
import string

from sqlalchemy.orm import Session

from .models import Computer, Location, Part, Project

PREFIX = "RH-"
_CONFUSABLE = set("ILO")
ALPHABET = "".join(c for c in string.ascii_uppercase + string.digits if c not in _CONFUSABLE)


def _random_id() -> str:
    return PREFIX + "".join(secrets.choice(ALPHABET) for _ in range(4))


# A tag as it is written on a label, in either case: RH- and four characters, with
# nothing of the same sort on either side of it. Historic ids are four digits and
# new ones four from ALPHABET, and both fit. Loose about the alphabet on purpose --
# a tag with an O in it is not one this register issued, and the answer to that is
# "no such tag", which the caller gives, rather than "that is not a tag".
_TAG = re.compile(r"(?<![0-9A-Z])RH-[0-9A-Z]{4}(?![0-9A-Z])", re.IGNORECASE)


def exact_tag(text: str | None) -> str | None:
    """The tag `text` is, uppercased, when it is a tag and nothing else."""
    typed = (text or "").strip()
    return typed.upper() if _TAG.fullmatch(typed) else None


def tag_in(text: str | None) -> str | None:
    """The one tag in what a scanner typed, or None.

    A barcode types the tag; a QR code read by a handheld scanner types the URL it
    holds, `<base_url>/items/RH-K7Q2/`. Either is the same label, so the tag is read
    out of whatever arrived -- and only when there is exactly one, since a code with
    two tags in it is not a label this register printed."""
    found = {m.upper() for m in _TAG.findall(text or "")}
    return found.pop() if len(found) == 1 else None


def next_asset_id(db: Session) -> str:
    taken: set[str] = set()
    for model in (Computer, Part, Project, Location):
        for (aid,) in db.query(model.asset_id).all():
            taken.add(aid)
    for _ in range(10000):
        candidate = _random_id()
        if candidate not in taken:
            return candidate
    raise RuntimeError("could not allocate a free asset id")
