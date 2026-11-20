"""what a survey corrected

ADR-0054. A survey fills what is empty and changes nothing else (ADR-0043), with one
exception: a memory total an older survey wrote from the conventional memory alone,
before survey programs could see above 1 MiB under HIMEM.SYS. What a survey corrected
is kept beside what it filled in and what differed, as a JSON list like them. Every
survey already taken corrected nothing, which is what the default says, so no row is
read or changed.

MariaDB auto-commits DDL, so the step looks before it acts, and the migration can be
run again after a failure part-way without wedging a restart.

Revision ID: 0050_what_a_survey_corrected
Revises: 0049_surveys
Create Date: 2026-11-20
"""

import sqlalchemy as sa
from alembic import op

revision = "0050_what_a_survey_corrected"
down_revision = "0049_surveys"
branch_labels = None
depends_on = None


def _columns(table):
    return {c["name"] for c in sa.inspect(op.get_bind()).get_columns(table)}


def upgrade():
    if "corrected" not in _columns("surveys"):
        op.add_column(
            "surveys", sa.Column("corrected", sa.Text(), nullable=False, server_default="[]")
        )


def downgrade():
    if "corrected" in _columns("surveys"):
        op.drop_column("surveys", "corrected")
