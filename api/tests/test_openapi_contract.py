"""The published shape of the API, pinned to a file and reviewed like code.

FastAPI writes the OpenAPI document from the code every time the app starts, so
on its own it can only ever agree with whatever the code happens to do: rename a
field and the document renames it too, and nothing anywhere says that was a
mistake. Keeping a copy in the repository turns that silence into a diff. The
document is still generated rather than authored -- this does not make it the
definition the API is built to -- but a change to the shape callers see now has
to be an act someone performed on purpose, in a pull request, with the change
itself on the page.

Rerun with RHDB_UPDATE_OPENAPI=1 to record a change you meant to make.
"""
import json
import os
from pathlib import Path

import pytest

from app.main import app

CONTRACT = Path(__file__).parents[1] / "openapi.json"
UPDATE = "RHDB_UPDATE_OPENAPI"
HOW_TO_UPDATE = f"    {UPDATE}=1 pytest api/tests/test_openapi_contract.py"


def rendered(document: dict) -> str:
    """The document as it is kept: sorted, indented, one change one line."""
    return json.dumps(document, indent=2, sort_keys=True) + "\n"


def differences(live: dict, kept: dict) -> list[str]:
    """What moved, named rather than diffed.

    A JSON diff of a document this size buries the answer. What a reader needs
    from a failure is which routes and which models are not what they were.
    """
    out = []
    sections = (
        ("route", live.get("paths", {}), kept.get("paths", {})),
        ("model",
         live.get("components", {}).get("schemas", {}),
         kept.get("components", {}).get("schemas", {})),
    )
    for name, now, before in sections:
        for key in sorted(set(now) - set(before)):
            out.append(f"  new {name}: {key}")
        for key in sorted(set(before) - set(now)):
            out.append(f"  gone {name}: {key}")
        for key in sorted(set(now) & set(before)):
            if now[key] != before[key]:
                out.append(f"  changed {name}: {key}")
    return out


def test_the_published_api_is_the_one_on_file():
    """Every route and model the API offers, against the copy in the repository.

    A failure here is not necessarily a fault: it says the shape callers see is
    no longer the shape that was agreed, and asks for that to be deliberate. The
    labels printed against this register are one of those callers, and so is
    anything anyone writes against the API later.
    """
    live = app.openapi()
    if os.getenv(UPDATE):
        CONTRACT.write_text(rendered(live), encoding="utf-8")
        pytest.skip(f"{CONTRACT.name} rewritten from the running app; commit the diff")
    assert CONTRACT.exists(), f"no contract on file -- record one with\n{HOW_TO_UPDATE}"
    kept = json.loads(CONTRACT.read_text(encoding="utf-8"))
    moved = differences(live, kept)
    assert not moved, (
        "the API's published shape has changed:\n"
        + "\n".join(moved)
        + "\n\nIf that was the intention, record it with\n"
        + HOW_TO_UPDATE
        + f"\nand the diff of {CONTRACT.name} is the change you are asking for."
    )
    assert rendered(live) == CONTRACT.read_text(encoding="utf-8"), (
        f"the document is equivalent but not as it is kept; rewrite it with\n{HOW_TO_UPDATE}"
    )
