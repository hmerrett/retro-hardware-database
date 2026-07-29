"""split disposed into a flag, a date and a note

disposed was one String doing two jobs: a truthy flag (the index filter, the
dimmed card, the banner) and the free text explaining the disposal, with the
literal "disposed" written when no text was given. It becomes a real BOOLEAN,
with disposed_at for when and disposed_note for why.

None of the three live disposals recorded a date, so they keep disposed_at NULL
-- which is why the flag has to be its own column rather than being inferred
from the date.

Revision ID: 0007_split_disposed
Revises: 0006_typed_year_date
Create Date: 2026-07-29
"""
from alembic import op
import sqlalchemy as sa

revision = "0007_split_disposed"
down_revision = "0006_typed_year_date"
branch_labels = None
depends_on = None

TABLES = ("computers", "parts")


def upgrade():
    for t in TABLES:
        op.add_column(t, sa.Column("disposed_at", sa.Date(), nullable=True))
        op.add_column(t, sa.Column("disposed_note", sa.Text(), nullable=True))

        # The old column's text is the note, unless it was the bare sentinel.
        op.execute(f"UPDATE {t} SET disposed_note = disposed "
                   "WHERE disposed <> '' AND disposed <> 'disposed'")
        op.execute(f"UPDATE {t} SET disposed = IF(disposed <> '', '1', '0')")
        op.alter_column(t, "disposed", type_=sa.Boolean(),
                        existing_type=sa.String(255), nullable=False,
                        server_default="0")


def downgrade():
    for t in TABLES:
        op.alter_column(t, "disposed", type_=sa.String(255),
                        existing_type=sa.Boolean(), nullable=True,
                        server_default=None)
        op.execute(f"UPDATE {t} SET disposed = CASE WHEN disposed = '1' THEN "
                   "COALESCE(NULLIF(disposed_note, ''), 'disposed') ELSE '' END")
        op.drop_column(t, "disposed_note")
        op.drop_column(t, "disposed_at")
