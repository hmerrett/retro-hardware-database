#!/usr/bin/env python3
"""Put the two documented power supplies back into the register.

On 6 July 2026 the flat-file system dropped PSU as a component and deleted all
four of the supplies filed under it. Three of those deletions were right: two rows
reading "Generic power supply, Form factor: AT" and, the same day, a generic hard
disk. A type whose every member is generic earns nothing.

The other two were documented models, and they went with the heading:

    RH-0189   Delta Electronics Ltd DPS-300SB-1 B Rev. 00, 300W, working,
              out of RABS at Retrofest 2026 and acquired 30 May 2026
    RH-0215   Kentex Electronic Co Ltd KTX-9006-81, 1992, working,
              in RH-0204 -- the Mitac MiStation 4052F/M it came in

This writes them back. Run it on the server, where the register lives:

    docker compose exec -T api python - < tools/restore_psus.py --list
    docker compose exec -T api python - < tools/restore_psus.py

WHAT IT WRITES, AND WHAT IT WILL NOT. Two parts and two history entries each: the
"created" line every item gets, and a note saying where the record came from and
what in it was read off a machine and what was not. It invents nothing. Every
field is the old row's, except the Delta's form factor and output, which are what
the model is, and both are on the label of any DPS-300SB-1.

The Delta takes its own number back. RH-0189 is a gap in the register and the gap
is its own -- nothing has been filed in it since. The Kentex cannot have RH-0215:
an Opus PCV Turbo has worn that number since shortly after the deletion, so this
allocates a new tag and writes the old number into the history instead.

Idempotent, and it says so rather than doing it twice: a taken asset id is left
alone, and the Kentex -- which cannot be recognised by its id, since it gets a new
one -- is matched on its maker and model.
"""
import sys
from datetime import UTC, date, datetime

from app import specdb
from app.db import SessionLocal
from app.ids import next_asset_id
from app.models import Computer, LogEntry, Part


def now():
    return datetime.now(UTC).replace(tzinfo=None)


def log(db, aid, message, kind="change"):
    db.add(LogEntry(asset_id=aid, created_at=now(), kind=kind, message=message))


WANTED = [
    (dict(asset_id="RH-0189", type="psu",
          manufacturer="Delta Electronics Ltd", model="DPS-300SB-1 B Rev. 00",
          specs="Form factor: ATX | Output: 300W", condition="Working",
          source="RABS, Retrofest 2026", acquired_date=date(2026, 5, 30)),
     "Back from the flat-file register, where this was RH-0189 until 6 July 2026,"
     " when power supplies stopped being a type and the four of them were deleted."
     " Maker, model, condition and where it came from are that row's, not re-read"
     " off the unit; ATX and 300W are what the model is."),
    (dict(asset_id=None, type="psu", computer_id="RH-0204",
          manufacturer="Kentex Electronic Co Ltd", model="KTX-9006-81", year=1992,
          condition="Working"),
     "Back from the flat-file register, where this was RH-0215 until 6 July 2026,"
     " when power supplies stopped being a type. That number is an Opus PCV Turbo"
     " now, so this one is filed under a tag of its own. Maker, model, year and the"
     " machine it is in are the old row's."),
]


def main(write=True):
    db = SessionLocal()
    try:
        for fields, note in WANTED:
            fields = dict(fields)
            aid = fields.pop("asset_id", None)
            if aid:
                held = next((m for m in (Part, Computer) if db.get(m, aid)), None)
                if held:
                    print(f"{aid} is taken already ({held.__name__}) -- skipped")
                    continue
            else:
                # Its own old number belongs to something else now, so it takes a
                # new one -- which means the id cannot say whether this has run
                # before. What the part is says it instead.
                already = (db.query(Part)
                           .filter(Part.manufacturer == fields["manufacturer"],
                                   Part.model == fields["model"]).first())
                if already:
                    print(f"{already.asset_id} is already"
                          f" {fields['model']} -- skipped")
                    continue
                aid = "(a new tag)" if not write else next_asset_id(db)
            host = fields.get("computer_id")
            if host and not db.get(Computer, host):
                print(f"{host} is not in the register -- skipped {fields['model']}")
                continue
            where = f"  in {host}" if host else ""
            print(f"{aid}  {fields['manufacturer']} {fields['model']}{where}")
            if not write:
                continue
            db.add(part := Part(asset_id=aid, **fields))
            db.flush()
            # The specs string is the display copy; the typed tables -- here plain
            # attributes, a supply having no table of its own -- are what the page
            # reads and what an edit writes back.
            specdb.write(db, part)
            log(db, aid, "created", "created")
            log(db, aid, note, "note")
        if write:
            db.commit()
    finally:
        db.close()


if __name__ == "__main__":
    main(write="--list" not in sys.argv)
