"""The installation's accent, and the four colours the register works out from it.

An accent is one colour with four jobs: fill a button and carry writing across it,
be read as a link on three shades of page, show as a bar against its own track, and
draw a focus ring that can be seen. No one colour does all four on every preset, so
`app/accent.py` derives five tokens from the one -- and because the setting takes
any `#rrggbb` at all, the derivation has to be right for colours nobody has looked
at. That is what the sweep at the foot of this file is: 1,260 colours across the
whole colour space, through every preset and mode, asserted on all nine pairs.

The nine pairs are not invented here. They are the nine accent rows of `PAIRS` in
`test_presets.py`, which is where the presets' own accents are already held to
them, so a derived accent is held to exactly what a designed one is.
"""

import json
import re
from pathlib import Path

import pytest

from app import accent, main, settings
from test_presets import PAIRS, PALETTES
from test_stylesheet import contrast, over

APP = Path(__file__).parents[1] / "app"

# The nine of the thirty-seven that name a token this module derives. Read off the
# list rather than written out again: an accent pair added to the design is a pair
# the sweep should start asserting without anybody remembering to come here.
DERIVED = set(accent.TOKENS)
ACCENT_PAIRS = [pair for pair in PAIRS if pair[0] in DERIVED or pair[1] in DERIVED]

THEMES = sorted(PALETTES["themes"])


def _theme(name: str) -> dict[str, str]:
    return {key: str(value) for key, value in PALETTES["themes"][name].items()}


def _holds(colours: dict[str, str], derived: dict[str, str]) -> list[str]:
    """Every accent pair that fails, as a sentence each. Empty is the pass."""
    resolved = colours | derived
    bad = []
    for fg, bg, floor in ACCENT_PAIRS:
        ground = over(resolved[bg], colours["surface"]) if len(resolved[bg]) == 9 else resolved[bg]
        ratio = contrast(resolved[fg][:7], ground)
        if ratio < floor:
            bad.append(f"{fg} on {bg} is {ratio:.2f}:1, needing {floor}:1")
    return bad


# ---- What the setting offers ------------------------------------------------


def test_the_accent_setting_offers_the_preset_and_eight_by_name():
    """The preset's own accent and eight named colours, and the first is what a
    fresh install gets: the accent a preset brings is part of the look it is."""
    choices = dict(settings.choices_for(settings.BY_KEY["accent"]))
    assert next(iter(choices)) == "preset"
    assert choices["preset"] == "As the preset"
    assert len(choices) == 9, "the preset's own, and the eight the register offers"
    assert settings.BY_KEY["accent"].default == "preset"


def test_every_offered_accent_is_a_colour_the_register_can_derive_from():
    """A name in the picker with no colour behind it is a face that paints nothing."""
    for key, _ in settings.choices_for(settings.BY_KEY["accent"])[1:]:
        assert re.fullmatch(r"#[0-9a-f]{6}", accent.BRANDS[key]), f"{key} has no brand colour"


def test_your_own_takes_a_hex_colour_and_nothing_else():
    """The box takes any colour written as `#rrggbb`. Anything else is not an
    answer this setting has, and `clean` returning None is what leaves the stored
    value alone rather than overwriting it with a typo."""
    d = settings.BY_KEY["accent_custom"]
    assert settings.clean(d, "#ff8800") == "#ff8800"
    assert settings.clean(d, "  #FF8800  ") == "#ff8800", "case and space are not the answer"
    assert settings.clean(d, "") == "", "emptying it is an answer: it hands back to the eight"
    for rubbish in ("ff8800", "#ff88", "#gggggg", "red", "#ff88000", "javascript:x"):
        assert settings.clean(d, rubbish) is None, f"{rubbish!r} was taken as a colour"


def test_your_own_wins_over_the_eight_and_giving_it_back_is_emptying_it(monkeypatch):
    """Two settings, one answer: the box wins while it has something in it, and the
    named choice is still there underneath when it is emptied."""
    monkeypatch.setattr(settings, "_cache", {"accent": "teal", "accent_custom": "#ff8800"})
    assert settings.accent_brand() == "#ff8800"
    monkeypatch.setattr(settings, "_cache", {"accent": "teal", "accent_custom": ""})
    assert settings.accent_brand() == accent.BRANDS["teal"]
    monkeypatch.setattr(settings, "_cache", {"accent": "preset", "accent_custom": ""})
    assert settings.accent_brand() == "", "as the preset is no accent of our own"


