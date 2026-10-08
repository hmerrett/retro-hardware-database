"""Locations as records (MANUAL §14 "Storage", §5 "Where it is kept"; ADR-0034).

A location is a thing in the register with a tag from the same pool, a page and a
label, and a thing is kept in one. Locations are kept in other locations, and the
path is worked out rather than written down -- which is what makes moving a box one
edit. These are the promises the manual makes about all of that, one to a test.
"""

import re
from html.parser import HTMLParser

import pytest

from app.models import Computer, Location, Part
from conftest import as_viewer, content, log_out

TAG = re.compile(r"RH-[0-9A-HJKMNP-Z]{4}")


class Outline(HTMLParser):
    """Which location each listed location is listed under, read off the nesting of
    the page's lists rather than off its indent: {tag: the tag above it, or None}."""

    def __init__(self) -> None:
        super().__init__()
        self.open: list[str | None] = []
        self.under: dict[str, str | None] = {}

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        if tag == "li":
            self.open.append(None)
            return
        page = re.fullmatch(r"/locations/(RH-\w{4})", dict(attrs).get("href") or "")
        if tag == "a" and page and self.open and self.open[-1] is None:
            self.open[-1] = page[1]
            above = [t for t in self.open[:-1] if t]
            self.under[page[1]] = above[-1] if above else None

    def handle_endtag(self, tag: str) -> None:
        if tag == "li" and self.open:
            self.open.pop()


def listed(client) -> dict[str, str | None]:
    outline = Outline()
    outline.feed(content(client.get("/locations").text))
    return outline.under


def line_of(page: str, tag: str) -> str:
    """A location's own line on the list: its name and what is said beside it, up to
    the list of what is inside it."""
    return re.split(r"<ul|</li>", page.split(f'href="/locations/{tag}"', 1)[1], maxsplit=1)[0]


@pytest.fixture
def location(client):
    """A saved location, as the API makes one."""

    def make(name="Box 14", kind="box", parent=None, notes=""):
        r = client.post(
            "/api/locations", json={"name": name, "kind": kind, "parent": parent, "notes": notes}
        )
        assert r.status_code == 200, r.text
        return r.json()["asset_id"]

    return make


@pytest.fixture
def workshop(location):
    """Workshop → Rack 3 → Shelf 2 → Box 14, by tag, top first."""
    room = location("Workshop", "room")
    rack = location("Rack 3", "rack", room)
    shelf = location("Shelf 2", "shelf", rack)
    box = location("Box 14", "box", shelf)
    return room, rack, shelf, box


def make_location(client, **fields):
    data = {"name": "Box 14", "kind": "box", "parent": "", "notes": ""} | fields
    return client.post("/locations/new", data=data, follow_redirects=False)


