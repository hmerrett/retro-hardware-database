"""onboard RAM key, and the nine spec values that never reached a typed column

Every one of these was recorded before the typed tables existed, or in a form the
numeric columns could not take, so it sat in part_attribute: rendered on the page,
invisible to a query. Each is moved to where it belongs, and the original text
goes into the item's history so nothing is lost.

  RH-0015  keyless '2 x serial, 1 x game, 1 x floppy, 2 x HDD' -> port rows. HDD
           is the vocabulary's IDE: the card is a VLB multi-I/O controller and
           the port grid only offers vocabulary names, so 'HDD' would have been
           dropped the next time the form was saved.
  RH-0056  keyless '64-256KB' -> Onboard RAM, a new motherboard key. Free text,
           not a number: a range is what identifies a 5150 board revision.
  RH-0076  'Cache: Fake' -> 0 KB, with PCChips' dummy cache chips noted.
  RH-0037  keyless 'RTC Card' -> the part's name; it says what the thing is.
  RH-HQ5T  'Installed RAM: 8MB' -> type 'ram' with Size, which is what an Intel
           Above Board is.
  RH-997B  keyless 'Mouse, PS/2' -> Type + Interface keys.
  RH-0124  keyless 'ES1869F' -> the sound card's Chip.
  RH-0016  keyless '840MB' -> deleted; Capacity already says 840 MB.
  RH-0246  'Capacity: 20MB (36MB?!)' -> 20 MB, with the doubt kept in notes.

parts.specs is a rendered cache of the typed tables, so the strings are brought
back into step afterwards by `python -m app.resync --write` -- the same follow-up
migrations 0002 and 0005 needed.

Revision ID: 0010_tidy_spec_values
Revises: 0009_disposed_note_not_null
Create Date: 2026-07-30
"""
from alembic import op
import sqlalchemy as sa

revision = "0010_tidy_spec_values"
down_revision = "0009_disposed_note_not_null"
branch_labels = None
depends_on = None

# (asset_id, history line) -- the original text, kept where a human will find it.
LOG = [
    ("RH-0015", "Ports: (unkeyed '2 x serial, 1 x game, 1 x floppy, 2 x HDD') "
                "→ 2× Serial, 1× Game, 1× Floppy, 2× IDE"),
    ("RH-0056", "Onboard RAM: (unkeyed '64-256KB') → 64-256KB"),
    ("RH-0076", "Cache: Fake → 0 KB (dummy cache chips; noted)"),
    ("RH-0037", "name: (empty) → RTC Card, from an unkeyed spec value"),
    ("RH-HQ5T", "type: other → ram; Installed RAM: 8MB → Size: 8192 KB"),
    ("RH-997B", "specs: (unkeyed 'Mouse, PS/2') → Type: Mouse | Interface: PS/2"),
    ("RH-0124", "Chip: (unkeyed 'ES1869F') → ES1869F"),
    ("RH-0016", "specs: removed the unkeyed '840MB' duplicating Capacity: 840 MB"),
    ("RH-0246", "Capacity: 20MB (36MB?!) → 20 MB (the 36MB doubt moved to notes)"),
]

PORTS = [("Serial", 2), ("Game", 1), ("Floppy", 1), ("IDE", 2)]


def upgrade():
    op.add_column("motherboard_spec",
                  sa.Column("onboard_ram", sa.String(64), nullable=True))
    conn = op.get_bind()
    ex = lambda sql, **p: conn.execute(sa.text(sql), p)

    for port, n in PORTS:
        ex("INSERT INTO part_port (part_id, port, count) "
           "VALUES ('RH-0015', :port, :n)", port=port, n=n)

    ex("UPDATE motherboard_spec SET onboard_ram = '64-256KB' WHERE part_id = 'RH-0056'")

    ex("UPDATE motherboard_spec SET cache_kb = 0 WHERE part_id = 'RH-0076'")
    ex("UPDATE parts SET notes = TRIM(CONCAT(notes, ' Cache chips are fake -- "
       "PCChips shipped the M918 with dummy cache packages.')) "
       "WHERE asset_id = 'RH-0076'")

    ex("UPDATE parts SET name = 'RTC Card' WHERE asset_id = 'RH-0037'")

    ex("UPDATE parts SET type = 'ram' WHERE asset_id = 'RH-HQ5T'")
    ex("INSERT INTO ram_spec (part_id, size_kb) VALUES ('RH-HQ5T', 8192)")

    ex("INSERT INTO part_attribute (part_id, akey, avalue) "
       "VALUES ('RH-997B', 'Type', 'Mouse'), ('RH-997B', 'Interface', 'PS/2')")

    ex("UPDATE sound_spec SET chip = 'ES1869F' WHERE part_id = 'RH-0124'")

    ex("UPDATE storage_spec SET capacity_kb = 20480 WHERE part_id = 'RH-0246'")
    ex("UPDATE parts SET notes = TRIM(CONCAT(notes, ' Capacity was recorded as "
       "\"20MB (36MB?!)\": 20 MB formatted, the label suggesting 36 MB.')) "
       "WHERE asset_id = 'RH-0246'")

    # Every value above now lives in a typed column or a keyed attribute.
    ex("DELETE FROM part_attribute WHERE (part_id, akey) IN "
       "(('RH-0015',''), ('RH-0056',''), ('RH-0076','Cache'), ('RH-0037',''), "
       " ('RH-HQ5T','Installed RAM'), ('RH-997B',''), ('RH-0124',''), "
       " ('RH-0016',''), ('RH-0246','Capacity'))")

    for aid, message in LOG:
        ex("INSERT INTO log_entry (asset_id, created_at, kind, message) "
           "VALUES (:aid, NOW(), 'change', :msg)", aid=aid, msg=message)


def downgrade():
    conn = op.get_bind()
    ex = lambda sql, **p: conn.execute(sa.text(sql), p)
    ex("DELETE FROM part_port WHERE part_id = 'RH-0015'")
    ex("DELETE FROM ram_spec WHERE part_id = 'RH-HQ5T'")
    ex("UPDATE parts SET type = 'other' WHERE asset_id = 'RH-HQ5T'")
    ex("UPDATE parts SET name = '' WHERE asset_id = 'RH-0037'")
    ex("DELETE FROM part_attribute WHERE part_id = 'RH-997B' "
       "AND akey IN ('Type', 'Interface')")
    ex("UPDATE sound_spec SET chip = NULL WHERE part_id = 'RH-0124'")
    ex("UPDATE motherboard_spec SET cache_kb = NULL WHERE part_id = 'RH-0076'")
    ex("UPDATE storage_spec SET capacity_kb = NULL WHERE part_id = 'RH-0246'")
    for aid, message in LOG:
        ex("DELETE FROM log_entry WHERE asset_id = :aid AND message = :msg",
           aid=aid, msg=message)
    op.drop_column("motherboard_spec", "onboard_ram")