def test_a_stored_accent_the_register_does_not_know_falls_back_to_the_preset(monkeypatch):
    """The value is spent on a colour written into a stylesheet. A row nobody on
    this page wrote comes back as no accent rather than as whatever it says."""
    monkeypatch.setattr(settings, "_cache", {"accent": "chartreuse", "accent_custom": ""})
    assert settings.accent_brand() == ""
    monkeypatch.setattr(settings, "_cache", {"accent": "preset", "accent_custom": "red"})
    assert settings.accent_brand() == ""


# ---- What the derivation promises -------------------------------------------


@pytest.mark.parametrize("theme", THEMES)
@pytest.mark.parametrize("name", [key for key, _ in accent.NAMED])
def test_every_offered_accent_holds_every_pair_in_every_preset_and_mode(name, theme):
    """The eight, in the fourteen: 112 derivations, nine pairs each. This is the
    table in the design system's accent-contrast page, asserted."""
    colours = _theme(theme)
    bad = _holds(colours, accent.derive(accent.BRANDS[name], colours))
    assert bad == [], f"{name} in {theme}: " + "; ".join(bad)


@pytest.mark.parametrize("theme", THEMES)
@pytest.mark.parametrize("name", [key for key, _ in accent.NAMED])
def test_the_button_keeps_the_chosen_colour_exactly_wherever_it_can(name, theme):
    """The manual's promise, and the one that matters: the button is where an
    accent is recognised. So the fill is moved only where the brand colour itself
    could not do the job -- if it holds its own against the page and can carry
    white or near-black writing, it is used exactly as given."""
    colours = _theme(theme)
    brand = accent.BRANDS[name]
    derived = accent.derive(brand, colours)
    if _holds(colours, accent.derive(brand, colours) | {"accent-fill": brand}) == []:
        assert derived["accent-fill"] == brand, "the brand colour would have passed unchanged"


@pytest.mark.parametrize("theme", ["light", "dark", "phosphor-light", "ninetyfive-dark"])
def test_the_hue_is_never_changed(theme):
    """Lighter or darker, and only that. An accent that came back a different hue
    would be a different colour wearing the name of the one that was chosen."""
    colours = _theme(theme)
    for brand in [accent.BRANDS[key] for key, _ in accent.NAMED] + ["#ffcc00", "#00ccff"]:
        want = accent.hsl(brand)[0]
        for token in ("accent", "accent-fill", "focus"):
            got = accent.hsl(accent.derive(brand, colours)[token])
            if got[1] < 0.05 or got[2] in (0.0, 1.0):
                continue  # no hue to speak of at the ends of the scale
            drift = min(abs(got[0] - want), 360 - abs(got[0] - want))
            assert drift <= 2, f"{brand} came back {drift:.0f} degrees away in {theme}"


@pytest.mark.parametrize("theme", THEMES)
def test_the_writing_on_the_button_is_white_or_near_black(theme):
    """Two answers, and the better of the two. Anything else would be a third
    colour to hold to a ratio, chosen for no reason the page could state."""
    colours = _theme(theme)
    for brand in [accent.BRANDS[key] for key, _ in accent.NAMED]:
        derived = accent.derive(brand, colours)
        assert derived["on-accent"] in (accent.WHITE, accent.INK)
        other = accent.INK if derived["on-accent"] == accent.WHITE else accent.WHITE
        fill = derived["accent-fill"]
        assert contrast(derived["on-accent"], fill) >= contrast(other, fill)


def test_the_track_is_the_fill_at_a_sixth_over_the_page():
    """A bar's track is the fill, faint. Stated as a mix rather than as a colour so
    it follows the fill wherever the fill goes."""
    colours = _theme("light")
    derived = accent.derive("#2563eb", colours)
    assert derived["accent-track"] == over(derived["accent-fill"] + "29", colours["surface"])


