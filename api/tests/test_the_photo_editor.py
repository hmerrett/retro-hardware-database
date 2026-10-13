"""The full-size view as the photo editor (MANUAL §2, "Photographs, full size"; §10,
"In the full-size view").

No browser runs in the suite (decided 27 Sep for this work), so the promises are
held the way the rest of the suite holds them: what the server renders and answers,
what the stylesheet says, and what the script's source says it does."""

import io
import re
from pathlib import Path

import pytest
from PIL import Image

from conftest import content, log_out, served, sign_in
from test_files import in_case, speak
from test_item_page_names import Node, Tree

APP = Path(__file__).resolve().parents[1] / "app"
COMPONENTS = APP / "static" / "css" / "components.css"
LEGACY = APP / "static" / "app.css"


def css(path: Path) -> str:
    return re.sub(r"/\*.*?\*/", "", path.read_text(encoding="utf-8"), flags=re.S)


def script() -> str:
    """The block of app.js that is the big view: from the top to the end of its
    first function."""
    js = (APP / "static" / "app.js").read_text(encoding="utf-8")
    return js[: js.index("})();")]


def phone_block(text: str) -> str:
    """The big view's own `max-width: 560px` block: the one that opens with the crop's
    two buttons."""
    return re.search(r"@media \(max-width: 560px\) \{\s*(\.lb \.lb-cropacts.*?)\n  \}", text, re.S)[
        1
    ]


def upload(client, kind, aid, n=1):
    for i in range(n):
        buf = io.BytesIO()
        Image.new("RGB", (90, 60), (120, 90, 60 + i)).save(buf, "JPEG", quality=92)
        buf.seek(0)
        client.post(
            f"/{kind}/{aid}/photo",
            files={"photos": (f"{aid}-{i}.jpg", buf, "image/jpeg")},
            follow_redirects=False,
        )
    return re.findall(r'data-rel="([^"]+)"', content(client.get(f"/{kind}/{aid}").text))


@pytest.fixture
def two(client, part):
    aid = part(model="Controller")["asset_id"]
    return aid, upload(client, "parts", aid, 2)


def lightbox(page: str) -> Node:
    t = Tree(page)
    return next(n for n in t.root.walk() if n.get("id") == "lightbox")


def names(t: Tree, root: Node) -> list[str]:
    return [t.name(n) for n in root.walk() if n.tag == "button"]