class TestALocation:
    """The record itself: a name, a kind, the location it is inside, and notes."""

    def test_it_takes_a_tag_from_the_registers_pool(self, client, location, computer):
        tag = location()
        assert TAG.fullmatch(tag)
        assert tag != computer()["asset_id"]

    def test_its_label_address_opens_its_page(self, client, location):
        """/items/<tag> is the address every label carries, whatever the tag is."""
        tag = location()
        r = client.get(f"/items/{tag}", follow_redirects=False)
        assert r.headers["location"] == f"/locations/{tag}"

    def test_new_location_makes_one_and_opens_its_page(self, client, db):
        r = make_location(client, name="Blue crate", kind="box", notes="under the stairs")
        assert r.status_code == 303
        tag = r.headers["location"].rsplit("/", 1)[-1]
        made = db.get(Location, tag)
        assert (made.name, made.kind, made.notes) == ("Blue crate", "box", "under the stairs")

    def test_the_form_offers_the_seven_kinds(self, client):
        page = client.get("/locations/new").text
        kinds = re.findall(r'<option value="([a-z]+)"', page.split('name="kind"', 1)[1])[:7]
        assert kinds == ["building", "room", "rack", "shelf", "box", "bag", "other"]

    def test_a_kind_it_does_not_offer_is_refused(self, client, db):
        r = make_location(client, kind="drawer")
        assert r.status_code == 400
        assert db.query(Location).count() == 0

    def test_a_name_is_required(self, client, db):
        r = make_location(client, name="  ")
        assert r.status_code == 400
        assert db.query(Location).count() == 0

    def test_inside_says_which_location_it_is_in(self, client, db, location):
        shelf = location("Shelf 2", "shelf")
        r = make_location(client, parent="Shelf 2")
        tag = r.headers["location"].rsplit("/", 1)[-1]
        assert db.get(Location, tag).inside_id == shelf

    def test_inside_left_blank_is_the_top_of_a_tree(self, client, db):
        tag = make_location(client, name="Workshop", kind="room").headers["location"][-7:]
        assert db.get(Location, tag).inside_id is None

    def test_a_location_cannot_be_put_inside_itself(self, client, db, workshop):
        room, *_ = workshop
        r = client.post(
            f"/locations/{room}/edit",
            data={"name": "Workshop", "kind": "room", "parent": room, "notes": ""},
            follow_redirects=False,
        )
        assert r.status_code == 400
        assert "inside itself" in r.text
        assert db.get(Location, room).inside_id is None

    def test_or_inside_anything_that_is_inside_it(self, client, db, workshop):
        room, _rack, _shelf, box = workshop
        r = client.post(
            f"/locations/{room}/edit",
            data={"name": "Workshop", "kind": "room", "parent": box, "notes": ""},
            follow_redirects=False,
        )
        assert r.status_code == 400
        assert db.get(Location, room).inside_id is None

    def test_an_empty_box_stays_on_the_register(self, client, db, location, computer):
        """An empty crate keeps its name and its label for the next time it is filled."""
        tag = location("Blue crate")
        aid = computer(location=tag)["asset_id"]
        client.patch(f"/api/computers/{aid}", json={"location": ""})
        assert db.get(Location, tag) is not None


class TestDeletingALocation:
    """A box is where things are, not what they are made of: deleting one deletes
    nothing in it (ADR-0036)."""

    def test_a_thing_in_it_is_kept_and_left_nowhere(self, client, db, location, computer):
        tag = location()
        aid = computer(location=tag)["asset_id"]
        r = client.post(f"/locations/{tag}/delete", follow_redirects=False)
        assert r.status_code == 303
        db.expire_all()
        assert db.get(Location, tag) is None
        assert db.get(Computer, aid).inside_id is None

    def test_so_is_a_location_in_it_with_its_contents(self, client, db, workshop):
        room, rack, *_ = workshop
        r = client.post(f"/locations/{room}/delete", follow_redirects=False)
        assert r.status_code == 303
        db.expire_all()
        assert db.get(Location, rack).inside_id is None

    def test_an_empty_one_is_deleted(self, client, db, location):
        tag = location()
        r = client.post(f"/locations/{tag}/delete", follow_redirects=False)
        assert r.status_code == 303
        assert db.get(Location, tag) is None

    def test_empty_into_the_location_above_puts_its_contents_where_it_was(
        self, client, db, workshop, location, computer, part
    ):
        _room, _rack, shelf, box = workshop
        bag = location("Bag 6", "bag", box)
        cid = computer(location=box)["asset_id"]
        pid = part(location=box)["asset_id"]
        r = client.post(f"/locations/{box}/empty", follow_redirects=False)
        assert r.status_code == 303
        db.expire_all()
        assert db.get(Computer, cid).inside_id == shelf
        assert db.get(Part, pid).inside_id == shelf
        assert db.get(Location, bag).inside_id == shelf
        assert client.post(f"/locations/{box}/delete", follow_redirects=False).status_code == 303

    def test_merge_into_puts_one_spelling_of_a_crate_into_the_other(
        self, client, db, location, computer
    ):
        """What the upgrade leaves behind when a crate was typed two ways: everything
        in the one moves into the other, which keeps its tag, and the first goes."""
        keep = location("Loft", "room")
        twin = location("loft crate", "other")
        inside = location("Bag 6", "bag", twin)
        aid = computer(location=twin)["asset_id"]
        r = client.post(f"/locations/{twin}/merge", data={"into": keep}, follow_redirects=False)
        assert r.status_code == 303
        assert r.headers["location"] == f"/locations/{keep}"
        db.expire_all()
        assert db.get(Location, twin) is None
        assert db.get(Computer, aid).inside_id == keep
        assert db.get(Location, inside).inside_id == keep

    def test_merging_a_location_into_its_own_contents_is_refused(self, client, db, workshop):
        room, _rack, _shelf, box = workshop
        r = client.post(f"/locations/{room}/merge", data={"into": box}, follow_redirects=False)
        assert r.status_code == 400
        assert db.get(Location, room) is not None


