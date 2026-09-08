"""Inventory storage foundation

Revision ID: 0035_inventory_storage
Revises: 0034_bom_foundation
Create Date: 2026-09-08
"""
from alembic import op
import sqlalchemy as sa

revision = "0035_inventory_storage"
down_revision = "0034_bom_foundation"
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        "storage_location",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column("parent_id", sa.Integer(), nullable=True),
        sa.Column("name", sa.String(255), nullable=False),
        sa.Column("kind", sa.String(64), nullable=True),
        sa.Column("display_order", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("active", sa.Boolean(), nullable=False, server_default="1"),
        sa.Column("notes", sa.Text(), nullable=True),
        sa.CheckConstraint("parent_id IS NULL OR parent_id != id",
                           name="ck_storage_location_not_self_parent"),
        sa.ForeignKeyConstraint(["parent_id"], ["storage_location.id"],
                                ondelete="SET NULL"),
    )
    op.create_index("ix_storage_location_parent_id", "storage_location",
                    ["parent_id"])
    op.create_table(
        "inventory_lot",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column("component_id", sa.Integer(), nullable=True),
        sa.Column("part_number_id", sa.Integer(), nullable=True),
        sa.Column("house_part_id", sa.Integer(), nullable=True),
        sa.Column("storage_location_id", sa.Integer(), nullable=True),
        sa.Column("quantity", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("condition", sa.String(32), nullable=True),
        sa.Column("test_status", sa.String(32), nullable=True),
        sa.Column("acquired_date", sa.Date(), nullable=True),
        sa.Column("source", sa.Text(), nullable=True),
        sa.Column("active", sa.Boolean(), nullable=False, server_default="1"),
        sa.Column("notes", sa.Text(), nullable=True),
        sa.CheckConstraint("quantity >= 0",
                           name="ck_inventory_lot_quantity_nonnegative"),
        sa.ForeignKeyConstraint(["component_id"], ["bom_component.id"],
                                ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["house_part_id"], ["bom_house_part.id"],
                                ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["part_number_id"], ["bom_part_number.id"],
                                ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["storage_location_id"], ["storage_location.id"],
                                ondelete="SET NULL"),
    )
    op.create_index("ix_inventory_lot_component_id", "inventory_lot",
                    ["component_id"])
    op.create_index("ix_inventory_lot_part_number_id", "inventory_lot",
                    ["part_number_id"])
    op.create_index("ix_inventory_lot_house_part_id", "inventory_lot",
                    ["house_part_id"])
    op.create_index("ix_inventory_lot_storage_location_id", "inventory_lot",
                    ["storage_location_id"])
    op.create_table(
        "inventory_item",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column("lot_id", sa.Integer(), nullable=False),
        sa.Column("item_code", sa.String(64), nullable=True),
        sa.Column("condition", sa.String(32), nullable=True),
        sa.Column("test_status", sa.String(32), nullable=True),
        sa.Column("active", sa.Boolean(), nullable=False, server_default="1"),
        sa.Column("notes", sa.Text(), nullable=True),
        sa.ForeignKeyConstraint(["lot_id"], ["inventory_lot.id"],
                                ondelete="CASCADE"),
        sa.UniqueConstraint("item_code", name="uq_inventory_item_code"),
    )
    op.create_index("ix_inventory_item_lot_id", "inventory_item", ["lot_id"])


def downgrade():
    op.drop_index("ix_inventory_item_lot_id", table_name="inventory_item")
    op.drop_table("inventory_item")
    op.drop_index("ix_inventory_lot_storage_location_id",
                  table_name="inventory_lot")
    op.drop_index("ix_inventory_lot_house_part_id", table_name="inventory_lot")
    op.drop_index("ix_inventory_lot_part_number_id", table_name="inventory_lot")
    op.drop_index("ix_inventory_lot_component_id", table_name="inventory_lot")
    op.drop_table("inventory_lot")
    op.drop_index("ix_storage_location_parent_id", table_name="storage_location")
    op.drop_table("storage_location")