class TestTheMarkup:
    def test_the_big_view_is_a_dialog(self, client, two):
        page = client.get(f"/parts/{two[0]}").text
        box = lightbox(page)
        assert box.tag == "dialog"
        title = box.get("aria-labelledby")
        assert title and re.search(rf'id="{title}"', page)

    def test_it_is_named_for_what_it_shows(self):
        """The photograph's own name -- "Controller, photograph 2 of 3" -- on the view
        and on the photograph in it."""
        js = script()
        assert "title.textContent = el.alt" in js
        assert "img.alt = el.alt" in js

    def test_the_crop_box_has_a_handle_at_each_corner(self, client, two):
        box = lightbox(client.get(f"/parts/{two[0]}").text)
        crop = next(n for n in box.walk() if n.get("id") == "lb-crop")
        assert "cropbox" in crop.classes()
        corners = sorted(c for n in crop.walk() if "h" in n.classes() for c in n.classes() - {"h"})
        assert corners == ["ne", "nw", "se", "sw"]

    def test_the_crop_box_is_reached_by_the_keyboard_and_says_what_it_is(self, client, two):
        box = lightbox(client.get(f"/parts/{two[0]}").text)
        crop = next(n for n in box.walk() if n.get("id") == "lb-crop")
        assert crop.get("tabindex") == "0" and crop.get("role") == "group"
        assert crop.get("aria-label") == "Crop box"
        assert crop.get("aria-describedby") == "lb-crop-how"

    def test_how_to_crop_is_written_on_the_toolbar(self, client, two):
        """In the markup, where it is read, and not in a tooltip."""
        box = lightbox(client.get(f"/parts/{two[0]}").text)
        how = next(n for n in box.walk() if n.get("id") == "lb-crop-how")
        assert (
            how.text()
            == "Drag the box or its corners. Arrow keys move it; Shift and an arrow resizes."
        )
        assert any(a.get("id") == "lb-tools" for a in how.ancestors())

    def test_a_tuned_photograph_is_marked_and_offers_undo(self, client, two):
        page = client.get(f"/parts/{two[0]}").text
        t = Tree(page)
        box = lightbox(page)
        tuned = next(n for n in box.walk() if n.get("id") == "lb-tuned")
        assert tuned.tag == "span" and tuned.text() == "Tuned up"
        undo = next(n for n in box.walk() if n.get("id") == "lb-untune")
        assert names(t, undo) == ["Undo tune-up"]
        js = script()
        assert "tuned.hidden = !kept" in js and "untune.hidden = !kept" in js

    def test_the_tools_read_in_three_groups(self, client, two):
        page = client.get(f"/parts/{two[0]}").text
        t = Tree(page)
        tools = next(n for n in lightbox(page).walk() if n.get("id") == "lb-tools")
        groups = [n for n in tools.walk() if "lb-group" in n.classes()]
        undo = {"Undo tune-up"}
        assert [[w for w in names(t, g) if w not in undo] for g in groups] == [
            ["Rotate anticlockwise", "Rotate clockwise", "Tune up"],
            ["Crop", "Default photo", "Reference image"],
            ["Delete"],
        ]
        between = [n for n in tools.children if isinstance(n, Node)]
        kinds = [
            "sep" if "lb-sep" in n.classes() else "group"
            for n in between
            if n.classes() & {"lb-sep", "lb-group"}
        ]
        assert kinds == ["group", "sep", "group", "sep", "group"]

    @pytest.mark.parametrize("case", ["cap", "lower"])
    def test_every_tool_is_named_in_words(self, client, two, case):
        speak(client, case)
        page = client.get(f"/parts/{two[0]}").text
        t = Tree(page)
        said = set(names(t, lightbox(page)))
        for words in (
            "Close",
            "Previous",
            "Next",
            "Rotate anticlockwise",
            "Rotate clockwise",
            "Tune up",
            "Undo tune-up",
            "Crop",
            "Apply crop",
            "Cancel",
            "Default photo",
            "Reference image",
            "Delete",
        ):
            assert in_case(words, case) in said, words

    def test_a_visitor_sees_the_count_and_none_of_the_tools(self, client, two):
        log_out(client)
        try:
            page = client.get(f"/parts/{two[0]}").text
            box = lightbox(page)
            assert any(n.get("id") == "lb-count" for n in box.walk())
            assert not any(n.get("id") == "lb-tools" for n in box.walk())
        finally:
            sign_in(client)

    def test_the_count_is_under_the_photograph_where_the_tools_join_it(self, client, two):
        box = lightbox(client.get(f"/parts/{two[0]}").text)
        bar = next(n for n in box.walk() if "lb-bar" in n.classes())
        ids = [n.get("id") for n in bar.walk() if n.get("id")]
        assert ids.index("lb-count") < ids.index("lb-tools")


class TestThePhotographsOnThePage:
    def test_carry_no_buttons_of_their_own(self, client, two):
        """Their tools are in the full-size view (decision 27)."""
        page = content(client.get(f"/parts/{two[0]}").text)
        assert "photo-ctrls" not in page
        assert "/primary-photo" not in page and "/photo-reference" not in page

    def test_each_says_whether_it_is_the_default_and_a_reference(self, client, two):
        aid, rels = two
        client.post(f"/parts/{aid}/photo-reference", data={"image": rels[1], "set": "1"})
        page = content(client.get(f"/parts/{aid}").text)
        shots = re.findall(r'<img class="[^"]*zoomable[^>]*>', page)
        first, second = shots[0], shots[1]
        assert 'data-primary="1"' in first and "data-primary" not in second
        assert 'data-ref="0"' in first and 'data-ref="1"' in second

    def test_a_location_s_are_not_offered_reference(self, client):
        made = client.post("/api/locations", json={"name": "Shelf", "kind": "shelf"}).json()
        aid = made["asset_id"]
        buf = io.BytesIO()
        Image.new("RGB", (90, 60), "white").save(buf, "JPEG")
        client.post(
            f"/locations/{aid}/photo", files={"photos": ("s.jpg", buf.getvalue(), "image/jpeg")}
        )
        page = content(client.get(f"/locations/{aid}").text)
        shot = re.search(r'<img class="[^"]*zoomable[^>]*>', page)[0]
        assert "data-ref" not in shot
        assert "refForm.hidden = !('ref' in d)" in script()


