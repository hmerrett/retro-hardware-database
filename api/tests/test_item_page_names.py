"""What an item page says in words as well as by its look (MANUAL §2, "With a
screen reader"; §4; §10).

A screen reader hears a page by its names, and a name that every photograph or
every history line shares is the same as none: "Delete history entry" seven times
down a page says which button it is only to somebody who can see where it sits.
So these tests compute names the way a browser does -- `aria-labelledby`, then
`aria-label`, then a `<label>`, then the words inside -- and ask what is heard."""

import re
from collections import Counter
from html.parser import HTMLParser
from pathlib import Path

import pytest

from conftest import content
from test_item_page_controls import _png

APP = Path(__file__).resolve().parents[1] / "app"
TEMPLATES = APP / "templates"
VOID = {"area", "br", "col", "embed", "hr", "img", "input", "link", "meta", "source", "wbr"}


class Node:
    def __init__(self, tag: str, attrs: dict[str, str | None], parent: "Node | None"):
        self.tag, self.attrs, self.parent = tag, attrs, parent
        self.children: list["Node | str"] = []

    def get(self, name: str) -> str:
        return self.attrs.get(name) or ""

    def classes(self) -> set[str]:
        return set(self.get("class").split())

    def ancestors(self):
        at = self.parent
        while at is not None:
            yield at
            at = at.parent

    def walk(self):
        for child in self.children:
            if isinstance(child, Node):
                yield child
                yield from child.walk()

    def text(self) -> str:
        """The words inside, with a picture read as its alt -- what a button made of
        an icon and a word is called."""
        out = []
        for child in self.children:
            if isinstance(child, str):
                out.append(child)
            elif child.tag == "img":
                out.append(child.get("alt"))
            elif child.get("aria-hidden") != "true":
                out.append(child.text())
        return " ".join("".join(out).split())


class Tree(HTMLParser):
    def __init__(self, markup: str):
        super().__init__(convert_charrefs=True)
        self.root = Node("#root", {}, None)
        self._at = self.root
        self.feed(markup)
        self.ids = {n.get("id"): n for n in self.root.walk() if n.get("id")}

    def handle_starttag(self, tag, attrs):
        node = Node(tag, dict(attrs), self._at)
        self._at.children.append(node)
        if tag not in VOID:
            self._at = node

    def handle_endtag(self, tag):
        at = self._at
        while at is not self.root and at.tag != tag:
            at = at.parent
        if at is not self.root:
            self._at = at.parent

    def handle_data(self, data):
        self._at.children.append(data)

    def name(self, node: Node, following: bool = True) -> str:
        if following and node.get("aria-labelledby"):
            return " ".join(
                self.name(self.ids[i], following=False) if i in self.ids else "?" + i
                for i in node.get("aria-labelledby").split()
            )
        if node.get("aria-label"):
            return node.get("aria-label")
        if node.tag == "img":
            return node.get("alt")
        if node.tag in ("input", "select", "textarea"):
            if node.get("type") in ("submit", "button"):
                return node.get("value")
            owner = next((a for a in node.ancestors() if a.tag == "label"), None)
            if owner is None and node.get("id"):
                owner = next(
                    (
                        n
                        for n in self.root.walk()
                        if n.tag == "label" and n.get("for") == node.get("id")
                    ),
                    None,
                )
            return owner.text() if owner is not None else ""
        return node.text()

    def pressables(self):
        """Everything on the page that is pressed rather than filled in."""
        for n in self.root.walk():
            if (
                n.tag == "button"
                or (n.tag == "input" and n.get("type") in ("submit", "button", "file"))
                or (n.tag == "a" and "btn" in n.classes())
                or n.get("role") == "button"
            ):
                yield n


def tree(page: str) -> Tree:
    return Tree(content(page))


def upload(client, kind, aid, n=1):
    for i in range(n):
        client.post(
            f"/{kind}/{aid}/photo",
            files={"photos": (f"p{i}.png", _png(), "image/png")},
            follow_redirects=False,
        )


@pytest.fixture
def stocked(client, computer, part):
    """A machine and a card with something in every panel an owner can press a
    button in: photographs, parts, notes, a history entry with photographs on it,
    and files."""
    pc = computer(name="Lounge PC")["asset_id"]
    io = part(type="io", model="Controller")["asset_id"]
    part(type="sound", model="SB16", computer_id=pc)
    part(type="video", model="VGA", computer_id=pc)
    for kind, aid in (("computers", pc), ("parts", io)):
        upload(client, kind, aid, 3)
        client.post(f"/{kind}/{aid}/note", data={"message": "Tested"})
        client.post(
            f"/{kind}/{aid}/note",
            data={"message": "Recapped"},
            files=[("photos", (f"r{i}.png", _png(), "image/png")) for i in range(2)],
        )
        client.post(f"/{kind}/{aid}/note", files=[("photos", ("only.png", _png(), "image/png"))])
        for name in ("a.img", "b.img"):
            client.post("/files", files={"uploads": (name, b"\0" * 100)}, data={"aid": aid})
    return {"computers": pc, "parts": io}


