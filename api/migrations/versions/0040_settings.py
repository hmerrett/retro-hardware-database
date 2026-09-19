"""a place for what is preferred rather than what is true

ADR-0023. The register has never had anywhere to keep a preference: everything in
it is a fact about a machine or a part, and everything told to it from outside
comes from the environment. What this collection is called, whether search engines
may list it, whether a photograph is stamped and which theme the site opens in are
none of those things -- they are decided by whoever owns the collection, changed
on a whim, and changed from a phone.

A key and a value, not a column apiece. The page is expected to grow and a
migration for each new row on it would be a tax on the thing this is supposed to
make cheap.

Nothing is seeded. Every setting's default lives in `settings.py`, so an empty
table is a working site on a fresh install and there is no data for this migration
to assume (ADR-0002).

Revision ID: 0040_settings
Revises: 0039_a_file_says_what_it_is_for
Create Date: 2026-09-19
"""

import sqlalchemy as sa
from alembic import op

revision = "0040_settings"
down_revision = "0039_a_file_says_what_it_is_for"
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        "setting",
        sa.Column("name", sa.String(length=64), primary_key=True, nullable=False),
        sa.Column("value", sa.Text(), nullable=False),
        sa.Column("updated_at", sa.DateTime(), nullable=True),
    )


def downgrade():
    op.drop_table("setting")
