"""a drive's description, split into the fields that now ask for it

The bay a drive fits and the disk it takes are picked from lists now, not written
into its description and read back out of the prose. Eight drives were recorded
before those pickers existed, and each says the same two things in the same order,
so each is split into them -- read by drivedb's own parser, whose answers these
are, rather than by a second reading of the same words:

  RH-3FTN  Sony MP-F17W-12         3.5” 1.44MB       -> 3.5"  1.44MB
  RH-3U0R  Mitsubishi MF353C-258NR 3.5” 720KB        -> 3.5"  720K
  RH-7663  Panasonic JU-256A217P   3.5” 1.44MB       -> 3.5"  1.44MB
  RH-EHXZ  Samsung SGD-321B        3.5” 1.44MB       -> 3.5"  1.44MB
  RH-ERBM  Sony MP-F17W-02         3.5” 1.44MB       -> 3.5"  1.44MB
  RH-HNT6  Matsushita JU-253A23M   3.5” 720K         -> 3.5"  720K
  RH-JCWB  Tandon TM100-1          5.25" 180K SS/DD  -> 5.25" 180K,  SS/DD kept
  RH-X91R  Mitsubishi M4853        5.25" 720K DS/DD  -> 5.25" 720K,  DS/DD kept

Six are said entirely by the two pickers, so their descriptions go. The other two
also record the media -- single- or double-sided, double density -- which no
picker offers and which is a real fact about the disks the drive takes, so that
much of the description stays and the drive keeps a description to show for it.

Only the notation changes. 720KB becomes 720K because that is the one spelling the
list offers, not because the disk is a different disk; no make or model is touched,
and every one of these eight already records both under Identity, which is where a
routed drive's make and model are read from now.

Six of the eight wrote the inch mark as a curly ” rather than a straight " -- what
a phone or a Mac autocorrects it to. drivedb did not know that character, so it
read 3.5” as the drive's *model*: the before-and-after here is what the parser
gives now that it does, which is why the fix to _FORM_RE ships with this.

parts.specs is a rendered cache of the typed tables, so the strings are brought
back into step afterwards by `python -m app.resync --write` -- the same follow-up
migrations 0002, 0005 and 0010 needed.

Revision ID: 0016_drive_description_split
Revises: 0015_bezel_yellowing
Create Date: 2026-08-07
"""
import sqlalchemy as sa
from alembic import op

revision = "0016_drive_description_split"
down_revision = "0015_bezel_yellowing"
branch_labels = None
depends_on = None

# asset, the description as recorded, its form factor, its capacity, and what is
# left of the description afterwards ("" deletes it).
SPLITS = [
    ("RH-3FTN", "3.5” 1.44MB", '3.5"', "1.44MB", ""),
    ("RH-3U0R", "3.5” 720KB", '3.5"', "720K", ""),
    ("RH-7663", "3.5” 1.44MB", '3.5"', "1.44MB", ""),
    ("RH-EHXZ", "3.5” 1.44MB", '3.5"', "1.44MB", ""),
    ("RH-ERBM", "3.5” 1.44MB", '3.5"', "1.44MB", ""),
    ("RH-HNT6", "3.5” 720K", '3.5"', "720K", ""),
    ("RH-JCWB", '5.25" 180K SS/DD', '5.25"', "180K", "SS/DD"),
    ("RH-X91R", '5.25" 720K DS/DD', '5.25"', "720K", "DS/DD"),
]


def _log(conn, aid, message):
    conn.execute(sa.text(
        "INSERT INTO log_entry (asset_id, created_at, kind, message) "
        "VALUES (:a, NOW(), 'change', :m)"), {"a": aid, "m": message})


def _set_attr(conn, aid, key, value):
    """Add a key, or leave a hand-entered one alone. Nothing here overwrites an
    answer someone has already given: a drive that has been through the pickers
    since is already saying what this would say."""
    existing = conn.execute(sa.text(
        "SELECT avalue FROM part_attribute WHERE part_id = :a AND akey = :k"),
        {"a": aid, "k": key}).first()
    if existing:
        return existing[0] == value
    conn.execute(sa.text(
        "INSERT INTO part_attribute (part_id, akey, avalue) "
        "VALUES (:a, :k, :v)"), {"a": aid, "k": key, "v": value})
    return True


def upgrade():
    conn = op.get_bind()
    for aid, before, form, size, after in SPLITS:
        # Only a description still reading exactly as it did: one edited since is
        # a newer answer than this migration's, and is left to stand.
        found = conn.execute(sa.text(
            "SELECT id FROM part_attribute "
            "WHERE part_id = :a AND akey = 'Description' AND avalue = :v"),
            {"a": aid, "v": before}).first()
        if not found:
            continue
        _set_attr(conn, aid, "Form factor", form)
        _set_attr(conn, aid, "Size", size)
        if after:
            conn.execute(sa.text(
                "UPDATE part_attribute SET avalue = :v WHERE id = :i"),
                {"v": after, "i": found[0]})
        else:
            conn.execute(sa.text("DELETE FROM part_attribute WHERE id = :i"),
                         {"i": found[0]})
        _log(conn, aid, f'drive: "{before}" → form factor {form}, size {size}'
                        + (f', description "{after}"' if after else ""))


def downgrade():
    conn = op.get_bind()
    for aid, before, form, size, after in SPLITS:
        for key, value in (("Form factor", form), ("Size", size)):
            conn.execute(sa.text(
                "DELETE FROM part_attribute "
                "WHERE part_id = :a AND akey = :k AND avalue = :v"),
                {"a": aid, "k": key, "v": value})
        if after:
            conn.execute(sa.text(
                "UPDATE part_attribute SET avalue = :b "
                "WHERE part_id = :a AND akey = 'Description' AND avalue = :v"),
                {"a": aid, "b": before, "v": after})
        else:
            conn.execute(sa.text(
                "INSERT INTO part_attribute (part_id, akey, avalue) "
                "VALUES (:a, 'Description', :v)"), {"a": aid, "v": before})
        conn.execute(sa.text(
            "DELETE FROM log_entry WHERE asset_id = :a AND message LIKE 'drive: %'"),
            {"a": aid})
