"""Allocate an asset id, unique across every table in the register.

The register is computers, parts and projects. The third is not an object on a
shelf and never gets a printed label, but it draws from the same pool because an
id is what /items/<id> resolves and what the history is keyed by: two things
sharing one would put one's notes on the other's page.

Historic ids are sequential (RH-0001); newly created ones are RH- followed by
four random uppercase alphanumeric characters, e.g. RH-K7Q2. Ids are treated
case-insensitively (lookups uppercase the id), so RH-k7q2 finds RH-K7Q2.

The alphabet drops characters that are easily confused when read off a label
and typed back in: the letters I, L, O (which look like 1 / 0) are excluded, so
each confusable pair keeps a single form.
"""

import secrets
import string

from sqlalchemy.orm import Session

from .models import Computer, Part, Project

PREFIX = "RH-"
_CONFUSABLE = set("ILO")
ALPHABET = "".join(c for c in string.ascii_uppercase + string.digits if c not in _CONFUSABLE)


def _random_id() -> str:
    return PREFIX + "".join(secrets.choice(ALPHABET) for _ in range(4))


def next_asset_id(db: Session) -> str:
    taken: set[str] = set()
    for model in (Computer, Part, Project):
        for (aid,) in db.query(model.asset_id).all():
            taken.add(aid)
    for _ in range(10000):
        candidate = _random_id()
        if candidate not in taken:
            return candidate
    raise RuntimeError("could not allocate a free asset id")
