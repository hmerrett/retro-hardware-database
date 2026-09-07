"""Behaviour carried by the shared stylesheet rather than one rendered page."""
from pathlib import Path


STYLESHEET = Path(__file__).parents[1] / "app" / "static" / "app.css"


def test_native_select_menus_have_an_explicit_themed_surface():
    """Some browsers inherit the dark text colour into a native menu but keep
    its default light background. Both halves must therefore be stated rather
    than leaving the popup to reconcile inherited and system colours."""
    css = STYLESHEET.read_text()
    assert "select { max-width: 100%; background: var(--bg); color: var(--fg); }" in css
    assert "option, optgroup { background: var(--bg); color: var(--fg); }" in css


def test_action_colours_have_dark_theme_foregrounds():
    """The dark accent is intentionally light, so white primary-button text and
    the light theme's brown danger text both lose contrast against dark surfaces."""
    css = STYLESHEET.read_text()
    assert "--primary-fg: #15171c" in css
    assert "--danger: #ffb37a" in css
    assert "color: var(--primary-fg)" in css
    assert "color: var(--danger)" in css