class TestALocationsPage:
    def test_it_shows_the_path_each_step_a_link(self, client, workshop):
        room, rack, shelf, box = workshop
        page = content(client.get(f"/locations/{box}").text)
        for tag, name in ((room, "Workshop"), (rack, "Rack 3"), (shelf, "Shelf 2")):
            assert f'<a href="/locations/{tag}">{name}</a>' in page

    def test_it_shows_its_name_tag_kind_and_notes(self, client, location):
        tag = location("Box 14", "box", notes="third rack on the left")
        page = content(client.get(f"/locations/{tag}").text)
        assert "Box 14" in page and tag in page
        assert "Box" in page
        assert "third rack on the left" in page

    def test_it_lists_the_locations_inside_with_what_each_holds_all_the_way_down(
        self, client, workshop, location, computer
    ):
        _room, _rack, shelf, box = workshop
        bag = location("Bag 6", "bag", box)
        computer(location=box)
        computer(location=bag)
        page = content(client.get(f"/locations/{shelf}").text)
        row = page.split(f'href="/locations/{box}"', 1)[1].split("</li>", 1)[0]
        assert "2 things" in row

    def test_it_lists_the_things_kept_in_it(self, client, location, computer, part):
        tag = location()
        cid = computer(location=tag, model="PC1512")["asset_id"]
        pid = part(location=tag, model="TVGA8900")["asset_id"]
        page = content(client.get(f"/locations/{tag}").text)
        assert f"/computers/{cid}" in page and f"/parts/{pid}" in page

    def test_a_part_fitted_in_a_machine_here_is_not_listed_again(
        self, client, location, computer, part
    ):
        """It goes where the machine goes, and the machine is listed."""
        tag = location()
        cid = computer(location=tag)["asset_id"]
        pid = part(computer_id=cid)["asset_id"]
        page = content(client.get(f"/locations/{tag}").text)
        assert f"/computers/{cid}" in page
        assert f"/parts/{pid}" not in page

    def test_something_disposed_of_is_not_kept_anywhere(self, client, location, computer):
        tag = location()
        aid = computer(location=tag)["asset_id"]
        client.patch(f"/api/computers/{aid}", json={"disposed": True})
        page = content(client.get(f"/locations/{tag}").text)
        assert f"/computers/{aid}" not in page
        assert "Empty" in page

    def test_an_empty_location_says_so(self, client, location):
        page = content(client.get(f"/locations/{location()}").text)
        assert "Empty" in page

    def test_its_label_panel_prints_its_labels(self, client, location):
        tag = location()
        page = content(client.get(f"/locations/{tag}").text)
        assert f"/locations/{tag}/label.pdf" in page
        assert f"/locations/{tag}/labels.pdf" in page

    def test_its_history_says_when_it_was_made(self, client, location):
        page = content(client.get(f"/locations/{location()}").text)
        assert "created" in page

    def test_its_path_starts_from_the_list_of_locations(self, client, workshop):
        _room, _rack, _shelf, box = workshop
        page = content(client.get(f"/locations/{box}").text)
        path = page.split('class="pathnav"', 1)[1].split("</nav>", 1)[0]
        assert re.findall(r'href="([^"]+)"', path)[0] == "/locations"


