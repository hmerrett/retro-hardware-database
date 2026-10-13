"""An item page's boxes and buttons, as MANUAL.md section 4 ("Its boxes and buttons")
promises them: every box labelled above it and drawn as the design system's box, the
words on the buttons and the line marks following Button text, nothing pressed on a
touchscreen under 36px, an empty panel saying so in a sentence, notes in the
summary's type, Take out as a bin, and the history restacking on a phone (section 15).

The pages are rendered for the owner with something in every panel that has a form,
so each box the page can offer is on it. The stylesheet promises are read off
components.css, as test_stylesheet_lint.py reads it: no rendered page can be asked
what size a control is under a coarse pointer.
"""

import re
from html.parser import HTMLParser

import pytest

from conftest import content
from test_files import speak
from test_stylesheet_lint import COMPONENTS, text

KINDS = pytest.mark.parametrize("kind", ["computers", "parts"])


class Controls(HTMLParser):
    """The boxes, the labels, and the words on what can be pressed, in a page."""

    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.boxes: list[dict[str, str]] = []
        self.labels: dict[str, str] = {}
        self.words: list[tuple[str, str]] = []
        self._open: list[tuple[str, dict[str, str], list[str]]] = []

    def handle_starttag(self, tag, attrs):
        a = {k: v or "" for k, v in attrs}
        boxlike = a.get("type") not in ("hidden", "file", "checkbox", "radio", "submit")
        if tag in ("input", "select", "textarea") and boxlike:
            self.boxes.append(a | {"tag": tag})
        cls = a.get("class", "").split()
        pressable = (
            tag == "button"
            or (tag in ("a", "label") and "btn" in cls and "data-wayback" not in a)
            or (tag == "span" and "chip" in cls)
        )
        if tag == "label" or pressable:
            self._open.append((tag, a | {"pressable": "1" if pressable else ""}, []))

    def handle_data(self, data):
        for _, _, out in self._open:
            out.append(data)

    def handle_endtag(self, tag):
        if self._open and self._open[-1][0] == tag:
            _, a, out = self._open.pop()
            words = " ".join("".join(out).split())
            if tag == "label" and a.get("for"):
                self.labels[a["for"]] = words
            if a["pressable"] and words:
                self.words.append((tag, words))


def controls(page: str) -> Controls:
    """What `<main>` holds, or the whole of a fragment that has no `<main>`."""
    c = Controls()
    c.feed(content(page) if "<main" in page else page)
    return c


@pytest.fixture
def full_pages(client, computer, part):
    """A machine and three parts, each with something in every panel that has a form:
    a spare board and a spare part the machine could take, a spare a part page could
    fit, and an I/O card with a drive it could mount."""
    pc = computer(name="Lounge PC")["asset_id"]
    part(type="motherboard", model="Spare board")
    part(type="video", model="Spare card")
    io = part(type="io", model="Controller")["asset_id"]
    part(type="storage", model="Spare drive")
    fitted = part(type="sound", model="SB16", computer_id=pc)["asset_id"]
    client.post(f"/computers/{pc}/note", data={"message": "Tested"})
    return {"computers": pc, "parts": io, "fitted": fitted}


