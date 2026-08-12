"""the machine that is not described by its parts

Everything the register knew how to describe was a PC: a chassis with a board in
it, cards in the board, drives in the bays, each its own tagged part with its own
specs. A ZX Spectrum is not that. It is a sealed machine that was built in a
handful of documented forms, and what identifies one is which form it is -- Issue
3B or 6A, 16K or 48K, a 5C102E ULA or a 6C001E-7, rubber keys or moulded ones. None
of that is a part to tag: nobody shelves a ULA, photographs it or gives it an asset
id, and a register that made them do so would claim to hold forty more objects than
it does.

So a machine gains a catalogue identity: computer_variant holds which model it is
and which of that model's variations this one is (the board as its make marked it,
the case or keyboard style, the region), and computer_chip holds one row per socket
-- the ULA, the SID, the CRTC type, the Kickstart in the ROM socket -- keyed by the
catalogue's stable role slug. computers.variant is the rendered cache of both, in
the same relation to them as installed_ram is to the memory tables: written from
the rows on every change, read by the page, the label, the search index and the
wire format, and never parsed back.

Only the slugs are stored. The model's name, year, CPU and the lists it offers live
in app/machines.py and are read fresh every time, so correcting an entry there
corrects every machine filed under it -- which is the lesson 0011 wrote down about
memory modules, applied before it could be learned a second time.

Nothing is backfilled, because there is nothing to backfill: all twenty-one machines
on file are PC-era and the catalogue names none of them. The first Spectrum will be
the first row in either table.

Revision ID: 0018_machine_variants
Revises: 0017_optical_media_and_speed
Create Date: 2026-08-12
"""
import sqlalchemy as sa
from alembic import op

revision = "0018_machine_variants"
down_revision = "0017_optical_media_and_speed"
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        "computer_variant",
        # One row per machine, so the machine's own id is the key: a computer is
        # one model of one thing, or it is not in the catalogue at all.
        sa.Column("computer_id", sa.String(16), primary_key=True),
        sa.Column("model_key", sa.String(64), nullable=False, server_default=""),
        sa.Column("issue", sa.String(64), nullable=False, server_default=""),
        sa.Column("style", sa.String(64), nullable=False, server_default=""),
        sa.Column("region", sa.String(32), nullable=False, server_default=""),
        sa.ForeignKeyConstraint(["computer_id"], ["computers.asset_id"],
                                ondelete="CASCADE"),
    )
    op.create_table(
        "computer_chip",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column("computer_id", sa.String(16), nullable=False),
        sa.Column("role", sa.String(32), nullable=False),
        sa.Column("variant", sa.String(64), nullable=False, server_default=""),
        sa.ForeignKeyConstraint(["computer_id"], ["computers.asset_id"],
                                ondelete="CASCADE"),
    )
    op.create_index("ix_computer_chip_computer_id", "computer_chip",
                    ["computer_id"])
    op.add_column("computers", sa.Column("variant", sa.Text(), nullable=False,
                                         server_default=""))


def downgrade():
    op.drop_column("computers", "variant")
    op.drop_index("ix_computer_chip_computer_id", "computer_chip")
    op.drop_table("computer_chip")
    op.drop_table("computer_variant")