class TestEveryLocation:
    """Locations, the section: the whole tree on one page, which is where the
    spellings the upgrade made into locations are found to be put away."""

    def test_each_location_is_listed_under_the_one_it_is_inside(self, client, workshop, location):
        room, rack, shelf, box = workshop
        loft = location("Loft", "room")
        assert listed(client) == {room: None, rack: room, shelf: rack, box: shelf, loft: None}

    def test_each_says_its_kind_its_tag_and_what_it_holds_all_the_way_down(
        self, client, workshop, computer
    ):
        room, _rack, shelf, box = workshop
        computer(location=box)
        computer(location=shelf)
        page = content(client.get("/locations").text)
        assert "Room" in line_of(page, room) and room in line_of(page, room)
        assert "2 things" in line_of(page, room)
        assert "2 things" in line_of(page, shelf)
        assert "1 thing" in line_of(page, box) and "things" not in line_of(page, box)

    def test_the_locations_in_one_place_are_in_order_of_name_numbers_as_numbers(
        self, client, location
    ):
        rack = location("Rack 3", "rack")
        for name in ("Shelf 10", "Shelf 2", "shelf 1", "Bin"):
            location(name, "shelf", rack)
        location("Attic", "room")
        page = content(client.get("/locations").text)
        names = re.findall(r'<a href="/locations/RH-\w{4}">([^<]+)</a>', page)
        assert names == ["Attic", "Rack 3", "Bin", "shelf 1", "Shelf 2", "Shelf 10"]

    def test_each_name_opens_its_page(self, client, location):
        tag = location("Blue crate")
        assert f'<a href="/locations/{tag}">Blue crate</a>' in content(
            client.get("/locations").text
        )

    def test_an_empty_location_is_listed_too(self, client, location, computer):
        empty = location("Spare crate")
        computer(location=location("Full crate"))
        assert "0 things" in line_of(content(client.get("/locations").text), empty)

    def test_an_administrator_can_add_one_from_the_top_of_the_list(self, client, location):
        location()
        assert 'href="/locations/new"' in content(client.get("/locations").text)

    def test_a_viewer_reads_the_list_and_is_not_offered_to_add_to_it(self, client, location):
        tag = location()
        as_viewer(client)
        page = content(client.get("/locations").text)
        assert f'href="/locations/{tag}"' in page
        assert 'href="/locations/new"' not in page

    def test_a_register_with_no_locations_yet_says_so(self, client):
        assert "No locations yet" in content(client.get("/locations").text)


class TestWhereAThingIs:
    """An item page's Location row (MANUAL §14, "Where a thing is")."""

    @pytest.mark.parametrize("kind", ["computers", "parts"])
    def test_the_row_shows_the_whole_path_each_step_a_link(
        self, client, workshop, computer, part, kind
    ):
        room, rack, shelf, box = workshop
        aid = (computer(location=box) if kind == "computers" else part(location=box))["asset_id"]
        page = content(client.get(f"/{kind}/{aid}").text)
        row = page.split("<dt>Location</dt>", 1)[1].split("</dd>", 1)[0]
        for tag, name in (
            (room, "Workshop"),
            (rack, "Rack 3"),
            (shelf, "Shelf 2"),
            (box, "Box 14"),
        ):
            assert f'<a href="/locations/{tag}">{name}</a>' in row

    def test_the_locations_notes_are_under_it(self, client, location, computer):
        tag = location("Box 14", notes="third rack on the left")
        aid = computer(location=tag)["asset_id"]
        row = client.get(f"/computers/{aid}").text.split("<dt>Location</dt>", 1)[1]
        assert "third rack on the left" in row.split("</dd>", 1)[0]

    def test_also_here_leads_to_the_rest_of_the_box(self, client, location, computer):
        tag = location()
        aid = computer(location=tag)["asset_id"]
        computer(location=tag)
        row = client.get(f"/computers/{aid}").text.split("<dt>Location</dt>", 1)[1]
        row = row.split("</dd>", 1)[0]
        assert "Also here" in row and f'href="/locations/{tag}"' in row

    def test_nothing_else_there_is_no_also_here(self, client, location, computer):
        aid = computer(location=location())["asset_id"]
        assert "Also here" not in client.get(f"/computers/{aid}").text

    def test_a_fitted_part_shows_its_machines_location_and_says_so(
        self, client, location, computer, part
    ):
        tag = location()
        cid = computer(location=tag)["asset_id"]
        pid = part(computer_id=cid)["asset_id"]
        page = client.get(f"/parts/{pid}").text
        assert f'<a href="/locations/{tag}">Box 14</a>' in page
        assert f'where <a href="/computers/{cid}">{cid}</a> is' in page

    def test_moving_the_box_moves_what_is_in_it(self, client, workshop, location, computer):
        """One edit, to the box: the thing inside is somewhere new at that moment."""
        _room, _rack, _shelf, box = workshop
        loft = location("Loft", "room")
        aid = computer(location=box)["asset_id"]
        client.patch(f"/api/locations/{box}", json={"parent": loft})
        row = client.get(f"/computers/{aid}").text.split("<dt>Location</dt>", 1)[1]
        row = row.split("</dd>", 1)[0]
        assert f'<a href="/locations/{loft}">Loft</a>' in row
        assert "Workshop" not in row


