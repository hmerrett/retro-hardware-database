"""what a screen will lock to, not only what it will show

A monitor's resolution and refresh rate say what picture it makes once it has one.
The sync rate says whether it will make one at all: a plain VGA monitor takes 31 kHz
and nothing else, and a machine putting out the TV rate of 15 kHz gets a black
screen off it however good the tube is.

Which is a fact about a collection rather than about a datasheet. Which machine can
be plugged into which screen is worth looking up rather than rediscovering behind a
desk, and nothing else on a monitor's record answers it: an Acorn AKF18 takes
15-38 kHz and so drives a BBC Micro and a PC both, where the 14-inch beside it may
take only the one rate and show nothing off the other machine.

Text, and a list, for the reason `interface` is: the answer is more than one. A tube
that lists a few rates has them and nothing between them, and a multiscan quotes a
continuous range instead -- neither of which a single kHz integer could hold. So the
rates are stored as they are given, comma-separated or as the range claimed.

Nothing is backfilled. A screen already filed says nothing about its sync rate
because nobody was asked, and guessing 31 kHz from "VGA (HD-15)" would put a fact
in the register that no one checked -- the one thing a 15 kHz tube is worth
recording for is precisely that it does what its socket does not imply.

Revision ID: 0026_display_sync
Revises: 0025_display_parts
Create Date: 2026-08-31
"""
import sqlalchemy as sa
from alembic import op

revision = "0026_display_sync"
down_revision = "0025_display_parts"
branch_labels = None
depends_on = None


def upgrade():
    op.add_column("display_spec", sa.Column("sync", sa.String(255)))


def downgrade():
    op.drop_column("display_spec", "sync")
