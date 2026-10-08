"""Moves (MANUAL §15, "Moves"; ADR-0034).

Every time a thing or a location changes where it is kept, its history records a
move: where it was, where it went, when, who, and how. A box that moves records the
move on its own history and only there.
"""

import pytest

from app.models import LogEntry, Move
from conftest import content


@pytest.fixture
def location(client):
    def make(name, kind="box", parent=None):
        r = client.post("/api/locations", json={"name": name, "kind": kind, "parent": parent})
        assert r.status_code == 200, r.text
        return r.json()["asset_id"]

    return make


def moves_of(db, aid):
    db.expire_all()
    return db.query(Move).filter(Move.asset_id == aid).order_by(Move.id).all()


class TestAMoveIsWrittenDown:
    def test_an_edit_records_where_it_was_and_where_it_went(self, client, db, location, computer):
        loft = location("Loft", "room")
        bench = location("Bench", "other")
        aid = computer(location=loft)["asset_id"]
        client.post(
            f"/computers/{aid}/edit",
            data={"manufacturer": "Acme", "model": "Test", "location": "Bench"},
            follow_redirects=False,
        )
        last = moves_of(db, aid)[-1]
        assert (last.from_id, last.to_id) == (loft, bench)
        assert (last.from_path, last.to_path) == ("Loft", "Bench")

    def test_it_says_who_and_that_it_was_by_edit(self, client, db, location, computer):
        loft = location("Loft", "room")
        aid = computer()["asset_id"]
        client.post(
            f"/computers/{aid}/edit",
            data={"manufacturer": "Acme", "model": "Test", "location": loft},
            follow_redirects=False,
        )
        last = moves_of(db, aid)[-1]
        assert (last.who, last.how) == ("owner", "edit")
        assert last.moved_at is not None

    def test_one_made_through_the_api_says_so(self, client, db, location, part):
        loft = location("Loft", "room")
        aid = part()["asset_id"]
        client.patch(f"/api/parts/{aid}", json={"location": loft})
        last = moves_of(db, aid)[-1]
        assert (last.who, last.how) == ("owner", "api")

    def test_saving_without_a_change_records_nothing(self, client, db, location, computer):
        loft = location("Loft", "room")
        aid = computer(location=loft)["asset_id"]
        before = len(moves_of(db, aid))
        client.post(
            f"/computers/{aid}/edit",
            data={"manufacturer": "Acme", "model": "Test", "location": "Loft"},
            follow_redirects=False,
        )
        assert len(moves_of(db, aid)) == before

    def test_the_history_shows_it_with_a_link_at_each_end(self, client, location, computer):
        loft = location("Loft", "room")
        bench = location("Bench", "other")
        aid = computer(location=loft)["asset_id"]
        client.patch(f"/api/computers/{aid}", json={"location": bench})
        page = content(client.get(f"/computers/{aid}").text)
        line = page.split('data-kind="move"', 1)[1].split("</dd>", 1)[0]
        assert f'<a href="/items/{loft}">Loft</a>' in line
        assert f'<a href="/items/{bench}">Bench</a>' in line
        assert "through the API" in line and "owner" in line


class TestAMovingBox:
    def test_records_one_move_on_the_box(self, client, db, location, computer):
        loft = location("Loft", "room")
        box = location("Box 14")
        aid = computer(location=box)["asset_id"]
        before = len(moves_of(db, aid))
        client.patch(f"/api/locations/{box}", json={"parent": loft})
        assert [(m.from_id, m.to_id) for m in moves_of(db, box)][-1] == (None, loft)
        assert len(moves_of(db, aid)) == before, "nobody moved the thing in the box"

    def test_its_page_shows_the_move(self, client, location):
        loft = location("Loft", "room")
        box = location("Box 14")
        client.patch(f"/api/locations/{box}", json={"parent": loft})
        page = content(client.get(f"/locations/{box}").text)
        assert f'<a href="/items/{loft}">Loft</a>' in page.split('data-kind="move"', 1)[1]


class TestTheApiReadsThemBack:
    def test_newest_first(self, client, location, computer):
        a, b = location("Loft", "room"), location("Bench", "other")
        aid = computer(location=a)["asset_id"]
        client.patch(f"/api/computers/{aid}", json={"location": b})
        got = client.get(f"/api/items/{aid}/moves").json()
        assert [(m["from"], m["to"]) for m in got] == [(a, b), (None, a)]
        assert {"from_path", "to_path", "moved_at", "who", "how"} <= set(got[0])

    def test_a_location_has_them_too(self, client, location):
        loft = location("Loft", "room")
        box = location("Box 14")
        client.patch(f"/api/locations/{box}", json={"parent": loft})
        assert client.get(f"/api/items/{box}/moves").json()[0]["to"] == loft

    def test_the_log_carries_the_move_as_words(self, client, db, location, computer):
        loft = location("Loft", "room")
        aid = computer(location=loft)["asset_id"]
        db.expire_all()
        line = db.query(LogEntry).filter(LogEntry.asset_id == aid, LogEntry.kind == "move").one()
        assert line.message == "moved from nowhere recorded to Loft, through the API"