KINDS = pytest.mark.parametrize("kind", ["computers", "parts"])


class TestAPhotographIsNamedForWhatItShows:
    @KINDS
    def test_each_says_the_item_and_where_it_falls_among_them(self, client, stocked, kind):
        t = tree(client.get(f"/{kind}/{stocked[kind]}").text)
        shots = [n for n in t.root.walk() if n.get("data-group") == "photos"]
        name = next(n for n in t.root.walk() if n.tag == "h1").text()
        assert [t.name(n) for n in shots] == [f"{name}, photograph {i} of 3" for i in (1, 2, 3)]

    @KINDS
    def test_one_on_a_history_entry_is_named_by_the_entry(self, client, stocked, kind):
        t = tree(client.get(f"/{kind}/{stocked[kind]}").text)
        names = [t.name(n) for n in t.root.walk() if n.get("data-group").startswith("log-")]
        assert "Recapped, photograph 1 of 2" in names
        assert "Recapped, photograph 2 of 2" in names

    @KINDS
    def test_or_by_the_item_where_the_entry_is_only_photographs(self, client, stocked, kind):
        t = tree(client.get(f"/{kind}/{stocked[kind]}").text)
        name = next(n for n in t.root.walk() if n.tag == "h1").text()
        names = [t.name(n) for n in t.root.walk() if n.get("data-group").startswith("log-")]
        assert f"{name}, photograph 1 of 1" in names

    def test_pressing_one_still_opens_it(self, client, stocked):
        """The name is what it shows; that it opens is its role."""
        t = tree(client.get(f"/computers/{stocked['computers']}").text)
        shots = [n for n in t.root.walk() if "zoomable" in n.classes()]
        assert shots and all(n.get("role") == "button" for n in shots)


class TestAButtonOnALineSaysWhichLine:
    @KINDS
    def test_no_two_things_an_owner_presses_share_a_name(self, client, stocked, kind):
        """The buttons on each photograph are left out: they move into the full-size
        view, where they act on the one photograph open (#129)."""
        t = tree(client.get(f"/{kind}/{stocked[kind]}").text)
        names = Counter(
            t.name(n)
            for n in t.pressables()
            if not any("photo-ctrls" in a.classes() for a in n.ancestors())
        )
        assert {k: v for k, v in names.items() if v > 1} == {}

    @KINDS
    def test_a_history_entrys_delete_says_its_date_and_its_words(self, client, stocked, kind):
        t = tree(client.get(f"/{kind}/{stocked[kind]}").text)
        names = [t.name(n) for n in t.pressables()]
        said = [n for n in names if n.startswith("Delete history entry ")]
        assert any(
            re.fullmatch(r"Delete history entry \d{4}-\d\d-\d\d \d\d:\d\d Note Tested", n)
            for n in said
        )

    @KINDS
    def test_and_so_does_its_attach(self, client, stocked, kind):
        t = tree(client.get(f"/{kind}/{stocked[kind]}").text)
        names = [t.name(n) for n in t.pressables()]
        assert any(
            re.fullmatch(
                r"Attach a photograph to the entry \d{4}-\d\d-\d\d \d\d:\d\d Note Tested", n
            )
            for n in names
        ), names

    def test_a_parts_bin_says_which_part(self, client, stocked):
        page = client.get(f"/computers/{stocked['computers']}").text
        t = tree(page)
        bins = [t.name(n) for n in t.pressables() if t.name(n).startswith("Take out")]
        assert len(bins) == 2 and all(re.fullmatch(r"Take out RH-\w+", b) for b in bins)


class TestTheReferenceBadgeSaysWhatItMeans:
    @pytest.fixture
    def marked(self, client, computer):
        aid = computer(name="Lounge PC")["asset_id"]
        upload(client, "computers", aid)
        rel = re.search(r'data-rel="([^"]+)"', client.get(f"/computers/{aid}").text)[1]
        client.post(f"/computers/{aid}/photo-reference", data={"image": rel, "set": "1"})
        return aid

    def badges(self, page: str) -> list[str]:
        t = Tree(page)
        return [n.text() for n in t.root.walk() if "ref-badge" in n.classes()]

    def test_on_the_item_page(self, client, marked):
        assert self.badges(content(client.get(f"/computers/{marked}").text)) == [
            "Ref: reference image, not this unit"
        ]

    def test_on_its_card_in_the_gallery(self, client, marked):
        assert "Ref: reference image, not this unit" in self.badges(client.get("/").text)

    def test_the_words_are_for_the_ear_alone(self, client, marked):
        page = content(client.get(f"/computers/{marked}").text)
        assert re.search(
            r'class="ref-badge"><span aria-hidden="true">Ref</span>'
            r'<span class="sr-only">Ref: reference image, not this unit</span>',
            page,
        )

    def test_a_site_icon_is_decoration_beside_the_same_words(self):
        """The source site's favicon is the badge's look, not its meaning."""
        for path in ("_photocol.html", "_ui.html"):
            assert 'alt="source site"' not in (TEMPLATES / path).read_text()
        badge = (TEMPLATES / "_ui.html").read_text().split("macro refbadge", 1)[1]
        badge = badge.split("endmacro", 1)[0]
        assert '<img src="/images/{{ icon }}" alt="">' in badge


