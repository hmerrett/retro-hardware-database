"""The ways the three faces can be pointed, read from the design data (ADR-0031).

The register sets its words in three faces by what kind of word each is: what
somebody wrote, what the interface says, and what somebody recorded. A pairing
decides which family plays which of those three parts, and nothing else -- no
size, no weight, no spacing -- so choosing one is a change of face and never a
change of layout.

`preset` is the answer that changes nothing: the preset's own three stand, which
is why it has no rules in `type.css` and puts no attribute on the page. The rest
are read from `design/scales.json` for the reason `presets.py` reads its list from
`palettes.json`: that file is what the stylesheet is generated from, and a list
written out again here would be a second opinion about what exists.
"""

from __future__ import annotations

import json
from pathlib import Path

# No attribute on the document element, and no stylesheet fetched: the faces are
# the ones the chosen preset names.
DEFAULT = "preset"

DESIGN = Path(__file__).parent / "design"


def _load() -> tuple[tuple[str, ...], dict[str, str]]:
    """The pairings in the order the menu shows them, and what each one is called."""
    data = json.loads((DESIGN / "scales.json").read_text(encoding="utf-8"))
    pairings = data["type"]["pairings"]
    ids = tuple(str(key) for key in pairings)
    return ids, {key: str(pairings[key]["name"]) for key in ids}


IDS, NAMES = _load()

# What the settings page offers, in the shape every other choice on it takes.
CHOICES: tuple[tuple[str, str], ...] = tuple((key, NAMES[key]) for key in IDS)


def known(name: str) -> str:
    """`name` if there is a pairing by that name, and the default if there is not.

    The same guard `presets.known` is, and for a milder version of the same reason:
    the value can arrive from a row nobody on this page wrote, and an unrecognised
    one should leave the site in the preset's own faces rather than carrying an
    attribute that matches no rule and a stylesheet that does nothing.
    """
    return name if name in IDS else DEFAULT
