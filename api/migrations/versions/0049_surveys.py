"""surveys: a machine's report of itself, what surveys have seen, and the answers kept
for things with no serial number

ADR-0043. Three new tables, and two columns on tables already there: a part's
Ethernet address, which is the owner's alone, and a file's digest, so that a ROM a
survey reads again is the file already kept. Nothing here reads or changes a row that
is already in the register: both columns start empty, which is what they mean for
everything no survey has touched.

MariaDB auto-commits DDL, so every step looks before it acts, and the migration can be
run again after a failure part-way without wedging a restart.

Revision ID: 0049_surveys
Revises: 0048_each_label_its_own
Create Date: 2026-11-06
"""

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects.mysql import MEDIUMTEXT

revision = "0049_surveys"
down_revision = "0048_each_label_its_own"
branch_labels = None
depends_on = None


def _has_table(name):
    return sa.inspect(op.get_bind()).has_table(name)


def _columns(table):
    return {c["name"] for c in sa.inspect(op.get_bind()).get_columns(table)}


def _indexes(table):
    return {ix["name"] for ix in sa.inspect(op.get_bind()).get_indexes(table)}


def upgrade():
    if "ethernet_address" not in _columns("parts"):
        op.add_column(
            "parts",
            sa.Column("ethernet_address", sa.String(length=17), nullable=False, server_default=""),
        )
    if "digest" not in _columns("files"):
        op.add_column(
            "files", sa.Column("digest", sa.String(length=64), nullable=False, server_default="")
        )
    if "ix_files_digest" not in _indexes("files"):
        op.create_index("ix_files_digest", "files", ["digest"])

    if not _has_table("surveys"):
        op.create_table(
            "surveys",
            sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
            sa.Column("agent", sa.String(length=64), nullable=False, server_default=""),
            sa.Column("taken", sa.DateTime(), nullable=False),
            sa.Column("clock", sa.String(length=32), nullable=False, server_default=""),
            sa.Column("report", MEDIUMTEXT(), nullable=False),
            sa.Column("keys", MEDIUMTEXT(), nullable=False),
            sa.Column("machine", sa.String(length=16), nullable=True),
            sa.Column("how", sa.String(length=16), nullable=False, server_default=""),
            sa.Column("by", sa.String(length=128), nullable=False, server_default=""),
            sa.Column("waiting", sa.String(length=16), nullable=True),
            sa.Column("reason", sa.String(length=255), nullable=False, server_default=""),
            sa.Column("result", sa.String(length=16), nullable=False, server_default=""),
            sa.Column("bench_card", sa.String(length=16), nullable=True),
            sa.Column("findings", MEDIUMTEXT(), nullable=False),
            sa.Column("filled", sa.Text(), nullable=False),
            sa.Column("differs", sa.Text(), nullable=False),
            sa.Column("missing", sa.Text(), nullable=False),
            sa.Column("roms", MEDIUMTEXT(), nullable=False),
            sa.Column("log_id", sa.Integer(), nullable=True),
            sa.PrimaryKeyConstraint("id"),
            sa.ForeignKeyConstraint(
                ["log_id"], ["log_entry.id"], name="fk_surveys_log_id", ondelete="SET NULL"
            ),
        )
        for column in ("taken", "machine", "waiting", "log_id"):
            op.create_index(f"ix_surveys_{column}", "surveys", [column])

    if not _has_table("survey_seen"):
        op.create_table(
            "survey_seen",
            sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
            sa.Column("kind", sa.String(length=8), nullable=False),
            sa.Column("value", sa.String(length=128), nullable=False),
            sa.Column("answer", sa.String(length=8), nullable=True),
            sa.Column("asset_id", sa.String(length=16), nullable=True),
            sa.Column("first_seen", sa.DateTime(), nullable=False),
            sa.Column("last_seen", sa.DateTime(), nullable=False),
            sa.Column("last_in", sa.String(length=16), nullable=True),
            sa.Column("last_survey", sa.Integer(), nullable=True),
            sa.PrimaryKeyConstraint("id"),
            sa.ForeignKeyConstraint(
                ["last_survey"],
                ["surveys.id"],
                name="fk_survey_seen_last_survey",
                ondelete="SET NULL",
            ),
            sa.UniqueConstraint("kind", "value", name="uq_survey_seen_kind_value"),
        )
        for column in ("asset_id", "last_seen", "last_survey"):
            op.create_index(f"ix_survey_seen_{column}", "survey_seen", [column])

    if not _has_table("survey_answers"):
        op.create_table(
            "survey_answers",
            sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
            sa.Column("machine", sa.String(length=16), nullable=False),
            sa.Column("thing", sa.String(length=191), nullable=False),
            sa.Column("nth", sa.SmallInteger(), nullable=False, server_default="0"),
            sa.Column("answer", sa.String(length=8), nullable=False),
            sa.Column("part", sa.String(length=16), nullable=True),
            sa.PrimaryKeyConstraint("id"),
            sa.UniqueConstraint("machine", "thing", "nth", name="uq_survey_answer"),
        )


def downgrade():
    for table in ("survey_answers", "survey_seen", "surveys"):
        if _has_table(table):
            op.drop_table(table)
    if "ix_files_digest" in _indexes("files"):
        op.drop_index("ix_files_digest", table_name="files")
    if "digest" in _columns("files"):
        op.drop_column("files", "digest")
    if "ethernet_address" in _columns("parts"):
        op.drop_column("parts", "ethernet_address")
