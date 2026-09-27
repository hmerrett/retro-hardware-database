"""The item page, as MANUAL.md section 4 ("An item page") promises it: the name, the
tag and the summary at the top; the owner's Edit and Duplicate beside Prev and
Next; the photographs in a side column that comes straight after the summary on a
narrow screen; the Label panel with its two print buttons; a part's Specification
and where it is Fitted in, with Take out; and Take out on every part a machine or
a card lists.

Auth is off in these tests, so the client is the owner; `visitor` turns it on.
"""

import re
from pathlib import Path

import pytest

from conftest import content, log_out


def visitor(client):
    """Turn the site into what an anonymous reader sees."""
    log_out(client)


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
            r'<div class="itemhead">\s*<div class="titleline">\s*<h1 class="title">Lounge PC</h1>'
            rf'.*?</div>\s*<div class="tag muted">{aid}</div>',
            head,
            re.S,
        ), head[:300]
        assert '<p class="prose">Found in a loft.</p>' in head[: head.index('class="itembody"')]

    @KINDS
    def test_there_is_one_heading_at_the_top(self, client, computer, part, kind):
        page = client.get(f"/{kind}/{item(kind, computer, part)}").text
        assert page.count("<h1") == 1

    @KINDS
    def test_the_owner_has_edit_and_duplicate_on_the_name_s_line(
        self, client, computer, part, kind
    ):
        """With what they act on, and out of the navigation landmark, since Duplicate
        is a form that posts (MANUAL §4)."""
        aid = item(kind, computer, part)
        page = client.get(f"/{kind}/{aid}").text
        line = re.search(r'<div class="titleline">(.*?)</div>\s*<div class="tag', page, re.S)[1]
        assert "<h1" in line
        assert f'href="/{kind}/{aid}/edit"' in line
        assert f'action="/{kind}/{aid}/duplicate"' in line
        nav = top_row(page)
        assert "/edit" not in nav and "<form" not in nav

    @KINDS
    def test_a_visitor_has_neither(self, client, computer, part, kind, monkeypatch):
        aid = item(kind, computer, part)
        visitor(client)
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
        visitor(client)
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
        visitor(client)
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
        visitor(client)
        assert "Take out" not in client.get(f"/computers/{cid}").text


def ways_back(html):
    """The links at the left of an item page's top row, before the spacer that pushes
    the owner's actions and Prev and Next to the right: the ways back."""
    nav = re.search(r'<nav class="itemnav".*?</nav>', html, re.S)[0]
    return re.findall(r'href="([^"]*)"', nav.split('<span class="push">')[0])


class TestTheWayBackToWhatAPartIsIn:
    """v0.1's part page had "← all · ← RH-…" to the machine the part is in; v0.2's
    shared item top kept only the first, and a part reached from its machine had no
    way back to it but the browser's."""

    def test_a_part_in_a_machine_leads_back_to_it(self, client, computer, part):
        cid = computer(model="PC1512")["asset_id"]
        pid = part(type="sound", computer_id=cid)["asset_id"]
        assert ways_back(client.get(f"/parts/{pid}").text) == ["/", f"/computers/{cid}"]

    def test_a_part_on_another_part_leads_back_to_that_part(self, client, part):
        host = part(type="io", model="Controller")["asset_id"]
        pid = part(type="storage", model="ST-225", parent_id=host)["asset_id"]
        assert ways_back(client.get(f"/parts/{pid}").text) == ["/", f"/parts/{host}"]

    def test_a_part_on_its_own_and_a_machine_have_only_the_way_back_to_the_register(
        self, client, computer, part
    ):
        pid = part(type="sound")["asset_id"]
        cid = computer()["asset_id"]
        assert ways_back(client.get(f"/parts/{pid}").text) == ["/"]
        assert ways_back(client.get(f"/computers/{cid}").text) == ["/"]


ITEM_CSS = Path(__file__).parents[1] / "app" / "static" / "css" / "components.css"


def item_css():
    return re.sub(r"/\*.*?\*/", "", ITEM_CSS.read_text(encoding="utf-8"), flags=re.S)


def top_row(html):
    return re.search(r'<nav class="itemnav".*?</nav>', html, re.S)[0]


class TestTheTopOfThePage:
    """The review found the actions standing above the photographs rather than with
    the name, a form that posts inside the navigation landmark, the two columns
    starting at different heights, and a phone's Tab key reaching the label before
    the details (MANUAL §4, "An item page")."""

    def test_the_top_row_holds_the_ways_back_and_prev_and_next_alone(self, client, computer):
        row = top_row(client.get(f"/computers/{computer()['asset_id']}").text)
        assert 'id="nav-prev"' in row and 'id="nav-next"' in row and 'href="/"' in row
        assert "/edit" not in row and "<form" not in row

    def test_a_visitor_sees_no_actions(self, client, computer):
        aid = computer()["asset_id"]
        log_out(client)
        html = client.get(f"/computers/{aid}").text
        assert "/edit" not in html and "/duplicate" not in html

    def test_the_page_reads_head_photographs_details_then_the_rest(self, client, computer):
        html = client.get(f"/computers/{computer()['asset_id']}").text
        at = [
            html.index(f'class="{c}"') for c in ("itemhead", "itemphotos", "itembody", "itemside")
        ]
        assert at == sorted(at)

    def test_nothing_is_moved_out_of_its_place_in_the_source(self):
        """The Tab key follows the source; an `order` would draw a panel somewhere the
        Tab key does not go."""
        itemcols = re.findall(r"\.itemcols[^{]*\{([^}]*)\}", item_css())
        assert itemcols and not any(re.search(r"(?:^|[;\s])order\s*:", body) for body in itemcols)

    def test_the_side_column_starts_level_with_the_details(self):
        rule = re.search(r"\.itemcols\s*\{([^}]*)\}", item_css())[1]
        areas = re.findall(r'"([^"]+)"', rule.split("grid-template-areas:")[1].split(";")[0])
        assert areas == ["head head", "body photos", "body side"]

    def test_on_a_phone_the_actions_go_under_the_name(self):
        phone = re.search(r"@media \(max-width: 560px\) \{([^@]*?\.itemacts[^}]*\})", item_css())
        assert phone and "flex-basis: 100%" in phone[1]

    def test_a_disposed_item_says_so_under_its_name(self, client, db, computer):
        from app.models import Computer

        aid = computer()["asset_id"]
        db.get(Computer, aid).disposed = True
        db.commit()
        html = client.get(f"/computers/{aid}").text
        head = re.search(
            r'<div class="itemhead">(.*?)<(?:aside|div) class="itemphotos"', html, re.S
        )[1]
        assert "<b>Disposed</b>" in head

    def test_a_project_s_actions_are_on_its_name_s_line_too(self, client):
        made = client.post("/api/projects", json={"name": "Recap the PC1512"}).json()
        html = client.get(f"/projects/{made['asset_id']}").text
        assert "<form" not in top_row(html)
        line = re.search(r'<div class="titleline">(.*?)</div>\s*</div>', html, re.S)
        assert line and "Mark done" in line[1] and "/edit" in line[1] and "/delete" in line[1]
