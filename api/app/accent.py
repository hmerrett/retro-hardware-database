"""The installation's accent: one colour in, the five the page is painted with out.

An accent has four jobs, and they pull against each other. It fills the primary
button and has to carry white or near-black writing across it; it is read as a link
on three different shades of page; it shows as a bar against a track made of
itself; and it draws the ring round whatever the Tab key has reached. No single
colour does all four in every preset -- a yellow that is right on a button is
invisible as a link on white -- so the setting takes one colour and this module
works the rest out from it, for the preset and the mode in force.

Two rules decide what may move. The **fill keeps the chosen colour exactly**
wherever it can, because the button is where an accent is recognised and an
approximation of somebody's brand colour is not their brand colour. The **link and
the ring move in lightness alone**: the hue is never touched, so what comes back is
lighter or darker but never a different colour wearing the same name.

Why it may be a free-for-all rather than a menu of eight: the derivation is a pure
function of the colour and the preset's own surfaces, and `test_accent.py` sweeps
1,260 colours across the whole space through all fourteen presets-and-modes and
asserts the nine pairs on every one of them (ADR-0028). An input nobody has looked
at, an output somebody has.

It is computed here, on the server, and served as one more stylesheet. Nothing is
worked out in the browser and no value reaches the markup: a `style` attribute is
what the content policy stopped allowing (ADR-0022), and a colour is data about the
installation rather than an instruction in a page.
"""

from __future__ import annotations

import colorsys
import json
from collections.abc import Callable, Mapping
from functools import lru_cache
from pathlib import Path

DESIGN = Path(__file__).parent / "design"

# The five an accent decides, and the whole of what this module may write. A sixth
# would be a token whose contrast nothing has checked.
TOKENS: tuple[str, ...] = ("accent", "accent-fill", "on-accent", "accent-track", "focus")

# The two answers for writing on a fill. Near-black rather than black: the register
# writes nothing in pure black, and a button would be the only place it did.
WHITE = "#ffffff"
INK = "#111111"

# The eight offered by name, and the label each goes by. They are the colours the
# design system's accent table was drawn from; a ninth is a row here and a row
# there, and the sweep already covers the space it would land in.
NAMED: tuple[tuple[str, str], ...] = (
    ("blue", "Blue"),
    ("teal", "Teal"),
    ("green", "Green"),
    ("amber", "Amber"),
    ("red", "Red"),
    ("magenta", "Magenta"),
    ("violet", "Violet"),
    ("slate", "Slate"),
)

BRANDS: dict[str, str] = {
    "blue": "#2563eb",
    "teal": "#0f766e",
    "green": "#15803d",
    "amber": "#b45309",
    "red": "#b91c1c",
    "magenta": "#a21caf",
    "violet": "#6d28d9",
    "slate": "#475569",
}

# What the picker's first face means, and the setting's default: the accent the
# chosen preset brings with it. A word rather than an empty string, because it is
# spent as the value of a radio button and on the face's own attribute.
AS_PRESET = "preset"

CHOICES: tuple[tuple[str, str], ...] = ((AS_PRESET, "As the preset"), *NAMED)

# Text holds 4.5:1 and anything merely drawn holds 3:1 -- the same two floors the
# presets' own colours are held to in test_presets.py, and the reason a derived
# accent can be judged by the same list of pairs as a designed one.
TEXT, EDGE = 4.5, 3.0

# The track is the fill laid over the page at a sixth of its strength. Stated as a
# mix rather than as a colour of its own so it follows the fill wherever the fill
# is moved to.
TRACK_ALPHA = 0x29


@lru_cache(maxsize=1)
def _palettes() -> dict[str, dict[str, dict[str, str]]]:
    """The design data, read once. The same file the stylesheets are generated
    from: a second copy of a preset's surfaces here would be the one that went
    stale, and the contrast it was judged on would be the stale one's."""
    data = json.loads((DESIGN / "palettes.json").read_text(encoding="utf-8"))
    themes = {
        name: {key: str(value) for key, value in colours.items()}
        for name, colours in data["themes"].items()
    }
    return {"themes": themes}


def theme_name(preset: str, mode: str) -> str:
    """Which block of the design data paints this preset in this mode. The default
    preset's two are simply `light` and `dark` -- they are the values `tokens.css`
    states on the root, and have no name of their own."""
    return mode if preset == "default" else f"{preset}-{mode}"


def colours(preset: str, mode: str) -> dict[str, str]:
    return dict(_palettes()["themes"][theme_name(preset, mode)])


# ---- Colour arithmetic ------------------------------------------------------


def _channels(colour: str) -> tuple[float, float, float]:
    digits = colour.strip().lstrip("#")
    if len(digits) == 3:
        digits = "".join(d * 2 for d in digits)
    return (
        int(digits[0:2], 16) / 255,
        int(digits[2:4], 16) / 255,
        int(digits[4:6], 16) / 255,
    )


