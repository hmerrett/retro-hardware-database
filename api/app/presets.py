"""The looks this installation can wear, read from the design data (ADR-0024).

A preset is a block of token values and nothing else -- colours for both modes,
the radii, the shadow and the three typefaces. It may not name a component and it
may not move anything, which is what keeps one look from becoming a second
stylesheet with its own layout to maintain.

The list is read from `design/palettes.json` because that is what the stylesheets
are generated from (`tools/build_presets.py`). Writing the ids out again here
would give the page its own idea of what exists, and the day the two disagreed the
page would offer a look with no stylesheet behind it -- a face that paints the
site in the default and says nothing about why.
"""

from __future__ import annotations

import json
from pathlib import Path

# No attribute on the document element, and no second stylesheet: the default's
# colours are the ones tokens.css states on `:root`.
DEFAULT = "default"

DESIGN = Path(__file__).parent / "design"


def _load() -> tuple[tuple[str, ...], dict[str, str]]:
    """The ids in the order the picker shows them, and the name each one goes by.

    Read into concrete types at import rather than passed around as whatever JSON
    hands back: this is a fixed list that ships with the software, and a typo in
    the data should fail here rather than three layers away."""
    data = json.loads((DESIGN / "palettes.json").read_text(encoding="utf-8"))
    ids = tuple(str(key) for key in data["presets"])
    return ids, {key: str(data["names"][key]) for key in ids}


IDS, NAMES = _load()

# What the settings page offers, in the shape every other choice on it takes.
CHOICES: tuple[tuple[str, str], ...] = tuple((key, NAMES[key]) for key in IDS)


def known(name: str) -> str:
    """`name` if there is a preset by that name, and the default if there is not.

    Every reading of the setting goes through this. The value can arrive from the
    environment or from a row in the database, neither of which the page wrote,
    and it is spent on the path of a stylesheet -- so an unrecognised one has to
    come back as the default rather than as a link to a file that is not there, or
    to a file somewhere else entirely.
    """
    return name if name in IDS else DEFAULT
