"""Check every storage part against the questions its kind is actually asked.

entry.STORAGE_ASKS decides what a drive of each kind is asked, and both the form and
the save path read it, so a part can only fall out of step with it from outside: a
CSV import, the JSON API, a hand-written UPDATE, or a change to the table itself
after records were already on file. This says which parts have, and what is wrong.

    docker compose exec api python -m app.audit_storage           # everything
    docker compose exec api python -m app.audit_storage --gaps    # and what is blank

An answer outside its kind's list is reported but is not necessarily wrong: a closed
list has a custom box beside it for the hardware it does not name, and a value from
there reopens on that box rather than being lost. Read it as "check this one", not
"repair this one". Nothing is written either way.
"""

from __future__ import annotations

import sys
from collections import Counter, defaultdict

from . import entry, specdb, specstruct
from .db import SessionLocal
from .models import Part, StorageSpec

# Recorded against a drive without being one of the asks: the kind itself, and the
# prose that says what the pickers could not. The bezel pair has its own kinds.
ALWAYS = ("Kind", "Description")
BEZEL = ("Colour", "Yellowing")


def _keys(db, part):
    return {k: v for k, v in specstruct.pairs(part.type or "storage", specdb.read(db, part)) if k}


def check(db, part):
    """Everything wrong with one part: (kind, [sentences])."""
    keys = _keys(db, part)
    kind = keys.get("Kind", "")
    if not kind:
        return "", ["no kind recorded, so nothing can be asked of it"]
    if kind not in entry.STORAGE_KINDS:
        return kind, [f"kind {kind!r} is not one the menu offers"]

    out = []
    asks = {a["key"]: a for a in entry.storage_asks(kind)}
    allowed = set(asks) | set(ALWAYS) | (set(BEZEL) if kind in entry.BEZEL_KINDS else set())
    for key, value in keys.items():
        if key not in allowed:
            out.append(f"has {key} = {value!r}, which this kind is not asked")
        elif (ask := asks.get(key)) and ask["options"] and value not in ask["options"]:
            out.append(
                f"{key} = {value!r} is not on this kind's list (the custom box, or a mistake)"
            )
    if not keys.get("Interface"):
        out.append("no interface, which every drive is asked for")

    # The two speed columns: a reader's × rating and a spindle's rpm. Nothing should
    # hold one where its kind means the other.
    row = db.get(StorageSpec, part.asset_id)
    if row:
        if row.speed_x is not None and kind != entry.OPTICAL_KIND:
            out.append(f"a × rating ({row.speed_x}) in the reader's column")
        if row.speed_rpm is not None and kind != entry.DISK_KIND:
            out.append(f"an rpm ({row.speed_rpm}) in the spindle's column")
    if part.disk_image and kind not in entry.DISK_IMAGE_KINDS:
        out.append(f"a disk image ({part.disk_image!r}), which this kind is not asked for")
    return kind, out


def gaps(db, parts):
    """Per kind, how many are missing each answer it is asked for. Blank is a fair
    answer -- nobody may have looked yet -- so this is a completeness report rather
    than a list of faults."""
    missing, totals = defaultdict(Counter), Counter()
    for part in parts:
        keys = _keys(db, part)
        kind = keys.get("Kind", "")
        if kind not in entry.STORAGE_KINDS:
            continue
        totals[kind] += 1
        for ask in entry.storage_asks(kind):
            if not keys.get(ask["key"]):
                missing[kind][ask["key"]] += 1
    return missing, totals


def main(argv=None):
    argv = sys.argv[1:] if argv is None else argv
    db = SessionLocal()
    try:
        parts = db.query(Part).filter(Part.type == "storage").order_by(Part.asset_id).all()
        faults = 0
        for part in parts:
            kind, found = check(db, part)
            if not found:
                continue
            faults += 1
            name = " ".join(x for x in (part.manufacturer, part.model) if x)
            print(f"{part.asset_id}  {kind or 'no kind'}" + (f" -- {name}" if name else ""))
            for line in found:
                print(f"    {line}")
        print(f"\n{len(parts)} storage part(s) checked, {faults} with something to look at.")
        if "--gaps" in argv:
            missing, totals = gaps(db, parts)
            print("\nWhat is still blank:")
            for kind in entry.STORAGE_KINDS:
                if not totals[kind]:
                    continue
                print(f"\n  {kind} ({totals[kind]})")
                for ask in entry.storage_asks(kind):
                    n = missing[kind][ask["key"]]
                    print(
                        f"    {ask['key']:12} "
                        + ("answered on every one" if not n else f"blank on {n}")
                    )
    finally:
        db.close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