def hsl(colour: str) -> tuple[float, float, float]:
    """A colour as hue in degrees, saturation and lightness, each 0-1 but the hue."""
    r, g, b = _channels(colour)
    hue, lightness, saturation = colorsys.rgb_to_hls(r, g, b)
    return hue * 360.0, saturation, lightness


def from_hsl(hue: float, saturation: float, lightness: float) -> str:
    """The other way, rounded to what a screen can actually show."""
    r, g, b = colorsys.hls_to_rgb((hue % 360.0) / 360.0, lightness, saturation)
    return f"#{round(r * 255):02x}{round(g * 255):02x}{round(b * 255):02x}"


@lru_cache(maxsize=4096)
def luminance(colour: str) -> float:
    """WCAG 2 relative luminance. Cached: the surfaces are asked for again on every
    candidate a search tries, and a sweep tries a great many."""
    out = []
    for c in _channels(colour):
        out.append(c / 12.92 if c <= 0.04045 else ((c + 0.055) / 1.055) ** 2.4)
    r, g, b = out
    return 0.2126 * r + 0.7152 * g + 0.0722 * b


def ratio(one: str, two: str) -> float:
    a, b = luminance(one), luminance(two)
    return (max(a, b) + 0.05) / (min(a, b) + 0.05)


def over(colour: str, alpha: int, under: str) -> str:
    """`colour` at `alpha` (0-255) painted on an opaque `under`, as a browser mixes
    it. The same arithmetic the suite composites the translucent tokens with."""
    weight = alpha / 255
    r, g, b = (
        round((weight * top + (1 - weight) * bottom) * 255)
        for top, bottom in zip(_channels(colour), _channels(under), strict=True)
    )
    return f"#{r:02x}{g:02x}{b:02x}"


# ---- The search -------------------------------------------------------------

# How finely lightness is searched. 1/256 is a step no screen can show as two
# colours, so a nearer answer than this one does not exist to be found.
STEP = 1 / 256


def _nearest(brand: str, ok: Callable[[str], bool]) -> str:
    """The colour nearest `brand` in lightness alone that `passes`, or the brand
    itself when it already does.

    Contrast against a fixed ground rises as a colour moves away from that ground's
    lightness and falls as it moves towards it, so the lightnesses that pass are a
    band at the dark end and a band at the light end with the failures between. That
    is what makes a binary search safe: the answer is found by halving towards
    whichever end passes, from both directions, and the nearer of the two is taken.

    The result is checked before it is returned all the same. The conjunction the
    fill is judged by -- readable on the page *and* able to carry writing -- is not
    quite the single monotone step the halving assumes, and a search that lands on
    a colour that fails is a worse answer than the far end that does not.
    """
    if ok(brand):
        return brand
    hue, saturation, start = hsl(brand)

    def candidate(lightness: float) -> str:
        return from_hsl(hue, saturation, min(1.0, max(0.0, lightness)))

    best: str | None = None
    for end in (0.0, 1.0):
        if not ok(candidate(end)):
            continue
        # Halve between the failing start and the passing end until the two are a
        # step apart; `near` is the last failure, so the answer is just past it.
        near, far = start, end
        while abs(far - near) > STEP:
            middle = (near + far) / 2
            if ok(candidate(middle)):
                far = middle
            else:
                near = middle
        found = candidate(far)
        if ok(found) and (best is None or abs(far - start) < abs(hsl(best)[2] - start)):
            best = found
    if best is not None:
        return best
    # Nothing between the brand and either end passed. Whichever end reads better
    # is still an answer, and a wrong-looking accent is a better failure than an
    # unreadable one -- though the sweep says this does not happen.
    return max((INK, WHITE), key=lambda c: ratio(c, brand))


def _reads_on(surfaces: tuple[str, ...], floor: float) -> Callable[[str], bool]:
    def passes(colour: str) -> bool:
        return all(ratio(colour, surface) >= floor for surface in surfaces)

    return passes


def _fills(page: str) -> Callable[[str], bool]:
    """Whether a colour can be the primary button: it has to stand out from the
    page, stand out from its own track, and carry white or near-black writing."""

    def passes(colour: str) -> bool:
        if ratio(colour, page) < EDGE:
            return False
        if ratio(colour, over(colour, TRACK_ALPHA, page)) < EDGE:
            return False
        return max(ratio(WHITE, colour), ratio(INK, colour)) >= TEXT

    return passes


