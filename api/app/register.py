"""The register as one thing: finding an item in it whichever table it is in.

A computer and a part are two tables and one register -- asset ids are unique
across both, and a reader who has scanned a label has an id and no idea which of
the two it belongs to. These are the questions that have to be asked of the pair
rather than of either: which table holds this id, what sits either side of it in
the register's order, and has the copy in front of you gone stale since it was
opened.
"""
from fastapi import HTTPException
from sqlalchemy import func

from . import entry
from .common import REGISTER
from .models import Computer, LogEntry, Part, StoredFile



def get_or_404(db, model, aid):
    obj = db.get(model, (aid or "").upper())
    if not obj:
        raise HTTPException(404, f"{model.__tablename__} {aid} not found")
    return obj


def _change_token(db, aid: str) -> str:
    """What an item's page was built from, as one short string.

    Every change to an asset writes a history entry -- a field edited, a photograph
    added, rotated, cropped or deleted -- so the highest id in that item's history
    already answers "has anything happened to this?" without a column being added
    anywhere. Files are the one thing an item page shows that is not filed against
    it (a driver belongs to a model, not to the card on the shelf), so the register
    of files is counted alongside: the newest id, and how many there are, because
    deleting one that is not the newest leaves the maximum where it was.

    Cheap on purpose. This is asked every few seconds by every open page, and it is
    two indexed aggregates over columns that are already there.
    """
    logged = db.query(func.max(LogEntry.id)).filter(LogEntry.asset_id == aid).scalar()
    newest = db.query(func.max(StoredFile.id)).scalar()
    count = db.query(func.count(StoredFile.id)).scalar()
    return f"{logged or 0}.{newest or 0}.{count or 0}"


def _register_order(db):
    """Every asset in register order, as (asset_id, kind, display name).

    Two small column queries: no photos are looked at, because this is only wanted
    for the prev/next buttons on an item page. It is the fallback order -- arrive
    from the gallery and the browser hands over the order it was actually showing,
    filtered and sorted as you left it (see base.html)."""
    rows = []
    for kind, cls in (("computers", Computer), ("parts", Part)):
        for aid, name, maker, model in db.query(cls.asset_id, cls.name,
                                                cls.manufacturer, cls.model):
            rows.append((aid, kind, entry.display_name(
                {"asset_id": aid, "name": name, "manufacturer": maker,
                 "model": model})))
    rows.sort()
    return rows


def _item_nav(db, aid):
    """{prev, next} for an item page: the assets either side of this one."""
    order = _register_order(db)
    here = next((n for n, row in enumerate(order) if row[0] == aid), None)
    if here is None:
        return {}

    def at(n):
        if not 0 <= n < len(order):
            return None
        a, kind, name = order[n]
        return {"url": f"/{kind}/{a}", "name": name, "aid": a}

    return {"prev": at(here - 1), "next": at(here + 1)}


# The two of them that can be put on the list of things wanting work. A project is
# in the register and answers at /items/<id> like the others, but it cannot be
# flagged as one: it is already what the flag points at, and `Project` has no such
# column -- so a route handed one would set an attribute on the instance, commit
# nothing, and redirect as though it had worked.
FLAGGABLE = REGISTER[:2]


def _asset_find(db, aid, kinds=REGISTER):
    """One thing from the shared register and the page it lives on, whichever kind
    it turns out to be -- or None for no such asset.

    What a route serving more than one kind actually wants: the log routes below
    only needed the address, but a route that changes something needs the row as
    well, and looking it up twice is how the two come to be about different items.

    `kinds` narrows which tables are searched, for the callers that can only act on
    some of them."""
    aid = (aid or "").strip().upper()
    for kind, cls in kinds:
        obj = db.get(cls, aid)
        if obj is not None:
            return obj, f"/{kind}/{aid}"
    return None


def _asset_or_404(db, aid, kinds=REGISTER):
    """The same, for the callers that have nothing to say about a miss. Which is
    most of them: an id in a URL that is not an asset is a broken link, while an id
    typed into a box is a typo, and only the second has anywhere useful to go."""
    found = _asset_find(db, aid, kinds)
    if found is None:
        raise HTTPException(404, f"no asset {(aid or '').strip().upper()}")
    return found


def _asset_page(db, aid):
    """Where a register id's page is, for a route that serves any of the kinds."""
    return _asset_or_404(db, aid)[1]