class TestEveryBoxIsLabelledAboveIt:
    @KINDS
    def test_every_box_is_the_design_systems_box_with_a_label(self, client, full_pages, kind):
        page = client.get(f"/{kind}/{full_pages[kind]}").text
        c = controls(page)
        assert c.boxes, "the page offered no boxes to check"
        for box in c.boxes:
            cls = box.get("class", "").split()
            want = "select" if box["tag"] == "select" else "input"
            assert want in cls, box
            assert box.get("id") in c.labels and c.labels[box["id"]], box

    @pytest.mark.parametrize(
        "kind,names",
        [
            (
                "computers",
                ["Why", "When", "Note", "Link a board", "Link a part", "Jobs", "Project"],
            ),
            ("parts", ["Why", "When", "Note", "Mount storage", "Jobs", "Project"]),
        ],
    )
    def test_each_box_is_named_for_what_it_takes(self, client, full_pages, kind, names):
        c = controls(client.get(f"/{kind}/{full_pages[kind]}").text)
        labelled = set(c.labels.values())
        for name in names:
            assert name in labelled, (name, sorted(labelled))

    def test_a_spare_offers_the_machines_under_a_label(self, client, computer, part):
        computer()
        spare = part()["asset_id"]
        c = controls(client.get(f"/parts/{spare}").text)
        assert "Machine" in c.labels.values()

    def test_files_has_a_note_box_of_its_own(self, client, full_pages):
        page = client.get(f"/computers/{full_pages['computers']}").text
        files = page[page.index("<h3>Files</h3>") :]
        c = controls(files[: files.index("</section>")])
        assert list(c.labels.values()) == ["Note"]

    def test_a_box_beside_a_button_takes_the_room_it_is_given(self):
        """The 34em measure is for prose; a box in a row of them is not prose."""
        css = text(COMPONENTS)
        assert re.search(
            r"\.addrow > \.field > :is\(\.input, \.select\) \{[^}]*max-width: none", css
        )


class TestTheWordsFollowButtonText:
    @KINDS
    @pytest.mark.parametrize("case", ["cap", "lower"])
    def test_every_button_and_mark_follows_the_setting(self, client, full_pages, kind, case):
        speak(client, case)
        c = controls(client.get(f"/{kind}/{full_pages[kind]}").text)
        assert c.words
        for tag, words in c.words:
            first = words.split()[0].lstrip("+‹›… ")
            if not first or not first[0].isalpha():
                continue
            if case == "cap":
                assert first[0].isupper(), (tag, words)
            else:
                # Lower case takes the capital off a word written Like This and
                # nothing else: an acronym or a name keeps its own.
                assert not (first[0].isupper() and first[1:].islower()), (tag, words)

    def test_a_history_line_is_marked_note_photo_or_moved(self, client, full_pages):
        page = client.get(f"/computers/{full_pages['computers']}").text
        assert '<span class="chip">Note</span>' in page


def media(css: str, query: str | None) -> str:
    """The rules inside the @media blocks whose query contains `query`, or, with
    None, the rules outside every @media block."""
    outside, inside, i = [], [], 0
    for m in re.finditer(r"@media[^{]*\{", css):
        if m.start() < i:
            continue
        depth, j = 1, m.end()
        while depth:
            depth += {"{": 1, "}": -1}.get(css[j], 0)
            j += 1
        outside.append(css[i : m.start()])
        if query is not None and query in m.group(0):
            inside.append(css[m.end() : j - 1])
        i = j
    outside.append(css[i:])
    return "".join(outside if query is None else inside)


class TestNothingPressedIsSmallOnATouchscreen:
    @staticmethod
    def sizes(css: str) -> dict[tuple[str, str], str]:
        out = {}
        for head, body in re.findall(r"([^{}]+)\{([^{}]*)\}", css):
            for line in body.split(";"):
                if ":" not in line:
                    continue
                prop, value = (s.strip() for s in line.split(":", 1))
                if prop in ("width", "height", "min-height"):
                    for sel in re.split(r",(?![^(]*\))", head):
                        out[(" ".join(sel.split()), prop)] = value
        return out

    @staticmethod
    def px(value: str) -> float | None:
        known = {"var(--control-h)": 32.0, "var(--tap)": 44.0}
        if value in known:
            return known[value]
        m = re.fullmatch(r"(\d+(?:\.\d+)?)px", value)
        return float(m.group(1)) if m else None

    def test_a_button_sized_under_36px_is_restated_for_a_coarse_pointer(self):
        css = text(COMPONENTS)
        restated = self.sizes(media(css, "pointer: coarse"))
        for (sel, prop), value in self.sizes(media(css, None)).items():
            if ".btn" not in sel or "svg" in sel:
                continue
            size = self.px(value)
            if size is None or size >= 36:
                continue
            assert (sel, prop) in restated, (sel, prop, value)
            assert (self.px(restated[(sel, prop)]) or 0) >= 36, (sel, prop)

    @pytest.mark.parametrize("sel,size", [(".btn.icon", "var(--tap)"), (".btn.icon.sm", "36px")])
    def test_an_icon_button_is_44_or_36_a_side(self, sel, size):
        coarse = media(text(COMPONENTS), "pointer: coarse")
        assert self.sizes(coarse).get((sel, "width")) == size

    @KINDS
    def test_the_photo_history_and_card_buttons_are_the_design_systems(
        self, client, full_pages, kind
    ):
        aid = full_pages[kind]
        client.post(
            f"/{kind}/{aid}/photo",
            files={"photos": ("a.png", _png(), "image/png")},
            follow_redirects=False,
        )
        page = content(client.get(f"/{kind}/{aid}").text)
        assert "iconbtn" not in page
        # The history's delete and attach: the photographs carry no buttons of their
        # own now, their tools being in the full-size view.
        assert re.search(r'class="btn( \w+)* sm icon\b', page)


