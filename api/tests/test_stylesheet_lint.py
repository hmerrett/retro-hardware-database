"""The component stylesheets hold to the tokens, and the utilities to layout.

components.css and utilities.css are the v0.2 stylesheets (ADR-0031). Their promise
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


# The one rule that paints the band with nothing written on it: the preset
# picker's miniature, where a strip of band is a drawing of a panel's title.
WORDLESS_BAND = {".mini .b"}


def test_a_rule_that_fills_with_the_band_says_what_is_written_on_it():
    """A v0.2 band may be dark -- black in Rubber Key, brown in Breadbin -- and only
    `band-text` and `band-muted` are held to it. The files list's filter painted the
    band and left its words to inherit `text`, which came to 1.06:1 in one look and
    under 2.5:1 in four more, with the one pair anybody had computed being the
    default look's. The fill and the text on it are one decision, as the accent's
    are (accessibility-standards), and belong in one rule."""
    silent = [
        " ".join(head.split())
        for head, body in re.findall(r"([^{}@;]+)\{([^{}]*)\}", text(COMPONENTS))
        if re.search(r"background(?:-color)?\s*:[^;]*var\(--band\)", body)
        and " ".join(head.split()) not in WORDLESS_BAND
        and not re.search(r"(?:^|[;\s])color\s*:\s*var\(--band-(?:text|muted)\)", body)
    ]
    assert silent == [], "these fill with the band but do not write in band-text or band-muted"


def test_the_one_wordless_band_is_still_there():
    """An exception nothing needs any more is a hole left open for the next one."""
    painted = {
        " ".join(head.split())
        for head, body in re.findall(r"([^{}@;]+)\{([^{}]*)\}", text(COMPONENTS))
        if re.search(r"background(?:-color)?\s*:[^;]*var\(--band\)", body)
    }
    assert WORDLESS_BAND - painted == set()


APP = CSS.parent.parent
TEMPLATES = APP / "templates"


def test_the_design_system_is_the_whole_of_the_styling():
    """The look is the token files, components.css, utilities.css and the generated
    /style/data.css: one vocabulary, and no second stylesheet outranking it. app.css
    held 0.1's rules while the pages moved over, and the v0.2 files sat in a cascade
    layer beneath it so that its rules won wherever a class name was shared."""
    assert not (CSS.parent / "app.css").exists()
    linked = "".join(t.read_text(encoding="utf-8") for t in TEMPLATES.rglob("*.html"))
    assert "app.css" not in linked
    assert "main_class" not in linked
    for path in (COMPONENTS, UTILITIES):
        assert "@layer" not in text(path), f"{path.name} is still inside a layer"


# Classes that draw nothing on purpose, each a name a rule could be written for and
# is not. Most are how a script finds its element; the rest are states the
# stylesheet has nothing to say about.
HOOKS = {
    # app.js: the full-size view's tool forms, the share, reload and theme buttons,
    # and every button that opens the scanner.
    "lb-act",
    "js-share",
    "js-reload",
    "js-theme",
    "scan-open",
    # part-form.js: the questions a kind of part asks, shown for that kind alone.
    "ask",
    # storage.js: the words of the audit's panel, rewritten with each scan.
    "words",
    # The figures' coverage line, which test_api.py reads the counts out of.
    "cover",
    # The audit's panel before anything is scanned, which is the panel as drawn.
    "tone-idle",
    # The tab an item page is on. Only Details changes anything (the photographs
    # come with it on a phone); the others are said so a rule could ask.
    "on-files",
    "on-history",
    "on-work",
}


def written_classes(page: str) -> set[str]:
    return {c for value in re.findall(r'\sclass="([^"]*)"', page) for c in value.split()}


def literal_classes(template: str) -> set[str]:
    """The classes a template writes in words, outside any `{{ }}` or `{% %}`: the
    ones a page might not render on the day the suite looks."""
    found = set()
    for value in re.findall(r'\sclass="([^"]*)"', template):
        # A name built round an expression -- `tone-{{ t }}` -- is the page's to say.
        bare = re.sub(r"\{\{.*?\}\}|\{%.*?%\}", "\0", value)
        found |= {c for c in bare.split() if re.fullmatch(r"-?[a-zA-Z_][\w-]*", c)}
    return found


def script_classes() -> set[str]:
    """What the scripts put on an element by name: classList calls and className."""
    found = set()
    for path in (APP / "static").glob("*.js"):
        js = path.read_text(encoding="utf-8")
        for args in re.findall(r"classList\.(?:add|remove|toggle|contains)\(([^)]*)\)", js):
            found |= set(re.findall(r"['\"]([\w-]+)['\"]", args))
        for value in re.findall(r"className\s*=\s*['\"]([^'\"]*)['\"]", js):
            found |= set(value.split())
        for value in re.findall(r'class="([^"$]*)"', js):
            found |= set(value.split())
    # `'tone-' + said.tone` is a name the script finishes with a value.
    return {c for c in found if not c.endswith("-")}


def drawn_classes() -> set[str]:
    from app.datacss import DATA_CSS

    sheets = text(COMPONENTS) + text(UTILITIES) + DATA_CSS
    heads = "".join(re.findall(r"([^{}]+)\{", sheets))
    return set(re.findall(r"\.(-?[a-zA-Z_][\w-]*)", heads))


def test_every_class_a_template_writes_is_drawn_or_is_a_hook(client, a_page_of_everything):
    """A class nothing draws is a promise the page makes and the stylesheet does not
    keep: `.flex` and `.srow` were written into the file pages and drew nothing,
    because the rules they named had been 0.1's and gone with its stylesheet. Read
    from the pages as rendered, from what the templates write in words, and from
    what the scripts add."""
    written = set()
    for path in a_page_of_everything:
        written |= written_classes(client.get(path).text)
    for template in TEMPLATES.rglob("*.html"):
        written |= literal_classes(template.read_text(encoding="utf-8"))
    written |= script_classes()
    undrawn = sorted(written - drawn_classes() - HOOKS)
    assert undrawn == [], f"these classes are written and nothing draws them: {undrawn}"


def test_every_hook_is_still_written(client, a_page_of_everything):
    """A hook nothing writes any more is a hole left open for the next one."""
    written = set()
    for path in a_page_of_everything:
        written |= written_classes(client.get(path).text)
    for template in TEMPLATES.rglob("*.html"):
        written |= literal_classes(template.read_text(encoding="utf-8"))
    assert HOOKS - written - script_classes() == set()
