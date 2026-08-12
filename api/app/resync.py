"""Re-render the derived caches: a part's specs string, and a machine's memory.

parts.specs is a rendered cache of those tables, refreshed whenever a part is
written, so it only drifts in bulk when something changes underneath it:

  * migration 0002 populated the tables from the strings but never rewrote the
    strings, so parts imported from the old CSVs still carry pre-canonical key
    orderings (16 of them when this was written);
  * migration 0005 turned quantities into numbers, which changes how they render
    ('840MB' -> '840 MB', a unitless '44' -> '44 MB').

A machine's installed_ram and installed_ram_kb are the same kind of cache, over
computer_ram_module / computer_ram_chip, and drift for the same reason: migration
0011 populated the rows, and the parity arithmetic has since been corrected to
group chips by depth (a bank's parity chips are often a different part number from
its data chips, and were being counted as capacity).

computers.variant is the third, over computer_variant / computer_chip, and is the one
that will drift most often: its words come from the catalogue in app/machines.py
rather than from the record, so correcting a chip's part number or renaming a model
leaves every machine filed under it rendering the old wording. That is what makes the
catalogue safe to edit, and this is what brings the strings back into line.

Either way it self-heals the next time that item is edited. This brings the whole
database into step in one pass instead, and prints what it would change first.

    docker compose exec api python -m app.resync           # report only
    docker compose exec api python -m app.resync --write   # apply
"""
from __future__ import annotations

import sys

from . import entry, machinedb, machines, ramdb, specdb, specstruct
from .db import SessionLocal
from .models import Computer, Part


def plan(db):
    """[(part, current specs, rendered specs)] for every part whose string differs."""
    out = []
    for part in db.query(Part).order_by(Part.asset_id).all():
        rendered = specstruct.format(part.type or "other", specdb.read(db, part))
        if rendered != (part.specs or ""):
            out.append((part, part.specs or "", rendered))
    return out


def plan_memory(db):
    """[(computer, current, rendered)] for every machine whose memory cache differs
    from what its module and chip rows now say."""
    out = []
    for c in db.query(Computer).order_by(Computer.asset_id).all():
        mods, chips = ramdb.read(db, c)
        kb = entry.ram_total_kb(mods, chips) or c.installed_ram_kb
        rendered = entry.render_installed_ram(mods, chips, kb,
                                              c.installed_ram_note or "")
        if rendered != (c.installed_ram or "") or kb != c.installed_ram_kb:
            out.append((c, f"{c.installed_ram or ''} [{c.installed_ram_kb} KB]",
                        f"{rendered} [{kb} KB]", mods, chips))
    return out


def plan_variant(db):
    """[(computer, current, rendered)] for every machine whose catalogue line differs
    from what its variant and chip rows now say.

    This one drifts for a reason the others do not: the words in the line come from
    the catalogue rather than from the record, so correcting a chip's part number or a
    model's name in app/machines.py leaves every machine filed under it rendering the
    old wording until it is next edited. That is the price of keeping the catalogue
    editable, and this is how it is paid."""
    out = []
    for c in db.query(Computer).order_by(Computer.asset_id).all():
        v = machinedb.read(db, c)
        rendered = machines.render(v["model_key"], v["issue"], v["style"],
                                   v["region"], v["chips"])
        if rendered != (c.variant or ""):
            out.append((c, c.variant or "", rendered))
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
        memory = plan_memory(db)
        for comp, before, after, _mods, _chips in memory:
            print(f"{comp.asset_id} (memory)")
            print(f"  - {before}")
            print(f"  + {after}")
        variants = plan_variant(db)
        for comp, before, after in variants:
            print(f"{comp.asset_id} (machine)")
            print(f"  - {before}")
            print(f"  + {after}")
        machines_touched = {c.asset_id for c, *_ in memory} | {
            c.asset_id for c, *_ in variants}
        if not changes and not machines_touched:
            print("Every derived value already matches the rows behind it.")
            return 0
        if write:
            for part, _before, after in changes:
                part.specs = after
            for comp, _before, _after, mods, chips in memory:
                ramdb.write(db, comp, mods, chips)
            for comp, _before, _after in variants:
                machinedb.refresh(db, comp)
            db.commit()
            print(f"\nRewrote {len(changes)} part(s) and "
                  f"{len(machines_touched)} machine(s).")
        else:
            print(f"\n{len(changes)} part(s) and {len(machines_touched)} machine(s) "
                  "would change. Re-run with --write to apply.")
    finally:
        db.close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
