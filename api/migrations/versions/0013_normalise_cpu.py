"""one notation for a machine's CPU

Eleven machines record a CPU in four notations: a bare speed appended ('Intel 486
SX 25', 'AMD 286 16'), a dash ('Intel 80286-6', 'Intel 386-20'), a split model
name ('486 SX'), and no speed at all ('Intel 8086'). The dash form is what the
entry form has always given as its example, and what the chips were actually
called, so the other four move to it.

Only the notation changes. No maker is added where none was recorded -- RH-0237's
'386 SX 16' becomes '386SX-16', not 'Intel 386SX-16', however likely Intel is for
a PS/2 Model 55 SX -- and no speed is invented for the three 8086 machines that
never had one recorded.

Revision ID: 0013_normalise_cpu
Revises: 0012_computer_drives
Create Date: 2026-07-30
"""
from alembic import op
import sqlalchemy as sa

revision = "0013_normalise_cpu"
down_revision = "0012_computer_drives"
branch_labels = None
depends_on = None

RENAMES = [
    ("RH-0204", "Intel 486 SX 25", "Intel 486SX-25"),
    ("RH-0215", "AMD 286 16", "AMD 286-16"),
    ("RH-0237", "386 SX 16", "386SX-16"),
    ("RH-0240", "Intel 386 SX 40", "Intel 386SX-40"),
]


def upgrade():
    conn = op.get_bind()
    for aid, before, after in RENAMES:
        result = conn.execute(sa.text(
            "UPDATE computers SET cpu = :after WHERE asset_id = :a AND cpu = :before"),
            {"a": aid, "before": before, "after": after})
        if result.rowcount:
            conn.execute(sa.text(
                "INSERT INTO log_entry (asset_id, created_at, kind, message) "
                "VALUES (:a, NOW(), 'change', :msg)"),
                {"a": aid, "msg": f"cpu: {before} → {after}"})


def downgrade():
    conn = op.get_bind()
    for aid, before, after in RENAMES:
        conn.execute(sa.text(
            "UPDATE computers SET cpu = :before WHERE asset_id = :a AND cpu = :after"),
            {"a": aid, "before": before, "after": after})
        conn.execute(sa.text(
            "DELETE FROM log_entry WHERE asset_id = :a AND message = :msg"),
            {"a": aid, "msg": f"cpu: {before} → {after}"})
