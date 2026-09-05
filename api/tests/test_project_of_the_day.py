"""One project, suggested, at the top of the list.

A list of twenty projects in hand is a list nobody picks from: every one of them is
a decision, and the decision is what stops the evening before it starts. So the page
picks one -- and picks badly on purpose, leaning towards the ones nothing has been
written about for longest and the ones whose status says stalled, because the point
of a nudge is the thing you had forgotten rather than the one you were doing
yesterday.
"""
import re
from datetime import timedelta

from app import main
from app.models import LogEntry


def visitor(monkeypatch):
    monkeypatch.setattr(main, "AUTH_ENABLED", True)


def panel(html):
    """The suggestion, or None if the page is not making one."""
    m = re.search(r'<section class="panel">\s*<header[^>]*>\s*<h3[^>]*>Something to '
                  r'do today.*?</section>', html, re.S)
    return m.group(0) if m else None


def make(client, name, status="planned", **fields):
    return client.post("/api/projects",
                       json={"name": name, "status": status} | fields
                       ).json()["asset_id"]


def quieten(db, project_id, days):
    """Push a project's history back, which is the only measure of when it was last
    thought about at all."""
    for row in db.query(LogEntry).filter(LogEntry.asset_id == project_id):
        row.created_at = row.created_at - timedelta(days=days)
    db.commit()


class TestWhetherThereIsOne:
    def test_nothing_is_suggested_when_there_is_nothing_in_hand(self, client):
        assert panel(client.get("/projects").text) is None

    def test_a_project_in_hand_is_suggested(self, client):
        make(client, "Recap the +2A")
        assert "Recap the +2A" in panel(client.get("/projects").text)

    def test_a_finished_one_is_not(self, client):
        """What to do today is not a list of what was done. done and abandoned are
        the two that are over."""
        make(client, "Alreadyzzz", status="done")
        make(client, "Gaveupzzz", status="abandoned")
        assert panel(client.get("/projects").text) is None

    def test_a_search_puts_it_away(self, client):
        """The page is answering a question that was asked, and a suggestion above
        the answer is an interruption."""
        make(client, "Recap the +2A")
        assert panel(client.get("/projects?q=recap").text) is None

    def test_a_mistyped_tag_puts_it_away_too(self, client):
        make(client, "Recap the +2A")
        r = client.post("/projects/quick", data={"job": "x", "aid": "RH-ZZZZ"},
                        follow_redirects=False)
        assert r.status_code == 400
        assert panel(r.text) is None


class TestWhichOne:
    def test_a_visitor_is_never_offered_a_private_one(self, client, db,
                                                      monkeypatch):
        """The same rule the list below it follows. A suggestion is the loudest
        place on the page to leak one from."""
        make(client, "Hiddenzzz", private=True)
        visitor(monkeypatch)
        for _ in range(20):
            assert "Hiddenzzz" not in client.get("/projects").text

    def test_the_owner_can_be_offered_their_own_private_one(self, client, db):
        make(client, "Hiddenzzz", private=True)
        drawn = {panel(client.get("/projects").text) for _ in range(5)}
        assert any("Hiddenzzz" in d for d in drawn if d)

    def test_the_quiet_one_comes_up_more_often(self, client, db):
        """The weighting, which is the whole of what makes this a nudge rather than
        a shuffle. Two projects, one of them untouched for months: over enough draws
        the forgotten one has to come up more.

        Counted over many draws rather than asserted on one, because the draw is
        random and a test that demanded a particular winner would be a test of the
        seed."""
        old = make(client, "Forgottenzzz")
        make(client, "Freshzzz")
        quieten(db, old, 200)
        seen = [("Forgottenzzz" in (panel(client.get("/projects").text) or ""))
                for _ in range(60)]
        assert sum(seen) > 30

    def test_being_stalled_counts_for_something(self, client, db):
        """Stalled is the state somebody chose to record -- waiting on a part, the
        weather or the will -- and those are the ones that never come up again on
        their own."""
        make(client, "Stalledzzz", status="stalled")
        make(client, "Planningzzz")
        seen = [("Stalledzzz" in (panel(client.get("/projects").text) or ""))
                for _ in range(60)]
        assert sum(seen) > 30

    def test_the_one_worked_on_today_is_still_in_the_draw(self, client, db):
        """Weighted down, not excluded: what was worked on this morning is still a
        reasonable answer to what to do this afternoon."""
        make(client, "Freshzzz")
        assert "Freshzzz" in panel(client.get("/projects").text)


class TestWhatItShows:
    def project_about(self, client, **item):
        aid = client.post("/api/computers",
                          json={"manufacturer": "Amstrad", "model": "PC1640"}
                          | item).json()["asset_id"]
        pid = make(client, "Refurb the 1640")
        client.post(f"/api/projects/{pid}/items", json={"asset_id": aid})
        return aid, pid

    def test_it_names_the_things_the_project_is_about(self, client):
        self.project_about(client)
        assert "Amstrad PC1640" in panel(client.get("/projects").text)

    def test_it_lists_what_is_left_to_do(self, client):
        _, pid = self.project_about(client)
        client.post(f"/api/projects/{pid}/tasks", json={"text": "recap the PSU"})
        assert "recap the PSU" in panel(client.get("/projects").text)

    def test_a_ticked_job_is_not_something_to_do(self, client):
        _, pid = self.project_about(client)
        t = client.post(f"/api/projects/{pid}/tasks",
                        json={"text": "already donezzz"}).json()
        client.patch(f"/api/projects/{pid}/tasks/{t['id']}", json={"done": True})
        assert "already donezzz" not in panel(client.get("/projects").text)

    def test_it_shows_a_photograph_of_the_thing(self, client):
        """A project has no photographs of its own -- it is a piece of work, and what
        can be photographed is the hardware it is about."""
        import io

        from PIL import Image
        aid, _ = self.project_about(client)
        buf = io.BytesIO()
        Image.new("RGB", (40, 30), "red").save(buf, "JPEG")
        buf.seek(0)
        client.post(f"/computers/{aid}/photo",
                    files={"photos": ("shot.jpg", buf, "image/jpeg")},
                    follow_redirects=False)
        rel = main.detect_images("computers", aid)[0]
        assert rel in panel(client.get("/projects").text)

    def test_it_says_how_long_it_has_been_quiet(self, client, db):
        """The reason this one was drawn and not another, said plainly."""
        pid = make(client, "Forgottenzzz")
        quieten(db, pid, 40)
        assert "nothing written for 40 days" in panel(client.get("/projects").text)

    def test_a_project_with_nothing_written_down_says_so(self, client):
        make(client, "Emptyzzz")
        assert "No jobs written down" in panel(client.get("/projects").text)

    def test_one_waiting_on_a_part_says_that_instead(self, client):
        pid = make(client, "Waitingzzz")
        client.post(f"/api/projects/{pid}/orders",
                    json={"description": "a belt", "qty": 1})
        assert "still on order" in panel(client.get("/projects").text)
