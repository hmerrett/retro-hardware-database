"""a file is not published until somebody says it is

The register's uploads have been public since 0020 gave them a table. That was
right for what the feature was first for -- a driver disk is part of what the
catalogue is *for*, and a manual nobody may download is a manual nobody has --
but the same box takes receipts, and a receipt carries a name, an address and
sometimes the last four digits of a card. The security notes have carried this as
an open decision for the owner ever since, with instructions not to change it
silently. This is the owner changing it (ADR-0009).

So `public`, and the wrong way up from `projects.private` deliberately: an unset
flag on a new column is the state every row starts in, and the state an upload
should start in is unpublished. Ticking a box to publish is a decision somebody
made; forgetting to tick one is not a disclosure.

What is already on file stays on file. Everything uploaded before today went up
under a rule that said uploads are public, and the collection's drivers and
manuals are linked from item pages and scanned QR labels -- turning all of them
off in a deployment would take the site's downloads away overnight to protect
the few of them that are receipts, and the owner's call was to keep them. The
backfill is general and data-driven, not a correction to named rows: it publishes
whatever the database in front of it happens to hold, and on a fresh install it
publishes nothing because there is nothing there (ADR-0002).

The column is added before the backfill, which is the only order available, and
MariaDB auto-commits DDL. Should the UPDATE fail, what has committed is a column
full of zeroes -- every file private, nothing disclosed -- and a restart re-runs
a migration whose backfill is idempotent. The failure mode is the safe one, which
is the argument for this direction over the other.

Revision ID: 0035_public_files
Revises: 0034_serial_not_null
Create Date: 2026-09-10
"""
import sqlalchemy as sa
from alembic import op

revision = "0035_public_files"
down_revision = "0034_serial_not_null"
branch_labels = None
depends_on = None


def upgrade():
    op.add_column("files", sa.Column("public", sa.Boolean(), nullable=False,
                                     server_default="0"))
    op.execute("UPDATE files SET public = 1")


def downgrade():
    """Takes the flag away, which puts every file back on public view.

    That is what the column meant before it existed, so going back is going back
    to it rather than to something safer -- worth knowing before running it on a
    database where somebody has since unticked a receipt."""
    op.drop_column("files", "public")
