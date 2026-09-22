"""Every preset's colours, in both modes, hold the contrast the register promises.

A preset is only token values (ADR-0024), and those values are data in
`app/design/palettes.json`: seven presets, each with a light and a dark mode. The
stylesheets that carry them are generated from that data, so the data is where the
contrast is checked, and the first test here holds the generated files to it.

The pairs are every pairing of a colour words are written in with a colour they
are written on, plus the edges and rings that have to be seen at all. Text holds
4.5:1 (WCAG 2.2 AA); a control's edge, the focus ring and a fill that stands in for
an edge hold 3:1. The lightbox's scrim is the one translucent token, and is judged
as painted over the page.
"""

import importlib.util
import json
import re
from pathlib import Path

import pytest

from test_stylesheet import contrast, over

APP = Path(__file__).parents[1] / "app"
PALETTES = json.loads((APP / "design" / "palettes.json").read_text(encoding="utf-8"))
THEMES = sorted(PALETTES["themes"])

TEXT, EDGE = 4.5, 3.0

# (colour written, ground it is written on, floor). The ground is where the design
# puts that colour and nowhere else -- `text-muted` never sits on `surface-hover`,
# for instance, because the hover row turns everything on it to `text`.
PAIRS = [
    ("text", "surface", TEXT),
    ("text", "surface-raised", TEXT),
    ("text", "surface-sunken", TEXT),
    ("text", "surface-hover", TEXT),
    ("text-muted", "surface", TEXT),
    ("text-muted", "surface-raised", TEXT),
    ("text-muted", "surface-sunken", TEXT),
    ("band-text", "band", TEXT),
    ("band-muted", "band", TEXT),
    ("danger", "surface", TEXT),
    ("danger", "surface-raised", TEXT),
    ("danger", "surface-sunken", TEXT),
    ("danger", "danger-wash", TEXT),
    ("text", "danger-wash", TEXT),
    ("warning", "surface", TEXT),
    ("warning", "surface-raised", TEXT),
    ("text", "warning-wash", TEXT),
    ("warning", "warning-wash", TEXT),
    ("success", "surface", TEXT),
    ("success", "surface-raised", TEXT),
    ("text", "success-wash", TEXT),
    ("success", "success-wash", TEXT),
    ("line-strong", "surface", EDGE),
    ("line-strong", "surface-raised", EDGE),
    ("danger-line", "surface", EDGE),
    ("on-scrim", "scrim", TEXT),
    ("on-scrim-muted", "scrim", TEXT),
    ("on-scrim-danger", "scrim", TEXT),
    ("accent", "surface", TEXT),
    ("accent", "surface-raised", TEXT),
    ("accent", "surface-sunken", TEXT),
    ("on-accent", "accent-fill", TEXT),
    ("accent-fill", "surface", EDGE),
    ("accent-fill", "accent-track", EDGE),
    ("focus", "surface", EDGE),
    ("focus", "surface-raised", EDGE),
    ("focus", "surface-sunken", EDGE),
]


def _builder():
    spec = importlib.util.spec_from_file_location(
        "build_presets", APP.parents[1] / "tools" / "build_presets.py"
    )
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_the_stylesheets_are_the_ones_the_design_data_writes():
    """tokens.css and the preset files are generated. A colour changed in one of
    them by hand is a colour the contrast tests below never saw, and the next run
    of the generator would quietly put the old one back."""
    stale = [
        path.relative_to(APP.parents[1]).as_posix()
        for path, text in _builder().outputs().items()
        if not path.exists() or path.read_text(encoding="utf-8") != text
    ]
    assert stale == [], "run `python tools/build_presets.py`; these differ from the design data"


def test_every_font_is_served_from_the_site_with_its_licence():
    """The faces are ours to serve, not a font service's: the CSP allows no other
    origin, and a face that is named but missing falls back without a word, so the
    page looks right to whoever has the font installed and wrong to everyone else.
    The OFL asks for the licence to travel with the files."""
    static = APP / "static"
    tokens = (static / "css" / "tokens.css").read_text(encoding="utf-8")
    sources = re.findall(r'src:\s*url\("([^"]+)"\)', tokens)
    assert len(sources) == 7, "two weights of the serif and the mono, three of the sans"
    for src in sources:
        assert src.startswith("/static/fonts/"), f"{src} is not served from this site"
        assert (static / src.removeprefix("/static/")).is_file(), f"{src} is not on disk"
    for folder in {Path(src).parent.name for src in sources}:
        assert (static / "fonts" / folder / "OFL.txt").is_file(), f"{folder} has no licence"


def test_every_preset_states_every_colour_in_both_modes():
    """A token a preset leaves out is inherited from the default preset underneath,
    which is a colour chosen for a different page -- a black band's text left
    white-on-white, say. Every preset says every colour, light and dark."""
    for preset in PALETTES["presets"]:
        for mode in ("light", "dark"):
            theme = mode if preset == "default" else f"{preset}-{mode}"
            missing = set(PALETTES["keys"]) - set(PALETTES["themes"][theme])
            assert missing == set(), f"{theme} does not state {sorted(missing)}"


@pytest.mark.parametrize("theme", THEMES)
@pytest.mark.parametrize(("fg", "bg", "floor"), PAIRS, ids=[f"{f}-on-{b}" for f, b, _ in PAIRS])
def test_every_pair_holds_in_every_preset_and_mode(theme, fg, bg, floor):
    """518 pairs: the 37 the design uses, in fourteen themes. A preset is judged as
    a whole set of passing pairs, not a palette swapped in by eye."""
    colours = PALETTES["themes"][theme]
    ground = over(colours[bg], colours["surface"]) if len(colours[bg]) == 9 else colours[bg]
    ratio = contrast(colours[fg][:7], ground)
    assert ratio >= floor, f"{fg} on {bg} is {ratio:.2f}:1 in {theme}; it needs {floor}:1"
