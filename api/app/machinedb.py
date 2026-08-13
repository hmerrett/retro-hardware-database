"""Map a machine's catalogue identity between its rows and plain values.

The same split as specstruct/specdb, entry/ramdb and drivedb: machines owns the
catalogue and the rendering, this module owns the database. The computer_variant
row and the computer_chip rows are the source of truth; computers.variant is a
rendered cache of them, kept for the machine page, the label, the search index and
the REST/MCP wire format.

    write(db, computer, model_key=..., chips=...)   values -> rows, and the string
    read(db, computer)                              rows -> values
    clear(db, computer)                             forget the catalogue entirely
    refresh(db, computer)                           re-render the string alone

Passing None for any field leaves it as it is, the convention ramdb and drivedb
already use: a caller that knows only the board issue must not wipe the chips.

Nothing here parses computers.variant back into rows. That is the mistake migration
0011 was written to undo -- the display string had become the storage, so renaming a
label silently orphaned records -- and the reason the rows hold stable slugs and the
string is written one way only.
"""
from __future__ import annotations

from . import machines
from .models import ComputerChip, ComputerVariant

# What read() gives for a machine the catalogue knows nothing about, so callers can
# treat "no catalogue row" and "a row saying nothing" alike.
BLANK = {"model_key": "", "issue": "", "style": "", "region": "", "chips": {},
         "sockets": {}}


def read(db, computer):
    """A machine's catalogue identity as a dict: the model key, the board issue,
    the style, the region, {role: variant} for the chips in catalogue order, and
    {role: bool} for the ones whose mounting has been looked at -- a socket a
    person has not answered for is absent rather than false."""
    row = db.get(ComputerVariant, computer.asset_id)
    chips = (db.query(ComputerChip)
             .filter(ComputerChip.computer_id == computer.asset_id)
             .order_by(ComputerChip.id).all())
    if row is None and not chips:
        return dict(BLANK)
    key = row.model_key if row else ""
    ordered = machines.in_role_order(key, [(c.role, c.variant) for c in chips])
    held = {c.role: c.socketed for c in chips if c.variant}
    return {"model_key": key,
            "issue": (row.issue if row else "") or "",
            "style": (row.style if row else "") or "",
            "region": (row.region if row else "") or "",
            "chips": {role: variant for role, variant in ordered if variant},
            "sockets": {role: bool(held[role]) for role, _v in ordered
                        if held.get(role) is not None}}


def read_many(db, computers):
    """{asset_id: identity} for a whole list of machines in two queries, so a list
    page or the API's list endpoint does not fall into a query per row -- the same
    reason specdb has its bulk lookups. Machines with no catalogue row are absent
    rather than blank, so a caller can tell "not a catalogue machine" from "a
    catalogue machine nothing is known about"."""
    ids = [c.asset_id for c in computers]
    if not ids:
        return {}
    out = {}
    for row in (db.query(ComputerVariant)
                .filter(ComputerVariant.computer_id.in_(ids)).all()):
        out[row.computer_id] = {"model_key": row.model_key or "",
                                "issue": row.issue or "", "style": row.style or "",
                                "region": row.region or "", "chips": {},
                                "sockets": {}}
    for row in (db.query(ComputerChip)
                .filter(ComputerChip.computer_id.in_(ids))
                .order_by(ComputerChip.id).all()):
        if row.variant:
            out.setdefault(row.computer_id,
                           dict(BLANK) | {"chips": {}, "sockets": {}})
            out[row.computer_id]["chips"][row.role] = row.variant
            if row.socketed is not None:
                out[row.computer_id]["sockets"][row.role] = bool(row.socketed)
    for identity in out.values():
        identity["chips"] = dict(machines.in_role_order(identity["model_key"],
                                                        identity["chips"]))
    return out


def recorded(db):
    """Every answer already given to a catalogue question, keyed by model:
    {model_key: {"issues": [...], "styles": [...], "regions": [...],
                 "chips": {role: [...]}}}.

    What this is for is the picker: machines.with_recorded folds it into the lists
    the form offers, so a ULA nobody had heard of when the catalogue was written is
    a radio button once one machine records it. Two queries, both distinct, because
    this is read on every edit form.

    Keyed by the model the machine is filed as now -- a chip is only evidence about
    the model it was found in.
    """
    out = {}

    def bucket(key):
        return out.setdefault(key, {"issues": [], "styles": [], "regions": [],
                                    "chips": {}})

    variants = (db.query(ComputerVariant.model_key, ComputerVariant.issue,
                         ComputerVariant.style, ComputerVariant.region)
                .filter(ComputerVariant.model_key != "").distinct().all())
    for key, issue, style, region in variants:
        got = bucket(key)
        for field, value in (("issues", issue), ("styles", style),
                             ("regions", region)):
            if (value or "").strip():
                got[field].append(value.strip())
    chips = (db.query(ComputerVariant.model_key, ComputerChip.role,
                      ComputerChip.variant)
             .join(ComputerChip,
                   ComputerChip.computer_id == ComputerVariant.computer_id)
             .filter(ComputerVariant.model_key != "").distinct().all())
    for key, role, variant in chips:
        if (variant or "").strip():
            bucket(key)["chips"].setdefault(role, []).append(variant.strip())
    return out