# ---- The sweep --------------------------------------------------------------

# 36 hues, 5 saturations, 7 lightnesses: 1,260 colours, the whole space at a
# spacing fine enough that a hole in the derivation cannot hide between two of
# them. Through fourteen themes, that is 17,640 derivations and 158,760 pairs.
SWEEP = [
    accent.from_hsl(h * 10.0, s / 4, 0.1 + lightness * 0.8 / 6)
    for h in range(36)
    for s in range(5)
    for lightness in range(7)
]


def test_the_sweep_is_the_whole_colour_space():
    """A sweep that had quietly become 40 colours would pass every day and mean
    nothing, so its own shape is asserted before it is trusted."""
    assert len(SWEEP) == 1260
    assert len(set(SWEEP)) > 1000, "the grid should not be collapsing onto itself"


@pytest.mark.parametrize("theme", THEMES)
def test_any_colour_at_all_derives_a_set_that_passes(theme):
    """Why the box may take a free-for-all: the derivation is a pure function and
    every colour in the space comes out of it holding all nine pairs. An input
    nobody has looked at, an output somebody has."""
    colours = _theme(theme)
    failed = []
    for brand in SWEEP:
        bad = _holds(colours, accent.derive(brand, colours))
        if bad:
            failed.append(f"{brand}: {bad[0]}")
    assert failed == [], f"{len(failed)} of {len(SWEEP)} colours fail in {theme}: {failed[:5]}"


# ---- The stylesheet it is served as -----------------------------------------


def test_as_the_preset_writes_no_colours_of_its_own():
    """The default answer leaves the preset's own accent where it is. A block
    restating it would be a second place for it to be changed."""
    sheet = accent.stylesheet("breadbin", "")
    assert ":root[data-preset=" not in sheet
    assert ".accents" in sheet, "the picker's faces are drawn whatever the answer is"


@pytest.mark.parametrize("preset", PALETTES["presets"])
def test_the_chosen_accent_is_stated_for_the_preset_and_for_both_ways_of_asking_for_dark(preset):
    """The same three blocks every preset file is written in: the light one, the
    one for a reader who has chosen dark, and the one for a reader whose device
    chose it for them. Two of those say the same thing, and are generated from one
    dictionary so they cannot come to disagree (accessibility-standards)."""
    sheet = accent.stylesheet(preset, "#2563eb")
    root = ":root" if preset == "default" else f':root[data-preset="{preset}"]'
    assert f"{root} {{" in sheet
    assert f'{root}[data-theme="dark"] {{' in sheet
    assert "@media (prefers-color-scheme: dark) {" in sheet
    assert f"{root}:not([data-theme]) {{" in sheet
    dark = accent.derive("#2563eb", _theme("dark" if preset == "default" else f"{preset}-dark"))
    for token, value in dark.items():
        assert sheet.count(f"--{token}: {value};") >= 2, f"--{token} is not stated in both"


def test_the_accent_stylesheet_declares_nothing_but_the_five_tokens():
    """An accent is a colour, not a look. A size or a border in this file would
    make choosing one a change of layout, which is the one thing nothing in the
    design system is allowed to be (ADR-0030)."""
    sheet = accent.stylesheet("amber", "#b45309")
    for selector, block in re.findall(r"([^{}]+)\{([^{}]*)\}", sheet):
        head = selector.strip().splitlines()[-1].strip()
        if head.startswith("@media"):
            continue
        for declaration in filter(None, (d.strip() for d in block.split(";"))):
            name = declaration.split(":", 1)[0].strip()
            assert name.removeprefix("--") in accent.TOKENS, f"{head} sets {name}"


