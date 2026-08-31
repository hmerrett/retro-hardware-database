"""the number stamped on this particular one

Everything a record has said so far describes a model: an A5000 is an A5000, a
72-pin SIMM is a 72-pin SIMM, and two of them are interchangeable in the register
as they are on a desk. The one thing that is not is the serial number. It belongs
to the object rather than to the model, and it is the only field here that is never
true of a second thing.

Which makes it the field a collection actually needs for the ordinary questions:
which of the two A5000s is this one, is the machine in this photograph the machine
on this shelf, and is the drive that came back from a repair the drive that went.
Written down, it also carries whatever the maker encoded in it -- a week and a year,
a factory, a production run -- for somebody who knows how to read it later.

On both tables, because an item is a computer or a part and both are objects with
numbers on them. A part is where it comes up most: two identical SIMMs are told
apart by nothing else, and a drive's date code lives only on its own label.

Nullable, with nothing backfilled. A serial is read off the object, and there is
nowhere else it could have come from.

Revision ID: 0028_serial_numbers
Revises: 0027_display_refresh_multi
Create Date: 2026-08-31
"""
import sqlalchemy as sa
from alembic import op

revision = "0028_serial_numbers"
down_revision = "0027_display_refresh_multi"
branch_labels = None
depends_on = None

TABLES = ("computers", "parts")


def upgrade():
    for table in TABLES:
        op.add_column(table, sa.Column("serial", sa.String(64)))


def downgrade():
    for table in TABLES:
        op.drop_column(table, "serial")
