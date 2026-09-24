"""The component stylesheets hold to the tokens, and the utilities to layout.

components.css and utilities.css are the v0.2 stylesheets (ADR-0030). Their promise
is that a preset is only token values: a colour stated here would be a colour no
preset could change and no contrast test would read, and a spacing figure stated
here would be one the scale no longer describes. These tests read the files the
browser gets, as test_stylesheet.py does, since there is no rendered page to ask.
"""

import re
from pathlib import Path

import pytest

CSS = Path(__file__).parents[1] / "app" / "static" / "css"
COMPONENTS = CSS / "components.css"
UTILITIES = CSS / "utilities.css"
LEGACY = CSS.parent / "app.css"

# The CSS named colours, less `transparent` and `currentcolor`, which name no hue.
NAMED = frozenset(
    re.findall(
        r"\w+",
        """
        aliceblue antiquewhite aqua aquamarine azure beige bisque black blanchedalmond
        blue blueviolet brown burlywood cadetblue chartreuse chocolate coral
        cornflowerblue cornsilk crimson cyan darkblue darkcyan darkgoldenrod darkgray
        darkgreen darkgrey darkkhaki darkmagenta darkolivegreen darkorange darkorchid
        darkred darksalmon darkseagreen darkslateblue darkslategray darkslategrey
        darkturquoise darkviolet deeppink deepskyblue dimgray dimgrey dodgerblue
        firebrick floralwhite forestgreen fuchsia gainsboro ghostwhite gold goldenrod
        gray green greenyellow grey honeydew hotpink indianred indigo ivory khaki
        lavender lavenderblush lawngreen lemonchiffon lightblue lightcoral lightcyan
        lightgoldenrodyellow lightgray lightgreen lightgrey lightpink lightsalmon
        lightseagreen lightskyblue lightslategray lightslategrey lightsteelblue
        lightyellow lime limegreen linen magenta maroon mediumaquamarine mediumblue
        mediumorchid mediumpurple mediumseagreen mediumslateblue mediumspringgreen
        mediumturquoise mediumvioletred midnightblue mintcream mistyrose moccasin
        navajowhite navy oldlace olive olivedrab orange orangered orchid palegoldenrod
        palegreen paleturquoise palevioletred papayawhip peachpuff peru pink plum
        powderblue purple rebeccapurple red rosybrown royalblue saddlebrown salmon
        sandybrown seagreen seashell sienna silver skyblue slateblue slategray slategrey
        snow springgreen steelblue tan teal thistle tomato turquoise violet wheat white
        whitesmoke yellow yellowgreen
        """,
    )
)
COLOUR_FUNCTION = re.compile(
    r"#[0-9a-fA-F]{3,8}\b|\b(?:rgba?|hsla?|hwb|lab|lch|oklab|oklch|color)\("
)

# Spacing is what the scale is for: the gaps, the padding, the corners and the
# rules. A component's own geometry -- an icon's size, a thumbnail's width, a grid
# track's minimum -- is a dimension of that component and is not checked here.
SPACING = re.compile(r"^(?:margin|padding|gap|row-gap|column-gap|border|outline)(?:-[\w-]+)?$")
ON_SCALE = {"0", "0px", "1px"}
# The honest exceptions, each with the reason it is not a token.
OFF_SCALE = {
    # A row's vertical padding -- key-value lines, table cells, menu items, a
    # panel's band, a suggestion, a task -- and the gap between ranked bars. It sits
    # between space-2 and space-3 on purpose: a dense list stays dense.
    "6px": "a row's vertical padding",
    # Packed things: the yellowing ladder's swatches and a model's row in the
    # catalogue, which would read as separate items at space-2.
    "3px": "the swatch ladder and the model rows",
    # The preset picker's miniature is a page drawn at a fifth of its size.
    "5px": "the preset miniature",
    # The heavy rules that have to be seen over a photograph or as a target -- the
    # drop zone, the crop box, the scan reticle -- and the search highlight's corner,
    # which is under radius-xs because it sits inside a line of text.
    "2px": "a heavy rule, and a highlight's corner",
    # The ring of the "!" beside a form error: 1px vanishes at 16px, 2px fills it.
    "1.5px": "the error mark's ring",
}
# What a utility may not set: anything that would put a colour, a face or an edge
# on the page, and so a pair into the contrast matrix.
NOT_LAYOUT = re.compile(r"^(?:color|background|border|font|box-shadow)(?:-[\w-]+)?$")