def write(db, computer, model_key=None, issue=None, style=None, region=None,
          chips=None, sockets=None):
    """Store what is known about a machine's catalogue identity and re-render the
    cache. The computer must already be flushed so its asset_id exists for the
    foreign key.

    Clearing the model clears everything: a machine that is no longer filed as a
    Spectrum has no Spectrum board issue and no Spectrum ULA, and leaving those
    behind would leave a record that reads as a machine nobody owns. Changing the
    model from one to another drops the chips whose sockets the new model does not
    have, for the same reason, and keeps the rest -- a C64 refiled as a C64C still
    has the SID it had.
    """
    if model_key is not None and not (model_key or "").strip():
        clear(db, computer)
        return
    aid = computer.asset_id
    row = db.get(ComputerVariant, aid)
    if row is None:
        row = ComputerVariant(computer_id=aid)
        db.add(row)
    for field, value in (("model_key", model_key), ("issue", issue),
                         ("style", style), ("region", region)):
        if value is not None:
            setattr(row, field, (value or "").strip())
    if chips is not None:
        # The rows are rewritten wholesale, so whether each chip is socketed has to
        # survive the rewrite: an answer in this call wins, and a socket this call
        # says nothing about keeps the answer it already had rather than going back
        # to "nobody has looked".
        was = {c.role: c.socketed for c in db.query(ComputerChip).filter(
            ComputerChip.computer_id == aid).all()}
        db.query(ComputerChip).filter(
            ComputerChip.computer_id == aid).delete(synchronize_session=False)
        given = _flags(sockets)
        for role, variant in _pairs(chips):
            if variant:
                held = given[role] if role in given else was.get(role)
                db.add(ComputerChip(computer_id=aid, role=role, variant=variant,
                                    socketed=held))
    elif sockets is not None:
        # Told only how the chips are held, which is an answer of its own: the
        # variants stay exactly as they are.
        given = _flags(sockets)
        for row in db.query(ComputerChip).filter(
                ComputerChip.computer_id == aid).all():
            if row.role in given:
                row.socketed = given[row.role]
    db.flush()
    if model_key is not None:
        _drop_foreign_chips(db, aid, row.model_key)
    refresh(db, computer)


def clear(db, computer):
    """Forget that a machine was ever a catalogue model: the row, its chips and the
    rendered string."""
    aid = computer.asset_id
    for model in (ComputerChip, ComputerVariant):
        db.query(model).filter(
            model.computer_id == aid).delete(synchronize_session=False)
    db.flush()
    computer.variant = ""


def refresh(db, computer):
    """Re-render computers.variant from the rows behind it. Called on every write,
    and by app.resync when the catalogue's own words have changed underneath a
    machine that has not been edited since."""
    v = read(db, computer)
    computer.variant = machines.render(v["model_key"], v["issue"], v["style"],
                                       v["region"], v["chips"])
    return computer.variant


def _flags(sockets):
    """{role: True/False/None} from a dict or pairs. None is kept and means nobody
    has looked, which is not the same answer as soldered -- so it is stored rather
    than folded into False."""
    if sockets is None:
        return {}
    items = sockets.items() if isinstance(sockets, dict) else sockets
    return {(role or "").strip(): (None if held is None else bool(held))
            for role, held in items}


def _pairs(chips):
    """(role, variant) pairs from a dict or an iterable of pairs, both stripped.
    A blank variant is how a socket is cleared, so it is kept here and dropped by
    the caller rather than being quietly turned into a row."""
    items = chips.items() if isinstance(chips, dict) else chips
    return [((role or "").strip(), (variant or "").strip())
            for role, variant in items]


def _drop_foreign_chips(db, aid, model_key):
    """Delete the chip rows whose socket the machine's model does not have."""
    keep = set(machines.roles(model_key))
    rows = db.query(ComputerChip).filter(ComputerChip.computer_id == aid).all()
    for row in rows:
        if row.role not in keep:
            db.delete(row)
    db.flush()


def duplicated_from(db, src, dest):
    """Give a duplicate of a machine the model its original is filed as, and
    nothing else.

    A second machine of the same model is the same model -- that is what the
    duplicate button means -- but the board issue, the style and the chips in it are
    this machine's own, found by opening this machine. Copying them across would
    write down a ULA nobody has looked at.
    """
    key = read(db, src)["model_key"]
    if key:
        write(db, dest, model_key=key)
