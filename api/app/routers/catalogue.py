"""The catalogue: what the register knows as models, rather than what is on a shelf.

machines.yaml is the catalogue itself and machines.py reads it; these are the two
ways it is offered out -- a page for somebody deciding whether their machine is
known, and the same answer as JSON. Neither touches the register except to count
how many of each model is held.
"""

from collections import Counter

from fastapi import APIRouter, Depends, Request
from fastapi.responses import HTMLResponse
from sqlalchemy.orm import Session

from .. import machines
from ..db import get_db
from ..models import AssetVariant
from ..web import _og, templates

router = APIRouter()


@router.get("/machines", response_class=HTMLResponse, include_in_schema=False)
def gui_machines(request: Request, db: Session = Depends(get_db)):
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


@router.get("/api/machines", tags=["computers"])
def api_list_machines():
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
