"""Map an asset's catalogue identity between its rows and plain values.

The same split as specstruct/specdb, entry/ramdb and drivedb: machines owns the
catalogue and the rendering, this module owns the database. The asset_variant row
and the asset_chip rows are the source of truth; the asset's own `variant` column
is a rendered cache of them, kept for the item page, the label, the search index
and the REST/MCP wire format.

    write(db, asset, model_key=..., chips=...)   values -> rows, and the string
    read(db, asset)                              rows -> values
    clear(db, asset)                             forget the catalogue entirely
    refresh(db, asset)                           re-render the string alone

`asset` is a computer or a part, and every function here takes either. That is the
whole of what the tables being keyed by a plain asset_id buys: a sealed Spectrum
and the Amiga 500 board on the shelf beside it are the same sort of answer to the
same question, so they are read and written by the same code rather than by two
copies of it that would drift. Both kinds of row carry a `variant` column for the
rendering to land in, which is why refresh() needs to know nothing about which it
has been handed.

What a part is asked is a subset: the model, the board issue and the chips. Style
and region are facts about an assembled machine in a case (see AssetVariant), so
nothing offers them for a board -- but nothing here refuses them either, because
the caller that knows which kind of asset it is holding is the one at the door.

Passing None for any field leaves it as it is, the convention ramdb and drivedb
already use: a caller that knows only the board issue must not wipe the chips.

Nothing here parses the rendered string back into rows. That is the mistake
migration 0011 was written to undo -- the display string had become the storage, so
renaming a label silently orphaned records -- and the reason the rows hold stable
slugs and the string is written one way only.
"""

from __future__ import annotations

from collections.abc import Iterable, Sequence
from typing import TypedDict

from sqlalchemy.orm import Session

from . import machines
from .models import AssetChip, AssetVariant, Computer, Part

# A catalogue question is asked of a machine or of the board out of one, and both
# answer it the same way -- which is what the tables being keyed by a plain asset
# id buys, and why nothing here needs to know which it has.
type Asset = Computer | Part
# What a caller may hand write() for the chips and their mountings: a mapping, or
# the pairs one would be built from.
type ChipsIn = dict[str, str] | Iterable[tuple[str, str]]
# Both dicts are named because a dict is invariant: what read() hands back holds
# no None, and has to be something write() will take.
type SocketsIn = dict[str, bool] | dict[str, bool | None] | Iterable[tuple[str, bool | None]]


class Identity(TypedDict):
    """What an asset says about its catalogue identity: the model it is filed as,
    the three variations a record holds, the chip in each socket, and which of those
    sockets somebody has looked at."""

    model_key: str
    issue: str
    style: str
    region: str
    chips: dict[str, str]
    sockets: dict[str, bool]


class Recorded(TypedDict, total=False):
    """Every answer one model has actually been given, which is what the catalogue's
    lists are extended with (machines.with_recorded).

    No key is required. recorded() fills all four, but what reads one takes a record
    that says nothing about styles as a model nobody has recorded a style for, and
    that is how a caller with one fact to state is able to state it."""

    issues: list[str]
    styles: list[str]
    regions: list[str]
    chips: dict[str, list[str]]


# What read() gives for an asset the catalogue knows nothing about, so callers can
# treat "no catalogue row" and "a row saying nothing" alike.
BLANK: Identity = {
    "model_key": "",
    "issue": "",
    "style": "",
    "region": "",
    "chips": {},
    "sockets": {},
}


def read(db: Session, asset: Asset) -> Identity:
    """An asset's catalogue identity as a dict: the model key, the board issue,
    the style, the region, {role: variant} for the chips in catalogue order, and
    {role: bool} for the ones whose mounting has been looked at -- a socket a
    person has not answered for is absent rather than false."""
    row = db.get(AssetVariant, asset.asset_id)
    chips = (
        db.query(AssetChip)
        .filter(AssetChip.asset_id == asset.asset_id)
        .order_by(AssetChip.id)
        .all()
    )
    if row is None and not chips:
        return BLANK.copy()
    key = row.model_key if row else ""
    ordered = machines.in_role_order(key, [(c.role, c.variant) for c in chips])
    held = {c.role: c.socketed for c in chips if c.variant}
    return {
        "model_key": key,
        "issue": (row.issue if row else "") or "",
        "style": (row.style if row else "") or "",
        "region": (row.region if row else "") or "",
        "chips": {role: variant for role, variant in ordered if variant},
        "sockets": {role: bool(held[role]) for role, _v in ordered if held.get(role) is not None},
    }


