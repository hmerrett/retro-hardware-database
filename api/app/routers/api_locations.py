"""The JSON API for where things are kept: the locations, and the moves.

The same rows the location pages edit, for the tool server and anything else that
is not a browser (ADR-0034). Behind the login entire, like the rest of /api, so
nothing here asks the Show locations switch anything: there is nobody on this side
of the token to keep a shelf from.
"""

from fastapi import APIRouter, Depends, HTTPException, Request
from sqlalchemy.orm import Session

from .. import locations
from ..db import get_db
from ..history import add_log
from ..ids import next_asset_id
from ..models import Location, Move
from ..photos import _purge_photos
from ..register import get_or_404
from ..schemas import LocationDetail, LocationIn, LocationOut, MoveOut

router = APIRouter()


def _out(loc: Location, tree: locations.Tree) -> dict[str, object]:
    return {
        "asset_id": loc.asset_id,
        "name": loc.name,
        "kind": loc.kind,
        "parent": loc.parent_id,
        "path": tree.text(loc.asset_id),
        "notes": loc.notes,
    }


def _kind(sent: str | None) -> str:
    """A kind as it is stored, or a 422: one of the seven, by slug."""
    kind = (sent or locations.OTHER).strip().lower()
    if kind not in locations.KIND_NAMES:
        raise HTTPException(
            422, f"no such kind of location: {kind} -- one of {', '.join(locations.KIND_NAMES)}"
        )
    return kind


def _parent(db: Session, sent: str | None) -> str | None:
    """The tag of the location something is to go inside, or a 404 for a tag that
    names none. Blank and null are both the top of a tree."""
    tag = (sent or "").strip().upper()
    if not tag:
        return None
    if db.get(Location, tag) is None:
        raise HTTPException(404, f"no location {tag}")
    return tag


@router.get("/api/locations", response_model=list[LocationOut], tags=["locations"])
def api_list_locations(db: Session = Depends(get_db)) -> list[dict[str, object]]:
    tree = locations.tree(db)
    rows = db.query(Location).all()
    rows.sort(key=lambda loc: tree.text(loc.asset_id).casefold())
    return [_out(loc, tree) for loc in rows]


@router.post("/api/locations", response_model=LocationOut, tags=["locations"])
def api_create_location(
    data: LocationIn, request: Request, db: Session = Depends(get_db)
) -> dict[str, object]:
    name = (data.name or "").strip()
    if not name:
        raise HTTPException(422, "a location needs a name")
    loc = Location(
        asset_id=next_asset_id(db),
        name=name[:255],
        kind=_kind(data.kind),
        notes=(data.notes or "").strip(),
    )
    db.add(loc)
    db.flush()
    add_log(db, loc.asset_id, "created", "created")
    parent = _parent(db, data.parent)
    if parent is not None:
        locations.move(db, loc, parent, locations.API, request.state.principal.username)
    db.commit()
    return _out(loc, locations.tree(db))


@router.get("/api/locations/{aid}", response_model=LocationDetail, tags=["locations"])
def api_get_location(aid: str, db: Session = Depends(get_db)) -> dict[str, object]:
    loc = get_or_404(db, Location, aid)
    tree = locations.tree(db)
    return _out(loc, tree) | {
        "things": [t.asset_id for t in locations.kept_in(db, loc.asset_id)],
        "locations": tree.children(loc.asset_id),
    }


@router.patch("/api/locations/{aid}", response_model=LocationOut, tags=["locations"])
def api_update_location(
    aid: str, data: LocationIn, request: Request, db: Session = Depends(get_db)
) -> dict[str, object]:
    loc = get_or_404(db, Location, aid)
    sent = data.model_dump(exclude_unset=True)
    changed = []
    if "name" in sent:
        name = (data.name or "").strip()
        if not name:
            raise HTTPException(422, "a location needs a name")
        if name != loc.name:
            changed.append(f"name: {loc.name} → {name}")
            loc.name = name[:255]
    if "kind" in sent:
        kind = _kind(data.kind)
        if kind != loc.kind:
            changed.append(f"kind: {loc.kind} → {kind}")
            loc.kind = kind
    if "notes" in sent and (data.notes or "").strip() != loc.notes:
        changed.append("notes changed")
        loc.notes = (data.notes or "").strip()
    if changed:
        add_log(db, loc.asset_id, "; ".join(changed))
    if "parent" in sent:
        try:
            locations.move(
                db, loc, _parent(db, data.parent), locations.API, request.state.principal.username
            )
        except locations.Refused as err:
            raise HTTPException(422, str(err)) from err
    db.commit()
    return _out(loc, locations.tree(db))


# response_model=None: the annotation is for the type checker. FastAPI would
# otherwise publish it as the response's shape, which the pinned contract
# (ADR-0010) leaves open.
@router.delete("/api/locations/{aid}", tags=["locations"], response_model=None)
def api_delete_location(aid: str, db: Session = Depends(get_db)) -> dict[str, object]:
    """Delete a location, which is refused while anything is still in it: a thing,
    or a location inside it. Its history goes with it; the moves of the things
    that were once in it stay on their own histories."""
    loc = get_or_404(db, Location, aid)
    if not locations.empty(db, loc.asset_id, locations.tree(db)):
        raise HTTPException(422, f"{loc.name} is not empty: move what is in it first")
    tag = loc.asset_id
    rels = locations.forget(db, loc)
    db.commit()  # the rows first: a file cannot be rolled back
    _purge_photos(rels)
    return {"deleted": tag}


@router.get("/api/items/{aid}/moves", response_model=list[MoveOut], tags=["log"])
def api_item_moves(aid: str, db: Session = Depends(get_db)) -> list[dict[str, object]]:
    """Where a thing or a location has been, newest first."""
    rows = (
        db.query(Move)
        .filter(Move.asset_id == (aid or "").upper())
        .order_by(Move.moved_at.desc(), Move.id.desc())
        .all()
    )
    return [
        {
            "from": m.from_id,
            "from_path": m.from_path,
            "to": m.to_id,
            "to_path": m.to_path,
            "moved_at": m.moved_at.isoformat(),
            "who": m.who,
            "how": m.how,
        }
        for m in rows
    ]
