"""re-fold the file tags now that a space is not part of a name

file_tag.fold is what a tag is matched on, and it was the tag with its spacing
tidied and its case dropped. It is now the tag with every space taken out, because
a name is as often written closed up as apart -- SoundBlaster, Sound Blaster -- and
neither spelling is the wrong one to have typed. Matching became containment at the
same time, which is what lets one tag cover a range: "Creative Labs Sound Blaster"
is on the AWE32 and the 16 and the Pro.

The column is derived, so this recomputes it rather than asking anyone to. `tag`
holds what was typed and never changes; parse_tags has already collapsed each name's
whitespace to single spaces on the way in, so taking those out is the whole of it.

Revision ID: 0021_fold_without_spaces
Revises: 0020_files
Create Date: 2026-08-14
"""
from alembic import op

revision = "0021_fold_without_spaces"
down_revision = "0020_files"
branch_labels = None
depends_on = None


def upgrade():
    op.execute("UPDATE file_tag SET fold = LOWER(REPLACE(tag, ' ', ''))")


def downgrade():
    op.execute("UPDATE file_tag SET fold = LOWER(tag)")
