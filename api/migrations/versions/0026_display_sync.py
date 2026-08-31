"""what a screen will lock to, not only what it will show

A monitor's resolution and refresh rate say what picture it makes once it has one.
The sync rate says whether it will make one at all: a plain VGA monitor takes 31 kHz
and nothing else, and a machine putting out the TV rate of 15 kHz gets a black
screen off it however good the tube is.

Which is a fact about a collection rather than about a datasheet. The Acorn AKF18
in this one does 15 kHz *and* 31 kHz, so it drives a BBC Micro and a PC both; the
14-inch beside it does only the one, and pairing it with the wrong machine is a
mistake worth being able to look up rather than rediscover behind a desk.

Text, and a list, for the reason `interface` is: the answer is more than one. Two
discrete rates are what a dual-sync tube has -- not a range between them, and not
one rate with the other rounded away -- and a true multisync quotes a range instead
(30-70 kHz), which no single kHz integer could hold either. So the rates are stored
as they are ticked, comma-separated, in the words the vocabulary offers.

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
