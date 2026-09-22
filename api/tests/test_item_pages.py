"""The item page, as MANUAL.md section 4 ("An item page") promises it: the name, the
tag and the summary at the top; the owner's Edit and Duplicate beside Prev and
Next; the photographs in a side column that comes straight after the summary on a
narrow screen; the Label panel with its two print buttons; a part's Specification
and where it is Fitted in, with Take out; and Take out on every part a machine or
a card lists.

Auth is off in these tests, so the client is the owner; `visitor` turns it on.
"""

import re

import pytest

from app import main
from conftest import content


def visitor(monkeypatch):
    """Turn the site into what an anonymous reader sees."""
    monkeypatch.setattr(main.auth, "AUTH_ENABLED", True)


def panel(page: str, title: str) -> str:
    """The markup of the panel with this title, up to the next panel or the column's
    end. Empty when there is no such panel."""
    m = re.search(
        rf"<section class=\"panel[^\"]*\">\s*<header>\s*<h3>{re.escape(title)}</h3>", page
    )
    if not m:
        return ""
    rest = page[m.end() :]
    stop = re.search(r'<section class="panel|</aside>|</div>\s*</div>\s*</main>', rest)
    return rest[: stop.start()] if stop else rest


def item(kind, computer, part, **fields):
    return (computer(**fields) if kind == "computers" else part(**fields))["asset_id"]


KINDS = pytest.mark.parametrize("kind", ["computers", "parts"])


class TestTheHead:
    @KINDS
    def test_the_page_opens_on_the_name_the_tag_and_the_summary(self, client, computer, part, kind):
        aid = item(kind, computer, part, name="Lounge PC", summary="Found in a loft.")
        page = client.get(f"/{kind}/{aid}").text
        head = page[page.index('<div class="itemhead">') :]
        assert re.match(
            r'<div class="itemhead">\s*<h1 class="title">Lounge PC</h1>\s*'
            rf'<div class="tag muted">{aid}</div>',
            head,
        ), head[:300]
        assert '<p class="prose">Found in a loft.</p>' in head[: head.index('class="itembody"')]

    @KINDS
    def test_there_is_one_heading_at_the_top(self, client, computer, part, kind):
        page = client.get(f"/{kind}/{item(kind, computer, part)}").text
        assert page.count("<h1") == 1

    @KINDS
    def test_the_owner_has_edit_and_duplicate_beside_prev_and_next(
        self, client, computer, part, kind
    ):
        aid = item(kind, computer, part)
        page = client.get(f"/{kind}/{aid}").text
        nav = page[page.index('<nav class="itemnav"') :]
        nav = nav[: nav.index("</nav>")]
        assert f'href="/{kind}/{aid}/edit"' in nav
        assert f'action="/{kind}/{aid}/duplicate"' in nav
        assert nav.index("/edit") < nav.index('id="nav-prev"')

    @KINDS
    def test_a_visitor_has_neither(self, client, computer, part, kind, monkeypatch):
        aid = item(kind, computer, part)
        visitor(monkeypatch)
        page = client.get(f"/{kind}/{aid}").text
        assert f"/{kind}/{aid}/edit" not in page
        assert f"/{kind}/{aid}/duplicate" not in page

    @KINDS
    def test_the_way_back_is_to_the_whole_register(self, client, computer, part, kind):
        page = client.get(f"/{kind}/{item(kind, computer, part)}").text
        assert re.search(r'<nav class="itemnav" [^>]*><a href="/">', page)


class TestTheDisplayFace:
    @KINDS
    def test_an_item_page_preloads_the_face_its_name_is_set_in(self, client, computer, part, kind):
        page = client.get(f"/{kind}/{item(kind, computer, part)}").text
        assert re.search(
            r'<link rel="preload" href="/static/fonts/source-serif-4/[^"]+\.woff2" as="font"', page
        )

    def test_the_gallery_does_not(self, client, computer):
        computer()
        assert 'rel="preload"' not in client.get("/").text