class TestAnEmptyPanelSaysSo:
    def test_a_bare_machine(self, client, computer):
        aid = computer(manufacturer="", model="", name="Bare")["asset_id"]
        page = content(client.get(f"/computers/{aid}").text)
        for sentence in (
            "No board linked yet.",
            "Nothing fitted in it yet.",
            "No files for this one yet.",
            "No jobs on it yet.",
            "Nothing recorded yet.",
        ):
            assert sentence in page, sentence

    def test_a_card_with_nothing_mounted(self, client, part):
        aid = part(type="io")["asset_id"]
        assert "Nothing mounted on it yet." in content(client.get(f"/parts/{aid}").text)

    def test_details_with_something_in_it_says_nothing_of_the_sort(self, client, computer):
        aid = computer()["asset_id"]
        assert "Nothing recorded yet." not in client.get(f"/computers/{aid}").text


class TestNotesAreInTheSummarysType:
    def test_notes_are_set_in_the_display_face(self):
        assert re.search(
            r"\.kv dd\.lines \{[^}]*font-family: var\(--font-display\)", text(COMPONENTS)
        )


class TestTakeOutIsABin:
    def test_a_fitted_part_has_a_bin_at_the_cards_right(self, client, full_pages):
        page = client.get(f"/computers/{full_pages['computers']}").text
        aid = full_pages["fitted"]
        card = page[page.index(f'<a class="tag" href="/parts/{aid}">') :]
        card = card[: card.index("</article>")]
        head, main = card.split("</header>", 1)
        assert "Take out" not in head
        button = re.search(r'<div class="cardact">.*?</button>', main, re.S)
        assert button, main
        b = button.group(0)
        assert 'class="btn sm icon"' in b and "danger" not in b
        assert f'aria-label="Take out {aid}"' in b
        assert "spare" in re.search(r'title="([^"]*)"', b).group(1)
        assert "<svg" in b

    def test_the_part_page_takes_it_out_with_the_same_bin(self, client, full_pages):
        aid = full_pages["fitted"]
        page = client.get(f"/parts/{aid}").text
        fitted = page[page.index("<h3>Fitted in</h3>") :]
        fitted = fitted[: fitted.index("</section>")]
        assert f'aria-label="Take out {aid}"' in fitted
        assert ">Take out<" not in fitted


class TestTheHistoryOnAPhone:
    def test_the_date_sits_above_the_entry_under_560px(self):
        phone = media(text(COMPONENTS), "(max-width: 560px)")
        assert re.search(r"\.kv\.log > div \{[^}]*flex-direction: column", phone)

    def test_the_buttons_keep_their_column(self):
        """The line inside the entry is still a row, buttons at its right end."""
        assert re.search(r"\.kv\.log dd \{ flex: 1 1 0%; \}", text(COMPONENTS))


def _png() -> bytes:
    from io import BytesIO

    from PIL import Image

    buf = BytesIO()
    Image.new("RGB", (8, 6), "white").save(buf, "PNG")
    return buf.getvalue()
