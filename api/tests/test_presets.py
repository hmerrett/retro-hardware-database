"""Every preset's colours, in both modes, hold the contrast the register promises.

A preset is only token values (ADR-0031), and those values are data in
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
from itertools import pairwise
from pathlib import Path

import pytest

from test_stylesheet import contrast, over
from test_stylesheet_lint import COMPONENTS, declarations

APP = Path(__file__).parents[1] / "app"
PALETTES = json.loads((APP / "design" / "palettes.json").read_text(encoding="utf-8"))
THEMES = sorted(PALETTES["themes"])

TEXT, EDGE = 4.5, 3.0

# (colour written, ground it is written on, floor). The ground is where the design
# puts that colour and nowhere else -- `text-muted` never sits on `surface-hover`,
# for instance, because the hover row turns everything on it to `text`. `surface-nav`
# is what the side rail and the phone's tab bar stand on: the words, the current
# tab's accent and the focus ring are all written on it.
PAIRS = [
    ("text", "surface", TEXT),
    ("text", "surface-raised", TEXT),
    ("text", "surface-sunken", TEXT),
    ("text", "surface-hover", TEXT),
    ("text", "surface-nav", TEXT),
    ("text-muted", "surface", TEXT),
    ("text-muted", "surface-raised", TEXT),
    ("text-muted", "surface-sunken", TEXT),
    ("text-muted", "surface-nav", TEXT),
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
    ("accent", "surface-nav", TEXT),
    ("on-accent", "accent-fill", TEXT),
    ("accent-fill", "surface", EDGE),
    ("accent-fill", "accent-track", EDGE),
    ("focus", "surface", EDGE),
    ("focus", "surface-raised", EDGE),
    ("focus", "surface-sunken", EDGE),
    ("focus", "surface-nav", EDGE),
]


def test_the_filter_you_are_on_is_written_in_a_pair_every_look_holds():
    """Above the files list, the filter you are on was told by the band a panel's
    title sits on, with `text` on it -- a pair no look is held to, and 1.06:1 in
    Rubber Key's light mode. The current one is told by weight and ground, and the
    ground is one every colour written on it is tested against, in every look."""
    rules: dict[str, dict[str, str]] = {}
    for selector, prop, value in declarations(COMPONENTS):
        rules.setdefault(selector, {})[prop] = value

    def token(selector, prop, fallback=""):
        value = rules.get(selector, {}).get(prop) or rules.get(fallback, {}).get(prop, "")
        found = re.fullmatch(r"var\(--([\w-]+)\)", value)
        assert found, f"{selector} states no {prop} token for the filter"
        return found.group(1)

    current = '.filefilters a[aria-current="page"]'
    ground = token(current, "background")
    written = {
        token(current, "color", fallback=".filefilters a"),
        token(".filefilters a span", "color"),
    }
    held = {(fg, bg) for fg, bg, _ in PAIRS}
    assert {(fg, ground) for fg in written} <= held, f"{written} on {ground} is not swept"


def test_the_filter_you_are_on_is_told_by_its_weight_as_well_as_its_ground():
    """The ground under the filter you are on is a shade off the page's, and in some
    looks barely one: enough to see, and not enough to be the only telling for
    anybody who cannot tell two pale greys apart. So the one you are on is set
    heavier as well, as the section you are in is in the banner."""
    faintest = min(
        contrast(mode["surface"], mode["surface-sunken"]) for mode in PALETTES["themes"].values()
    )
    weights = {
        value
        for selector, prop, value in declarations(COMPONENTS)
        if selector == '.filefilters a[aria-current="page"]' and prop == "font-weight"
    }
    assert weights & {"600", "700", "bold"}, (
        f"the filter you are on is told only by a ground {faintest:.2f}:1 off the page's"
    )


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
    """574 pairs: the 41 the design uses, in fourteen themes. A preset is judged as
    a whole set of passing pairs, not a palette swapped in by eye."""
    colours = PALETTES["themes"][theme]
    ground = over(colours[bg], colours["surface"]) if len(colours[bg]) == 9 else colours[bg]
    ratio = contrast(colours[fg][:7], ground)
    assert ratio >= floor, f"{fg} on {bg} is {ratio:.2f}:1 in {theme}; it needs {floor}:1"


def test_a_preset_names_no_component():
    """A preset is token values and nothing else (ADR-0031). The moment one names a
    component -- a button, a panel, the rail -- a look stops being a palette and
    becomes a second stylesheet, and the next component added to the design has to
    be drawn seven times. So every rule in a preset file selects the document
    element by its attribute, and every declaration in it is a custom property."""
    for path in sorted((APP / "static" / "css" / "presets").glob("*.css")):
        for selector, block in re.findall(
            r"([^{}]+)\{([^{}]*)\}", path.read_text(encoding="utf-8")
        ):
            head = selector.strip().splitlines()[-1].strip()
            if head.startswith("@media"):
                continue
            assert head.startswith(':root[data-preset="'), f"{path.name} styles {head}"
            for declaration in filter(None, (d.strip() for d in block.split(";"))):
                assert declaration.startswith("--"), f"{path.name} sets {declaration}"


def test_every_face_in_the_picker_is_drawn_in_its_own_colours():
    """The settings page shows each preset as a miniature, and a miniature painted
    in the colours of the preset already in force would show seven of the same
    thing. The halves are scoped by attribute inside `.mini`, and the tokens they
    are scoped with are generated from the same data as the presets themselves --
    so what the owner is choosing between is what they will get."""
    components = (APP / "static" / "css" / "components.css").read_text(encoding="utf-8")
    mini = [line for line in components.splitlines() if line.strip().startswith(".mini")]
    read = {name for line in mini for name in re.findall(r"var\((--[\w-]+)\)", line)}
    # Only what a preset may change. The spacing a face is padded with is the same
    # in all seven -- a preset states colour and construction and nothing else
    # (section 6) -- so restating it on every half would say nothing.
    settable = {f"--{key}" for key in PALETTES["keys"]}
    settable |= {f"--{key}" for c in PALETTES["construction"].values() for key in c}
    wanted = read & settable
    assert wanted, "the .mini rules read no token a preset can change; this checks nothing"
    tokens = (APP / "static" / "css" / "tokens.css").read_text(encoding="utf-8")
    for preset in PALETTES["presets"]:
        for mode in ("light", "dark"):
            head = f'.mini [data-preset="{preset}"][data-theme="{mode}"]'
            assert head in tokens, f"no face rule for {preset} in {mode}"
            block = tokens.split(head, 1)[1].split("}", 1)[0]
            missing = {name for name in wanted if f"{name}:" not in block}
            assert missing == set(), f"{preset}-{mode}'s face does not state {sorted(missing)}"


def stops(gradient: str) -> list[tuple[str, float, float]]:
    """A gradient's colour stops as (colour, where it starts, where it ends) in px, so
    `var(--stripe-2) 14.5px 27.5px` is stripe-2 from 14.5 to 27.5. The first argument
    is the direction and is left out."""
    inner = gradient[gradient.index("(") + 1 : gradient.rindex(")")]
    arguments, depth, current = [], 0, ""
    for ch in inner + ",":
        depth += (ch == "(") - (ch == ")")
        if ch == "," and not depth:
            arguments.append(current.strip())
            current = ""
        else:
            current += ch
    found = []
    for stop in arguments[1:]:
        colour, *positions = stop.split()
        assert positions, f"{stop} does not say where it is, so its edges cannot be read"
        found.append(
            (
                colour,
                float(positions[0].removesuffix("px")),
                float(positions[-1].removesuffix("px")),
            )
        )
    return found


def test_the_flash_has_no_hard_edge_between_its_bands():
    """The flash is slanted, and the line between two of its bands is not the edge of
    a shape but a change of colour inside one gradient. A browser smooths a shape's
    edges and not a gradient's, so on a slant a hard stop is drawn as a staircase: at
    25 degrees a step every two rows and a longer one every seventh or so, which is
    what the eye reads as a jiggle. A pixel of blend smoothed the stair and still
    read a little jagged on staging, so each band runs into the next over 4px, the
    way neighbouring colours do on a screen, and keeps a solid middle of its own."""
    flashes = {
        preset: values["flash"]
        for preset, values in PALETTES["construction"].items()
        if values.get("flash", "none") != "none"
    }
    assert flashes, "no preset draws a flash; this checks nothing"
    for preset, flash in flashes.items():
        bands = stops(flash)
        hard = [
            f"{colour} to {after} at {ends:g}px"
            for (colour, _, ends), (after, starts, _) in pairwise(bands)
            if starts - ends < 4
        ]
        assert hard == [], f"{preset}'s flash changes colour in less than 4px"


def test_the_banner_s_flash_and_a_panel_s_are_slanted_alike():
    """The design draws one flash -- four bands slanted 25 degrees, at the end of the
    banner's rule and of every panel's title band, all on one vertical line. The
    panels' were slanted and the banner's stood upright, which made two of it: four
    flat blocks under the banner, and bars on the panels below."""
    flashes = (".stripe::after", ".panel > header::after")
    slants = {
        selector: value
        for selector, prop, value in declarations(COMPONENTS)
        if selector in flashes and prop == "transform"
    }
    assert slants == dict.fromkeys(flashes, "skewX(-25deg)")
