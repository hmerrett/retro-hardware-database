"""An item's photograph in a 4:3 frame, and the same frame where there is none
(MANUAL §10, "In the panel").

No rendered page says how tall a box is drawn, so these read the stylesheets, as the
contrast tests do: the rules for the two frames in components.css, and nothing left
in app.css that would outrank them -- it is unlayered, so any rule of 0.1's naming
either frame wins over the design system's whatever the order."""

import re

from conftest import content
from test_item_page_controls import _png
from test_stylesheet_lint import COMPONENTS, LEGACY, text


def rule(css: str, selector: str) -> str:
    """The body of the rule whose selector list is exactly `selector`."""
    found = re.search(r"(?:^|[}\s])" + re.escape(selector) + r"\s*\{([^}]*)\}", css)
    assert found, f"no rule for {selector}"
    return found.group(1)


def says(body: str, prop: str) -> str:
    found = re.search(r"(?:^|;)\s*" + re.escape(prop) + r":\s*([^;]+)", body)
    return found.group(1).strip() if found else ""


class TestThePhotographIsFramed4By3:
    def test_the_frame_is_the_cards_shape_the_width_of_the_panel(self):
        body = rule(text(COMPONENTS), ".photo-main")
        assert says(body, "aspect-ratio") == "var(--thumb-ratio)"
        assert says(body, "width") == "100%"

    def test_a_photograph_of_another_shape_is_shown_whole_on_a_shaded_ground(self):
        body = rule(text(COMPONENTS), ".photo-main")
        assert says(body, "object-fit") == "contain"
        assert says(body, "background") == "var(--surface-sunken)"

    def test_nothing_caps_its_height(self):
        """340px high was the old cap: a frame of no fixed shape, so the panels under
        it moved with every photograph's proportions."""
        assert "max-height" not in rule(text(COMPONENTS), ".photo-main")


class TestNoPhotographHasTheSameFrame:
    def test_the_same_shape_on_the_same_ground(self):
        css = text(COMPONENTS)
        frame, empty = rule(css, ".photo-main"), rule(css, ".nophoto")
        for prop in ("aspect-ratio", "background", "border", "border-radius"):
            assert says(empty, prop) == says(frame, prop), prop

    def test_holding_the_cards_drawing_at_the_cards_size(self):
        """The design system's card draws its picture at 46% of the frame."""
        assert says(rule(text(COMPONENTS), ".nophoto img.ph"), "width") == "46%"

    def test_and_the_words(self, client, computer):
        aid = computer(name="Lounge PC")["asset_id"]
        page = content(client.get(f"/computers/{aid}").text)
        empty = page.split('class="nophoto"', 1)[1].split("</div>", 1)[0]
        assert 'class="ph"' in empty and "No photograph yet." in empty


def test_nothing_of_0_1_s_outranks_either_frame():
    legacy = text(LEGACY)
    assert not re.search(r"\.photo-main\b", legacy)
    assert not re.search(r"\.nophoto\b", legacy)


def test_the_page_draws_the_photograph_in_the_frame(client, computer):
    aid = computer(name="Lounge PC")["asset_id"]
    client.post(f"/computers/{aid}/photo", files={"photos": ("p.png", _png(), "image/png")})
    page = content(client.get(f"/computers/{aid}").text)
    assert re.search(r'<img class="photo-main zoomable"', page)
