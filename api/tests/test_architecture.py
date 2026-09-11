"""The documents in `docs/` are held to the code they describe.

Prose about intent cannot be checked by a machine, and this does not try. What it
checks is the part that can be: that the map still lists the modules that exist,
and that the generated catalogue is the catalogue the suite would generate today.
Those are the two ways a document of this kind goes wrong quietly -- a module is
added and never written down, or a behaviour changes and the description of it
stays as it was.

Rerun with RHDB_UPDATE_BEHAVIOUR=1 to rewrite the catalogue.
"""
import os
import re
from pathlib import Path

import pytest

from behaviour_catalogue import DOCUMENT, render

ROOT = Path(__file__).parents[2]
ARCHITECTURE = ROOT / "docs" / "architecture.md"
MODULES = ROOT / "api" / "app"
UPDATE = "RHDB_UPDATE_BEHAVIOUR"

# The package marker is not a module anyone navigates by; a line for it in the map
# would be noise rather than orientation.
UNLISTED = {"__init__.py"}
MARKER = "<!-- module-inventory:"


def inventory() -> set[str]:
    """The module names in the map's inventory table, and only those.

    Scoped to the marked table rather than read off the whole document, which
    also names test files and templates in passing -- those are orientation, not
    a claim about what `api/app` contains.
    """
    text = ARCHITECTURE.read_text(encoding="utf-8")
    assert MARKER in text, "the module inventory's marker has gone from the map"
    table = text.split(MARKER, 1)[1]
    table = table.split("\n\n", 2)[1] if "\n\n" in table else table
    return set(re.findall(r"`([a-z_]+\.py)`", table))


def test_the_map_lists_every_module_and_no_others():
    """A map that has quietly stopped matching the code is worse than none: it is
    read by whoever knows the code least. Both directions are checked -- a module
    added without a line in the inventory, and a line for one that has since gone."""
    listed = inventory()
    actual = {p.name for p in MODULES.glob("*.py")} - UNLISTED
    assert not actual - listed, f"modules the map does not list: {sorted(actual - listed)}"
    assert not listed - actual, f"the map lists modules that are gone: {sorted(listed - actual)}"


def test_the_behaviour_catalogue_is_the_one_the_suite_would_write():
    """The catalogue is generated, so the only way it can be wrong is by being
    stale. Regenerating it is part of changing the tests, in the same way that
    changing the API's shape means recording the new one."""
    current = render()
    if os.getenv(UPDATE):
        DOCUMENT.write_text(current, encoding="utf-8")
        pytest.skip(f"{DOCUMENT.name} rewritten from the suite; commit the diff")
    assert DOCUMENT.exists(), f"no catalogue on file -- write one with {UPDATE}=1"
    assert DOCUMENT.read_text(encoding="utf-8") == current, (
        "docs/behaviour.md is not what the suite describes any more. Rewrite it:\n"
        f"    {UPDATE}=1 pytest api/tests/test_architecture.py"
    )
