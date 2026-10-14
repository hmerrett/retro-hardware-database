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
from conftest import log_out


def visitor(client):
    log_out(client)


def panel(html):
    """The suggestion, or None if the page is not making one."""
    m = re.search(
        r'<section class="panel today">\s*<header[^>]*>\s*<h3[^>]*>Something to '
        r"do today.*?</section>",
        html,
        re.S,
    )
    return m.group(0) if m else None


def make(client, name, status="planned", **fields):
    return client.post("/api/projects", json={"name": name, "status": status} | fields).json()[
        "asset_id"
    ]


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
        r = client.post(
            "/projects/quick", data={"job": "x", "aid": "RH-ZZZZ"}, follow_redirects=False
        )
        assert r.status_code == 400
        assert panel(r.text) is None


class TestWhichOne:
    def test_a_visitor_is_never_offered_a_private_one(self, client, db, monkeypatch):
        """The same rule the list below it follows. A suggestion is the loudest
        place on the page to leak one from."""
        make(client, "Hiddenzzz", private=True)
        visitor(client)
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
        seen = [("Forgottenzzz" in (panel(client.get("/projects").text) or "")) for _ in range(60)]
        assert sum(seen) > 30

    def test_being_stalled_counts_for_something(self, client, db):
        """Stalled is the state somebody chose to record -- waiting on a part, the
        weather or the will -- and those are the ones that never come up again on
        their own."""
        make(client, "Stalledzzz", status="stalled")
        make(client, "Planningzzz")
        seen = [("Stalledzzz" in (panel(client.get("/projects").text) or "")) for _ in range(60)]
        assert sum(seen) > 30

    def test_the_one_worked_on_today_is_still_in_the_draw(self, client, db):
        """Weighted down, not excluded: what was worked on this morning is still a
        reasonable answer to what to do this afternoon."""
        make(client, "Freshzzz")
        assert "Freshzzz" in panel(client.get("/projects").text)


class TestWhatItShows:
    def project_about(self, client, **item):
        aid = client.post(
            "/api/computers", json={"manufacturer": "Amstrad", "model": "PC1640"} | item
        ).json()["asset_id"]
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
        t = client.post(f"/api/projects/{pid}/tasks", json={"text": "already donezzz"}).json()
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
        client.post(
            f"/computers/{aid}/photo",
            files={"photos": ("shot.jpg", buf, "image/jpeg")},
            follow_redirects=False,
        )
        rel = main.detect_images("computers", aid)[0]
        assert rel in panel(client.get("/projects").text)

    def test_it_says_how_long_it_has_been_quiet(self, client, db):
        """The reason this one was drawn and not another, said plainly."""
        pid = make(client, "Forgottenzzz")
        quieten(db, pid, 40)
        assert "nothing written for 40 days" in panel(client.get("/projects").text)

    def test_a_project_with_nothing_written_down_says_so(self, client):
        make(client, "Emptyzzz")
        assert "No jobs yet" in panel(client.get("/projects").text)

    def test_one_waiting_on_a_part_says_that_instead(self, client):
        pid = make(client, "Waitingzzz")
        client.post(f"/api/projects/{pid}/orders", json={"description": "a belt", "qty": 1})
        assert "1 on order" in panel(client.get("/projects").text)


def shown(html):
    """The asset tag of the project the panel is suggesting."""
    return re.search(r'<h4><a href="/projects/([^"]+)">', panel(html)).group(1)


def shuffle(html):
    """The panel's Shuffle control, or None."""
    m = re.search(r"<a [^>]*data-shuffle[^>]*>[^<]*</a>", panel(html))
    return m.group(0) if m else None


