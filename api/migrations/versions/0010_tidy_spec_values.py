"""onboard RAM key

Adds the motherboard_spec.onboard_ram column.

This migration originally also carried a batch of one-off data corrections for
specific assets in the original database, moving values that predated the typed
columns out of part_attribute and into their proper homes. Those corrections have
been removed from the migration history: they only ever applied to the one
database that held that data, and their blind INSERTs made a fresh
`alembic upgrade head` fail on an empty database (a foreign key with no parent
row, and then a wedged restart because MariaDB does not roll back the column it
had already added). See ADR-0002. Only the schema change remains, and it runs on
any database. The original corrections have long since been applied to the live
database by the first run of this migration.

Revision ID: 0010_tidy_spec_values
Revises: 0009_disposed_note_not_null
Create Date: 2026-07-30
"""
from alembic import op
import sqlalchemy as sa

revision = "0010_tidy_spec_values"
down_revision = "0009_disposed_note_not_null"
branch_labels = None
depends_on = None


def upgrade():
    op.add_column("motherboard_spec",
                  sa.Column("onboard_ram", sa.String(64), nullable=True))


def downgrade():
    op.drop_column("motherboard_spec", "onboard_ram")
