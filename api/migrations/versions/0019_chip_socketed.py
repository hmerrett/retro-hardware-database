"""whether a chip sits in a socket or is soldered to the board

A sealed machine's chips are recorded by what is marked on them, which says what
the chip is but not how it is held. The difference matters to whoever opens the
case next: a socketed SID can be swapped to test a fault or lifted before a repair,
and a soldered one means forty pins and a desoldering station. On some models it
even tells the boards apart -- early C64 ASSYs socket nearly everything and the
later ones solder most of it down.

So one nullable flag per chip row. NULL is the honest answer for the rows written
before the question was asked: nothing here backfills "soldered" onto a chip nobody
has looked at, which is the same rule the catalogue's "not recorded" follows. A
machine answers it the next time its form is saved, with somebody looking at the
board.

Revision ID: 0019_chip_socketed
Revises: 0018_machine_variants
Create Date: 2026-08-13
"""
import sqlalchemy as sa
from alembic import op

revision = "0019_chip_socketed"
down_revision = "0018_machine_variants"
branch_labels = None
depends_on = None


def upgrade():
    op.add_column("computer_chip", sa.Column("socketed", sa.Boolean(),
                                             nullable=True))


def downgrade():
    op.drop_column("computer_chip", "socketed")
