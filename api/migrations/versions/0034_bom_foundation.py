"""BOM foundation as a provenance-first layer

Revision ID: 0034_bom_foundation
Revises: 0033_work_project_names
Create Date: 2026-09-08
"""
from alembic import op
import sqlalchemy as sa

revision = "0034_bom_foundation"
down_revision = "0033_work_project_names"
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        "bom_component",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column("generic_name", sa.String(128), nullable=True),
        sa.Column("category", sa.String(64), nullable=True),
        sa.Column("specification", sa.Text(), nullable=True),
        sa.Column("package", sa.String(64), nullable=True),
        sa.Column("notes", sa.Text(), nullable=True),
    )
    op.create_table(
        "bom_part_number",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column("component_id", sa.Integer(), nullable=True),
        sa.Column("manufacturer", sa.String(255), nullable=True),
        sa.Column("part_number", sa.String(128), nullable=True),
        sa.Column("package", sa.String(64), nullable=True),
        sa.Column("notes", sa.Text(), nullable=True),
        sa.ForeignKeyConstraint(["component_id"], ["bom_component.id"],
                                ondelete="SET NULL"),
    )
    op.create_index("ix_bom_part_number_component_id", "bom_part_number",
                    ["component_id"])
    op.create_table(
        "bom_part_marking",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column("part_number_id", sa.Integer(), nullable=False),
        sa.Column("marking", sa.String(128), nullable=False),
        sa.Column("notes", sa.Text(), nullable=True),
        sa.ForeignKeyConstraint(["part_number_id"], ["bom_part_number.id"],
                                ondelete="CASCADE"),
        sa.UniqueConstraint("part_number_id", "marking",
                            name="uq_bom_part_marking"),
    )
    op.create_index("ix_bom_part_marking_part_number_id", "bom_part_marking",
                    ["part_number_id"])
    op.create_table(
        "bom_house_part",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column("component_id", sa.Integer(), nullable=True),
        sa.Column("organization", sa.String(255), nullable=True),
        sa.Column("house_number", sa.String(128), nullable=False),
        sa.Column("notes", sa.Text(), nullable=True),
        sa.ForeignKeyConstraint(["component_id"], ["bom_component.id"],
                                ondelete="SET NULL"),
    )
    op.create_index("ix_bom_house_part_component_id", "bom_house_part",
                    ["component_id"])
    op.create_table(
        "bom_house_part_option",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column("house_part_id", sa.Integer(), nullable=False),
        sa.Column("part_number_id", sa.Integer(), nullable=False),
        sa.Column("notes", sa.Text(), nullable=True),
        sa.ForeignKeyConstraint(["house_part_id"], ["bom_house_part.id"],
                                ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["part_number_id"], ["bom_part_number.id"],
                                ondelete="CASCADE"),
        sa.UniqueConstraint("house_part_id", "part_number_id",
                            name="uq_bom_house_part_option"),
    )
    op.create_index("ix_bom_house_part_option_house_part_id",
                    "bom_house_part_option", ["house_part_id"])
    op.create_index("ix_bom_house_part_option_part_number_id",
                    "bom_house_part_option", ["part_number_id"])
    op.create_table(
        "bom_source",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column("source_type", sa.String(64), nullable=False),
        sa.Column("title", sa.String(255), nullable=False, server_default=""),
        sa.Column("publisher", sa.String(255), nullable=True),
        sa.Column("publication", sa.String(64), nullable=True),
        sa.Column("url", sa.Text(), nullable=True),
        sa.Column("file_id", sa.Integer(), nullable=True),
        sa.Column("locator", sa.String(255), nullable=True),
        sa.Column("notes", sa.Text(), nullable=True),
        sa.ForeignKeyConstraint(["file_id"], ["files.id"], ondelete="SET NULL"),
    )
    op.create_index("ix_bom_source_file_id", "bom_source", ["file_id"])
    op.create_table(
        "reference_bom",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column("model_key", sa.String(64), nullable=True),
        sa.Column("manufacturer", sa.String(255), nullable=True),
        sa.Column("platform", sa.String(255), nullable=True),
        sa.Column("board_identifier", sa.String(128), nullable=True),
        sa.Column("pcb_revision", sa.String(64), nullable=True),
        sa.Column("population_variant", sa.String(64), nullable=True),
        sa.Column("region", sa.String(64), nullable=True),
        sa.Column("video_standard", sa.String(32), nullable=True),
        sa.Column("name", sa.String(255), nullable=False, server_default=""),
        sa.Column("status", sa.String(16), nullable=False, server_default="draft"),
        sa.Column("notes", sa.Text(), nullable=True),
    )
    op.create_index("ix_reference_bom_model_key", "reference_bom", ["model_key"])
    op.create_table(
        "bom_position",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column("reference_bom_id", sa.Integer(), nullable=False),
        sa.Column("refdes", sa.String(32), nullable=False),
        sa.Column("component_id", sa.Integer(), nullable=True),
        sa.Column("part_number_id", sa.Integer(), nullable=True),
        sa.Column("house_part_id", sa.Integer(), nullable=True),
        sa.Column("expected", sa.Text(), nullable=True),
        sa.Column("package", sa.String(64), nullable=True),
        sa.Column("applicability", sa.String(255), nullable=True),
        sa.Column("side", sa.String(16), nullable=True),
        sa.Column("x_norm", sa.Float(), nullable=True),
        sa.Column("y_norm", sa.Float(), nullable=True),
        sa.Column("rotation", sa.Float(), nullable=True),
        sa.Column("region", sa.String(64), nullable=True),
        sa.Column("notes", sa.Text(), nullable=True),
        sa.ForeignKeyConstraint(["component_id"], ["bom_component.id"],
                                ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["house_part_id"], ["bom_house_part.id"],
                                ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["part_number_id"], ["bom_part_number.id"],
                                ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["reference_bom_id"], ["reference_bom.id"],
                                ondelete="CASCADE"),
        sa.UniqueConstraint("id", "reference_bom_id",
                            name="uq_bom_position_id_reference_bom"),
        sa.CheckConstraint("x_norm IS NULL OR (x_norm >= 0 AND x_norm <= 1)",
                           name="ck_bom_position_x_norm"),
        sa.CheckConstraint("y_norm IS NULL OR (y_norm >= 0 AND y_norm <= 1)",
                           name="ck_bom_position_y_norm"),
        sa.UniqueConstraint("reference_bom_id", "refdes",
                            name="uq_bom_position_refdes"),
    )
    op.create_index("ix_bom_position_component_id", "bom_position",
                    ["component_id"])
    op.create_index("ix_bom_position_part_number_id", "bom_position",
                    ["part_number_id"])
    op.create_index("ix_bom_position_house_part_id", "bom_position",
                    ["house_part_id"])
    op.create_index("ix_bom_position_reference_bom_id", "bom_position",
                    ["reference_bom_id"])
    op.create_table(
        "bom_position_evidence",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column("position_id", sa.Integer(), nullable=False),
        sa.Column("source_id", sa.Integer(), nullable=False),
        sa.Column("locator", sa.String(255), nullable=False, server_default=""),
        sa.Column("notes", sa.Text(), nullable=True),
        sa.ForeignKeyConstraint(["position_id"], ["bom_position.id"],
                                ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["source_id"], ["bom_source.id"],
                                ondelete="CASCADE"),
        sa.UniqueConstraint("position_id", "source_id", "locator",
                            name="uq_bom_position_evidence"),
    )
    op.create_index("ix_bom_position_evidence_position_id",
                    "bom_position_evidence", ["position_id"])
    op.create_index("ix_bom_position_evidence_source_id",
                    "bom_position_evidence", ["source_id"])
    op.create_table(
        "part_bom",
        sa.Column("part_id", sa.String(16), primary_key=True),
        sa.Column("reference_bom_id", sa.Integer(), nullable=False),
        sa.Column("baseline_state", sa.String(32), nullable=False,
                  server_default="unknown"),
        sa.Column("inspection_status", sa.String(32), nullable=False,
                  server_default="uninspected"),
        sa.Column("notes", sa.Text(), nullable=True),
        sa.ForeignKeyConstraint(["part_id"], ["parts.asset_id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["reference_bom_id"], ["reference_bom.id"],
                                ondelete="CASCADE"),
        sa.UniqueConstraint("part_id", "reference_bom_id",
                            name="uq_part_bom_reference"),
    )
    op.create_index("ix_part_bom_reference_bom_id", "part_bom",
                    ["reference_bom_id"])
    op.create_table(
        "part_bom_position_state",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column("part_id", sa.String(16), nullable=False),
        sa.Column("reference_bom_id", sa.Integer(), nullable=False),
        sa.Column("position_id", sa.Integer(), nullable=False),
        sa.Column("state", sa.String(32), nullable=False),
        sa.Column("observed_part_number_id", sa.Integer(), nullable=True),
        sa.Column("observed_house_part_id", sa.Integer(), nullable=True),
        sa.Column("observed", sa.Text(), nullable=True),
        sa.Column("notes", sa.Text(), nullable=True),
        sa.ForeignKeyConstraint(["observed_house_part_id"], ["bom_house_part.id"],
                                ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["observed_part_number_id"], ["bom_part_number.id"],
                                ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["part_id", "reference_bom_id"],
                                ["part_bom.part_id", "part_bom.reference_bom_id"],
                                ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["position_id", "reference_bom_id"],
                                ["bom_position.id", "bom_position.reference_bom_id"],
                                ondelete="CASCADE"),
        sa.UniqueConstraint("part_id", "position_id",
                            name="uq_part_bom_position_state"),
    )
    op.create_index("ix_part_bom_position_state_observed_part_number_id",
                    "part_bom_position_state", ["observed_part_number_id"])
    op.create_index("ix_part_bom_position_state_observed_house_part_id",
                    "part_bom_position_state", ["observed_house_part_id"])
    op.create_index("ix_part_bom_position_state_part_id",
                    "part_bom_position_state", ["part_id"])
    op.create_index("ix_part_bom_position_state_reference_bom_id",
                    "part_bom_position_state", ["reference_bom_id"])
    op.create_index("ix_part_bom_position_state_position_id",
                    "part_bom_position_state", ["position_id"])


def downgrade():
    # Dropping each table also drops its indexes. MariaDB will not let an index
    # be removed separately while a foreign key still depends on it.
    op.drop_table("part_bom_position_state")
    op.drop_table("part_bom")
    op.drop_table("bom_position_evidence")
    op.drop_table("bom_position")
    op.drop_table("reference_bom")
    op.drop_table("bom_source")
    op.drop_table("bom_house_part_option")
    op.drop_table("bom_house_part")
    op.drop_table("bom_part_marking")
    op.drop_table("bom_part_number")
    op.drop_table("bom_component")
