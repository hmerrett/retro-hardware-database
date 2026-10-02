"""Who is told where things are kept (MANUAL §19 "Where things are kept"; ADR-0034).

Show locations decides it, and out of the box nobody but the people signed in is
told. A location's page is the same fact as an item's Location row at more length,
with a photograph of the room and directions to the rack, so it follows the same
switch -- and a visitor kept from it gets the 404 a private project gives, not a
login prompt, so a tag on a box says nothing about the box to a stranger.
"""

import io

import pytest
from PIL import Image

from app import settings
from conftest import as_viewer, content, log_out


@pytest.fixture
def location(client):
    def make(name="Box 14", kind="box", parent=None, notes=""):
        r = client.post(
            "/api/locations", json={"name": name, "kind": kind, "parent": parent, "notes": notes}
        )
        assert r.status_code == 200, r.text
        return r.json()["asset_id"]

    return make


def show_locations(client, on=True):
    data = {"public_locations": "1"} if on else {}
    r = client.post("/settings/server", data=data, follow_redirects=False)
    assert r.status_code == 303, r.text


def photograph(client, tag):
    buf = io.BytesIO()
    Image.new("RGB", (40, 30), "white").save(buf, format="JPEG")
    client.post(
        f"/locations/{tag}/photo",
        files={"photos": ("shelf.jpg", buf.getvalue(), "image/jpeg")},
        follow_redirects=False,
    )
    return client.get(f"/locations/{tag}").text


class TestWithShowLocationsOff:
    """The default (ADR-0027): a visitor is told nothing."""

    def test_it_is_off_by_default(self, client):
        assert settings.on("public_locations") is False

    def test_a_visitor_gets_nothing_here_for_a_locations_page(self, client, location):
        tag = location()
        log_out(client)
        r = client.get(f"/locations/{tag}", headers={"Accept": "text/html"}, follow_redirects=False)
        assert r.status_code == 404
        assert "Nothing here" in r.text

    def test_the_same_answer_as_for_a_tag_nothing_has(self, client, location):
        """Not a login prompt, which would say there is something to log in for."""
        tag = location()
        log_out(client)
        real = client.get(f"/locations/{tag}", follow_redirects=False)
        none = client.get("/locations/RH-ZZZZ", follow_redirects=False)
        assert (real.status_code, none.status_code) == (404, 404)

    def test_its_label_address_is_not_followed_for_a_visitor(self, client, location):
        """/items/<tag> answers 404 itself, rather than redirecting to a path that
        would say the tag is a location."""
        tag = location()
        log_out(client)
        r = client.get(f"/items/{tag}", follow_redirects=False)
        assert r.status_code == 404

    def test_its_labels_answer_nothing_here(self, client, location):
        tag = location()
        log_out(client)
        assert client.get(f"/locations/{tag}/label.pdf", follow_redirects=False).status_code == 404
        assert client.get(f"/locations/{tag}/labels.pdf", follow_redirects=False).status_code == 404

    def test_its_photographs_are_not_served_to_a_visitor(self, client, location):
        tag = location()
        page = photograph(client, tag)
        src = page.split('src="/images/locations/', 1)[1].split('"', 1)[0]
        assert client.get(f"/images/locations/{src}").status_code == 200, "the owner sees it"
        log_out(client)
        assert client.get(f"/images/locations/{src}").status_code == 404

    def test_a_visitor_is_not_shown_where_a_thing_moved(self, client, location, computer):
        """The history is public, and a move says where something is kept."""
        loft = location("Loft", "room")
        aid = computer(location=loft)["asset_id"]
        assert 'data-kind="move"' in client.get(f"/computers/{aid}").text, "the owner sees it"
        log_out(client)
        page = content(client.get(f"/computers/{aid}").text)
        assert 'data-kind="move"' not in page
        assert "Loft" not in page

    def test_a_visitors_search_does_not_match_on_a_location(self, client, location, computer):
        aid = computer(location=location("Loft", "room"))["asset_id"]
        log_out(client)
        assert aid not in content(client.get("/?q=loft").text)
        assert aid not in client.get("/suggest?q=loft").text

    def test_a_visitor_is_not_offered_a_location_by_the_suggestions(self, client, location):
        tag = location("Loft", "room")
        log_out(client)
        assert tag not in client.get("/suggest?q=loft").text

    def test_a_signed_in_viewer_sees_them_all_the_same(self, client, location, computer):
        tag = location()
        aid = computer(location=tag)["asset_id"]
        as_viewer(client)
        assert client.get(f"/locations/{tag}").status_code == 200
        assert f"/locations/{tag}" in client.get(f"/computers/{aid}").text

    def test_a_visitor_gets_nothing_here_for_the_list_of_locations(self, client, location):
        location()
        log_out(client)
        r = client.get("/locations", headers={"Accept": "text/html"}, follow_redirects=False)
        assert r.status_code == 404
        assert "Nothing here" in r.text

    def test_and_is_not_offered_the_section(self, client):
        """Not in the banner, the rail, the ⋯ menu or the phone's More, which are all
        in the page whatever its width: a section that answers 404 is a section
        saying there is something being kept back."""
        log_out(client)
        assert 'href="/locations"' not in client.get("/").text

    def test_a_signed_in_viewer_is_offered_the_section(self, client):
        as_viewer(client)
        assert 'href="/locations"' in client.get("/").text


class TestWithShowLocationsOn:
    def test_a_locations_page_is_as_public_as_an_item_page(self, client, location):
        tag = location(notes="third rack on the left")
        show_locations(client)
        log_out(client)
        r = client.get(f"/locations/{tag}")
        assert r.status_code == 200
        assert "third rack on the left" in r.text

    def test_so_are_its_photographs(self, client, location):
        tag = location()
        page = photograph(client, tag)
        src = page.split('src="/images/locations/', 1)[1].split('"', 1)[0]
        show_locations(client)
        log_out(client)
        assert client.get(f"/images/locations/{src}").status_code == 200

    def test_and_the_moves_on_an_items_history(self, client, location, computer):
        aid = computer(location=location("Loft", "room"))["asset_id"]
        show_locations(client)
        log_out(client)
        assert 'data-kind="move"' in client.get(f"/computers/{aid}").text

    def test_and_a_visitors_search_finds_by_them(self, client, location, computer):
        aid = computer(location=location("Loft", "room"))["asset_id"]
        show_locations(client)
        log_out(client)
        assert aid in content(client.get("/?q=loft").text)

    def test_and_the_list_of_locations_with_its_section(self, client, location):
        tag = location()
        show_locations(client)
        log_out(client)
        assert 'href="/locations"' in client.get("/").text
        assert f'href="/locations/{tag}"' in content(client.get("/locations").text)


class TestTheAuditIsForAdministrators:
    """Whichever way the switch is set: the audit moves things."""

    def test_a_viewer_is_turned_away(self, client):
        as_viewer(client)
        assert client.get("/audit", follow_redirects=False).status_code == 403

    def test_a_visitor_is_asked_to_log_in(self, client):
        log_out(client)
        r = client.get("/audit", follow_redirects=False)
        assert r.status_code == 303 and r.headers["location"].startswith("/login")

    def test_a_viewer_cannot_scan(self, client, location):
        tag = location()
        as_viewer(client)
        r = client.post("/audit/scan", data={"code": tag}, follow_redirects=False)
        assert r.status_code == 403
