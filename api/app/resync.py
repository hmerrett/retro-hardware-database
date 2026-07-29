"""Re-render every part's specs string from the typed spec tables.

parts.specs is a rendered cache of those tables, refreshed whenever a part is
written, so it only drifts in bulk when something changes underneath it:

  * migration 0002 populated the tables from the strings but never rewrote the
    strings, so parts imported from the old CSVs still carry pre-canonical key
    orderings (16 of them when this was written);
  * migration 0005 turned quantities into numbers, which changes how they render
    ('840MB' -> '840 MB', a unitless '44' -> '44 MB').

Either way it self-heals the next time that part is edited. This brings the whole
table into step in one pass instead, and prints what it would change first.

    docker compose exec api python -m app.resync           # report only
    docker compose exec api python -m app.resync --write   # apply
"""
from __future__ import annotations

import sys

from . import specdb, specstruct
from .db import SessionLocal
from .models import Part


def plan(db):
    """[(part, current specs, rendered specs)] for every part whose string differs."""
    out = []
    for part in db.query(Part).order_by(Part.asset_id).all():
        rendered = specstruct.format(part.type or "other", specdb.read(db, part))
        if rendered != (part.specs or ""):
            out.append((part, part.specs or "", rendered))
    return out


def main(argv=None):
    argv = sys.argv[1:] if argv is None else argv
    write = "--write" in argv
    db = SessionLocal()
    try:
        changes = plan(db)
        for part, before, after in changes:
            print(f"{part.asset_id} ({part.type or 'other'})")
            print(f"  - {before}")
            print(f"  + {after}")
        if not changes:
            print("Every part's specs string already matches its typed rows.")
            return 0
        if write:
            for part, _before, after in changes:
                part.specs = after
            db.commit()
            print(f"\nRewrote {len(changes)} part(s).")
        else:
            print(f"\n{len(changes)} part(s) would change. Re-run with --write to apply.")
    finally:
        db.close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
