"""real foreign keys for a part's computer_id and parent_id

Both were plain indexed strings defaulting to "", so integrity was hand-rolled:
queries for standalone parts had to test for "" *and* NULL because both occurred,
and deleting a computer left its parts pointing at an id that no longer existed.

The live data is clean -- no NULLs, no dangling references -- so the conversion
is only "" -> NULL plus the constraints. ON DELETE SET NULL matches how the GUI
behaves: removing a machine or a host card leaves the parts standing alone rather
than deleting them.

Revision ID: 0008_link_fks
Revises: 0007_split_disposed
Create Date: 2026-07-29
"""
from alembic import op
import sqlalchemy as sa

revision = "0008_link_fks"
down_revision = "0007_split_disposed"
branch_labels = None
depends_on = None


def upgrade():
    op.execute("UPDATE parts SET computer_id = NULL WHERE computer_id = ''")
    op.execute("UPDATE parts SET parent_id = NULL WHERE parent_id = ''")
    op.create_foreign_key("fk_parts_computer_id", "parts", "computers",
                          ["computer_id"], ["asset_id"], ondelete="SET NULL")
    op.create_foreign_key("fk_parts_parent_id", "parts", "parts",
                          ["parent_id"], ["asset_id"], ondelete="SET NULL")


def downgrade():
    op.drop_constraint("fk_parts_parent_id", "parts", type_="foreignkey")
    op.drop_constraint("fk_parts_computer_id", "parts", type_="foreignkey")
    op.execute("UPDATE parts SET computer_id = '' WHERE computer_id IS NULL")
    op.execute("UPDATE parts SET parent_id = '' WHERE parent_id IS NULL")
