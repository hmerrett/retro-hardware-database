"""a queue for labels printed somewhere else

ADR-0025. The label printers are not attached to the machine the register runs on
-- it is a server, and they are on a desk behind a broadband router. An agent on
that desk asks for its jobs and prints them; this is what it is told.

Nothing is seeded and nothing is read: an installation that names no agents has no
queue, and an empty table is that installation working correctly (ADR-0002).

Revision ID: 0042_print_queue
Revises: 0041_block_search_engines
Create Date: 2026-09-19
"""

import sqlalchemy as sa
from alembic import op

revision = "0042_print_queue"
down_revision = "0041_block_search_engines"
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        "print_job",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True, nullable=False),
        sa.Column("agent", sa.String(length=64), nullable=False),
        sa.Column("kind", sa.String(length=16), nullable=False),
        sa.Column("asset_id", sa.String(length=16), nullable=False),
        sa.Column("media", sa.String(length=32), nullable=False),
        sa.Column("fmt", sa.String(length=8), nullable=False),
        sa.Column("dpi", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("copies", sa.Integer(), nullable=False, server_default="1"),
        sa.Column("state", sa.String(length=16), nullable=False, server_default="queued"),
        sa.Column("error", sa.String(length=255), nullable=False, server_default=""),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("claimed_at", sa.DateTime(), nullable=True),
        sa.Column("finished_at", sa.DateTime(), nullable=True),
    )
    op.create_index("ix_print_job_agent", "print_job", ["agent"])
    op.create_index("ix_print_job_asset_id", "print_job", ["asset_id"])
    op.create_index("ix_print_job_state", "print_job", ["state"])
    op.create_index("ix_print_job_created_at", "print_job", ["created_at"])


def downgrade():
    op.drop_index("ix_print_job_created_at", table_name="print_job")
    op.drop_index("ix_print_job_state", table_name="print_job")
    op.drop_index("ix_print_job_asset_id", table_name="print_job")
    op.drop_index("ix_print_job_agent", table_name="print_job")
    op.drop_table("print_job")