class TestTheLocationBox:
    """The Location box on a machine's and a part's form (MANUAL §5, "Where it is
    kept")."""

    def offered(self, client, path):
        page = client.get(path).text
        found = re.search(r'<datalist id="dl_locations">(.*?)</datalist>', page, re.S)
        assert found, "the box offers no list"
        return re.findall(r'<option value="([^"]*)"', found.group(1))

    def test_it_offers_every_location_by_its_path(self, client, workshop, location):
        location("Loft", "room")
        offered = self.offered(client, "/computers/new")
        assert "Workshop / Rack 3 / Shelf 2 / Box 14" in offered
        assert "Loft" in offered

    def test_the_part_form_offers_the_same(self, client, workshop):
        assert "Workshop / Rack 3 / Shelf 2 / Box 14" in self.offered(client, "/parts/new")

    def test_choosing_a_path_puts_it_there(self, client, db, workshop, computer):
        *_, box = workshop
        aid = computer()["asset_id"]
        client.post(
            f"/computers/{aid}/edit",
            data={
                "manufacturer": "Acme",
                "model": "Test",
                "location": "Workshop / Rack 3 / Shelf 2 / Box 14",
            },
            follow_redirects=False,
        )
        db.expire_all()
        assert db.get(Computer, aid).inside_id == box

    def test_a_tag_will_do(self, client, db, location, part):
        tag = location()
        aid = part()["asset_id"]
        client.post(
            f"/parts/{aid}/edit",
            data={"type": "other", "model": "Widget", "location": tag.lower()},
            follow_redirects=False,
        )
        db.expire_all()
        assert db.get(Part, aid).inside_id == tag

    def test_a_name_that_matches_no_location_makes_one_at_the_top(self, client, db, computer):
        aid = computer()["asset_id"]
        client.post(
            f"/computers/{aid}/edit",
            data={"manufacturer": "Acme", "model": "Test", "location": "Under the bench"},
            follow_redirects=False,
        )
        db.expire_all()
        made = db.get(Location, db.get(Computer, aid).inside_id)
        assert (made.name, made.kind, made.inside_id) == ("Under the bench", "other", None)

    def test_a_name_two_locations_share_is_refused_rather_than_guessed(
        self, client, db, location, computer
    ):
        location("Box 14", "box", location("Workshop", "room"))
        location("Box 14", "box", location("Loft", "room"))
        aid = computer()["asset_id"]
        r = client.post(
            f"/computers/{aid}/edit",
            data={"manufacturer": "Acme", "model": "Test", "location": "Box 14"},
            follow_redirects=False,
        )
        assert r.status_code == 400
        assert "More than one location is called Box 14" in r.text
        db.expire_all()
        assert db.get(Computer, aid).inside_id is None

    def test_the_tag_of_something_that_is_not_a_location_is_refused(self, client, computer):
        other = computer()["asset_id"]
        aid = computer()["asset_id"]
        r = client.post(
            f"/computers/{aid}/edit",
            data={"manufacturer": "Acme", "model": "Test", "location": other},
            follow_redirects=False,
        )
        assert r.status_code == 400
        assert f"{other} is a computer, not a location" in r.text

    def test_blank_is_nowhere_recorded(self, client, db, location, computer):
        aid = computer(location=location())["asset_id"]
        client.post(
            f"/computers/{aid}/edit",
            data={"manufacturer": "Acme", "model": "Test", "location": ""},
            follow_redirects=False,
        )
        db.expire_all()
        assert db.get(Computer, aid).inside_id is None

    def test_the_form_shows_the_path_it_holds(self, client, workshop, computer):
        *_, box = workshop
        aid = computer(location=box)["asset_id"]
        page = client.get(f"/computers/{aid}/edit").text
        assert 'value="Workshop / Rack 3 / Shelf 2 / Box 14"' in page

    def test_a_new_machine_can_be_put_away_as_it_is_entered(self, client, db, location):
        tag = location()
        r = client.post(
            "/computers/new",
            data={"manufacturer": "Acme", "model": "Test", "location": "Box 14"},
            follow_redirects=False,
        )
        aid = r.headers["location"].split("/")[2].split("?")[0]
        assert db.get(Computer, aid).inside_id == tag


