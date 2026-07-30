"""a machine's fitted memory as rows instead of a parsed string

installed_ram was both the display string and the storage: the form's module and
chip grids were rendered into it on save and regex'd back out of it on edit. The
module patterns were built from the *display labels*, so renaming "1MB 30-pin"
would have silently orphaned every machine that had one fitted.

The counts now live in computer_ram_module / computer_ram_chip keyed by stable
slugs and part numbers, with installed_ram_kb holding the usable total (a bank of
nine ×1 chips counted as eight of data plus parity) and installed_ram left as the
rendered cache. Anything that is neither a breakdown nor a plain amount goes to
installed_ram_note verbatim.

This parses the existing strings one last time to seed the rows -- the same regex
work the app is losing, kept here where it runs once. Six machines hold a
breakdown, five a bare total, three nothing.

Revision ID: 0011_computer_memory
Revises: 0010_tidy_spec_values
Create Date: 2026-07-30
"""
import re

from alembic import op
import sqlalchemy as sa

revision = "0011_computer_memory"
down_revision = "0010_tidy_spec_values"
branch_labels = None
depends_on = None

# (slug, KB, label) and (part number, KB, organisation), as entry.py has them.
MODULES = [("30p256k", 256, "256KB 30-pin"), ("30p1m", 1024, "1MB 30-pin"),
           ("30p4m", 4096, "4MB 30-pin"), ("sipp256k", 256, "256KB SIPP"),
           ("sipp1m", 1024, "1MB SIPP"), ("sipp4m", 4096, "4MB SIPP"),
           ("72p1m", 1024, "1MB 72-pin"), ("72p2m", 2048, "2MB 72-pin"),
           ("72p4m", 4096, "4MB 72-pin"), ("72p8m", 8192, "8MB 72-pin"),
           ("72p16m", 16384, "16MB 72-pin"), ("72p32m", 32768, "32MB 72-pin")]
CHIPS = {"4116": (2, 1), "4164": (8, 1), "4416": (8, 4), "4464": (32, 4),
         "41256": (32, 1), "44256": (128, 4), "411000": (128, 1),
         "514256": (128, 4)}

_AMOUNT = re.compile(r"^\s*([\d.]+)\s*([kKmMgG]?)[bB]?\s*$")
_UNIT = {"k": 1, "": 1024, "m": 1024, "g": 1024 * 1024}


def _to_kb(text):
    m = _AMOUNT.match(text or "")
    if not m:
        return None
    return int(round(float(m.group(1)) * _UNIT[m.group(2).lower()]))


def _split(text):
    """One installed_ram string -> ({slug: n}, {chip: n}, total_kb, note)."""
    mods, chips, note_bits, total = {}, {}, [], None
    for seg in (text or "").split(";"):
        seg = seg.strip()
        if not seg:
            continue
        hit = False
        for slug, _kb, label in MODULES:
            m = re.search(r"(\d+)\s*[×x]\s*" + re.escape(label) + r"(?![\w-])", seg)
            if m:
                mods[slug] = mods.get(slug, 0) + int(m.group(1))
                hit = True
        for m in re.finditer(r"(\d+)\s*[×x]\s*(\d{4,6})", seg):
            if m.group(2) in CHIPS:
                chips[m.group(2)] = chips.get(m.group(2), 0) + int(m.group(1))
                hit = True
        if hit:
            continue
        # Not a breakdown: a bare amount is the total, anything else is a note.
        kb = _to_kb(seg)
        if kb is not None and total is None:
            total = kb
        else:
            note_bits.append(seg)
    return mods, chips, total, "; ".join(note_bits)


def _usable_kb(mods, chips):
    total = sum(n * kb for slug, kb, _ in MODULES for s, n in mods.items() if s == slug)
    for pn, n in chips.items():
        kb, width = CHIPS[pn]
        total += (n // 9) * 8 * kb if width == 1 and n % 9 == 0 else n * kb
    return total


def _render(mods, chips, total_kb, note):
    def amount(kb):
        return f"{kb // 1024} MB" if kb and kb % 1024 == 0 else f"{kb} KB"
    out = []
    label = {s: lbl for s, _kb, lbl in MODULES}
    order = [s for s, _kb, _l in MODULES]
    if mods:
        items = sorted(mods.items(), key=lambda kv: order.index(kv[0]))
        kb = _usable_kb(mods, {})
        out.append(", ".join(f"{n}× {label[s]}" for s, n in items) + f" ({amount(kb)})")
    if chips:
        kb = _usable_kb({}, chips)
        parity = any(CHIPS[pn][1] == 1 and n % 9 == 0 for pn, n in chips.items())
        out.append(", ".join(f"{n}× {pn}" for pn, n in chips.items())
                   + f" ({amount(kb)}{' + parity' if parity else ''})")
    if not out and total_kb:
        out.append(amount(total_kb))
    if note:
        out.append(note)
    return "; ".join(out)


def upgrade():
    op.create_table(
        "computer_ram_module",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column("computer_id", sa.String(16), nullable=False),
        sa.Column("module", sa.String(32), nullable=False),
        sa.Column("count", sa.Integer()),
        sa.ForeignKeyConstraint(["computer_id"], ["computers.asset_id"],
                                ondelete="CASCADE"),
    )
    op.create_index("ix_computer_ram_module_computer_id", "computer_ram_module",
                    ["computer_id"])
    op.create_table(
        "computer_ram_chip",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column("computer_id", sa.String(16), nullable=False),
        sa.Column("chip", sa.String(32), nullable=False),
        sa.Column("count", sa.Integer()),
        sa.ForeignKeyConstraint(["computer_id"], ["computers.asset_id"],
                                ondelete="CASCADE"),
    )
    op.create_index("ix_computer_ram_chip_computer_id", "computer_ram_chip",
                    ["computer_id"])
    op.add_column("computers", sa.Column("installed_ram_kb", sa.Integer(),
                                         nullable=True))
    op.add_column("computers", sa.Column("installed_ram_note", sa.String(255),
                                         nullable=False, server_default=""))

    conn = op.get_bind()
    rows = conn.execute(sa.text(
        "SELECT asset_id, installed_ram FROM computers")).fetchall()
    for aid, text in rows:
        mods, chips, total, note = _split(text or "")
        for slug, n in mods.items():
            conn.execute(sa.text(
                "INSERT INTO computer_ram_module (computer_id, module, count) "
                "VALUES (:a, :m, :n)"), {"a": aid, "m": slug, "n": n})
        for pn, n in chips.items():
            conn.execute(sa.text(
                "INSERT INTO computer_ram_chip (computer_id, chip, count) "
                "VALUES (:a, :c, :n)"), {"a": aid, "c": pn, "n": n})
        usable = _usable_kb(mods, chips) or total
        conn.execute(sa.text(
            "UPDATE computers SET installed_ram_kb = :kb, installed_ram_note = :note, "
            "installed_ram = :rendered WHERE asset_id = :a"),
            {"kb": usable, "note": note, "a": aid,
             "rendered": _render(mods, chips, usable, note)})


def downgrade():
    op.drop_column("computers", "installed_ram_note")
    op.drop_column("computers", "installed_ram_kb")
    op.drop_table("computer_ram_chip")
    op.drop_table("computer_ram_module")
