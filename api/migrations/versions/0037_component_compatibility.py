"""Evidence-backed component compatibility

Revision ID: 0037_component_compatibility
Revises: 0036_donor_workflow
Create Date: 2026-09-08
"""
from alembic import op
import sqlalchemy as sa

revision = "0037_component_compatibility"
down_revision = "0036_donor_workflow"
branch_labels = None
depends_on = None

RELATIONSHIPS = (
    "'exact-equivalent', 'manufacturer-alternate', 'electrical-substitute', "
    "'pin-compatible-substitute', 'functional-substitute', "
    "'documented-service-substitute', 'production-alternate', "
    "'conditional-substitute', 'incompatible'"
)
DIMENSIONS = [
    "function_compatible", "pinout_compatible", "package_compatible",
    "voltage_compatible", "logic_level_compatible", "timing_compatible",
    "frequency_compatible", "thermal_current_compatible", "analogue_compatible",
    "firmware_content_compatible", "region_standard_compatible",
]


def upgrade():
    op.add_column("bom_house_part_option", sa.Column(
        "mapping_status", sa.String(24), nullable=False, server_default="draft"))
    op.create_check_constraint(
        "ck_bom_house_part_option_status", "bom_house_part_option",
        "mapping_status IN ('draft', 'confirmed', 'production-supplier', "
        "'probable', 'disputed', 'unknown')")

    columns = [
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column("source_part_number_id", sa.Integer(), nullable=False),
        sa.Column("target_part_number_id", sa.Integer(), nullable=False),
        sa.Column("relationship_type", sa.String(40), nullable=False),
        sa.Column("status", sa.String(16), nullable=False, server_default="draft"),
    ]
    columns.extend(sa.Column(name, sa.String(16), nullable=True) for name in DIMENSIONS)
    columns.extend([
        sa.Column("scope_reference_bom_id", sa.Integer(), nullable=True),
        sa.Column("scope_position_id", sa.Integer(), nullable=True),
        sa.Column("platform", sa.String(255), nullable=True),
        sa.Column("manufacturer", sa.String(255), nullable=True),
        sa.Column("required_package", sa.String(64), nullable=True),
        sa.Column("region", sa.String(64), nullable=True),
        sa.Column("video_standard", sa.String(32), nullable=True),
        sa.Column("caveat", sa.Text(), nullable=True),
        sa.Column("notes", sa.Text(), nullable=True),
        sa.CheckConstraint("source_part_number_id <> target_part_number_id",
                           name="ck_component_compatibility_not_self"),
        sa.CheckConstraint(f"relationship_type IN ({RELATIONSHIPS})",
                           name="ck_component_compatibility_relationship"),
        sa.CheckConstraint("status IN ('draft', 'evidenced', 'verified', 'disputed', "
                           "'deprecated')", name="ck_component_compatibility_status"),
        sa.CheckConstraint("scope_position_id IS NULL OR scope_reference_bom_id IS NOT NULL",
                           name="ck_component_compatibility_position_scope"),
        sa.CheckConstraint(" AND ".join(
            f"({name} IS NULL OR {name} IN ('compatible', 'conditional', 'incompatible'))"
            for name in DIMENSIONS), name="ck_component_compatibility_dimensions"),
        sa.ForeignKeyConstraint(["source_part_number_id"], ["bom_part_number.id"],
                                ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(["target_part_number_id"], ["bom_part_number.id"],
                                ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(["scope_reference_bom_id"], ["reference_bom.id"],
                                ondelete="CASCADE"),
        sa.ForeignKeyConstraint(
            ["scope_position_id", "scope_reference_bom_id"],
            ["bom_position.id", "bom_position.reference_bom_id"],
            name="fk_component_compatibility_position_scope", ondelete="CASCADE"),
        sa.UniqueConstraint(
            "source_part_number_id", "target_part_number_id", "relationship_type",
            "scope_reference_bom_id", "scope_position_id", "platform", "manufacturer",
            "required_package", "region", "video_standard",
            name="uq_component_compatibility_scope"),
        sa.UniqueConstraint("source_part_number_id", "target_part_number_id",
                            "relationship_type", "scope_position_id",
                            name="uq_component_compatibility_position"),
    ])
    op.create_table("component_compatibility", *columns)
    for column in ("source_part_number_id", "target_part_number_id",
                   "scope_reference_bom_id", "scope_position_id"):
        op.create_index(f"ix_component_compatibility_{column}",
                        "component_compatibility", [column])

    op.create_table(
        "component_compatibility_evidence",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column("compatibility_id", sa.Integer(), nullable=False),
        sa.Column("source_id", sa.Integer(), nullable=False),
        sa.Column("locator", sa.String(255), nullable=False, server_default=""),
        sa.Column("directly_states_claim", sa.Boolean(), nullable=False,
                  server_default=sa.text("0")),
        sa.Column("notes", sa.Text(), nullable=True),
        sa.ForeignKeyConstraint(["compatibility_id"], ["component_compatibility.id"],
                                ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["source_id"], ["bom_source.id"], ondelete="RESTRICT"),
        sa.UniqueConstraint("compatibility_id", "source_id", "locator",
                            name="uq_component_compatibility_evidence"),
    )
    op.create_index("ix_component_compatibility_evidence_compatibility_id",
                    "component_compatibility_evidence", ["compatibility_id"])
    op.create_index("ix_component_compatibility_evidence_source_id",
                    "component_compatibility_evidence", ["source_id"])

    op.create_table(
        "bom_house_part_option_evidence",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column("option_id", sa.Integer(), nullable=False),
        sa.Column("source_id", sa.Integer(), nullable=False),
        sa.Column("locator", sa.String(255), nullable=False, server_default=""),
        sa.Column("directly_states_mapping", sa.Boolean(), nullable=False,
                  server_default=sa.text("0")),
        sa.Column("notes", sa.Text(), nullable=True),
        sa.ForeignKeyConstraint(["option_id"], ["bom_house_part_option.id"],
                                ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["source_id"], ["bom_source.id"], ondelete="RESTRICT"),
        sa.UniqueConstraint("option_id", "source_id", "locator",
                            name="uq_bom_house_option_evidence"),
    )
    op.create_index("ix_bom_house_part_option_evidence_option_id",
                    "bom_house_part_option_evidence", ["option_id"])
    op.create_index("ix_bom_house_part_option_evidence_source_id",
                    "bom_house_part_option_evidence", ["source_id"])

    op.create_table(
        "component_production_use",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column("part_number_id", sa.Integer(), nullable=False),
        sa.Column("reference_bom_id", sa.Integer(), nullable=False),
        sa.Column("position_id", sa.Integer(), nullable=True),
        sa.Column("status", sa.String(16), nullable=False, server_default="draft"),
        sa.Column("notes", sa.Text(), nullable=True),
        sa.CheckConstraint("status IN ('draft', 'evidenced', 'verified', 'disputed', "
                           "'deprecated')", name="ck_component_production_use_status"),
        sa.CheckConstraint("position_id IS NULL OR reference_bom_id IS NOT NULL",
                           name="ck_component_production_use_position_scope"),
        sa.ForeignKeyConstraint(["part_number_id"], ["bom_part_number.id"],
                                ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(["reference_bom_id"], ["reference_bom.id"],
                                ondelete="CASCADE"),
        sa.ForeignKeyConstraint(
            ["position_id", "reference_bom_id"],
            ["bom_position.id", "bom_position.reference_bom_id"],
            name="fk_component_production_use_position_scope", ondelete="CASCADE"),
        sa.UniqueConstraint("part_number_id", "reference_bom_id", "position_id",
                            name="uq_component_production_use_scope"),
    )
    for column in ("part_number_id", "reference_bom_id", "position_id"):
        op.create_index(f"ix_component_production_use_{column}",
                        "component_production_use", [column])

    op.create_table(
        "component_production_use_evidence",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column("production_use_id", sa.Integer(), nullable=False),
        sa.Column("source_id", sa.Integer(), nullable=False),
        sa.Column("locator", sa.String(255), nullable=False, server_default=""),
        sa.Column("notes", sa.Text(), nullable=True),
        sa.ForeignKeyConstraint(["production_use_id"], ["component_production_use.id"],
                                ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["source_id"], ["bom_source.id"], ondelete="RESTRICT"),
        sa.UniqueConstraint("production_use_id", "source_id", "locator",
                            name="uq_component_production_use_evidence"),
    )
    op.create_index("ix_component_production_use_evidence_production_use_id",
                    "component_production_use_evidence", ["production_use_id"])
    op.create_index("ix_component_production_use_evidence_source_id",
                    "component_production_use_evidence", ["source_id"])


def downgrade():
    op.drop_table("component_production_use_evidence")
    op.drop_table("component_production_use")
    op.drop_table("bom_house_part_option_evidence")
    op.drop_table("component_compatibility_evidence")
    op.drop_table("component_compatibility")
    op.drop_constraint("ck_bom_house_part_option_status", "bom_house_part_option",
                       type_="check")
    op.drop_column("bom_house_part_option", "mapping_status")