@pytest.mark.parametrize("preset", PALETTES["presets"])
def test_every_face_in_the_accent_picker_is_drawn_in_its_own_colour(preset):
    """Nine faces, each a real button and a real link in the accent it is offering,
    derived for the preset in force -- so the owner is choosing the thing rather
    than a word for it. Painted in the colours of the preset already on the page
    they would be nine of the same face."""
    components = (APP / "static" / "css" / "components.css").read_text(encoding="utf-8")
    rules = [line for line in components.splitlines() if line.strip().startswith(".accents")]
    read = {n for line in rules for n in re.findall(r"var\((--[\w-]+)\)", line)}
    wanted = read & {f"--{token}" for token in accent.TOKENS}
    assert wanted, "the .accents rules read no accent token; this checks nothing"
    sheet = accent.stylesheet(preset, "")
    for name in ("preset", *(key for key, _ in accent.NAMED)):
        for mode in ("light", "dark"):
            head = f'.accents [data-accent="{name}"]'
            assert head in sheet, f"no face for {name}"
            for block in re.findall(re.escape(head) + r"[^{]*\{([^}]*)\}", sheet):
                missing = {n for n in wanted if f"{n}:" not in block}
                assert missing == set(), f"{name}'s face does not state {sorted(missing)}"
            assert sheet.count(head) >= 2, f"{name} is not drawn for {mode} as well"


def test_the_preset_face_shows_the_preset_and_not_the_chosen_accent():
    """The first face has to go on meaning "as the preset" once an accent has been
    chosen. Left to inherit, it would show the chosen one and offer to change
    nothing."""
    palettes = json.loads((APP / "design" / "palettes.json").read_text(encoding="utf-8"))
    own = palettes["themes"]["breadbin-light"]["accent-fill"]
    sheet = accent.stylesheet("breadbin", "#2563eb")
    block = sheet.split('.accents [data-accent="preset"]', 1)[1].split("}", 1)[0]
    assert f"--accent-fill: {own};" in block


# ---- The page it is chosen on, and the page it is served to ------------------


class TestTheAccentOnThePage:
    """What an owner does with it, and what a reader is served because of it."""

    def test_the_picker_offers_nine_faces_each_drawn_in_what_it_offers(self, client):
        """The thing rather than a word for it: a face carries its own value, and
        `accent.css` is what paints that face in that colour."""
        page = client.get("/settings").text
        assert page.count('<input type="radio" name="accent"') == 9
        for name in ("preset", *(key for key, _ in accent.NAMED)):
            assert f'class="demo" data-accent="{name}"' in page

    def test_the_stylesheet_is_linked_by_a_stamp_of_what_it_serves(self, client):
        """A colour that can change while the site is up, cached for a year: the two
        are only compatible if changing it changes the URL. The page asks the same
        call for the stamp that the route asks for the rules."""
        page = client.get("/settings").text
        stamp = re.search(r'/style/accent\.css\?v=([^"]+)"', page)
        assert stamp, "no accent stylesheet on the page"
        served = client.get(f"/style/accent.css?v={stamp.group(1)}")
        assert served.status_code == 200
        assert served.headers["content-type"].startswith("text/css")
        assert "immutable" in served.headers["cache-control"]

    def test_choosing_one_changes_what_is_served_and_what_is_asked_for(self, client):
        """The whole of the feature, end to end: an answer on the form, a different
        stylesheet, and a page that asks for the new one rather than the old."""
        before = client.get("/settings").text
        was = re.search(r'/style/accent\.css\?v=([^"]+)"', before).group(1)
        assert "--accent-fill" not in client.get("/style/accent.css").text.split(".accents")[0]

        client.post(
            "/settings",
            data={"accent": "violet", "accent_custom": "", "theme": "system", "watermark": "1"},
            follow_redirects=False,
        )
        settings.forget()
        after = client.get("/settings").text
        now = re.search(r'/style/accent\.css\?v=([^"]+)"', after).group(1)
        assert now != was, "the stamp did not move, so a cache would hold the old colour"
        sheet = client.get("/style/accent.css").text
        violet = accent.derive(accent.BRANDS["violet"], _theme("light"))
        assert f"--accent-fill: {violet['accent-fill']};" in sheet

    def test_a_visitor_is_served_the_accent_but_is_offered_no_say_in_it(self, client, monkeypatch):
        """It is the installation's look, like the preset: a reader chooses light or
        dark and that is all. The stylesheet itself is public -- a page a stranger
        may read is a page they may read the styling of."""
        monkeypatch.setattr(main.auth, "AUTH_ENABLED", True)
        assert client.get("/style/accent.css").status_code == 200
        assert client.get("/settings", follow_redirects=False).status_code == 303
