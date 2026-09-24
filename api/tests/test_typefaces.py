"""The Type setting: which family does the writing, the interface and the values.

A pairing is three declarations and nothing else (ADR-0030), which is what keeps
choosing one a change of face rather than a change of layout. The three that are
not "as the preset" are generated into `type.css` from `design/scales.json`, so
what follows reads the file the browser is served rather than a second copy of the
same intention.
"""

import re
from pathlib import Path

import pytest

from app import typefaces

TYPE_CSS = Path(__file__).parents[1] / "app" / "static" / "css" / "type.css"


@pytest.fixture(scope="module")
def css() -> str:
    return TYPE_CSS.read_text(encoding="utf-8")


def block(css: str, name: str) -> str:
    """The declarations `type.css` makes for one pairing."""
    return css.split(f':root[data-type="{name}"] {{', 1)[1].split("}", 1)[0]


class TestWhatIsOffered:
    def test_four_answers_beginning_with_the_preset_s_own(self):
        """The list is the data's and in the data's order, so the menu cannot come
        to offer a pairing nothing was generated for."""
        assert typefaces.IDS == ("preset", "catalogue", "plain", "ledger")
        assert typefaces.NAMES["preset"] == "As the preset"

    def test_the_preset_s_own_is_the_default(self):
        """A fresh install wears the look it was given, faces included."""
        assert typefaces.DEFAULT == "preset"

    def test_an_answer_nobody_offered_falls_back_to_the_preset_s_own(self):
        """The value can arrive from a row this page never wrote. Unrecognised, the
        site keeps the preset's faces rather than carrying an attribute that matches
        no rule."""
        assert typefaces.known("ledger") == "ledger"
        assert typefaces.known("blackletter") == typefaces.DEFAULT
        assert typefaces.known("") == typefaces.DEFAULT


class TestWhatAPairingChanges:
    @pytest.mark.parametrize("name", ["catalogue", "plain", "ledger"])
    def test_a_pairing_declares_nothing_but_the_three_families(self, css, name):
        """A size or a weight here would make the Type setting move the page, which
        is the one thing no look in the register is allowed to do."""
        declared = re.findall(r"--([a-z-]+):", block(css, name))
        assert declared == ["font-display", "font-ui", "font-data"]

    def test_catalogue_is_the_three_roles_at_their_most_distinct(self, css):
        rules = block(css, "catalogue")
        assert "Source Serif 4" in rules
        assert "IBM Plex Sans" in rules
        assert "IBM Plex Mono" in rules

    def test_plain_drops_the_serif_and_keeps_the_monospace(self, css):
        rules = block(css, "plain")
        assert "Source Serif 4" not in rules
        assert rules.count("IBM Plex Sans") == 2
        assert "IBM Plex Mono" in rules

    def test_ledger_is_monospaced_throughout(self, css):
        assert block(css, "ledger").count("IBM Plex Mono") == 3

    def test_the_preset_s_own_has_no_block_at_all(self, css):
        """It is the answer that changes nothing: no rules, and no attribute on the
        page for rules to hang from."""
        assert 'data-type="preset"' not in css

    def test_every_family_named_is_one_the_site_serves(self, css):
        """The three faces ship with the register and are served from it: a pairing
        that named a fourth would be asking for a file that is not there, or worse,
        for one from somewhere else (ADR-0021)."""
        faces = set(re.findall(r'"([A-Z][^"]+)"', css))
        assert faces == {"Source Serif 4", "IBM Plex Sans", "IBM Plex Mono"}
