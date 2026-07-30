"""a machine's fitted drives as rows instead of a semicolon blob

drives was free text nothing ever read apart from the search index and the label:
eleven machines in six different notations ('2 x 5.25" 360K', '2x 5.25" 360K
Floppy', '1x GOTEK; 1x 5.25" 360K', '3.5-inch 1.44 MB floppy drive', 'Custom
GOTEK 2.88MB', 'Integral 2GB SD'). Each drive is a row now, so "which machines
have a Gotek" is a query, and computers.drives is the rendered cache.

The backfill is the parsed result for each of the eleven, verified value by value
rather than re-derived here: a literal table cannot drift when the app's parser
changes, and if a string is not what was recorded the whole thing goes to
drives_note instead of being silently mis-split.

size and form_factor keep the labels a person writes. 1.44MB is 1475 KB only by
convention, and a drive's media designation is not a measured quantity.

RH-Y0XD's 'Unknown hard disk' is not converted: a hard disk is a part with its
own asset tag by the model's own rule, so it becomes one separately.

Revision ID: 0012_computer_drives
Revises: 0011_computer_memory
Create Date: 2026-07-30
"""
from alembic import op
import sqlalchemy as sa

revision = "0012_computer_drives"
down_revision = "0011_computer_memory"
branch_labels = None
depends_on = None

# asset_id -> (the string as it stands, [(count, kind, form factor, size, model)])
BACKFILL = {
    "RH-0001": ("3.5-inch 1.44 MB floppy drive",
                [(1, "floppy", '3.5"', "1.44MB", "")]),
    "RH-0005": ("3.5-inch 1.44 MB floppy drive",
                [(1, "floppy", '3.5"', "1.44MB", "")]),
    "RH-0010": ("3.5-inch 1.44 MB floppy drive",
                [(1, "floppy", '3.5"', "1.44MB", "")]),
    "RH-0204": ("3.5-inch 1.44 MB floppy drive; SanDisk Extreme 4GB; "
                "Gotek floppy emulator (1.44MB)",
                [(1, "floppy", '3.5"', "1.44MB", ""),
                 # The string never says SD or CF, so neither does the row.
                 (1, "", "", "4GB", "SanDisk Extreme"),
                 (1, "Gotek", "", "1.44MB", "")]),
    "RH-0215": ('Mitsubishi MF504A-318U (1.2MB); Unknown 3.5" 1.44MB Floppy Drive; '
                'Integral 2GB SD',
                [(1, "floppy", "", "1.2MB", "Mitsubishi MF504A-318U"),
                 (1, "floppy", '3.5"', "1.44MB", "Unknown"),
                 (1, "SD", "", "2GB", "Integral")]),
    "RH-0237": ("Custom GOTEK 2.88MB",
                [(1, "Gotek", "", "2.88MB", "Custom")]),
    "RH-0259": ('2 x 5.25" 360K',
                [(2, "floppy", '5.25"', "360K", "")]),
    "RH-0CDY": ('1x 5.25" 1.2MB ; 1x 5.25" 360K',
                [(1, "floppy", '5.25"', "1.2MB", ""),
                 (1, "floppy", '5.25"', "360K", "")]),
    "RH-C241": ('2x 5.25" 360K Floppy',
                [(2, "floppy", '5.25"', "360K", "")]),
    "RH-F5A7": ("1x GOTEK; 1x 5.25\" 360K",
                [(1, "Gotek", "", "", ""),
                 (1, "floppy", '5.25"', "360K", "")]),
    "RH-TJ8E": ("1GB CF",
                [(1, "CF", "", "1GB", "")]),
}


def _render(rows, note):
    out = []
    for count, kind, form, size, model in rows:
        body = " ".join(b for b in (model, form, size, kind) if b)
        out.append(f"{count}× {body}" if count > 1 else body)
    if note:
        out.append(note)
    return "; ".join(x for x in out if x)


def upgrade():
    op.create_table(
        "computer_drive",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column("computer_id", sa.String(16), nullable=False),
        sa.Column("count", sa.Integer()),
        sa.Column("kind", sa.String(32), nullable=False, server_default=""),
        sa.Column("form_factor", sa.String(16), nullable=False, server_default=""),
        sa.Column("size", sa.String(32), nullable=False, server_default=""),
        sa.Column("model", sa.String(255), nullable=False, server_default=""),
        sa.ForeignKeyConstraint(["computer_id"], ["computers.asset_id"],
                                ondelete="CASCADE"),
    )
    op.create_index("ix_computer_drive_computer_id", "computer_drive",
                    ["computer_id"])
    op.add_column("computers", sa.Column("drives_note", sa.String(255),
                                         nullable=False, server_default=""))

    conn = op.get_bind()
    for aid, drives in conn.execute(sa.text(
            "SELECT asset_id, drives FROM computers WHERE drives <> ''")).fetchall():
        expected, rows = BACKFILL.get(aid, (None, []))
        if " ".join((drives or "").split()) != " ".join((expected or "").split()):
            # Not what was recorded: keep every character, structure nothing.
            conn.execute(sa.text("UPDATE computers SET drives_note = :n "
                                 "WHERE asset_id = :a"), {"n": drives, "a": aid})
            continue
        for count, kind, form, size, model in rows:
            conn.execute(sa.text(
                "INSERT INTO computer_drive (computer_id, count, kind, "
                "form_factor, size, model) VALUES (:a, :c, :k, :f, :s, :m)"),
                {"a": aid, "c": count, "k": kind, "f": form, "s": size, "m": model})
        conn.execute(sa.text("UPDATE computers SET drives = :d WHERE asset_id = :a"),
                     {"d": _render(rows, ""), "a": aid})


def downgrade():
    for aid, (expected, _rows) in BACKFILL.items():
        op.execute(sa.text("UPDATE computers SET drives = :d WHERE asset_id = :a")
                   .bindparams(d=expected, a=aid))
    op.drop_column("computers", "drives_note")
    op.drop_table("computer_drive")
