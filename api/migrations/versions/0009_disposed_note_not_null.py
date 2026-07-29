"""disposed_note holds '' rather than NULL

0007 added the column nullable, so every undisposed row got a NULL where the
other text columns all hold "". The API's response model types it as a string,
so listing parts failed on those rows. Backfill and make the column match its
neighbours.

Revision ID: 0009_disposed_note_not_null
Revises: 0008_link_fks
Create Date: 2026-07-29
"""
from alembic import op
import sqlalchemy as sa

revision = "0009_disposed_note_not_null"
down_revision = "0008_link_fks"
branch_labels = None
depends_on = None

TABLES = ("computers", "parts")


def upgrade():
    for t in TABLES:
        op.execute(f"UPDATE {t} SET disposed_note = '' WHERE disposed_note IS NULL")
        op.alter_column(t, "disposed_note", existing_type=sa.Text(),
                        nullable=False, server_default="")


def downgrade():
    for t in TABLES:
        op.alter_column(t, "disposed_note", existing_type=sa.Text(),
                        nullable=True, server_default=None)
