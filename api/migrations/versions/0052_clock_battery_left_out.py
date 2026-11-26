"""a clock that failed on its battery does not fail a survey's board tests

ADR-0056. tinydiag's clock test checks first what the clock's battery keeps, and a clock
that fails there (its memory said not valid, its SET bit left on, its divider stopped,
the CMOS's power or checksum lost) is taken as not applying, as a clock on an XT is. A
clock that runs and fails still fails the board.

Every survey already taken has its `board_result` worked out again by that rule, so a
board whose newest deciding survey failed on its clock's battery alone is verified from
the day this runs. As in 0051, the rule below is a copy of `surveys.board_tests` as it
stands today, kept here on purpose, and nothing is written in the history.

Downgrading works the verdicts out again by 0051's rule, which counted the battery.
Each row is set outright, so running either way twice gives the same answer.

Revision ID: 0052_clock_battery_left_out
Revises: 0051_a_surveys_board_tests
Create Date: 2026-11-26
"""

import json
import re

import sqlalchemy as sa
from alembic import op

revision = "0052_clock_battery_left_out"
down_revision = "0051_a_surveys_board_tests"
branch_labels = None
depends_on = None

# tinydiag's tests of the board and its memory, as surveys.BOARD_TESTS has them.
BOARD_TESTS = ("TICK", "CPU", "FPU", "ROM", "PIT", "DMA", "PIC", "NMI", "RTC", "RAM", "RAMSYS")
MEMORY_TESTS = ("RAM", "RAMSYS")
HMA_KB = 64
_REACHED = re.compile(r"\b(\d+)K XMS\b")
# The clock test's failures its battery explains, as tinydiag words them in DETAIL_RTC.
_BATTERY = re.compile(
    r"^(battery flat|clock halted|oscillator off|BIOS: CMOS lost power|BIOS: CMOS checksum bad"
    r"|CMOS checksum:)",
    re.IGNORECASE,
)


def _all_memory(keys):
    cpu = (keys.get("CPU") or "").strip().upper()
    if cpu.startswith(("808", "8018", "V2", "V3")):
        return True
    above = (keys.get("EXTKB") or "").strip()
    if not above.isdigit():
        return False
    if int(above) == 0:
        return True
    reached = _REACHED.search(keys.get("DETAIL_RAM") or "")
    return reached is not None and int(reached.group(1)) + HMA_KB >= int(above)


def _board_result(keys, battery_counts):
    results = {name: (keys.get(f"TEST_{name}") or "").strip().upper() for name in BOARD_TESTS}
    detail = (keys.get("DETAIL_RTC") or "").strip()
    if not battery_counts and results["RTC"] == "FAIL" and _BATTERY.match(detail):
        results["RTC"] = "NA"
    if "FAIL" in results.values():
        return "FAIL"
    for name, result in results.items():
        if result != "PASS" and (result != "NA" or name in MEMORY_TESTS):
            return ""
    return "PASS" if _all_memory(keys) else ""


def _loads(text):
    try:
        value = json.loads(text or "")
    except ValueError:
        return None
    return value


def _judge(battery_counts):
    conn = op.get_bind()
    rows = conn.execute(sa.text("SELECT id, `keys`, board_result FROM surveys")).all()
    for sid, keys_text, was in rows:
        keys = _loads(keys_text)
        keys = keys if isinstance(keys, dict) else {}
        now = _board_result({str(k): str(v) for k, v in keys.items()}, battery_counts)
        if now != (was or ""):
            conn.execute(
                sa.text("UPDATE surveys SET board_result = :result WHERE id = :id"),
                {"result": now, "id": sid},
            )


def upgrade():
    _judge(battery_counts=False)


def downgrade():
    _judge(battery_counts=True)
