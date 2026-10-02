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


def _load() -> tuple[tuple[str, ...], dict[str, str], dict[str, str]]:
    """The pairings in the order the menu shows them, what each one is called, and
    which of the three faces each sets the interface in."""
    data = json.loads((DESIGN / "scales.json").read_text(encoding="utf-8"))
    pairings = data["type"]["pairings"]
    ids = tuple(str(key) for key in pairings)
    names = {key: str(pairings[key]["name"]) for key in ids}
    ui = {key: str(pairings[key]["roles"]["ui"]) for key in ids if "roles" in pairings[key]}
    return ids, names, ui


IDS, NAMES, _UI_ROLE = _load()

# Which family each preset sets its interface in, when it names one of its own:
# Phosphor and Amber are monospaced throughout, because the screens they are drawn
# from were. Read from the design data, like everything else about a preset.
_PRESET_UI = {
    str(preset): str(values.get("font-ui", ""))
    for preset, values in json.loads((DESIGN / "palettes.json").read_text(encoding="utf-8"))[
        "construction"
    ].items()
}


def interface_face(preset: str, pairing: str) -> str:
    """`mono` or `sans`: the family the interface is set in for this look and this
    pairing -- what a label set *as the look* is set in (MANUAL §13, "The type on a
    label"). A pairing that names the interface's face wins over the preset's own,
    as it does on the page; "as the preset" leaves it to the preset."""
    role = _UI_ROLE.get(pairing)
    if pairing != DEFAULT and role is not None:
        return "mono" if role == "data" else "sans"
    return "mono" if "Mono" in _PRESET_UI.get(preset, "") else "sans"


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
