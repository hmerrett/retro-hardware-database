"""Behaviour carried by the stylesheets rather than by one rendered page.

Two invariants that a read-through keeps missing. Both are checked against the
declarations themselves because that is where the behaviour lives: no page can be
asked what size iOS thinks its search box is, or what contrast a button's text
has against its own background.
"""

import json
import re
from pathlib import Path

import pytest

APP = Path(__file__).parents[1] / "app"
COMPONENTS = APP / "static" / "css" / "components.css"
# Where the colours live: generated from the design data (ADR-0031).
TOKENS = APP / "static" / "css" / "tokens.css"
PALETTES = json.loads((APP / "design" / "palettes.json").read_text(encoding="utf-8"))
THEMES = sorted(PALETTES["themes"])

# A file picker shows a button, not text you type into, so its deliberate
# `font-size: 0` is not a control that can zoom the page.
NOT_TYPED_INTO = re.compile(r"input\[type=file\]")


def css(path: Path = COMPONENTS) -> str:
    """A stylesheet with its comments removed, which otherwise match as rules."""
    return re.sub(r"/\*.*?\*/", "", path.read_text(encoding="utf-8"), flags=re.S)


def rules(text: str) -> list[tuple[str, str]]:
    """Every `selector { body }` pair, ignoring the `@media` wrappers themselves."""
    return [(head.strip(), body) for head, body in re.findall(r"([^{}@]+)\{([^{}]*)\}", text)]


def selectors(head: str) -> list[str]:
    return [s.strip() for s in head.replace("\n", " ").split(",") if s.strip()]


def touch_rules() -> list[tuple[str, str]]:
    """Every rule in components.css's `@media (pointer: coarse)` blocks: one for the
    controls, and a line or two beside the components that size their own."""
    blocks = re.findall(
        r"@media\s*\(pointer:\s*coarse\)\s*\{((?:[^{}]|\{[^{}]*\})*)\}", css(COMPONENTS)
    )
    assert blocks, "the coarse-pointer blocks have gone; touch devices zoom without them"
    return rules("\n".join(blocks))


def test_every_control_given_its_own_size_is_listed_for_touch():
    """iOS zooms the page when it focuses a control whose text is under 16px, and
    does not zoom back out. The stylesheet answers that with one coarse-pointer
    block, but a rule that names a control through a class outranks the bare
    `input` in it -- so every such rule has to be restated there, and the ones
    added since were not. Anything that sizes a control belongs in that list."""
    sized = {
        selector
        for head, body in rules(css(COMPONENTS))
        if re.search(r"(?:^|[;\s])font(?:-size)?\s*:", body)
        for selector in selectors(head)
        if re.search(r"\b(?:input|select|textarea)\b", selector)
        and not NOT_TYPED_INTO.search(selector)
    }
    listed = {
        selector
        for head, body in touch_rules()
        if re.search(r"font-size\s*:\s*16px", body)
        for selector in selectors(head)
    }
    assert sized - listed == set(), (
        "these rules size a control but are not in the coarse-pointer block, so a "
        "phone will zoom the page when one is tapped"
    )


def test_a_bare_box_is_16px_on_a_phone_too():
    """Every box the templates write today carries `.input` or `.select`, which the
    list above covers. A box without one -- written by a script, or by the next
    template -- would zoom the page all the same, so the element itself is listed."""
    listed = {
        selector
        for head, body in touch_rules()
        if re.search(r"font-size\s*:\s*16px", body)
        for selector in selectors(head)
    }
    assert {"input", "select", "textarea"} <= listed


def declarations(text: str, head: str) -> dict[str, str]:
    """The custom properties in the first block whose selector is exactly `head`."""
    block = re.search(re.escape(head) + r"\s*\{(.*?)\}", text, re.S)
    assert block, f"the {head} variable block has gone"
    return dict(re.findall(r"(--[\w-]+)\s*:\s*([^;]+?)\s*;", block.group(1)))


def tokens_css() -> str:
    return re.sub(r"/\*.*?\*/", "", TOKENS.read_text(encoding="utf-8"), flags=re.S)


def luminance(colour: str) -> float:
    """Relative luminance of a `#rgb`/`#rrggbb` colour, per WCAG 2."""
    digits = colour.strip().lstrip("#")
    if len(digits) == 3:
        digits = "".join(d * 2 for d in digits)
    assert len(digits) == 6, f"expected an opaque hex colour, got {colour!r}"
    channels = []
    for pair in (digits[0:2], digits[2:4], digits[4:6]):
        c = int(pair, 16) / 255
        channels.append(c / 12.92 if c <= 0.04045 else ((c + 0.055) / 1.055) ** 2.4)
    r, g, b = channels
    return 0.2126 * r + 0.7152 * g + 0.0722 * b


def contrast(one: str, two: str) -> float:
    a, b = luminance(one), luminance(two)
    lighter, darker = max(a, b), min(a, b)
    return (lighter + 0.05) / (darker + 0.05)