def text(path: Path) -> str:
    return re.sub(r"/\*.*?\*/", "", path.read_text(encoding="utf-8"), flags=re.S)


def declarations(path: Path) -> list[tuple[str, str, str]]:
    """Every (selector, property, value) in the file, out of any @media or @layer."""
    found = []
    for head, body in re.findall(r"([^{}@;]+)\{([^{}]*)\}", text(path)):
        for line in body.split(";"):
            if ":" in line:
                prop, value = line.split(":", 1)
                found.append((" ".join(head.split()), prop.strip().lower(), value.strip()))
    return found


@pytest.mark.parametrize("path", [COMPONENTS, UTILITIES], ids=lambda p: p.name)
def test_no_colour_is_stated_outside_the_token_files(path):
    """A colour written into a component is one no preset can change and no
    contrast test reads. Every colour is a token, stated in tokens.css or a preset
    file, where the contrast tests find it."""
    stated = [
        f"{selector} {{ {prop}: {value} }}"
        for selector, prop, value in declarations(path)
        if not prop.startswith("--")
        and (COLOUR_FUNCTION.search(value) or NAMED & set(re.findall(r"[a-z]+", value.lower())))
    ]
    assert stated == [], "these state a colour rather than naming a token"


def test_the_spacing_is_on_the_scale():
    """Every gap, padding, corner and rule is a token, 0, 1px, or a named
    exception with its reason. A new figure is either a step the scale
    already has -- and so a `var()` -- or an exception that argues its case in
    OFF_SCALE."""
    off = [
        f"{selector} {{ {prop}: {value} }}"
        for selector, prop, value in declarations(COMPONENTS)
        if SPACING.match(prop)
        for figure in re.findall(r"(?<![\w.-])(\d*\.?\d+px)", value)
        if figure not in ON_SCALE and figure not in OFF_SCALE
    ]
    assert off == [], "these space things by a figure the scale does not have"


def test_every_exception_to_the_scale_is_still_used():
    """An exception nothing needs any more is a hole left open for the next one."""
    used = {
        figure
        for _, prop, value in declarations(COMPONENTS)
        if SPACING.match(prop)
        for figure in re.findall(r"(?<![\w.-])(\d*\.?\d+px)", value)
    }
    assert set(OFF_SCALE) - used == set()


def test_a_utility_carries_layout_only():
    """utilities.css is for one-off arrangement. A utility that sets a colour, a
    face, an edge or a shadow is a component in hiding, and one that the contrast
    matrix would never hear about."""
    styled = [
        f"{selector} {{ {prop}: {value} }}"
        for selector, prop, value in declarations(UTILITIES)
        if NOT_LAYOUT.match(prop)
    ]
    assert styled == [], "these utilities do more than lay things out"


@pytest.mark.parametrize("path", [COMPONENTS, UTILITIES], ids=lambda p: p.name)
def test_while_app_css_is_here_it_outranks_the_new_stylesheets(path):
    """The templates move over a group at a time, and until a group has moved its
    0.1 rules have to win wherever a class name is shared -- .btn, .panel and fifty
    more. A cascade layer does that whatever the specificity; this holds the
    stylesheets inside it until app.css is deleted, when the layer comes off."""
    if not LEGACY.exists():
        pytest.skip("app.css has gone, and the layer with it")
    body = text(path).strip()
    assert body.startswith("@layer v2 {") and body.endswith("}")


def test_a_bare_0_1_rule_lets_every_tone_past_it():
    """0.1's `.banner` is kept for the one template still writing the class bare,
    and is written as a `:not()` list so a migrated page's toned banner falls
    through to components.css. Every tone has to be in the list: `:not(.warning)`
    alone let the rule take `banner danger` as well, and its `display: block` cost
    the lead and the sentence beside it the gap the flex row puts between them --
    on the login page, the delete confirmation, /projects and the project form,
    all at once and in none of their own tests."""
    if not LEGACY.exists():
        pytest.skip("app.css has gone, and the transitional rules with it")
    rule = next(line for line in text(LEGACY).splitlines() if line.lstrip().startswith(".banner"))
    for tone in ("warning", "danger", "success", "toast"):
        assert f":not(.{tone})" in rule, tone