def read_many(db: Session, assets: Sequence[Asset]) -> dict[str, Identity]:
    """{asset_id: identity} for a whole list of assets in two queries, so a list
    page or the API's list endpoint does not fall into a query per row -- the same
    reason specdb has its bulk lookups. Assets with no catalogue row are absent
    rather than blank, so a caller can tell "not a catalogue machine" from "a
    catalogue machine nothing is known about"."""
    ids = [a.asset_id for a in assets]
    if not ids:
        return {}
    out: dict[str, Identity] = {}
    for row in db.query(AssetVariant).filter(AssetVariant.asset_id.in_(ids)).all():
        out[row.asset_id] = {
            "model_key": row.model_key or "",
            "issue": row.issue or "",
            "style": row.style or "",
            "region": row.region or "",
            "chips": {},
            "sockets": {},
        }
    for chip in (
        db.query(AssetChip).filter(AssetChip.asset_id.in_(ids)).order_by(AssetChip.id).all()
    ):
        if chip.variant:
            out.setdefault(chip.asset_id, BLANK | {"chips": {}, "sockets": {}})
            out[chip.asset_id]["chips"][chip.role] = chip.variant
            if chip.socketed is not None:
                out[chip.asset_id]["sockets"][chip.role] = bool(chip.socketed)
    for identity in out.values():
        identity["chips"] = dict(machines.in_role_order(identity["model_key"], identity["chips"]))
    return out


def recorded(db: Session) -> dict[str, Recorded]:
    """Every answer already given to a catalogue question, keyed by model:
    {model_key: {"issues": [...], "styles": [...], "regions": [...],
                 "chips": {role: [...]}}}.

    What this is for is the picker: machines.with_recorded folds it into the lists
    the form offers, so a ULA nobody had heard of when the catalogue was written is
    a radio button once one machine records it. Two queries, both distinct, because
    this is read on every edit form.

    Every asset teaches, machine and board alike. A Rev 6A read off a bare board is
    the same evidence about what Amiga 500 boards say as one read out of a whole
    Amiga -- it is the same board either way -- and which object it was found on is
    exactly what does not matter about it.

    Keyed by the model the asset is filed as now: a chip is only evidence about the
    model it was found in.
    """
    out: dict[str, Recorded] = {}

    def bucket(key: str) -> Recorded:
        return out.setdefault(key, {"issues": [], "styles": [], "regions": [], "chips": {}})

    variants = (
        db.query(
            AssetVariant.model_key, AssetVariant.issue, AssetVariant.style, AssetVariant.region
        )
        .filter(AssetVariant.model_key != "")
        .distinct()
        .all()
    )
    for key, issue, style, region in variants:
        got = bucket(key)
        for seen, value in (
            (got["issues"], issue),
            (got["styles"], style),
            (got["regions"], region),
        ):
            if (value or "").strip():
                seen.append(value.strip())
    chips = (
        db.query(AssetVariant.model_key, AssetChip.role, AssetChip.variant)
        .join(AssetChip, AssetChip.asset_id == AssetVariant.asset_id)
        .filter(AssetVariant.model_key != "")
        .distinct()
        .all()
    )
    for key, role, variant in chips:
        if (variant or "").strip():
            bucket(key)["chips"].setdefault(role, []).append(variant.strip())
    return out