@pytest.mark.parametrize("theme", THEMES)
def test_a_primary_button_reads_against_its_own_fill(theme):
    """The dark theme's accent is a light blue, chosen to carry on a dark page.
    White text on it came to 2.4:1 -- readable to whoever picked the colour and
    to nobody at arm's length on a phone. The pair has to hold in every look."""
    colours = PALETTES["themes"][theme]
    ratio = contrast(colours["on-accent"], colours["accent-fill"])
    assert ratio >= 4.5, f"primary button text on its fill is {ratio:.1f}:1 in {theme}"


@pytest.mark.parametrize("theme", THEMES)
def test_a_danger_control_reads_against_the_page(theme):
    """The register's warning colour is a brown picked for a white page; on the
    dark one it fell to 3.7:1 against the background it sits on."""
    colours = PALETTES["themes"][theme]
    ratio = contrast(colours["danger"], colours["surface"])
    assert ratio >= 4.5, f"danger text on the page is {ratio:.1f}:1 in {theme}"


def test_the_two_dark_theme_blocks_agree():
    """Dark is declared twice: for the system preference and for the explicit
    toggle. A colour fixed in one and forgotten in the other gives a reader whose
    Mac is set to light and site to dark a different page from everyone else.
    Both are generated from one dictionary now (tools/build_presets.py), and this
    still reads the file, because the file is what the browser gets."""
    preferred = re.search(
        r"@media\s*\(prefers-color-scheme:\s*dark\)\s*\{\s*"
        r":root:not\(\[data-theme\]\)\s*\{(.*?)\}",
        tokens_css(),
        re.S,
    )
    assert preferred, "the prefers-color-scheme dark block has gone"
    by_preference = dict(re.findall(r"(--[\w-]+)\s*:\s*([^;]+?)\s*;", preferred.group(1)))
    assert by_preference == declarations(tokens_css(), ':root[data-theme="dark"]')


# The accent fills that carry no words: a bar's length, an upload's progress, the
# preset picker's drawing of an accent, and the swatch beside an accent's name.
WORDLESS_FILLS = {".bars .fill", ".up .meter > i", ".mini .a", ".accents .demo .dot"}


def test_an_accent_fill_states_the_text_colour_on_it():
    """A rule that fills something with the accent and leaves the foreground to be
    inherited gets whatever the surrounding rule set, which in the lightbox was a
    fixed white -- unreadable once the dark theme made the accent a pale blue. The
    fill and the text on it are one decision and belong in one rule."""
    silent = [
        " ".join(head.split())
        for head, body in rules(css())
        if re.search(r"background(-color)?\s*:[^;]*var\(--accent(?:-fill)?\)", body)
        and not re.search(r"(?:^|[;\s])color\s*:", body)
        and " ".join(head.split()) not in WORDLESS_FILLS
    ]
    assert silent == [], (
        "these rules fill with the accent but do not say what colour the text on it is"
    )


def test_every_wordless_fill_is_still_there():
    """An exception nothing needs any more is a hole left open for the next one."""
    filled = {
        " ".join(head.split())
        for head, body in rules(css())
        if re.search(r"background(-color)?\s*:[^;]*var\(--accent(?:-fill)?\)", body)
    }
    assert WORDLESS_FILLS - filled == set()


def over(foreground: str, background: str) -> str:
    """`foreground` composited onto an opaque `background`, as the browser paints it.

    The warning wash is a translucent brown, so the colour a reader actually sees
    is neither of the two named in the stylesheet.
    """
    digits = foreground.strip().lstrip("#")
    if len(digits) in (3, 4):
        digits = "".join(d * 2 for d in digits)
    alpha = int(digits[6:8], 16) / 255 if len(digits) == 8 else 1.0
    under = background.strip().lstrip("#")
    if len(under) == 3:
        under = "".join(d * 2 for d in under)
    mixed = []
    for i in (0, 2, 4):
        top, bottom = int(digits[i : i + 2], 16), int(under[i : i + 2], 16)
        mixed.append(round(alpha * top + (1 - alpha) * bottom))
    return "#%02x%02x%02x" % tuple(mixed)


@pytest.mark.parametrize("theme", THEMES)
def test_a_warning_banner_can_be_read(theme):
    """A banner carries the words of a disposal, a rejected form or a refused login
    in the page's own foreground colour. Its wash is faint by design, so what has
    to hold is the reading against the wash as painted, not against the page. The
    rest of the pairs are test_presets.py's, in every look."""
    colours = PALETTES["themes"][theme]
    for wash in ("warning-wash", "danger-wash"):
        painted = (
            over(colours[wash], colours["surface"]) if len(colours[wash]) == 9 else colours[wash]
        )
        ratio = contrast(colours["text"], painted)
        assert ratio >= 4.5, f"banner text is {ratio:.1f}:1 on {wash} in {theme}"
