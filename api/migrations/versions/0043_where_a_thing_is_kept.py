"""where a thing is kept, and a memory of the places used

The register has always said what a thing is and where it came from, and never
where it is. That is the question asked most often and answered least well: a
shelf, a loft, a crate with a number on it, and by the time somebody wants the
machine the answer is in whoever put it there. So `location` on both halves of
the register, free text, because a collection's geography is its own and no menu
written here would fit somebody else's house.

On both tables for the reason the serial number is on both (0028): an item is a
computer or a part and both are objects that sit somewhere. A part is not covered
by its machine's answer -- a card fitted in a machine is wherever that machine is,
but a card in a drawer is in the drawer, and the register cannot tell which case
it is looking at from `computer_id` alone.

Nothing is backfilled, and there is nothing to backfill from. Where a thing is
kept is read off the shelf it is on; there is no column here it could be inferred
from, and inferring it from a note that happens to mention the loft would be
inventing a fact rather than migrating one (ADR-0002). A fresh install and an
existing one both start with the column empty, which is the truth in both cases.

Empty, though, and not NULL. `nullable=False` with a server default of "", which
is the shape 0034 had to go back and put on `serial` after 0028 left it nullable.
The lesson is worth restating here because it is the same one: the model beside
this says `default=""` like every other text column, so rows written through the
app get "" while rows already in the collection when the migration ran get NULL,
and nothing in the app or the page tells the two apart. The API does. `location`
is typed `str` on the wire, so one NULL row fails response validation for the
*whole list* -- `GET /api/computers` a 500 for every caller, over rows whose only
crime is being older than the feature. Born with a server default, the column has
one spelling of "nobody has written it down" from the first row to the last, and
there is no second state for a later migration to come back and tidy up.

The `location` table is the other half, and the register's first stored vocabulary
(ADR-0027). Every pick list so far has been derived from the column it offers
back, which works while the answers stay true; a location stops being true when
the thing is moved, so the last item out of a crate would take the crate's
spelling with it. A row per place ever saved holds what the derived list loses.
It starts empty and stays empty until something is saved with a location in it --
there is no vocabulary to seed, and seeding one would be this migration assuming
data it cannot have.

Three steps, and MariaDB auto-commits DDL, so a failure partway leaves some of
them applied: the column on `computers` and not on `parts`, or both columns and no
table. Every step restarts safely, and the server default is what makes that true
of the columns -- MariaDB fills existing rows as it adds one, in the same
statement, so there is no window in which the column exists and its rows do not
have a value, and nothing to finish by hand if the next step fails. Re-running
adds whichever of the two is missing. `create_table` is last because a table
nothing has written to yet is the cheapest thing to be without. A half-applied
schema here is a database where half the register cannot say where it is, rather
than one that will not start -- and nothing reads either the column or the table
until the app is the version that has them.

Revision ID: 0043_where_a_thing_is_kept
Revises: 0042_print_queue
Create Date: 2026-09-21
"""

import sqlalchemy as sa
from alembic import op

revision = "0043_where_a_thing_is_kept"
down_revision = "0042_print_queue"
branch_labels = None
depends_on = None

TABLES = ("computers", "parts")


def upgrade():
    for table in TABLES:
        op.add_column(
            table,
            sa.Column("location", sa.String(255), nullable=False, server_default=""),
        )
    op.create_table(
        "location",
        sa.Column("name", sa.String(length=255), primary_key=True, nullable=False),
        sa.Column("used_at", sa.DateTime(), nullable=True),
    )


def downgrade():
    """Takes back both halves. What is lost is where everything was kept and the
    list of places it has been kept -- nothing else held either, and no item is
    otherwise changed by losing them."""
    op.drop_table("location")
    for table in TABLES:
        op.drop_column(table, "location")