class TestShuffle:
    """Drawing again was always there -- a reload did it -- but nothing said so, and
    nobody guesses that reloading a page changes what is on it."""

    def test_the_panel_has_a_shuffle_that_is_a_link(self, client):
        """A link and not a button, so it works with no script at all: following it
        is the reload, and the reload is the draw."""
        tag = make(client, "Recap the +2A")
        control = shuffle(client.get("/projects").text)
        assert control is not None
        assert f'href="/projects?instead_of={tag}"' in control
        assert ">Shuffle</a>" in control

    def test_it_never_hands_back_the_one_on_screen(self, client):
        """Weighted, the same project could come up twice running, and a Shuffle that
        changes nothing reads as a Shuffle that is broken."""
        first = make(client, "Recap the +2A")
        second = make(client, "Re-cap the C64 PSU")
        for _ in range(20):
            assert shown(client.get(f"/projects?instead_of={first}").text) == second

    def test_it_stands_in_the_title_band_not_under_the_project(self, client, db):
        """Under the project it moved with every draw -- across with the number of
        photographs, down with the number of jobs -- so it had to be found again
        before it could be pressed again. The band is the same whatever is drawn."""
        pid = make(client, "Recap the +2A")
        for n in range(4):
            client.post(f"/api/projects/{pid}/tasks", json={"text": f"job {n}"})
        p = panel(client.get("/projects").text)
        band = re.search(r"<header[^>]*>(.*?)</header>", p, re.S).group(1)
        body = re.search(r'<div class="pbody">.*', p, re.S).group(0)
        assert "data-shuffle" in band
        assert "data-shuffle" not in body
        # After the title, so it is read as the panel's control rather than its name.
        assert band.index("Something to do today") < band.index("data-shuffle")

    def test_its_focus_ring_is_drawn_in_the_bands_own_ink(self):
        """The ring is --focus everywhere else, and on a band it can all but vanish:
        #0000cd on rubberkey's black, #40318d on breadbin's brown. The band's text
        colour is held to 4.5:1 against the band in every preset (test_presets.PAIRS),
        so a ring drawn in it is seen wherever the band is -- the lightbox's answer
        to its scrim, for the same reason."""
        sheet = (main.STATIC_DIR / "css" / "components.css").read_text()
        assert re.search(
            r"\.panel > header :focus-visible \{ outline-color: var\(--band-text\); \}", sheet
        )

    def test_with_only_one_in_hand_it_comes_back(self, client):
        """Nothing else to offer is not a reason to offer nothing."""
        only = make(client, "Recap the +2A")
        assert shown(client.get(f"/projects?instead_of={only}").text) == only

    def test_a_visitor_has_it_too(self, client):
        make(client, "Recap the +2A")
        visitor(client)
        assert shuffle(client.get("/projects").text) is not None

    def test_a_visitor_shuffling_is_still_never_offered_a_private_one(self, client):
        first = make(client, "Recap the +2A")
        second = make(client, "Re-cap the C64 PSU")
        make(client, "Hiddenzzz", private=True)
        visitor(client)
        for _ in range(20):
            page = client.get(f"/projects?instead_of={first}").text
            assert shown(page) == second
            assert "Hiddenzzz" not in page

    def test_naming_one_that_is_not_there_changes_nothing(self, client):
        """A stale link, or a private tag a visitor has been handed: the draw goes
        ahead as though it had not been named, and the page says nothing about it."""
        make(client, "Recap the +2A")
        hidden = make(client, "Hiddenzzz", private=True)
        visitor(client)
        for tag in ("RH-ZZZZ", hidden, ""):
            r = client.get(f"/projects?instead_of={tag}")
            assert r.status_code == 200
            assert shown(r.text) != hidden

    def test_it_follows_the_button_text_setting(self, client):
        from test_settings import save

        make(client, "Recap the +2A")
        save(client, button_case="lower")
        assert ">shuffle</a>" in shuffle(client.get("/projects").text)

    def test_with_script_it_swaps_the_panel_in_place(self, client):
        """The page loads the script that fetches the next draw and puts it where
        the last one was, so the list below does not move and the place on the page
        is kept."""
        make(client, "Recap the +2A")
        page = client.get("/projects").text
        assert re.search(r'<script defer src="/static/today\.js\?v=[^"]+"></script>', page)
        script = (main.STATIC_DIR / "today.js").read_text()
        assert "[data-shuffle]" in script
        assert ".today" in script

    def test_with_script_shuffle_is_handed_the_next_draw_to_send_away(self, client):
        """Shuffle is not swapped with the body, being outside it, so its address is
        taken from the page that was fetched: otherwise the second press would ask to
        leave out the first project rather than the one on screen."""
        script = (main.STATIC_DIR / "today.js").read_text()
        assert re.search(r"\.today \[data-shuffle\]'\)", script), "reads the new draw's Shuffle"
        assert "go.setAttribute('href'" in script
