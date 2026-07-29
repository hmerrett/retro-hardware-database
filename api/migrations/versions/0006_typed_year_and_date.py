"""typed year + acquired_date on computers and parts

year becomes a SMALLINT and acquired_date a DATE, on both tables. The live data
is clean enough to convert, with three exceptions among the parts, all fixed
here first:

  * 26 dates typed day-first (17/06/2026). Unambiguous -- 17/05, 22/11 and 23/06
    rule out a month-first reading -- so they convert with STR_TO_DATE.
  * one typo, 2026-05016, which is 2026-05-16.
  * five year-only values (2025, 2026) that a DATE cannot hold. These become
    NULL, and the original is written to the asset's history so the detail
    survives where a human will see it.

Blank strings become NULL throughout: "not recorded" was always what they meant.

Revision ID: 0006_typed_year_date
Revises: 0005_numeric_spec_values
Create Date: 2026-07-29
"""
from alembic import op
import sqlalchemy as sa

revision = "0006_typed_year_date"
down_revision = "0005_numeric_spec_values"
branch_labels = None
depends_on = None

TABLES = ("computers", "parts")

YEAR_RE = "^[0-9]{4}$"
ISO_RE = "^[0-9]{4}-[0-9]{2}-[0-9]{2}$"
DMY_RE = "^[0-9]{1,2}/[0-9]{1,2}/[0-9]{4}$"


def upgrade():
    conn = op.get_bind()

    for t in TABLES:
        # A year that is not four digits was never a year.
        conn.execute(sa.text(
            f"UPDATE {t} SET year = NULL WHERE year IS NULL OR year NOT REGEXP :re"
        ), {"re": YEAR_RE})

        conn.execute(sa.text(
            f"UPDATE {t} SET acquired_date = '2026-05-16' "
            "WHERE acquired_date = '2026-05016'"))

        conn.execute(sa.text(
            f"UPDATE {t} SET acquired_date = DATE_FORMAT("
            "STR_TO_DATE(acquired_date, '%d/%m/%Y'), '%Y-%m-%d') "
            "WHERE acquired_date REGEXP :re"), {"re": DMY_RE})

        # Keep what a year-only value told us, then let the column go NULL.
        conn.execute(sa.text(
            "INSERT INTO log_entry (asset_id, created_at, kind, message) "
            f"SELECT asset_id, NOW(), 'change', CONCAT("
            "'acquired_date: ', acquired_date, ' → (empty) — no month or day recorded') "
            f"FROM {t} WHERE acquired_date IS NOT NULL AND acquired_date <> '' "
            "AND acquired_date NOT REGEXP :re"), {"re": ISO_RE})

        conn.execute(sa.text(
            f"UPDATE {t} SET acquired_date = NULL "
            "WHERE acquired_date IS NULL OR acquired_date NOT REGEXP :re"),
            {"re": ISO_RE})

        op.alter_column(t, "year", type_=sa.SmallInteger(),
                        existing_type=sa.String(16), existing_nullable=True)
        op.alter_column(t, "acquired_date", type_=sa.Date(),
                        existing_type=sa.String(32), existing_nullable=True)


def downgrade():
    for t in TABLES:
        op.alter_column(t, "acquired_date", type_=sa.String(32),
                        existing_type=sa.Date(), existing_nullable=True)
        op.alter_column(t, "year", type_=sa.String(16),
                        existing_type=sa.SmallInteger(), existing_nullable=True)
        op.execute(f"UPDATE {t} SET year = '' WHERE year IS NULL")
        op.execute(f"UPDATE {t} SET acquired_date = '' WHERE acquired_date IS NULL")
