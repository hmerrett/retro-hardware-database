"""what a survey's board tests said, and of which board

ADR-0055. A motherboard is Verified when the newest survey of it that tested its board
passed every board test. That is read from the surveys rather than kept on the board,
so each survey keeps two things: `board_result`, the verdict of its board tests (PASS,
FAIL, or empty where it did not run them all or did not reach all of the memory), and
`board`, the motherboard they were of.

Both are filled here for every survey already taken, from what each one kept: its
report's keys, and the answer it gave for its motherboard. So a board whose newest
deciding survey passed is verified from the day this runs, as it would have been had the
survey been taken after. The rule below is a copy of `surveys.board_tests` as it stands
today, kept here on purpose: a migration is run against the data of its own day, and
must not change its answer when the app's code moves on. Nothing in the history is
written: the surveys already wrote their lines.

MariaDB auto-commits DDL, so every step looks before it acts, and the migration can be
run again after a failure part-way without wedging a restart. The fill sets each row
outright, so running it twice gives the same answer.

Revision ID: 0051_a_surveys_board_tests
Revises: 0050_what_a_survey_corrected
Create Date: 2026-11-25
"""

import json
import re

import sqlalchemy as sa
from alembic import op

revision = "0051_a_surveys_board_tests"
down_revision = "0050_what_a_survey_corrected"
branch_labels = None
depends_on = None

# tinydiag's tests of the board and its memory, as surveys.BOARD_TESTS has them.
BOARD_TESTS = ("TICK", "CPU", "FPU", "ROM", "PIT", "DMA", "PIC", "NMI", "RTC", "RAM", "RAMSYS")
MEMORY_TESTS = ("RAM", "RAMSYS")
HMA_KB = 64
_REACHED = re.compile(r"\b(\d+)K XMS\b")


def _columns(table):
    return {c["name"] for c in sa.inspect(op.get_bind()).get_columns(table)}


def _indexes(table):
    return {ix["name"] for ix in sa.inspect(op.get_bind()).get_indexes(table)}


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


def _board_result(keys):
    results = {name: (keys.get(f"TEST_{name}") or "").strip().upper() for name in BOARD_TESTS}
    if "FAIL" in results.values():
        return "FAIL"
    for name, result in results.items():
        if result != "PASS" and (result != "NA" or name in MEMORY_TESTS):
            return ""
    return "PASS" if _all_memory(keys) else ""


def _board(conn, machine, findings):
    if not machine:
        return None
    board = next((f for f in findings if isinstance(f, dict) and f.get("kind") == "board"), None)
    if board is not None:
        if board.get("answer") == "part" and board.get("part"):
            return str(board["part"]).upper()[:16]
        if board.get("answer") == "machine":
            return machine
        return None
    # A report that said nothing of its board: the board surveyed on its own, or the
    # one fitted in the machine.
    own = conn.execute(
        sa.text("SELECT type FROM parts WHERE asset_id = :tag"), {"tag": machine}
    ).first()
    if own is not None:
        return machine if own[0] == "motherboard" else None
    fitted = conn.execute(
        sa.text(
            "SELECT p.asset_id FROM register r JOIN parts p ON p.asset_id = r.asset_id "
            "WHERE r.inside_id = :tag AND p.type = 'motherboard' ORDER BY p.asset_id"
        ),
        {"tag": machine},
    ).first()
    return fitted[0] if fitted is not None else None


def _loads(text):
    try:
        value = json.loads(text or "")
    except ValueError:
        return None
    return value


def upgrade():
    if "board" not in _columns("surveys"):
        op.add_column("surveys", sa.Column("board", sa.String(length=16), nullable=True))
    if "ix_surveys_board" not in _indexes("surveys"):
        op.create_index("ix_surveys_board", "surveys", ["board"])
    if "board_result" not in _columns("surveys"):
        op.add_column(
            "surveys",
            sa.Column("board_result", sa.String(length=8), nullable=False, server_default=""),
        )

    conn = op.get_bind()
    rows = conn.execute(sa.text("SELECT id, machine, `keys`, findings FROM surveys")).all()
    for sid, machine, keys_text, findings_text in rows:
        keys = _loads(keys_text)
        findings = _loads(findings_text)
        keys = keys if isinstance(keys, dict) else {}
        findings = findings if isinstance(findings, list) else []
        conn.execute(
            sa.text("UPDATE surveys SET board = :board, board_result = :result WHERE id = :id"),
            {
                "board": _board(conn, machine, findings),
                "result": _board_result({str(k): str(v) for k, v in keys.items()}),
                "id": sid,
            },
        )


def downgrade():
    if "board_result" in _columns("surveys"):
        op.drop_column("surveys", "board_result")
    if "ix_surveys_board" in _indexes("surveys"):
        op.drop_index("ix_surveys_board", table_name="surveys")
    if "board" in _columns("surveys"):
        op.drop_column("surveys", "board")