@lru_cache(maxsize=8192)
def _derive(brand: str, surface: str, raised: str, sunken: str) -> tuple[tuple[str, str], ...]:
    surfaces = (surface, raised, sunken)
    fill = _nearest(brand, _fills(surface))
    on = WHITE if ratio(WHITE, fill) >= ratio(INK, fill) else INK
    return (
        ("accent", _nearest(brand, _reads_on(surfaces, TEXT))),
        ("accent-fill", fill),
        ("on-accent", on),
        ("accent-track", over(fill, TRACK_ALPHA, surface)),
        ("focus", _nearest(brand, _reads_on(surfaces, EDGE))),
    )


def derive(brand: str, palette: Mapping[str, str]) -> dict[str, str]:
    """The five tokens `brand` becomes on a page painted in `palette`.

    Pure, and cached on its four inputs: a page draws nine faces and its own set,
    which is eighteen derivations of the same handful of colours.
    """
    return dict(
        _derive(
            brand.strip().lower(),
            palette["surface"],
            palette["surface-raised"],
            palette["surface-sunken"],
        )
    )


# ---- The stylesheet ---------------------------------------------------------

HEADER = (
    "/* Generated by app/accent.py from the accent setting -- one colour, worked out\n"
    "   for the preset in force. Nothing writes it to disk: it is built per answer\n"
    "   and served from memory, because the answer is a row in the database. */\n"
)


def _decls(values: Mapping[str, str], indent: str = "  ") -> str:
    return "".join(f"{indent}--{name}: {value};\n" for name, value in values.items())


def _faces(preset: str, tokens: tuple[str, ...]) -> str:
    """The picker's nine faces: each one a real button and a real link in the accent
    it offers, derived for the preset in force.

    Scoped inside `.accents` so none of these can reach the document element, the
    way the preset picker's miniatures are. The first face states the preset's own
    accent rather than inheriting, because once an accent has been chosen the page
    around it is painted in that one, and a face left to inherit would show the
    chosen colour on the button offering to go back.
    """
    out = []
    for mode, prefix in (
        ("light", ""),
        ("dark", ':root[data-theme="dark"] '),
        ("dark", "@media"),
    ):
        palette = colours(preset, mode)
        rules = []
        for name in (AS_PRESET, *(key for key, _ in NAMED)):
            derived = (
                {token: palette[token] for token in tokens}
                if name == AS_PRESET
                else {token: derive(BRANDS[name], palette)[token] for token in tokens}
            )
            head = f'.accents [data-accent="{name}"]'
            if prefix == "@media":
                rules.append(
                    f"  :root:not([data-theme]) {head} {{\n" + _decls(derived, "    ") + "  }\n"
                )
            else:
                rules.append(f"{prefix}{head} {{\n" + _decls(derived) + "}\n")
        if prefix == "@media":
            out.append("@media (prefers-color-scheme: dark) {\n" + "".join(rules) + "}\n")
        else:
            out.extend(rules)
    return "".join(out)


@lru_cache(maxsize=64)
def stylesheet(preset: str, brand: str) -> str:
    """The whole of what an accent puts on the page: the tokens themselves when one
    has been chosen, and the picker's faces either way.

    The selectors are the ones the preset's own file uses, so this outranks nothing
    and nothing outranks it -- the two are the same weight, and the link that comes
    second wins, which `base.html` is what decides. The dark block is written twice,
    once for a reader who chose dark and once for a device that chose it for them,
    from one dictionary so the two cannot drift (accessibility-standards).
    """
    root = ":root" if preset == "default" else f':root[data-preset="{preset}"]'
    out = [HEADER]
    if brand:
        light = derive(brand, colours(preset, "light"))
        dark = derive(brand, colours(preset, "dark"))
        out.append(f"{root} {{\n" + _decls(light) + "}\n")
        out.append(f'{root}[data-theme="dark"] {{\n' + _decls(dark) + "}\n")
        out.append(
            "@media (prefers-color-scheme: dark) {\n"
            + f"  {root}:not([data-theme]) {{\n"
            + _decls(dark, "    ")
            + "  }\n}\n"
        )
    out.append(_faces(preset, ("accent-fill", "accent")))
    return "".join(out)


def known(name: str) -> str:
    """`name` if it is one of the answers the picker offers, and the preset's own
    if it is not. Every reading of the setting goes through here: the value is
    spent on a colour written into a stylesheet, and a row nobody on this page
    wrote should come back as no accent rather than as whatever it says."""
    return name if name in BRANDS else AS_PRESET


def custom(value: str) -> str:
    """A colour of the owner's own, normalised, or empty if it is not one.

    Six hexadecimal digits behind a `#` and nothing else -- not a colour name, not
    a three-digit short form, and certainly not a URL. This is read on the way out
    as well as checked on the way in, because the row can also have been written
    before the check existed.
    """
    text = value.strip().lower()
    if len(text) == 7 and text[0] == "#" and all(c in "0123456789abcdef" for c in text[1:]):
        return text
    return ""