class TestSearchingByWhereThingsAre:
    """MANUAL §3: where a thing is kept is searched along its whole path."""

    def test_a_search_for_the_top_finds_what_is_at_the_bottom(self, client, workshop, computer):
        *_, box = workshop
        aid = computer(location=box)["asset_id"]
        assert aid in content(client.get("/?q=workshop").text)

    def test_a_search_for_a_locations_name_finds_what_is_in_it(self, client, workshop, computer):
        *_, box = workshop
        aid = computer(location=box)["asset_id"]
        other = computer()["asset_id"]
        page = content(client.get('/?q="box 14"').text)
        assert aid in page and other not in page

    def test_a_part_in_a_machine_in_a_box_is_found_by_the_box(
        self, client, workshop, computer, part
    ):
        *_, box = workshop
        cid = computer(location=box)["asset_id"]
        pid = part(computer_id=cid)["asset_id"]
        assert pid in content(client.get("/?q=workshop").text)

    def test_a_thing_that_has_left_is_not_found_by_where_it_was(self, client, location, computer):
        """Its history says it was in the loft; the search is for what is there now."""
        loft = location("Loft", "room")
        aid = computer(location=loft)["asset_id"]
        client.patch(f"/api/computers/{aid}", json={"location": "Garage"})
        assert aid not in content(client.get("/?q=loft").text)

    def test_the_suggestions_offer_locations_with_their_paths(self, client, workshop):
        *_, box = workshop
        found = client.get("/suggest?q=box 14").json()["items"]
        row = next(i for i in found if i["aid"] == box)
        assert row["cat"] == "Location"
        assert row["url"] == f"/locations/{box}"
        assert row["here"] == "in Workshop / Rack 3 / Shelf 2"


class TestATagInTheSearchBox:
    """MANUAL §3: an asset tag on its own opens what it belongs to."""

    @pytest.mark.parametrize("kind", ["computers", "parts"])
    def test_enter_on_a_tag_opens_the_thing(self, client, computer, part, kind):
        aid = (computer() if kind == "computers" else part())["asset_id"]
        r = client.get(f"/?q={aid.lower()}", follow_redirects=False)
        assert r.status_code == 303
        assert r.headers["location"] == f"/{kind}/{aid}"

    def test_and_a_location(self, client, location):
        tag = location()
        r = client.get(f"/?q={tag}", follow_redirects=False)
        assert r.headers["location"] == f"/locations/{tag}"

    def test_a_scanned_label_url_does_the_same(self, client, computer):
        aid = computer()["asset_id"]
        r = client.get(f"/?q=https://example.test/items/{aid}/", follow_redirects=False)
        assert r.headers["location"] == f"/computers/{aid}"

    def test_a_tag_nothing_has_is_an_ordinary_search(self, client):
        r = client.get("/?q=RH-ZZZZ", follow_redirects=False)
        assert r.status_code == 200

    def test_a_visitor_is_not_taken_to_a_private_project(self, client):
        tag = client.post("/api/projects", json={"name": "Secret", "private": True}).json()[
            "asset_id"
        ]
        log_out(client)
        r = client.get(f"/?q={tag}", follow_redirects=False)
        assert r.status_code == 200
        assert f"/projects/{tag}" not in content(r.text)

    def test_nor_to_a_location_while_locations_are_not_shown(self, client, location):
        tag = location()
        log_out(client)
        r = client.get(f"/?q={tag}", follow_redirects=False)
        assert r.status_code == 200
        assert f"/locations/{tag}" not in content(r.text)


