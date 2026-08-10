"""what an optical drive takes, and how fast, as fields that ask for it

A floppy is known by the disk it takes -- 3.5", 1.44MB -- and 0016 gave those
their own pickers. An optical drive is known by two different things, and had
nowhere to put either: the discs it reads and writes, and the × rating on its
front. Both were being written into the description, which is where a fact goes
when nothing asks for it.

So a drive row gains media and speed alongside its size, and a storage part gains
a speed_x to sit beside speed_rpm. Two columns for a speed because 48× and
5400 rpm are different quantities that could not share one and still sort or
compare; they answer to one Speed spec key, and the unit written in the value says
which is meant.

All four optical drives on file say both things in their descriptions, in the
notation each was typed in:

  RH-NUUF  "CDRW 48x"             -> Media: CD-RW,  Speed: 48×
  RH-VA5R  "48x CD-ROM Drive"     -> Media: CD-ROM, Speed: 48×
  RH-GN8U  "52x32x52x CD-RW"      -> Media: CD-RW,  Speed: 52×/32×/52×
  RH-PVUB  "4x 2x 20x CD RW"      -> Media: CD-RW,  Speed: 4×/2×/20×

No description says anything else -- "Drive" is the word for the thing it is
already filed as -- so all four go, as six of 0016's eight did. Only the notation
changes: CDRW is the CD-RW the list offers and 48x is the 48× it offers, and no
drive is a different drive for being written down properly.

Two of them quote what a writer does with a disc rather than a single figure --
write, rewrite and read. That is one rating and is kept as one, in the notation
the pickers write it in; it is no kind of a number, so it rides as a verbatim
attribute the way an unparseable quantity always has, and only the drives quoting
one figure fill the speed_x column.

parts.specs is a rendered cache of the typed tables, so the strings are brought
back into step afterwards by `python -m app.resync --write` -- the same follow-up
0002, 0005, 0010 and 0016 needed.

Revision ID: 0017_optical_media_and_speed
Revises: 0016_drive_description_split
Create Date: 2026-08-10
"""
import re

import sqlalchemy as sa
from alembic import op

revision = "0017_optical_media_and_speed"
down_revision = "0016_drive_description_split"
branch_labels = None
depends_on = None

# asset, the description as recorded, its medium, and its rating as written.
SPLITS = [
    ("RH-NUUF", "CDRW 48x", "CD-RW", "48×"),
    ("RH-VA5R", "48x CD-ROM Drive", "CD-ROM", "48×"),
    ("RH-GN8U", "52x32x52x CD-RW", "CD-RW", "52×/32×/52×"),
    ("RH-PVUB", "4x 2x 20x CD RW", "CD-RW", "4×/2×/20×"),
]
# The one figure that is a number, and so has a column to go in.
_ONE_FIGURE = re.compile(r"^(\d+)×$")


def _log(conn, aid, message):
    conn.execute(sa.text(
        "INSERT INTO log_entry (asset_id, created_at, kind, message) "
        "VALUES (:a, NOW(), 'change', :m)"), {"a": aid, "m": message})


def upgrade():
    op.add_column("computer_drive", sa.Column("media", sa.String(32),
                                              nullable=False, server_default=""))
    op.add_column("computer_drive", sa.Column("speed", sa.String(16),
                                              nullable=False, server_default=""))
    op.add_column("storage_spec", sa.Column("speed_x", sa.Integer))

    conn = op.get_bind()
    for aid, before, media, speed in SPLITS:
        # Only a description still reading exactly as it did: one edited since is a
        # newer answer than this migration's, and is left to stand.
        found = conn.execute(sa.text(
            "SELECT id FROM part_attribute "
            "WHERE part_id = :a AND akey = 'Description' AND avalue = :v"),
            {"a": aid, "v": before}).first()
        if not found:
            continue
        # Nothing here overwrites an answer someone has already given; a drive that
        # has been through the pickers since is already saying what this would say.
        one = _ONE_FIGURE.match(speed)
        conn.execute(sa.text(
            "UPDATE storage_spec SET media = COALESCE(media, :m), "
            "speed_x = COALESCE(speed_x, :s) WHERE part_id = :a"),
            {"m": media, "s": int(one.group(1)) if one else None, "a": aid})
        if not one:
            # A writer's three figures are one rating and no kind of a number, so
            # they ride as a verbatim attribute -- where an unparseable quantity has
            # always gone, and where the Speed key reads them back from.
            conn.execute(sa.text(
                "INSERT INTO part_attribute (part_id, akey, avalue) "
                "VALUES (:a, 'Speed', :v)"), {"a": aid, "v": speed})
        conn.execute(sa.text("DELETE FROM part_attribute WHERE id = :i"),
                     {"i": found[0]})
        _log(conn, aid, f'drive: "{before}" → media {media}, speed {speed}')


def downgrade():
    conn = op.get_bind()
    for aid, before, media, speed in SPLITS:
        conn.execute(sa.text(
            "UPDATE storage_spec SET media = NULL WHERE part_id = :a AND media = :m"),
            {"a": aid, "m": media})
        conn.execute(sa.text(
            "DELETE FROM part_attribute WHERE part_id = :a AND akey = 'Speed' "
            "AND avalue = :v"), {"a": aid, "v": speed})
        conn.execute(sa.text(
            "INSERT INTO part_attribute (part_id, akey, avalue) "
            "VALUES (:a, 'Description', :v)"), {"a": aid, "v": before})
        conn.execute(sa.text(
            "DELETE FROM log_entry WHERE asset_id = :a AND message LIKE 'drive: %'"),
            {"a": aid})
    op.drop_column("storage_spec", "speed_x")
    op.drop_column("computer_drive", "speed")
    op.drop_column("computer_drive", "media")
