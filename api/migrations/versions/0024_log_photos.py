"""a history entry can carry photographs

The register has had one photograph of a thing since the beginning -- the portrait
on computers.image -- and it answers the question a register is for: which one is
this, the one on the shelf with the yellowed lid. It has never been able to answer
the other one. A recap, a repair, a crack found on arrival, the label under the
lid that settled which revision the board is: all of that is what happened to the
machine, it is already written down one line at a time in log_entry, and the
photographs of it had nowhere to go but the gallery, where they sat between two
portraits saying nothing about when they were taken or why.

So a photograph can hang on the history entry that already says what happened. The
entry's message is the caption -- there is no caption column here, because writing
one would mean writing the sentence twice.

The files go under images/log/ and nowhere else. The two folders the register
already has are read by filename: everything in computers/ whose stem is an asset
id is that asset's gallery, and the first of them is its portrait. A photograph of
a recap filed beside the part would therefore have become one of that part's
pictures and would have been counted as its portrait, which is a figure the stats
page is about to start reporting as a work queue. A folder of its own is what
keeps the two kinds of photograph from being mistaken for each other.

log_id is a real foreign key, unlike log_entry's own asset_id: an entry is a row
in one table rather than an identity in the shared register, and a log_photo means
nothing without the entry it belongs to. The cascade is still not what deletes
these -- main.py clears them by hand, because it has to read `rel` while the rows
are still there and delete the files after the transaction is safe.

Revision ID: 0024_log_photos
Revises: 0023_catalogue_on_any_asset
Create Date: 2026-08-18
"""
import sqlalchemy as sa
from alembic import op

revision = "0024_log_photos"
down_revision = "0023_catalogue_on_any_asset"
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        "log_photo",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column("log_id", sa.Integer(), nullable=False),
        # The path under the images directory, which is where the photograph
        # actually is. Stored rather than worked out from the entry's id, so that
        # what the register believes it has is a row and not a guess about a
        # folder listing.
        sa.Column("rel", sa.String(255), nullable=False),
        sa.ForeignKeyConstraint(["log_id"], ["log_entry.id"], ondelete="CASCADE"),
    )
    op.create_index("ix_log_photo_log_id", "log_photo", ["log_id"])


def downgrade():
    """The rows go; the files under images/log/ are left where they are. A dropped
    table can be recreated by upgrading again, and a deleted photograph cannot be
    recovered at all -- so this leaves behind a folder to tidy by hand rather than
    taking the one irreversible action on the way back down."""
    op.drop_table("log_photo")
