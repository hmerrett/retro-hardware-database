"""a flag for the things waiting to be worked on, and the note saying what for

The register has been able to say what a thing is and what became of it, and has
had nowhere to say what is going to happen to it. A collection is half a list of
objects and half a list of intentions -- the Amiga waiting on a recap, the drive
that needs a belt, the machine that would run if somebody found it a power supply
-- and those intentions have been living in the free-text notes, mixed in with
everything else written there, where they cannot be counted, listed, or crossed
off.

Two columns, in exactly the shape `disposed` and `disposed_note` already have: a
flag that can be asked of the whole register at once, and the text saying what the
plan actually is. The same shape on purpose, because a reader who has understood
one of the pairs has understood the other.

No date beside them, which is where the parallel stops. `disposed_at` is a fact
about the object -- the day it left -- and the day somebody decided to recap a
board is bookkeeping about the register rather than anything true of the hardware.
What the plan is worth saying about itself, it can say in the note.

On both tables, because an item is a computer or a part and both get worked on. If
anything it is the part more often: a recap is a thing done to a board and a belt
is a thing done to a drive.

Nothing is backfilled. Nothing is a project until somebody says it is one, and the
notes column is not a place a plan can be recognised in by machine.

Revision ID: 0029_future_projects
Revises: 0028_serial_numbers
Create Date: 2026-09-01
"""
import sqlalchemy as sa
from alembic import op

revision = "0029_future_projects"
down_revision = "0028_serial_numbers"
branch_labels = None
depends_on = None

TABLES = ("computers", "parts")


def upgrade():
    for table in TABLES:
        op.add_column(table, sa.Column("project", sa.Boolean(), nullable=False,
                                       server_default="0"))
        op.add_column(table, sa.Column("project_note", sa.Text(), nullable=False,
                                       server_default=""))


def downgrade():
    for table in TABLES:
        op.drop_column(table, "project_note")
        op.drop_column(table, "project")
