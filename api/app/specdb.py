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

from . import specstruct
from .models import (CpuSpec, IoSpec, MotherboardSpec, NetworkSpec,
                     PartAttribute, PartPort, PartRamSlot, PartSlot, RamSpec,
                     SoundSpec, StorageSpec, VideoSpec)

# Which typed spec table backs each part type.
SPEC_MODEL = {
    "motherboard": MotherboardSpec, "cpu": CpuSpec, "ram": RamSpec,
    "video": VideoSpec, "sound": SoundSpec, "network": NetworkSpec,
    "io": IoSpec, "storage": StorageSpec,
}
SPEC_TABLES = [*list(SPEC_MODEL.values()), PartSlot, PartRamSlot, PartPort, PartAttribute]

# CHS lives in three columns but travels as one tuple on the Struct.
_CHS_COLS = ("chs_c", "chs_h", "chs_s")

# (model, attribute holding the value, Struct list) for the count-list children.
_LIST_TABLES = ((PartSlot, "bus", "slots"),
                (PartRamSlot, "slot_type", "ram_slots"),
                (PartPort, "port", "ports"))


def write(db, part):
    """Keep the typed tables in step with a part's specs string, and canonicalise
    the string itself. Called on every part create/update; the part must already
    be flushed so its asset_id exists for the foreign key."""
    ptype = part.type or "other"
    st = specstruct.parse(ptype, part.specs or "")
    part.specs = specstruct.format(ptype, st)
    aid = part.asset_id
    for model in SPEC_TABLES:
        db.query(model).filter(model.part_id == aid).delete(synchronize_session=False)
    model = SPEC_MODEL.get(ptype)
    if model:
        cols = dict(st.scalars)
        if ptype == "storage" and st.chs:
            cols["chs_c"], cols["chs_h"], cols["chs_s"] = st.chs
        db.add(model(part_id=aid, **cols))
    for model, attr, listname in _LIST_TABLES:
        for value, n in getattr(st, listname):
            db.add(model(part_id=aid, **{attr: value}, count=n))
    for k, v in st.attributes:
        db.add(PartAttribute(part_id=aid, akey=k or "", avalue=v))


def read(db, part) -> specstruct.Struct:
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
            if all(st.scalars.get(c) is not None for c in _CHS_COLS):
                st.chs = tuple(st.scalars[c] for c in _CHS_COLS)
            for c in _CHS_COLS:
                st.scalars.pop(c, None)
    for child, attr, listname in _LIST_TABLES:
        rows = (db.query(child).filter(child.part_id == aid)
                .order_by(child.id).all())
        setattr(st, listname, [(getattr(r, attr), r.count) for r in rows])
    st.attributes = [(r.akey, r.avalue) for r in
                     db.query(PartAttribute).filter(PartAttribute.part_id == aid)
                     .order_by(PartAttribute.id).all()]
    return st


def pairs(db, part):
    """Ordered (display key, rendered value) pairs for a part's spec table."""
    return specstruct.pairs(part.type or "other", read(db, part))


def scalars(db, part) -> dict:
    """A part's typed scalar spec columns, keyed by column name."""
    return read(db, part).scalars


# --- bulk lookups (constant queries, for list pages) -----------------------

def column_by_part(db, model, column) -> dict:
    """{part_id: value} for one typed column across every part, in one query --
    so a list page does not fall into a query per row."""
    return dict(db.query(model.part_id, column).filter(column.isnot(None)).all())


def storage_kinds(db) -> dict:
    """{part_id: Kind} for storage parts, for placeholder-icon routing."""
    return column_by_part(db, StorageSpec, StorageSpec.kind)


def form_factors(db) -> dict:
    """{part_id: Form factor} for motherboards."""
    return column_by_part(db, MotherboardSpec, MotherboardSpec.form_factor)
