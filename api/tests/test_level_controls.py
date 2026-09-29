"""Controls that stand in one row are one height, and four small things the design
review's high-fidelity pass found, held where every page shares them.

A box beside a button was taller than the button -- 35px beside 28px in the history's
note bar, 38px beside 36px on a phone -- and the view switch was shorter than the
small buttons it sits among. Read from the stylesheet itself, since no rendered page
can be asked how tall a control is.
"""

import re
from pathlib import Path

CSS = Path(__file__).parents[1] / "app" / "static" / "css" / "components.css"


def text():
    return re.sub(r"/\*.*?\*/", "", CSS.read_text(), flags=re.S)


def coarse():
    """The body of every @media (pointer: coarse) block, run together."""
    css, out = text(), []
    for m in re.finditer(r"@media \(pointer: coarse\)\s*\{", css):
        depth, i = 1, m.end()
        while depth:
            depth += {"{": 1, "}": -1}.get(css[i], 0)
            i += 1
        out.append(css[m.end() : i - 1])
    return "\n".join(out)


def outside_coarse():
    css = text()
    return re.sub(r"@media \(pointer: coarse\)\s*\{(?:[^{}]|\{[^{}]*\})*\}", "", css)


def rule(css, selector):
    m = re.search(rf"(?:^|[}}\s]){re.escape(selector)}\s*\{{([^}}]*)\}}", css)
    assert m, selector
    return m[1]


ROWS = ".notebar, .fileform, .toolbar, .photo-actions form"


class TestARowOfControlsIsOneHeight:
    def test_a_box_and_the_buttons_beside_it_take_the_control_height(self):
        css = outside_coarse()
        assert ROWS in css, "no rule for the rows a box shares with buttons"
        block = css[css.index(ROWS) :]
        buttons = re.search(r"\.btn[^{]*\{([^}]*)\}", block)
        boxes = re.search(r"input:not\([^{]*\{([^}]*)\}", block)
        assert buttons and "min-height: var(--control-h)" in buttons[1]
        assert boxes and "height: var(--control-h)" in boxes[1]

    def test_on_a_touch_screen_both_take_the_tap_height(self):
        block = coarse()
        assert ROWS in block
        assert block.count("var(--tap)") >= 2

    def test_the_view_switch_is_a_small_button_s_height(self):
        small = rule(outside_coarse(), ".btn.sm")
        height = re.search(r"min-height:\s*(\d+)px", small)[1]
        switch = rule(outside_coarse(), ".viewswitch a")
        assert f"calc({height}px - 2 * var(--border-w))" in switch

    def test_and_on_a_touch_screen_too(self):
        small = re.search(r"\.btn\.sm\s*\{[^}]*min-height:\s*(\d+)px", coarse())[1]
        assert re.search(
            rf"\.viewswitch a\s*\{{[^}}]*calc\({small}px - 2 \* var\(--border-w\)\)", coarse()
        )


class TestTheSmallThings:
    def test_a_card_grid_shares_its_width_among_the_cards_it_has(self):
        assert "auto-fit" in rule(outside_coarse(), ".cardgrid")

    def test_the_files_public_tick_is_a_tap_target_on_a_phone(self):
        assert re.search(
            r"\.tickbox input\[type=checkbox\][^{]*\{[^}]*width: 22px; height: 22px", coarse()
        )

    def test_a_file_s_date_and_time_stay_together(self):
        assert "white-space: nowrap" in rule(outside_coarse(), ".fwhen")
