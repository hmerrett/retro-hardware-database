"""files kept beside the register, filed under the names they are for

Photographs were the only thing the register could be given, and a photograph is
about one object: this card, on this shelf. A driver disk is not. It is about the
card as a model, and a collection with three of them would have carried the same
download three times and lost two of them the day two cards went.

So a file is not hung off an asset id. It is tagged with the names it covers, and
every item answering to one of those names offers it -- the card, the machine the
card shipped in, or one particular unit when the tag is its asset id. The matching
lives in app/filesdb.py; what is here is the two tables it reads.

`stored` is the name on disk and is generated. The uploaded name is kept beside it
to call the download by, and is never a path: a filename is the one part of an
upload chosen entirely by whoever sent it.

Revision ID: 0020_files
Revises: 0019_chip_socketed
Create Date: 2026-08-14
"""
import sqlalchemy as sa
from alembic import op

revision = "0020_files"
down_revision = "0019_chip_socketed"
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        "files",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column("stored", sa.String(72), nullable=False, unique=True),
        sa.Column("filename", sa.String(255), nullable=False),
        sa.Column("size", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("note", sa.String(255), nullable=False, server_default=""),
        sa.Column("created_at", sa.DateTime(), nullable=True),
    )
    op.create_index("ix_files_created_at", "files", ["created_at"])
    op.create_table(
        "file_tag",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column("file_id", sa.Integer(), nullable=False),
        # As written, for showing back; and folded, which is what is matched on.
        sa.Column("tag", sa.String(120), nullable=False),
        sa.Column("fold", sa.String(120), nullable=False),
        sa.ForeignKeyConstraint(["file_id"], ["files.id"], ondelete="CASCADE"),
    )
    op.create_index("ix_file_tag_file_id", "file_tag", ["file_id"])
    op.create_index("ix_file_tag_fold", "file_tag", ["fold"])


def downgrade():
    op.drop_table("file_tag")
    op.drop_table("files")