class TestTheSideColumn:
    @KINDS
    def test_the_photographs_come_before_the_details(self, client, computer, part, kind):
        """In the source, so that one column on a phone reads summary, photograph,
        details: a visitor from a label wants to see they have the right thing."""
        page = content(client.get(f"/{kind}/{item(kind, computer, part)}").text)
        order = [
            page.index(s)
            for s in (
                'class="itemhead"',
                "<aside",
                "<h3>Photographs</h3>",
                'class="itembody"',
                "<h3>Details</h3>",
            )
        ]
        assert order == sorted(order)

    @KINDS
    def test_the_label_panel_prints_both_labels(self, client, computer, part, kind):
        aid = item(kind, computer, part)
        label = panel(client.get(f"/{kind}/{aid}").text, "Label")
        assert f'href="/{kind}/{aid}/label.pdf?small=1"' in label
        assert re.search(rf'href="/{kind}/{aid}/label\.pdf(\?small=0)?"', label)
        assert "Small label" in label and "Full label" in label

    @KINDS
    def test_a_visitor_has_no_label_panel(self, client, computer, part, kind, monkeypatch):
        aid = item(kind, computer, part)
        visitor(monkeypatch)
        page = client.get(f"/{kind}/{aid}").text
        assert not panel(page, "Label")
        assert "label.pdf" not in page


class TestAPartsSpecification:
    def test_the_specs_are_a_panel_of_their_own(self, client, part):
        aid = part(type="storage", specs="Capacity: 32 MiB | Heads: 4")["asset_id"]
        spec = panel(client.get(f"/parts/{aid}").text, "Specification")
        assert '<dl class="specs">' in spec
        assert re.search(r"<dt>Capacity</dt>\s*<dd>32 MiB</dd>", spec)

    def test_a_part_with_no_specs_has_no_panel(self, client, part):
        page = client.get(f"/parts/{part()['asset_id']}").text
        assert not panel(page, "Specification")


class TestFittedIn:
    def test_a_part_in_a_machine_names_it_and_offers_take_out(self, client, computer, part):
        cid = computer(model="PS/1")["asset_id"]
        aid = part(computer_id=cid)["asset_id"]
        fitted = panel(client.get(f"/parts/{aid}").text, "Fitted in")
        assert f'href="/computers/{cid}"' in fitted
        assert f'action="/parts/{aid}/unlink"' in fitted
        assert ">Take out</button>" in fitted

    def test_a_part_on_a_card_names_the_card_and_offers_take_out(self, client, part):
        host = part(type="io", model="Controller")["asset_id"]
        aid = part(type="storage", parent_id=host)["asset_id"]
        fitted = panel(client.get(f"/parts/{aid}").text, "Fitted in")
        assert f'href="/parts/{host}"' in fitted
        assert f'action="/parts/{aid}/detach"' in fitted
        assert ">Take out</button>" in fitted

    def test_taking_it_out_makes_it_a_spare(self, client, computer, part):
        cid = computer()["asset_id"]
        aid = part(computer_id=cid)["asset_id"]
        client.post(f"/parts/{aid}/unlink", follow_redirects=False)
        assert "Not fitted in anything." in panel(client.get(f"/parts/{aid}").text, "Fitted in")

    def test_a_spare_says_so_and_offers_fit_in(self, client, computer, part):
        cid = computer()["asset_id"]
        aid = part()["asset_id"]
        fitted = panel(client.get(f"/parts/{aid}").text, "Fitted in")
        assert "Not fitted in anything." in fitted
        assert f'action="/parts/{aid}/link"' in fitted
        assert f'<option value="{cid}">' in fitted
        assert ">Fit in</button>" in fitted

    def test_a_visitor_sees_where_it_is_and_nothing_to_press(
        self, client, computer, part, monkeypatch
    ):
        cid = computer()["asset_id"]
        aid = part(computer_id=cid)["asset_id"]
        visitor(monkeypatch)
        fitted = panel(client.get(f"/parts/{aid}").text, "Fitted in")
        assert f'href="/computers/{cid}"' in fitted
        assert "<form" not in fitted


class TestTakeOutOnTheLists:
    def test_a_machines_parts_each_offer_take_out(self, client, computer, part):
        cid = computer()["asset_id"]
        aid = part(computer_id=cid)["asset_id"]
        parts = panel(client.get(f"/computers/{cid}").text, "Parts")
        assert f'action="/parts/{aid}/unlink"' in parts
        assert ">Take out</button>" in parts

    def test_a_cards_mounted_parts_each_offer_take_out(self, client, part):
        host = part(type="io")["asset_id"]
        aid = part(type="storage", parent_id=host)["asset_id"]
        mounted = panel(client.get(f"/parts/{host}").text, "Mounted parts")
        assert f'action="/parts/{aid}/detach"' in mounted
        assert ">Take out</button>" in mounted

    def test_a_visitor_is_offered_neither(self, client, computer, part, monkeypatch):
        cid = computer()["asset_id"]
        part(computer_id=cid)
        visitor(monkeypatch)
        assert "Take out" not in client.get(f"/computers/{cid}").text
