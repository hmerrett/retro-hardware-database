"""one spelling of a serial nobody has written down

0028 added `serial` to both tables nullable and backfilled nothing, on the
reasoning that a serial is read off the object and there is nowhere else it could
have come from. That is true of where a serial *comes from*, but it settled
nothing about how "not recorded" is stored -- and the model beside it had already
answered that question the other way, with `default=""` like every other text
column here. So the two states arrived together: rows already in a collection when
0028 ran got NULL, rows written through the app since got "". Nothing in the app
or the UI tells them apart; both render as a blank box.

What made it a bug rather than an untidiness is that the API only ever spoke one
of them. `ComputerOut.serial` is typed `str`, so a single NULL row failed response
validation for the *whole list* -- `GET /api/computers` was a 500 for every
caller, which took the public REST API and every MCP tool with it, over 25 rows
that simply had no number on them.

This settles it on "", which is what the models, the forms and the wire format
already say. General and data-driven, not a correction to named rows: it updates
whatever NULLs the database in front of it holds and does nothing at all on one
that holds none, a fresh install included (ADR-0002).

The backfill runs before the ALTER, in that order, because MariaDB auto-commits
DDL and cannot roll it back. Should the ALTER fail, what has committed is a
backfill that is idempotent and safe to leave, so a restart re-runs the migration
from a state it can handle rather than a half-changed schema it cannot.

Revision ID: 0034_serial_not_null
Revises: 0033_work_project_names
Create Date: 2026-09-09
"""
import sqlalchemy as sa
from alembic import op

revision = "0034_serial_not_null"
down_revision = "0033_work_project_names"
branch_labels = None
depends_on = None

TABLES = ("computers", "parts")


def upgrade():
    for table in TABLES:
        op.execute(f"UPDATE {table} SET serial = '' WHERE serial IS NULL")
        op.alter_column(table, "serial",
                        existing_type=sa.String(64),
                        nullable=False,
                        server_default="")


def downgrade():
    """Puts the column back as 0028 left it, which is the nullability only.

    Which rows held NULL is not recoverable -- the upgrade overwrote exactly the
    information that would say -- so the values stay as "". That is the honest
    half of the pair rather than a shortfall: "" is what an unrecorded serial
    means on either side of this migration, and inventing NULLs back would be
    guessing at rows that may never have had one.
    """
    for table in TABLES:
        op.alter_column(table, "serial",
                        existing_type=sa.String(64),
                        nullable=True,
                        server_default=None)