class TestTheCodeUnderThePhotographs:
    def test_is_a_picture_named_for_what_it_is_for(self, client, computer):
        aid = computer(name="Lounge PC")["asset_id"]
        t = tree(client.get(f"/computers/{aid}").text)
        code = next(n for n in t.root.walk() if "qr" in n.classes())
        assert code.get("role") == "img"
        assert t.name(code) == "Code for this page, to add photographs from a phone"


class TestWhatHappensWithoutYouIsReadOut:
    """Something that appears where you are not looking is announced from a region
    that is in the page before anything is said into it: a region that was hidden
    until the moment it spoke is not reliably heard."""

    def test_an_item_page_has_somewhere_to_say_it(self, client, computer):
        aid = computer()["asset_id"]
        page = client.get(f"/computers/{aid}").text
        assert re.search(r'<p class="sr-only" id="said" role="status"></p>', page)

    def test_uploading_is_said_as_the_upload_goes(self):
        js = (APP / "static" / "app.js").read_text()
        autosend = js[js.index("form[data-autosend]") :][:1500]
        assert "say(busy.textContent)" in autosend

    def test_a_changed_record_is_said_when_the_bar_appears(self):
        js = (APP / "static" / "live.js").read_text()
        assert re.search(r"bar\.hidden = false;\s*say\(", js)


class TestTheBannersAreDifferentKindsOfNews:
    @pytest.fixture
    def disposed(self, client, computer):
        aid = computer(name="Lounge PC")["asset_id"]
        client.post(
            f"/computers/{aid}/status",
            data={"status": "disposed", "note": "sold", "date": "2026-10-01"},
        )
        return aid

    def banner(self, page: str) -> Node:
        t = tree(page)
        return next(
            n for n in t.root.walk() if "banner" in n.classes() and "toast" not in n.classes()
        )

    def test_disposed_is_a_warning(self, client, disposed):
        b = self.banner(client.get(f"/computers/{disposed}").text)
        assert b.classes() == {"banner", "warning"}
        assert b.text().startswith("Disposed")

    def test_with_delete_at_its_right(self, client, disposed):
        """Restore went to the Status panel (MANUAL section 16); Delete… stays, as the
        one thing nothing else on the page does."""
        b = self.banner(client.get(f"/computers/{disposed}").text)
        last = [n for n in b.walk() if n.tag in ("button", "a") and "btn" in n.classes()]
        assert [n.text() for n in last] == ["Delete…"]
        assert any("push" in n.classes() for n in b.walk())

    def test_build_walk_is_plain(self, client, computer):
        aid = computer(name="Lounge PC")["asset_id"]
        page = client.get(f"/computers/{aid}?build=1").text
        b = self.banner(page)
        assert b.classes() == {"banner"}
        assert b.text().startswith("Build walk.")

    def test_every_banner_is_one_of_the_design_systems(self):
        """A tone the stylesheet does not draw is drawn as plain, which is how
        `warn` came to be a refusal with nothing to mark it as one."""
        tones = set()
        for path in TEMPLATES.glob("*.html"):
            src = path.read_text()
            tones |= set(re.findall(r"U\.banner\('([^']*)'", src))
            assert not re.search(
                r'class="banner(?: [^"]*)?"', src.replace('class="banner toast"', "")
            ), path.name
        assert tones <= {"", "warning", "danger", "success"}, tones

    def test_a_fetch_that_found_nothing_is_a_warning_at_the_top_of_the_panel(
        self, client, computer
    ):
        aid = computer(name="Lounge PC", url="https://example.com/pc")["asset_id"]
        t = tree(client.get(f"/computers/{aid}?imgerr=1").text)
        panel = next(n for n in t.root.walk() if "itemphotos" in n.classes())
        body = next(n for n in panel.walk() if "pbody" in n.classes())
        first = next(c for c in body.children if isinstance(c, Node))
        assert first.classes() == {"banner", "warning"}
        said = [c.text() for c in first.children if isinstance(c, Node)]
        assert said == [
            "Nothing found at the reference.",
            "Check the Reference URL, or add a photograph yourself.",
        ]