class TestTheApi:
    """MANUAL §20: `location` on a computer or a part, and /api/locations."""

    def test_a_thing_reads_back_its_locations_tag_and_path(self, client, workshop, computer):
        *_, box = workshop
        got = computer(location=box)
        assert got["location"] == box
        assert got["location_path"] == "Workshop / Rack 3 / Shelf 2 / Box 14"

    def test_nowhere_recorded_reads_back_blank(self, client, computer):
        got = computer()
        assert (got["location"], got["location_path"]) == ("", "")

    def test_a_name_matching_one_location_means_that_one(self, client, location, part):
        tag = location("Spares drawer", "other")
        assert part(location="spares drawer")["location"] == tag

    def test_a_name_matching_none_makes_one_at_the_top(self, client, db, part):
        got = part(location="Spares drawer")
        made = db.get(Location, got["location"])
        assert (made.name, made.kind, made.inside_id) == ("Spares drawer", "other", None)

    def test_a_name_matching_several_is_refused_with_the_tags(self, client, location):
        a = location("Box 14", "box", location("Workshop", "room"))
        b = location("Box 14", "box", location("Loft", "room"))
        r = client.post("/api/computers", json={"model": "Test", "location": "Box 14"})
        assert r.status_code == 422
        assert a in r.text and b in r.text

    def test_location_path_is_ignored_if_sent(self, client, location, computer):
        aid = computer(location=location())["asset_id"]
        r = client.patch(f"/api/computers/{aid}", json={"location_path": "Nowhere"})
        assert r.json()["location_path"] == "Box 14"

    def test_the_list_gives_each_location_with_its_path(self, client, workshop):
        listed = {row["asset_id"]: row for row in client.get("/api/locations").json()}
        *_, box = workshop
        assert listed[box]["path"] == "Workshop / Rack 3 / Shelf 2 / Box 14"
        assert listed[box]["kind"] == "box"

    def test_one_location_comes_with_what_is_in_it(self, client, workshop, location, computer):
        _room, _rack, shelf, box = workshop
        aid = computer(location=shelf)["asset_id"]
        got = client.get(f"/api/locations/{shelf}").json()
        assert got["things"] == [aid]
        assert got["locations"] == [box]

    def test_a_patch_renames_and_refiles(self, client, db, location):
        tag = location("Box 14")
        loft = location("Loft", "room")
        got = client.patch(
            f"/api/locations/{tag}", json={"name": "Box 15", "kind": "bag", "parent": loft}
        ).json()
        assert (got["name"], got["kind"], got["parent"]) == ("Box 15", "bag", loft)
        assert got["path"] == "Loft / Box 15"

    def test_a_parent_inside_itself_is_refused(self, client, workshop):
        room, *_, box = workshop
        assert client.patch(f"/api/locations/{room}", json={"parent": box}).status_code == 422

    def test_an_unknown_kind_is_refused(self, client):
        r = client.post("/api/locations", json={"name": "Drawer", "kind": "drawer"})
        assert r.status_code == 422

    def test_delete_leaves_what_was_in_it_nowhere(self, client, location, computer):
        """A box is where things are, not what they are made of (ADR-0036)."""
        tag = location()
        aid = computer(location=tag)["asset_id"]
        assert client.delete(f"/api/locations/{tag}").status_code == 200
        assert client.get(f"/api/computers/{aid}").json()["location"] == ""

    def test_delete_of_an_empty_one_goes_through(self, client, db, location):
        tag = location()
        assert client.delete(f"/api/locations/{tag}").status_code == 200
        assert db.get(Location, tag) is None