class TestTheRoutes:
    def test_default_photo_from_the_big_view_comes_back_to_it_still_open(self, client, two):
        """Under its new name: the default is the file named for the item."""
        aid, rels = two
        r = client.post(
            f"/parts/{aid}/primary-photo",
            data={"image": rels[1], "next": f"/parts/{aid}?photo={rels[1]}"},
            follow_redirects=False,
        )
        assert r.status_code == 303
        assert r.headers["location"] == f"/parts/{aid}?photo=parts%2F{aid}.jpg"

    def test_default_photo_from_anywhere_else_still_goes_to_the_page(self, client, two):
        aid, rels = two
        r = client.post(
            f"/parts/{aid}/primary-photo", data={"image": rels[1]}, follow_redirects=False
        )
        assert r.headers["location"] == f"/parts/{aid}"

    def test_and_on_the_tab_it_came_from(self, client, two):
        aid, rels = two
        r = client.post(
            f"/parts/{aid}/primary-photo?tab=files",
            data={"image": rels[1], "next": "x"},
            follow_redirects=False,
        )
        assert r.headers["location"] == f"/parts/{aid}?tab=files&photo=parts%2F{aid}.jpg"

    def test_reference_from_the_big_view_comes_back_to_it_still_open(self, client, two):
        aid, rels = two
        back = f"/parts/{aid}?photo={rels[1]}"
        r = client.post(
            f"/parts/{aid}/photo-reference",
            data={"image": rels[1], "set": "1", "next": back},
            follow_redirects=False,
        )
        assert r.headers["location"] == back


class TestTheStylesheet:
    def test_each_handle_is_a_24px_target(self):
        text = css(COMPONENTS)
        handle = re.search(r"\.cropbox \.h \{([^}]*)\}", text)[1]
        assert "width: 24px" in handle and "height: 24px" in handle
        assert re.search(r"\.cropbox \.h::after \{[^}]*width: 12px; height: 12px", text)

    def test_apply_crop_is_the_primary_on_the_scrim_without_a_fill(self):
        body = re.search(r"\.lb \.btn\.primary \{([^}]*)\}", css(COMPONENTS))[1]
        assert "background: none" in body
        assert "color: var(--on-scrim)" in body
        assert "border: 2px solid var(--on-scrim)" in body
        assert "font-weight: 600" in body

    def test_no_0_1_rule_draws_the_big_view(self):
        legacy = css(LEGACY)
        assert "#lightbox" not in legacy and "#lb-crop" not in legacy

    def test_no_0_1_button_rule_reaches_the_big_view(self):
        """The view is outside `<main>`, so 0.1's buttons -- kept off v0.2 pages by
        `:not(main.v2 *)` -- reached it, and being unlayered they outranked the scrim's
        own: a pale fill under pale words. None of them is left."""
        assert re.findall(r"([^{}]*\.btn[^{}]*)\{", css(LEGACY)) == []

    def test_apply_and_cancel_are_wide_on_a_phone(self):
        assert re.search(
            r"@media \(max-width: 560px\) \{[^}]*\.lb \.lb-cropacts \.btn \{ flex: 1 1 0; \}",
            css(COMPONENTS),
        )

    def test_delete_reads_as_the_destructive_one(self, client, two):
        """Colour is what says this tool is not like its neighbours, in the scrim's
        own danger shade: the page's is unreadable on the dark."""
        assert re.search(
            r"\.lb \.btn\.danger \{[^}]*color: var\(--on-scrim-danger\)", css(COMPONENTS)
        )
        box = lightbox(client.get(f"/parts/{two[0]}").text)
        delete = next(n for n in box.walk() if n.get("id") == "lb-delete")
        assert any("danger" in n.classes() for n in delete.walk() if n.tag == "button")

    def test_on_a_phone_the_photograph_is_edge_to_edge(self):
        text = css(COMPONENTS)
        phone = phone_block(text)
        assert ".lb { --lb-w: 100vw; }" in phone
        assert "width: var(--lb-w)" in text and "max-width: var(--lb-w)" in text

    def test_on_a_phone_the_rows_part_the_groups_rather_than_the_rules(self):
        """Wrapped, a rule is left hanging at the end of a line with nothing after it."""
        text = css(COMPONENTS)
        phone = phone_block(text)
        assert ".lb .lb-sep { display: none; }" in phone

    def test_the_scrim_outside_the_box_stops_at_the_photograph(self):
        assert ".lb .lb-stage.cropping .lb-fit { overflow: hidden; }" in css(COMPONENTS)

    def test_the_dialog_fills_the_window_and_shows_only_when_open(self):
        text = css(COMPONENTS)
        lb = re.search(r"\n\s*\.lb \{([^}]*)\}", text)[1]
        for decl in ("max-width: none", "max-height: none", "margin: 0", "padding: 0", "border: 0"):
            assert decl in lb, decl
        assert ".lb[open] { display: flex;" in text
        assert ".lb.open" not in text


