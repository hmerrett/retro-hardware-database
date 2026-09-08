"""Donor workflow and traceable component history

Revision ID: 0036_donor_workflow
Revises: 0035_inventory_storage
Create Date: 2026-09-08
"""
from alembic import op
import sqlalchemy as sa

revision = "0036_donor_workflow"
down_revision = "0035_inventory_storage"
branch_labels = None
depends_on = None


def upgrade():
    op.add_column("parts", sa.Column("board_role", sa.String(16), nullable=False,
                                     server_default="normal"))
    op.create_check_constraint("ck_parts_board_role", "parts",
                               "board_role IN ('normal', 'donor', 'repair')")
    op.add_column("inventory_item", sa.Column(
        "lifecycle_status", sa.String(16), nullable=False,
        server_default="inventory"))
    op.create_check_constraint(
        "ck_inventory_item_lifecycle", "inventory_item",
        "lifecycle_status IN ('inventory', 'installed', 'discarded', 'unavailable')")
    op.add_column("part_bom_position_state", sa.Column(
        "inventory_item_id", sa.Integer(), nullable=True))
    op.create_unique_constraint("uq_part_bom_position_state_inventory_item",
                                "part_bom_position_state", ["inventory_item_id"])
    op.create_foreign_key(
        "fk_position_state_inventory_item", "part_bom_position_state",
        "inventory_item", ["inventory_item_id"], ["id"], ondelete="SET NULL")

    op.create_table(
        "component_event",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column("event_type", sa.String(32), nullable=False),
        sa.Column("created_at", sa.DateTime(), nullable=False,
                  server_default=sa.text("CURRENT_TIMESTAMP")),
        sa.Column("event_date", sa.Date(), nullable=True),
        sa.Column("source_part_id", sa.String(16), nullable=True),
        sa.Column("source_reference_bom_id", sa.Integer(), nullable=True),
        sa.Column("source_position_id", sa.Integer(), nullable=True),
        sa.Column("destination_part_id", sa.String(16), nullable=True),
        sa.Column("destination_reference_bom_id", sa.Integer(), nullable=True),
        sa.Column("destination_position_id", sa.Integer(), nullable=True),
        sa.Column("inventory_lot_id", sa.Integer(), nullable=True),
        sa.Column("inventory_item_id", sa.Integer(), nullable=True),
        sa.Column("source_storage_location_id", sa.Integer(), nullable=True),
        sa.Column("destination_storage_location_id", sa.Integer(), nullable=True),
        sa.Column("project_id", sa.String(16), nullable=True),
        sa.Column("notes", sa.Text(), nullable=True),
        sa.CheckConstraint(
            "event_type IN ('acquired', 'harvested', 'added-to-inventory', "
            "'moved', 'installed', 'removed', 'tested', 'marked-failed', "
            "'discarded')", name="ck_component_event_type"),
        sa.ForeignKeyConstraint(["inventory_lot_id"], ["inventory_lot.id"],
                                ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["inventory_item_id"], ["inventory_item.id"],
                                ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["source_storage_location_id"],
                                ["storage_location.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["destination_storage_location_id"],
                                ["storage_location.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["project_id"], ["projects.asset_id"],
                                ondelete="SET NULL"),
        sa.ForeignKeyConstraint(
            ["source_part_id", "source_reference_bom_id"],
            ["part_bom.part_id", "part_bom.reference_bom_id"],
            name="fk_component_event_source_part_bom", ondelete="SET NULL"),
        sa.ForeignKeyConstraint(
            ["source_position_id", "source_reference_bom_id"],
            ["bom_position.id", "bom_position.reference_bom_id"],
            name="fk_component_event_source_position", ondelete="SET NULL"),
        sa.ForeignKeyConstraint(
            ["destination_part_id", "destination_reference_bom_id"],
            ["part_bom.part_id", "part_bom.reference_bom_id"],
            name="fk_component_event_destination_part_bom", ondelete="SET NULL"),
        sa.ForeignKeyConstraint(
            ["destination_position_id", "destination_reference_bom_id"],
            ["bom_position.id", "bom_position.reference_bom_id"],
            name="fk_component_event_destination_position", ondelete="SET NULL"),
    )
    for column in (
        "event_type", "created_at", "source_part_id", "source_position_id",
        "destination_part_id", "destination_position_id", "inventory_lot_id",
        "inventory_item_id", "source_storage_location_id",
        "destination_storage_location_id", "project_id",
    ):
        op.create_index(f"ix_component_event_{column}", "component_event", [column])


def downgrade():
    op.drop_table("component_event")
    op.drop_constraint("fk_position_state_inventory_item",
                       "part_bom_position_state", type_="foreignkey")
    op.drop_constraint("uq_part_bom_position_state_inventory_item",
                       "part_bom_position_state", type_="unique")
    op.drop_column("part_bom_position_state", "inventory_item_id")
    op.drop_constraint("ck_inventory_item_lifecycle", "inventory_item",
                       type_="check")
    op.drop_column("inventory_item", "lifecycle_status")
    op.drop_constraint("ck_parts_board_role", "parts", type_="check")
    op.drop_column("parts", "board_role")
