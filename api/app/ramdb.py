"""Map a computer's fitted memory between its child tables and plain counts.

The same split as specstruct/specdb, for the other half of the schema: entry owns
the pure rendering, this module owns the database. The module and chip rows are
the source of truth; computers.installed_ram is a rendered cache of them, kept for
display, the search index, labels and the REST/MCP wire format.

    write(db, computer, modules, chips, note)   counts -> rows, total and string
    read(db, computer)                          rows -> (modules, chips)

Modules are keyed by their slug from entry.RAM_MODULES rather than their display
label. The label used to be the key -- installed_ram was parsed back with a regex
built from it -- so renaming one orphaned every machine that had that module
fitted, silently.
"""

from __future__ import annotations

from collections.abc import Sequence
from enum import Enum, auto

from sqlalchemy.orm import Session

from . import entry
from .models import Computer, ComputerRamChip, ComputerRamModule


class _Keep(Enum):
    """The sentinel's own type, so "leave it as it is" is a value a signature can
    name rather than one only the body can recognise."""

    TOKEN = auto()


# Default for write()'s total_kb: "leave it as it is", so that passing None can
# mean "clear it" -- a caller replacing the whole field must be able to.
KEEP = _Keep.TOKEN

# How many of one module or chip are fitted, and a machine's worth of them: the
# pairs the tables store, read() hands back and write() is given.
Count = tuple[str, int | None]
Counts = list[Count]


def read(db: Session, computer: Computer) -> tuple[Counts, Counts]:
    """A machine's fitted memory as ([(slug, n)], [(chip, n)]), in entry order."""
    aid = computer.asset_id
    mods = (
        db.query(ComputerRamModule)
        .filter(ComputerRamModule.computer_id == aid)
        .order_by(ComputerRamModule.id)
        .all()
    )
    chips = (
        db.query(ComputerRamChip)
        .filter(ComputerRamChip.computer_id == aid)
        .order_by(ComputerRamChip.id)
        .all()
    )
    return ([(r.module, r.count) for r in mods], [(r.chip, r.count) for r in chips])


def write(
    db: Session,
    computer: Computer,
    modules: Sequence[Count] | None = None,
    chips: Sequence[Count] | None = None,
    note: str | None = None,
    total_kb: int | _Keep | None = KEEP,
) -> None:
    """Store a machine's memory and refresh the derived column and string.

    modules / chips are [(key, count)]; passing None leaves those rows alone, so a
    caller that only knows the total does not wipe a breakdown. The total is
    computed from the rows whenever there are any, and otherwise taken from
    total_kb -- which is applied even when it is None, so replacing a machine's
    RAM with a note clears the stale figure. The computer must already be flushed
    so its asset_id exists for the foreign key.
    """
    aid = computer.asset_id
    if modules is not None:
        db.query(ComputerRamModule).filter(ComputerRamModule.computer_id == aid).delete(
            synchronize_session=False
        )
        for slug, n in modules:
            if n:
                db.add(ComputerRamModule(computer_id=aid, module=slug, count=n))
    if chips is not None:
        db.query(ComputerRamChip).filter(ComputerRamChip.computer_id == aid).delete(
            synchronize_session=False
        )
        for pn, n in chips:
            if n:
                db.add(ComputerRamChip(computer_id=aid, chip=pn, count=n))
    db.flush()

    if note is not None:
        computer.installed_ram_note = note
    mods, chps = read(db, computer)
    computed = entry.ram_total_kb(mods, chps)
    if computed:
        computer.installed_ram_kb = computed
    elif total_kb is not KEEP:
        computer.installed_ram_kb = total_kb or None
    computer.installed_ram = entry.render_installed_ram(
        mods, chps, computer.installed_ram_kb, computer.installed_ram_note or ""
    )


def from_string(text: str | None) -> tuple[int | None, str]:
    """A plain installed-RAM string as (total_kb, note): a bare amount is the
    total, anything else is kept verbatim. This is the REST/MCP path, where a
    caller sends '640KB' rather than a module breakdown -- the breakdown has its
    own grids in the GUI."""
    text = (text or "").strip()
    if not text:
        return None, ""
    kb = entry.to_kb(text)
    return (kb, "") if kb is not None else (None, text)
