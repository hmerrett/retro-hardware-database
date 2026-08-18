"""a board can answer the catalogue's questions too

A catalogue identity could hang on a computer and nowhere else, because when 0018
wrote it the only thing that could be a ZX Spectrum was a whole ZX Spectrum. Two
things it did not cover turn up as soon as the register is used. A bare Amiga 500
board on a shelf is a real object with an asset tag, and it is an Amiga 500 board
-- Rev 6A, this Agnus, this Gary -- but with nowhere to file that it was written
in free text or not at all. And a machine whose board has been swapped had no way
to say which board is in it now, because the only board it could describe was the
one it was born with.

So the two tables move to the shared asset register, keyed by a plain asset_id the
way log_entry is: what answers a catalogue question is a machine or the board out
of one, and both give the same sort of answer. computer_variant becomes
asset_variant and computer_chip becomes asset_chip, and parts gains the rendered
cache computers.variant already had -- written from the rows on every change, read
by the page, the label, the search index and the wire format, and never parsed
back.

The tables are made and the rows copied rather than renamed in place, because what
is being dropped is the foreign key to computers as much as the name: an asset_id
here is from the register rather than from one table of it, so nothing at the
database level can say which. What replaces the cascade is the same thing that has
always cleared a log entry -- the delete path in main.py removes them by hand.

style and region come across and stay: they are asked only of a machine (a board
out of a PAL Spectrum is not a PAL board), and a column two of the three kinds of
row leave blank is cheaper than a second table to hold them.

Revision ID: 0023_catalogue_on_any_asset
Revises: 0022_computer_topbench
Create Date: 2026-08-18
"""
import sqlalchemy as sa
from alembic import op

revision = "0023_catalogue_on_any_asset"
down_revision = "0022_computer_topbench"
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        "asset_variant",
        # One row per asset, so the asset's own id is the key: a thing is one model
        # of one thing, or it is not in the catalogue at all.
        sa.Column("asset_id", sa.String(16), primary_key=True),
        sa.Column("model_key", sa.String(64), nullable=False, server_default=""),
        sa.Column("issue", sa.String(64), nullable=False, server_default=""),
        sa.Column("style", sa.String(64), nullable=False, server_default=""),
        sa.Column("region", sa.String(32), nullable=False, server_default=""),
    )
    op.create_table(
        "asset_chip",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column("asset_id", sa.String(16), nullable=False),
        sa.Column("role", sa.String(32), nullable=False),
        sa.Column("variant", sa.String(64), nullable=False, server_default=""),
        sa.Column("socketed", sa.Boolean(), nullable=True),
    )
    op.create_index("ix_asset_chip_asset_id", "asset_chip", ["asset_id"])

    conn = op.get_bind()
    conn.execute(sa.text(
        "INSERT INTO asset_variant (asset_id, model_key, issue, style, region) "
        "SELECT computer_id, model_key, issue, style, region FROM computer_variant"))
    conn.execute(sa.text(
        "INSERT INTO asset_chip (asset_id, role, variant, socketed) "
        "SELECT computer_id, role, variant, socketed FROM computer_chip"))

    # The tables go whole, indexes and foreign keys with them. Dropping the index
    # first is what MariaDB will not have: the foreign key to computers is holding
    # it, and the constraint only lets go when the table does.
    op.drop_table("computer_chip")
    op.drop_table("computer_variant")

    op.add_column("parts", sa.Column("variant", sa.Text(), nullable=False,
                                     server_default=""))


def downgrade():
    """Back to a catalogue only a computer can have. Anything filed against a part
    goes: there is nowhere in the old shape to put it, and a board's identity
    written onto the machine it came out of would be a claim nobody made."""
    op.drop_column("parts", "variant")
    op.create_table(
        "computer_variant",
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
        sa.Column("socketed", sa.Boolean(), nullable=True),
        sa.ForeignKeyConstraint(["computer_id"], ["computers.asset_id"],
                                ondelete="CASCADE"),
    )
    op.create_index("ix_computer_chip_computer_id", "computer_chip",
                    ["computer_id"])
    conn = op.get_bind()
    conn.execute(sa.text(
        "INSERT INTO computer_variant (computer_id, model_key, issue, style, region) "
        "SELECT v.asset_id, v.model_key, v.issue, v.style, v.region "
        "FROM asset_variant v JOIN computers c ON c.asset_id = v.asset_id"))
    conn.execute(sa.text(
        "INSERT INTO computer_chip (computer_id, role, variant, socketed) "
        "SELECT k.asset_id, k.role, k.variant, k.socketed "
        "FROM asset_chip k JOIN computers c ON c.asset_id = k.asset_id"))
    op.drop_table("asset_chip")
    op.drop_table("asset_variant")
