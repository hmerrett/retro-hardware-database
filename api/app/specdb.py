"""Map a part's structured specs between the typed tables and a specstruct.Struct.

specstruct owns the pure string <-> Struct conversion; this module owns
Struct <-> database. Together they make the typed tables the read path for
structured spec data (form grids, label fields, the spec table on an item page),
with parts.specs kept in step as the rendered string used for display, free-text
search and the REST/MCP wire format.

    write(db, part)   parse part.specs -> typed rows, and canonicalise the string
    read(db, part)    typed rows -> Struct
    pairs(db, part)   typed rows -> ordered (key, value) pairs for display
"""

from __future__ import annotations

from typing import cast

from sqlalchemy.orm import InstrumentedAttribute, Session

from . import specstruct
from .models import (
    CpuSpec,
    DisplaySpec,
    IoSpec,
    MotherboardSpec,
    NetworkSpec,
    Part,
    PartAttribute,
    PartPort,
    PartRamSlot,
    PartSlot,
    RamSpec,
    SoundSpec,
    StorageSpec,
    VideoSpec,
)

# The one-row-per-part tables, and those plus the children a part can have many
# of: named as types so that what every one of them has in common -- a part_id --
# is something a reader and a type checker can both see.
type ScalarSpec = (
    MotherboardSpec
    | CpuSpec
    | RamSpec
    | VideoSpec
    | SoundSpec
    | NetworkSpec
    | IoSpec
    | StorageSpec
    | DisplaySpec
)
type SpecTable = ScalarSpec | PartSlot | PartRamSlot | PartPort | PartAttribute
type CountedTable = PartSlot | PartRamSlot | PartPort

# Which typed spec table backs each part type.
SPEC_MODEL: dict[str, type[ScalarSpec]] = {
    "motherboard": MotherboardSpec,
    "cpu": CpuSpec,
    "ram": RamSpec,
    "video": VideoSpec,
    "sound": SoundSpec,
    "network": NetworkSpec,
    "io": IoSpec,
    "storage": StorageSpec,
    "display": DisplaySpec,
}
SPEC_TABLES: list[type[SpecTable]] = [
    *list(SPEC_MODEL.values()),
    PartSlot,
    PartRamSlot,
    PartPort,
    PartAttribute,
]

# CHS lives in three columns but travels as one tuple on the Struct.
_CHS_COLS = ("chs_c", "chs_h", "chs_s")

# (model, attribute holding the value, Struct list) for the count-list children.
_LIST_TABLES = (
    (PartSlot, "bus", "slots"),
    (PartRamSlot, "slot_type", "ram_slots"),
    (PartPort, "port", "ports"),
)


def write(db: Session, part: Part) -> None:
    """Keep the typed tables in step with a part's specs string, and canonicalise
    the string itself. Called on every part create/update; the part must already
    be flushed so its asset_id exists for the foreign key."""
    ptype = part.type or "other"
    st = specstruct.parse(ptype, part.specs or "")
    part.specs = specstruct.format(ptype, st)
    aid = part.asset_id
    for table in SPEC_TABLES:
        db.query(table).filter(table.part_id == aid).delete(synchronize_session=False)
    model = SPEC_MODEL.get(ptype)
    if model:
        cols = dict(st.scalars)
        if ptype == "storage" and st.chs:
            cols["chs_c"], cols["chs_h"], cols["chs_s"] = st.chs
        db.add(model(part_id=aid, **cols))
    for child, attr, listname in _LIST_TABLES:
        for value, n in getattr(st, listname):
            db.add(child(part_id=aid, **{attr: value}, count=n))
    for k, v in st.attributes:
        db.add(PartAttribute(part_id=aid, akey=k or "", avalue=v))


def read(db: Session, part: Part) -> specstruct.Struct:
    """A part's structured specs from the typed tables -- the inverse of write().

    Children are ordered by insertion (id) so slots and ports keep the order they
    were entered in, matching what write() stored.
    """
    st = specstruct.Struct()
    aid = part.asset_id
    ptype = part.type or "other"
    model = SPEC_MODEL.get(ptype)
    if model:
        row = db.get(model, aid)
        if row is not None:
            for col in model.__table__.columns:
                if col.name == "part_id":
                    continue
                value = getattr(row, col.name)
                if value not in (None, ""):
                    st.scalars[col.name] = value
            c, h, s = (st.scalars.get(name) for name in _CHS_COLS)
            if isinstance(c, int) and isinstance(h, int) and isinstance(s, int):
                st.chs = (c, h, s)
            for c in _CHS_COLS:
                st.scalars.pop(c, None)
    for child, attr, listname in _LIST_TABLES:
        # Queried with a class picked out of several, the rows come back typed as
        # the base the three share, which is not where `count` is declared.
        rows = cast(
            "list[CountedTable]",
            db.query(child).filter(child.part_id == aid).order_by(child.id).all(),
        )
        setattr(st, listname, [(getattr(r, attr), r.count) for r in rows])
    st.attributes = [
        (r.akey or "", r.avalue or "")
        for r in db.query(PartAttribute)
        .filter(PartAttribute.part_id == aid)
        .order_by(PartAttribute.id)
        .all()
    ]
    return st


def pairs(db: Session, part: Part, display: bool = False) -> list[tuple[str, str]]:
    """Ordered (display key, rendered value) pairs for a part's spec table.

    `display` on is for a page or a label; off gives the edit form and the stored
    specs string values that parse back to the same numbers."""
    return specstruct.pairs(part.type or "other", read(db, part), display)


def scalars(db: Session, part: Part) -> dict[str, str | int | None]:
    """A part's typed scalar spec columns, keyed by column name."""
    return read(db, part).scalars


# --- bulk lookups (constant queries, for list pages) -----------------------


def column_by_part(
    db: Session, model: type[ScalarSpec], column: InstrumentedAttribute[str | None]
) -> dict[str, str | None]:
    """{part_id: value} for one typed column across every part, in one query --
    so a list page does not fall into a query per row."""
    # .tuples() is for the type checker rather than the database: it says the rows
    # are the pairs dict() is being handed, and leaves the query itself alone.
    return dict(db.query(model.part_id, column).filter(column.isnot(None)).tuples().all())


def storage_kinds(db: Session) -> dict[str, str | None]:
    """{part_id: Kind} for storage parts, for placeholder-icon routing."""
    return column_by_part(db, StorageSpec, StorageSpec.kind)


def form_factors(db: Session) -> dict[str, str | None]:
    """{part_id: Form factor} for motherboards."""
    return column_by_part(db, MotherboardSpec, MotherboardSpec.form_factor)
