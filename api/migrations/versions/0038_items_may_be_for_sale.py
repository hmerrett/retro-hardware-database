"""an item may be flagged as one that could go

The register records what is owned (ADR-0007) and `disposed` records the end of
that. What had nowhere to live was the step before it -- "this one could go" --
which ended up in a note on the item, where anybody can read it, or in somebody's
memory, where it did not survive the week.

So `for_sale` on both halves of the register, false everywhere. No backfill and
nothing to infer: a machine already disposed of is not a machine that might be
sold, and reading an intention out of a note would be inventing one. An
installation that has never thought about selling anything gets a column of
zeroes, which is exactly what it should have (ADR-0002).

Two tables, and MariaDB auto-commits DDL, so a failure between them leaves the
column on `computers` and not on `parts`. That restarts safely: the column is
nullable=False with a server default, so re-running adds the missing one and the
half-applied state is a database where half the register cannot be flagged rather
than one that will not start. Nothing reads the column until the app is the version
that has it.

Owner-only wherever it appears (ADR-0018) -- which is a fact about the code and not
about the schema, so there is nothing here to enforce it. The reason it is written
on the migration too is that a column is the thing somebody finds first.

Revision ID: 0038_items_may_be_for_sale
Revises: 0037_one_project_to_a_thing
Create Date: 2026-09-16
"""
import sqlalchemy as sa
from alembic import op

revision = "0038_items_may_be_for_sale"
down_revision = "0037_one_project_to_a_thing"
branch_labels = None
depends_on = None

TABLES = ("computers", "parts")


def upgrade():
    for table in TABLES:
        op.add_column(table, sa.Column("for_sale", sa.Boolean(), nullable=False,
                                       server_default="0"))


def downgrade():
    """Takes the shortlist away. Nothing else held it -- the flag is not in the API
    and not in any other table -- so what is lost is which items were ticked, and
    nothing that was ticked is otherwise changed."""
    for table in TABLES:
        op.drop_column(table, "for_sale")
