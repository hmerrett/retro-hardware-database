"""The catalogue: what the register knows as models, rather than what is on a shelf.

machines.yaml is the catalogue itself and machines.py reads it; these are the two
ways it is offered out -- a page for somebody deciding whether their machine is
known, and the same answer as JSON. Neither touches the register except to count
how many of each model is held.
"""

from collections import Counter
from typing import TypedDict

from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import HTMLResponse
from sqlalchemy.orm import Session

from .. import entry, filesdb, machines
from ..common import folder_images, to_dict
from ..db import get_db
from ..models import AssetVariant, Computer, Part
from ..photos import pick_images
from ..web import _og, templates

router = APIRouter()


@router.get("/machines", response_class=HTMLResponse, include_in_schema=False)
def gui_machines(request: Request, db: Session = Depends(get_db)) -> HTMLResponse:
    """Every machine the catalogue names, on one page, and which of them are here.

    catalogue.txt answers this question in a text file and /api/machines answers it
    in JSON; this is the same question asked in a browser, which is where it
    actually gets asked -- "does it know my machine?" is what somebody wants to
    know before they type one in, and reading a JSON document to find out is not a
    reasonable thing to ask of anybody.

    The count of what is held against each model comes from the register, so the
    page doubles as the other view of the catalogue: not what was made, but how
    much of it is on the shelf."""
    held: Counter[str] = Counter()
    for row in db.query(AssetVariant.model_key).filter(AssetVariant.model_key != ""):
        held[row[0]] += 1
    families = [{"name": name, "models": group} for name, group in machines.grouped()]
    return templates.TemplateResponse(
        request,
        "machines.html",
        {
            "families": families,
            "held": held,
            "n_models": len(machines.keys()),
            "n_families": len(families),
            "og": _og(
                request,
                "Machines the catalogue names",
                f"{len(machines.keys())} machines the register knows as models, "
                "with the board issues, styles and chips each was built in.",
            ),
        },
    )


class Unit(TypedDict):
    """One thing in the register filed as a model, as its row on the model's page."""

    href: str
    tag: str
    name: str
    sub: str
    image: str
    placeholder: str
    disposed: bool


def _units(db: Session, key: str) -> list[Unit]:
    """Everything filed as this model, machines and bare boards alike, by tag.

    The same rows the count on /machines is made of -- asset_variant, whichever
    table the asset is in -- so the list and the count cannot disagree, disposed
    ones included."""
    filed = {v.asset_id: v for v in db.query(AssetVariant).filter(AssetVariant.model_key == key)}
    if not filed:
        return []
    held: list[tuple[str, Computer | Part]] = [
        *(("computers", c) for c in db.query(Computer).filter(Computer.asset_id.in_(filed))),
        *(("parts", p) for p in db.query(Part).filter(Part.asset_id.in_(filed))),
    ]
    listings = {kind: folder_images(kind) for kind, _ in held}
    units: list[Unit] = []
    for kind, obj in sorted(held, key=lambda h: h[1].asset_id):
        v = filed[obj.asset_id]
        ptype = "computer" if kind == "computers" else (getattr(obj, "type", None) or "other")
        imgs = pick_images(kind, obj.asset_id, listings[kind])
        units.append(
            {
                "href": f"/{kind}/{obj.asset_id}",
                "tag": obj.asset_id,
                "name": entry.display_name(to_dict(obj)),
                "sub": " · ".join(
                    x
                    for x in (
                        "Computer" if kind == "computers" else entry.type_label(ptype),
                        v.issue,
                        v.region,
                        str(obj.year or ""),
                    )
                    if x
                ),
                "image": imgs[0] if imgs else "",
                "placeholder": entry.placeholder_for(ptype),
                "disposed": bool(obj.disposed),
            }
        )
    return units


@router.get("/machines/{key}", response_class=HTMLResponse, include_in_schema=False)
def gui_model(key: str, request: Request, db: Session = Depends(get_db)) -> HTMLResponse:
    """One model: what the catalogue records about it, and which of it is here.

    Public for the list's reason -- the catalogue is what was made, not what is on
    the shelf -- and everything else on it is public already: the units' own pages,
    and the files attached to the model, of which a visitor gets the published ones
    as everywhere else (ADR-0009)."""
    m = machines.model(key)
    if m is None:
        raise HTTPException(404, "no such model in the catalogue")
    facts = [
        ("Maker", m["manufacturer"]),
        ("CPU", m["cpu"]),
        ("Memory", ", ".join(label for label, _kb in m["ram"])),
        ("Board issues", ", ".join(m["issues"])),
        ("Styles", ", ".join(m["styles"])),
        ("Regions", ", ".join(m["regions"])),
        ("Chassis", m["chassis"]),
        ("OS", m["os"]),
    ]
    return templates.TemplateResponse(
        request,
        "model.html",
        {
            "m": m,
            "facts": [(k, v) for k, v in facts if v],
            "units": _units(db, key),
            "files": filesdb.for_model(db, filesdb.CATALOGUE, key, request.state.authed),
            "og": _og(request, m["full_name"], m["summary"]),
        },
    )


# response_model=None: the annotation is for the type checker. FastAPI would
# otherwise publish it as the response's shape, which the pinned contract
# (ADR-0010) leaves open.
@router.get("/api/machines", tags=["computers"], response_model=None)
def api_list_machines() -> dict[str, list[dict[str, object]]]:
    """The catalogue of machines the register knows as models -- home computers,
    consoles and the documented branded PCs -- with the memory sizes, board issues,
    case and keyboard styles, regions and chip sockets each was built in. `key` is
    what a computer's `machine.model_key` is set to.

    Every list names what is commonly seen rather than everything that exists, so a
    board issue or a chip from outside one is recorded as it is given."""
    return {
        "families": [
            {
                "name": name,
                "models": [
                    {
                        "key": m["key"],
                        "model": m["model"],
                        "year": m["year"],
                        "manufacturer": m["manufacturer"],
                        "summary": m["summary"],
                        "ram": [lbl for lbl, _kb in m["ram"]],
                        "issues": m["issues"],
                        "styles": m["styles"],
                        "regions": m["regions"],
                        "chips": [
                            {"role": c["role"], "label": c["label"], "variants": c["variants"]}
                            for c in m["chips"]
                        ],
                    }
                    for m in group
                ],
            }
            for name, group in machines.grouped()
        ]
    }
