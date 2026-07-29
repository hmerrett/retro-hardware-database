"""store spec quantities as numbers instead of text

Capacity/Cache/Speed/FSB were String columns holding '840MB', '256KB', '25 MHz',
so they could not be sorted or range-filtered -- the whole point of the typed
tables. Each becomes an integer in a fixed small unit named by the new column
(_kb, _khz, _ns, _rpm); specstruct renders them back to friendly units.

A value that will not parse as a number is preserved verbatim as a part_attribute
row rather than being dropped, which is what happens to the two in the live data:
motherboard RH-0076 'Cache: Fake' and storage RH-0246 'Capacity: 20MB (36MB?!)'.

Self-contained by design: no app imports. Migration 0002 imported app.models and
broke the moment 0003 added a column, so this one carries its own parsing.

Revision ID: 0005_numeric_spec_values
Revises: 0004_log_entry
Create Date: 2026-07-29
"""
import re

from alembic import op
import sqlalchemy as sa

revision = "0005_numeric_spec_values"
down_revision = "0004_log_entry"
branch_labels = None
depends_on = None

# (table, old text column, new numeric column, unit, spec key for fallbacks)
COLUMNS = [
    ("motherboard_spec", "cache", "cache_kb", "kb", "Cache"),
    ("cpu_spec", "speed", "speed_khz", "khz", "Speed"),
    ("cpu_spec", "fsb", "fsb_khz", "khz", "FSB"),
    ("cpu_spec", "cache", "cache_kb", "kb", "Cache"),
    ("ram_spec", "speed", "speed_ns", "ns", "Speed"),
    ("storage_spec", "capacity", "capacity_kb", "kb_mb", "Capacity"),
    ("storage_spec", "speed", "speed_rpm", "rpm", "Speed"),
]

_KB_RE = re.compile(r"^\s*([\d.]+)\s*([kKmMgG]?)[bB]?\s*$")
_MHZ_RE = re.compile(r"^\s*([\d.]+)\s*(?:mhz)?\s*$", re.I)
_PLAIN_RE = re.compile(r"^\s*(\d+)\s*(?:ns|rpm)?\s*$", re.I)


def _to_kb(text, bare):
    m = _KB_RE.match(text or "")
    if not m:
        return None
    mult = {"k": 1, "m": 1024, "g": 1024 * 1024}.get(m.group(2).lower(), bare)
    try:
        return int(round(float(m.group(1)) * mult))
    except ValueError:
        return None


def _parse(unit, text):
    if unit == "kb":
        return _to_kb(text, 1)
    if unit == "kb_mb":          # a unitless drive capacity means MB
        return _to_kb(text, 1024)
    if unit == "khz":
        m = _MHZ_RE.match(text or "")
        try:
            return int(round(float(m.group(1)) * 1000)) if m else None
        except ValueError:
            return None
    m = _PLAIN_RE.match(text or "")
    return int(m.group(1)) if m else None


def upgrade():
    bind = op.get_bind()
    attr = sa.table("part_attribute", sa.column("part_id"), sa.column("akey"),
                    sa.column("avalue"))
    for table, old, new, unit, key in COLUMNS:
        op.add_column(table, sa.Column(new, sa.Integer(), nullable=True))
        rows = bind.execute(sa.text(
            f"SELECT part_id, `{old}` FROM {table} "
            f"WHERE `{old}` IS NOT NULL AND `{old}` <> ''")).all()
        for part_id, raw in rows:
            n = _parse(unit, raw)
            if n is None:
                bind.execute(attr.insert().values(
                    part_id=part_id, akey=key, avalue=raw))
            else:
                bind.execute(
                    sa.text(f"UPDATE {table} SET `{new}` = :n WHERE part_id = :p"),
                    {"n": n, "p": part_id})
        op.drop_column(table, old)


def _as_text(unit, n):
    """Render a stored number back to text without losing its value, so a
    downgrade followed by an upgrade is a round trip. Only the original spelling
    ('840MB' vs '840 MB') is not recoverable -- the quantity always is, which is
    why a capacity that is not a whole MB/GB goes back as KB rather than being
    rounded."""
    if unit == "kb":
        return f"{n} KB"
    if unit == "kb_mb":
        if n >= 1024 * 1024 and n % (1024 * 1024) == 0:
            return f"{n // (1024 * 1024)} GB"
        if n % 1024 == 0:
            return f"{n // 1024} MB"
        return f"{n} KB"
    if unit == "khz":
        return f"{n / 1000:g} MHz"
    return f"{n} {unit}"


def downgrade():
    bind = op.get_bind()
    for table, old, new, unit, _key in COLUMNS:
        op.add_column(table, sa.Column(old, sa.String(64), nullable=True))
        rows = bind.execute(sa.text(
            f"SELECT part_id, `{new}` FROM {table} WHERE `{new}` IS NOT NULL")).all()
        for part_id, n in rows:
            bind.execute(
                sa.text(f"UPDATE {table} SET `{old}` = :v WHERE part_id = :p"),
                {"v": _as_text(unit, n), "p": part_id})
        op.drop_column(table, new)
