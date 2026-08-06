"""yellowing as its own field, and a bezel on storage parts too

0014 gave a drive one colour field whose vocabulary ran from the factory shades
into the stages of yellowing. That answers "how bad is this one" but loses "what
did this machine's drives look like new", and the two are different questions: a
beige drive that has yellowed is still a beige drive. So the shade a bezel was
made in and how far it has gone since are separate fields now, and either can be
recorded without the other.

The same two things belong to a storage part -- a full-height hard disk or a tape
drive has a bezel on the front of the machine like any other -- so storage_spec
gets them as well, from the same vocabulary (entry.BEZEL_COLOURS, entry.YELLOWING)
and under the Colour and Yellowing spec keys.

Any colour recorded under 0014's combined vocabulary moves: a yellowing value goes
to the new column and leaves the shade blank, because "heavily yellowed" never
said what the drive started as, and guessing beige would be inventing it. The
machine's cached drives string is re-rendered for the rows that moved.

Revision ID: 0015_bezel_yellowing
Revises: 0014_drive_colour
Create Date: 2026-08-06
"""
from alembic import op
import sqlalchemy as sa

revision = "0015_bezel_yellowing"
down_revision = "0014_drive_colour"
branch_labels = None
depends_on = None

# 0014's colour vocabulary, split into what each value means now.
YELLOWING = ["Lightly yellowed", "Yellowed", "Heavily yellowed", "Browned",
             "Unevenly yellowed"]


def _render(rows):
    """computers.drives from its drive rows -- the app's drivedb.render, copied so
    this migration cannot change meaning when that function does."""
    out = []
    for count, kind, form, size, model, colour, yellowing in rows:
        body = " ".join(b for b in (model, form, size, kind) if b)
        bezel = ", ".join(x.lower() for x in (colour, yellowing) if x)
        if bezel:
            body = f"{body} ({bezel})".strip()
        out.append(f"{count}× {body}" if (count or 1) > 1 else body)
    return "; ".join(x for x in out if x)


def upgrade():
    op.add_column("computer_drive", sa.Column("yellowing", sa.String(32),
                                              nullable=False, server_default=""))
    op.add_column("storage_spec", sa.Column("colour", sa.String(32)))
    op.add_column("storage_spec", sa.Column("yellowing", sa.String(32)))

    conn = op.get_bind()
    moved = conn.execute(sa.text(
        "SELECT DISTINCT computer_id FROM computer_drive WHERE colour IN :vals"
    ).bindparams(sa.bindparam("vals", YELLOWING, expanding=True))).fetchall()
    conn.execute(sa.text(
        "UPDATE computer_drive SET yellowing = colour, colour = '' "
        "WHERE colour IN :vals"
    ).bindparams(sa.bindparam("vals", YELLOWING, expanding=True)))

    # The string is a cache of the rows, so the machines whose rows changed need
    # theirs rebuilt; their note (which the string ends with) is kept.
    for (aid,) in moved:
        rows = conn.execute(sa.text(
            "SELECT count, kind, form_factor, size, model, colour, yellowing "
            "FROM computer_drive WHERE computer_id = :a ORDER BY id"),
            {"a": aid}).fetchall()
        note = conn.execute(sa.text(
            "SELECT drives_note FROM computers WHERE asset_id = :a"),
            {"a": aid}).scalar() or ""
        rendered = "; ".join(x for x in (_render(rows), note) if x)
        conn.execute(sa.text("UPDATE computers SET drives = :d WHERE asset_id = :a"),
                     {"d": rendered, "a": aid})


def downgrade():
    # Back to one field: a yellowing level was the whole of 0014's colour for these
    # rows, so it goes back where it came from.
    op.execute("UPDATE computer_drive SET colour = yellowing "
               "WHERE colour = '' AND yellowing <> ''")
    op.drop_column("computer_drive", "yellowing")
    op.drop_column("storage_spec", "yellowing")
    op.drop_column("storage_spec", "colour")