def write(
    db: Session,
    asset: Asset,
    model_key: str | None = None,
    issue: str | None = None,
    style: str | None = None,
    region: str | None = None,
    chips: ChipsIn | None = None,
    sockets: SocketsIn | None = None,
) -> None:
    """Store what is known about an asset's catalogue identity and re-render the
    cache. The asset must already be flushed so its asset_id exists.

    Clearing the model clears everything: a machine that is no longer filed as a
    Spectrum has no Spectrum board issue and no Spectrum ULA, and leaving those
    behind would leave a record that reads as a machine nobody owns. Changing the
    model from one to another drops the chips whose sockets the new model does not
    have, for the same reason, and keeps the rest -- a C64 refiled as a C64C still
    has the SID it had.
    """
    if model_key is not None and not (model_key or "").strip():
        clear(db, asset)
        return
    aid = asset.asset_id
    row = db.get(AssetVariant, aid)
    if row is None:
        row = AssetVariant(asset_id=aid)
        db.add(row)
    for field, value in (
        ("model_key", model_key),
        ("issue", issue),
        ("style", style),
        ("region", region),
    ):
        if value is not None:
            setattr(row, field, (value or "").strip())
    if chips is not None:
        # The rows are rewritten wholesale, so whether each chip is socketed has to
        # survive the rewrite: an answer in this call wins, and a socket this call
        # says nothing about keeps the answer it already had rather than going back
        # to "nobody has looked".
        was = {
            c.role: c.socketed for c in db.query(AssetChip).filter(AssetChip.asset_id == aid).all()
        }
        db.query(AssetChip).filter(AssetChip.asset_id == aid).delete(synchronize_session=False)
        given = _flags(sockets)
        for role, variant in _pairs(chips):
            if variant:
                held = given[role] if role in given else was.get(role)
                db.add(AssetChip(asset_id=aid, role=role, variant=variant, socketed=held))
    elif sockets is not None:
        # Told only how the chips are held, which is an answer of its own: the
        # variants stay exactly as they are.
        given = _flags(sockets)
        for chip in db.query(AssetChip).filter(AssetChip.asset_id == aid).all():
            if chip.role in given:
                chip.socketed = given[chip.role]
    db.flush()
    if model_key is not None:
        _drop_foreign_chips(db, aid, row.model_key)
    refresh(db, asset)


def clear(db: Session, asset: Asset) -> None:
    """Forget that an asset was ever a catalogue model: the row, its chips and the
    rendered string."""
    aid = asset.asset_id
    table: type[AssetChip] | type[AssetVariant]
    for table in (AssetChip, AssetVariant):
        db.query(table).filter(table.asset_id == aid).delete(synchronize_session=False)
    db.flush()
    asset.variant = ""


def refresh(db: Session, asset: Asset) -> str:
    """Re-render the asset's variant string from the rows behind it. Called on every
    write, and by app.resync when the catalogue's own words have changed underneath
    something that has not been edited since."""
    v = read(db, asset)
    asset.variant = machines.render(v["model_key"], v["issue"], v["style"], v["region"], v["chips"])
    return asset.variant


def _flags(sockets: SocketsIn | None) -> dict[str, bool | None]:
    """{role: True/False/None} from a dict or pairs. None is kept and means nobody
    has looked, which is not the same answer as soldered -- so it is stored rather
    than folded into False."""
    if sockets is None:
        return {}
    items = sockets.items() if isinstance(sockets, dict) else sockets
    return {(role or "").strip(): (None if held is None else bool(held)) for role, held in items}


def _pairs(chips: ChipsIn) -> list[tuple[str, str]]:
    """(role, variant) pairs from a dict or an iterable of pairs, both stripped.
    A blank variant is how a socket is cleared, so it is kept here and dropped by
    the caller rather than being quietly turned into a row."""
    items = chips.items() if isinstance(chips, dict) else chips
    return [((role or "").strip(), (variant or "").strip()) for role, variant in items]


def _drop_foreign_chips(db: Session, aid: str, model_key: str) -> None:
    """Delete the chip rows whose socket the asset's model does not have."""
    keep = set(machines.roles(model_key))
    rows = db.query(AssetChip).filter(AssetChip.asset_id == aid).all()
    for row in rows:
        if row.role not in keep:
            db.delete(row)
    db.flush()


def duplicated_from(db: Session, src: Asset, dest: Asset) -> None:
    """Give a duplicate of an asset the model its original is filed as, and
    nothing else.

    A second machine of the same model is the same model -- that is what the
    duplicate button means -- but the board issue, the style and the chips in it are
    this one's own, found by opening this one. Copying them across would write down
    a ULA nobody has looked at.
    """
    key = read(db, src)["model_key"]
    if key:
        write(db, dest, model_key=key)