class TestTheScript:
    def test_the_view_takes_the_focus_and_gives_it_back(self):
        js = script()
        assert "box.showModal()" in js
        assert "box.close()" in js
        assert "current().focus({ preventScroll: true })" in js

    def test_esc_cancels_a_crop_before_it_closes_the_view(self):
        js = script()
        cancel = js[js.index("box.addEventListener('cancel'") :][:300]
        assert "e.preventDefault()" in cancel
        assert "cropping() ? cropMode(false) : close()" in cancel
        assert "e.key === 'Escape'" not in js

    def test_crop_gives_the_box_the_focus(self):
        assert "cropLayer.focus()" in script()

    def test_the_box_starts_at_the_whole_photograph_less_a_margin(self):
        js = script()
        assert "const MARGIN = 0.05" in js
        assert "sel = { x: MARGIN, y: MARGIN, w: 1 - 2 * MARGIN, h: 1 - 2 * MARGIN }" in js

    def test_the_arrow_keys_move_the_box_while_it_has_focus(self):
        js = script()
        keys = js[js.index("cropLayer.addEventListener('keydown'") :][:1600]
        assert "const NUDGE = 0.01" in js
        assert "ArrowLeft" in keys and "ArrowDown" in keys
        assert "e.stopPropagation()" in keys

    def test_shift_and_an_arrow_resize_it(self):
        keys = script()[script().index("cropLayer.addEventListener('keydown'") :][:1600]
        assert "e.shiftKey" in keys

    def test_enter_on_the_box_applies_the_crop(self):
        keys = script()[script().index("cropLayer.addEventListener('keydown'") :][:1600]
        assert "e.key === 'Enter'" in keys and "cropForm.requestSubmit()" in keys

    def test_its_size_is_said_after_each_key(self):
        assert "said.textContent = `Crop box" in script()

    def test_the_arrows_stay_on_the_photograph_while_cropping(self):
        js = script()
        keys = js[js.index("document.addEventListener('keydown'") :][:400]
        assert "if (cropping()) return;" in keys

    def test_the_rest_of_the_toolbar_steps_out_while_cropping(self):
        assert "groups.forEach(g => { g.hidden = on; })" in script()

    def test_any_corner_resizes_it(self):
        js = script()
        assert "corner.includes('w')" in js and "corner.includes('n')" in js

    def test_the_page_still_sees_an_open_big_view(self, client, part):
        page = served(client, client.get(f"/parts/{part()['asset_id']}").text)
        assert "document.querySelector('#lightbox[open]')" in page
