"""what an optical drive takes, and how fast, as fields that ask for it

Adds media and speed to computer_drive, and speed_x to storage_spec. Two columns
for a speed because a 48x rating and a 5400 rpm figure are different quantities
that could not share one column and still sort or compare; they answer to one
Speed spec key, and the unit written in the value says which is meant.

This migration originally also moved four specific optical drives' descriptions
into these new fields. Those one-off, per-asset corrections have been removed from
the migration history (they belong with the database they apply to, not the shared
schema history; see ADR-0002) and were applied to the live database by the first
run of this migration. Only the schema change remains, and it runs on any
database.

Revision ID: 0017_optical_media_and_speed
Revises: 0016_drive_description_split
Create Date: 2026-08-10
"""
import sqlalchemy as sa
from alembic import op

revision = "0017_optical_media_and_speed"
down_revision = "0016_drive_description_split"
branch_labels = None
depends_on = None


def upgrade():
    op.add_column("computer_drive", sa.Column("media", sa.String(32),
                                              nullable=False, server_default=""))
    op.add_column("computer_drive", sa.Column("speed", sa.String(16),
                                              nullable=False, server_default=""))
    op.add_column("storage_spec", sa.Column("speed_x", sa.Integer))


def downgrade():
    op.drop_column("storage_spec", "speed_x")
    op.drop_column("computer_drive", "speed")
    op.drop_column("computer_drive", "media")
