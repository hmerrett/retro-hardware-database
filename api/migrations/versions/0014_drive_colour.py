"""the colour of a drive's bezel

A box of 3.5" floppy drives is a box of near-identical drives in several shades:
which one goes in a machine is partly which one matches it. The colour of the
bezel now has a column, from a fixed vocabulary (drivedb.COLOURS) covering the
factory shades -- black through grey to the beiges -- and the stages of yellowing
that time adds to them.

Nothing is backfilled. No drive in the register records a colour today, and
guessing one from the machine's age would be inventing data: an unrecorded colour
is blank, and blank means nobody has looked yet rather than "no colour".

Revision ID: 0014_drive_colour
Revises: 0013_normalise_cpu
Create Date: 2026-08-06
"""
from alembic import op
import sqlalchemy as sa

revision = "0014_drive_colour"
down_revision = "0013_normalise_cpu"
branch_labels = None
depends_on = None


def upgrade():
    op.add_column("computer_drive", sa.Column("colour", sa.String(32),
                                              nullable=False, server_default=""))


def downgrade():
    op.drop_column("computer_drive", "colour")
