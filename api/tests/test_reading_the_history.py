"""Reading an item's history, as MANUAL.md section 15 ("Reading it") promises it: a
line at the top saying when it was acquired, where from and how long it has been
held; Notes, Changes and All as links with addresses of their own, opening on Notes
unless there are none; and the latest twenty lines, then Show all.
"""

import html
import re
from datetime import date, datetime, timedelta

import pytest

from app.history import held_for
from app.models import Computer, LogEntry
from conftest import log_out
from test_files import project

PAGES = pytest.mark.parametrize("kind", ["computers", "parts"])


def make(kind, computer, part, **fields):
    return (computer if kind == "computers" else part)(**fields)["asset_id"]


def panel(page: str) -> str:
    """The History panel, alone."""
    found = re.search(r"<h3>History</h3>.*?</section>", page, re.S)
    assert found, "the page has no History panel"
    return found.group(0)


def said(page: str) -> list[str]:
    """What each line of the history says, top to bottom, its chip included."""
    return [
        " ".join(re.sub(r"<[^>]+>", " ", html.unescape(m)).split())
        for m in re.findall(r'<div class="logmsg" id="log-\d+-what">(.*?)</div>', panel(page), re.S)
    ]


def timeline(page: str) -> str | None:
    found = re.search(r'<p class="ptimeline">(.*?)</p>', panel(page), re.S)
    return (
        " ".join(re.sub(r"<[^>]+>", " ", html.unescape(found.group(1))).split()) if found else None
    )


def views(page: str) -> dict[str, str]:
    """The three links: words to href."""
    nav = re.search(
        r'<nav class="[^"]*\blogviews\b[^"]*" aria-label="Which entries">(.*?)</nav>',
        panel(page),
        re.S,
    )
    assert nav, "the panel has no Notes, Changes and All"
    return {
        " ".join(w.split()): html.unescape(h)
        for h, w in re.findall(r'<a href="([^"]+)"[^>]*>(.*?)</a>', nav.group(1), re.S)
    }


def shown_view(page: str) -> str:
    nav = re.search(r'aria-label="Which entries">(.*?)</nav>', panel(page), re.S).group(1)
    current = re.findall(r'<a [^>]*aria-current="page"[^>]*>(.*?)</a>', nav, re.S)
    assert len(current) == 1, current
    return current[0].strip()


def show_all(page: str) -> tuple[str, str] | None:
    found = re.search(r'<a class="btn[^"]*" href="([^"]+)"[^>]*>(Show all \d+)</a>', panel(page))
    return (html.unescape(found.group(1)), found.group(2)) if found else None


def write(db, aid, *lines, start=datetime(2026, 1, 1, 12, 0)):
    """The item's history, and nothing else: these lines, oldest first, ten minutes
    apart so none of them fold. Whatever creating it wrote goes first."""
    db.query(LogEntry).filter(LogEntry.asset_id == aid).delete()
    for i, (kind, message) in enumerate(lines):
        db.add(
            LogEntry(
                asset_id=aid,
                kind=kind,
                message=message,
                created_at=start + timedelta(minutes=10 * i),
            )
        )
    db.commit()


def years_ago(n: int) -> date:
    today = date.today()
    try:
        return today.replace(year=today.year - n)
    except ValueError:  # 29 February
        return today.replace(year=today.year - n, day=28)


class TestHowLongItHasBeenHere:
    @PAGES
    def test_the_line_says_when_it_was_acquired_where_from_and_how_long_held(
        self, client, computer, part, kind
    ):
        aid = make(kind, computer, part, acquired_date=str(years_ago(2)), source="Club swap meet")
        line = timeline(client.get(f"/{kind}/{aid}").text)
        assert line == f"Acquired {years_ago(2)} from Club swap meet · held 2 years", line

    def test_a_visitor_reads_the_line_too(self, client, computer):
        aid = computer(acquired_date="2024-05-18", source="Club swap meet")["asset_id"]
        log_out(client)
        assert timeline(client.get(f"/computers/{aid}").text).startswith(
            "Acquired 2024-05-18 from Club swap meet · held"
        )

    def test_for_something_disposed_of_the_time_held_runs_to_the_day_it_went(
        self, client, db, computer
    ):
        aid = computer(acquired_date="2020-01-15", source="eBay")["asset_id"]
        c = db.get(Computer, aid)
        c.disposed, c.disposed_at = True, date(2022, 5, 20)
        db.commit()
        line = timeline(client.get(f"/computers/{aid}").text)
        assert line == "Acquired 2020-01-15 from eBay · held 2 years 4 months", line

    def test_with_no_date_of_disposal_there_is_no_figure(self, client, db, computer):
        aid = computer(acquired_date="2020-01-15")["asset_id"]
        c = db.get(Computer, aid)
        c.disposed, c.disposed_at = True, None
        db.commit()
        assert timeline(client.get(f"/computers/{aid}").text) == "Acquired 2020-01-15"

    def test_with_no_acquired_date_the_line_says_only_where_it_came_from(self, client, computer):
        aid = computer(source="Club swap meet")["asset_id"]
        assert timeline(client.get(f"/computers/{aid}").text) == "From Club swap meet"

    def test_with_an_acquired_date_and_no_source_the_line_leaves_the_source_out(
        self, client, computer
    ):
        aid = computer(acquired_date=str(years_ago(3)))["asset_id"]
        line = timeline(client.get(f"/computers/{aid}").text)
        assert line == f"Acquired {years_ago(3)} · held 3 years", line

    @PAGES
    def test_with_neither_the_line_is_not_there(self, client, computer, part, kind):
        aid = make(kind, computer, part)
        assert timeline(client.get(f"/{kind}/{aid}").text) is None

    def test_a_project_and_a_location_have_no_such_line(self, client):
        tag = client.post("/api/locations", json={"name": "Workshop", "kind": "room"}).json()[
            "asset_id"
        ]
        for page in (f"/projects/{project(client)}", f"/locations/{tag}"):
            assert timeline(client.get(page).text) is None, page


class TestHeldFor:
    @pytest.mark.parametrize(
        ("start", "end", "words"),
        [
            (date(2024, 5, 18), date(2026, 9, 18), "2 years 4 months"),
            (date(2024, 5, 18), date(2026, 9, 17), "2 years 3 months"),
            (date(2025, 9, 18), date(2026, 9, 18), "1 year"),
            (date(2026, 8, 1), date(2026, 9, 1), "1 month"),
            (date(2026, 9, 1), date(2026, 9, 30), "less than a month"),
            (date(2026, 9, 1), date(2026, 9, 1), "less than a month"),
        ],
    )
    def test_years_and_months_as_a_person_would_say_them(self, start, end, words):
        assert held_for(start, end) == words

    def test_a_date_after_the_end_gives_no_figure(self):
        assert held_for(date(2027, 1, 1), date(2026, 1, 1)) is None


class TestNotesFirst:
    @PAGES
    def test_the_panel_opens_on_notes_and_the_photographs_added_as_entries(
        self, client, db, computer, part, kind
    ):
        aid = make(kind, computer, part)
        write(db, aid, ("change", "edited model"), ("note", "recapped"), ("photo", ""))
        page = client.get(f"/{kind}/{aid}").text
        assert shown_view(page) == "Notes"
        assert said(page) == ["Photo", "Note recapped"]

    def test_changes_are_what_the_register_wrote(self, client, db, computer):
        aid = computer()["asset_id"]
        write(db, aid, ("note", "recapped"), ("change", "edited model"))
        page = client.get(f"/computers/{aid}?log=changes").text
        assert shown_view(page) == "Changes"
        assert "Note recapped" not in said(page)
        assert "edited model" in said(page)

    def test_all_is_both_newest_first(self, client, db, computer):
        aid = computer()["asset_id"]
        write(db, aid, ("note", "recapped"), ("change", "edited model"), ("note", "tested"))
        page = client.get(f"/computers/{aid}?log=all").text
        assert shown_view(page) == "All"
        assert said(page)[:3] == ["Note tested", "edited model", "Note recapped"]

    def test_with_no_notes_yet_it_opens_on_all(self, client, db, computer):
        aid = computer()["asset_id"]
        write(db, aid, ("change", "edited model"))
        page = client.get(f"/computers/{aid}").text
        assert shown_view(page) == "All"
        assert "edited model" in said(page)

    def test_pressing_notes_there_says_no_notes_yet(self, client, db, computer):
        aid = computer()["asset_id"]
        write(db, aid, ("change", "edited model"))
        page = client.get(f"/computers/{aid}?log=notes").text
        assert shown_view(page) == "Notes"
        assert said(page) == []
        assert "No notes yet." in panel(page)

    def test_an_address_naming_no_view_opens_as_the_bare_one_does(self, client, db, computer):
        aid = computer()["asset_id"]
        write(db, aid, ("note", "recapped"))
        assert shown_view(client.get(f"/computers/{aid}?log=sideways").text) == "Notes"

    def test_each_view_is_a_link_of_its_own(self, client, computer):
        aid = computer()["asset_id"]
        links = views(client.get(f"/computers/{aid}").text)
        assert list(links) == ["Notes", "Changes", "All"]
        assert [h.split("#")[0] for h in links.values()] == [
            "?log=notes",
            "?log=changes",
            "?log=all",
        ]

    def test_a_visitor_has_the_same_three(self, client, db, computer):
        aid = computer()["asset_id"]
        write(db, aid, ("note", "recapped"))
        log_out(client)
        page = client.get(f"/computers/{aid}").text
        assert list(views(page)) == ["Notes", "Changes", "All"]
        assert said(page) == ["Note recapped"]

    def test_on_a_tabbed_page_the_links_stay_on_the_history_tab(self, client, computer):
        aid = computer()["asset_id"]
        page = client.get(f"/computers/{aid}?layout=tabs&tab=history").text
        assert views(page)["Changes"].split("#")[0] == "?tab=history&log=changes"

    def test_the_history_tab_counts_every_line_whichever_view_is_open(self, client, db, computer):
        aid = computer()["asset_id"]
        write(db, aid, ("note", "recapped"), ("change", "edited model"), ("change", "edited year"))
        page = client.get(f"/computers/{aid}?layout=tabs&tab=history&log=notes").text
        tab = re.search(r'<nav class="tabs itemtabs".*?</nav>', page, re.S).group(0)
        assert re.search(r"History\s*<span[^>]*>3</span>", tab), tab


class TestComingBackToTheViewYouWereReading:
    def test_the_note_box_sends_the_view_and_comes_back_to_it(self, client, computer):
        aid = computer()["asset_id"]
        page = client.get(f"/computers/{aid}?log=changes").text
        action = html.unescape(
            re.search(r'<form method="post" action="([^"]+/note[^"]*)"', panel(page)).group(1)
        )
        assert action == f"/computers/{aid}/note?log=changes"
        r = client.post(action, data={"message": "recapped"}, follow_redirects=False)
        assert r.headers["location"] == f"/computers/{aid}?log=changes"

    def test_a_tabbed_page_keeps_both_the_tab_and_the_view(self, client, computer):
        aid = computer()["asset_id"]
        page = client.get(f"/computers/{aid}?layout=tabs&tab=history&log=all&full=1").text
        action = html.unescape(
            re.search(r'<form method="post" action="([^"]+/note[^"]*)"', panel(page)).group(1)
        )
        assert action == f"/computers/{aid}/note?tab=history&log=all&full=1"
        r = client.post(action, data={"message": "recapped"}, follow_redirects=False)
        assert r.headers["location"] == f"/computers/{aid}?tab=history&log=all&full=1"

    def test_deleting_a_line_comes_back_to_the_view_it_was_deleted_from(self, client, db, computer):
        aid = computer()["asset_id"]
        write(db, aid, ("change", "edited model"))
        page = panel(client.get(f"/computers/{aid}?log=changes").text)
        form = re.search(
            r'<form method="post" action="([^"]+/log/delete[^"]*)"(.*?)</form>', page, re.S
        )
        ids = re.findall(r'name="id" value="(\d+)"', form.group(2))
        r = client.post(html.unescape(form.group(1)), data={"id": ids}, follow_redirects=False)
        assert r.headers["location"] == f"/computers/{aid}?log=changes"

    def test_attaching_a_photograph_sends_the_view_too(self, client, db, computer):
        aid = computer()["asset_id"]
        write(db, aid, ("note", "recapped"))
        page = panel(client.get(f"/computers/{aid}?log=notes").text)
        action = re.search(r'action="([^"]+/log/\d+/photo[^"]*)"', page).group(1)
        assert html.unescape(action).endswith("/photo?log=notes")

    def test_an_address_cannot_be_made_to_carry_anything_else_back(self, client, computer):
        aid = computer()["asset_id"]
        r = client.post(
            f"/computers/{aid}/note?log=elsewhere&full=yes&next=//evil.example",
            data={"message": "recapped"},
            follow_redirects=False,
        )
        assert r.headers["location"] == f"/computers/{aid}"

    @pytest.mark.parametrize("where", ["projects", "locations"])
    def test_a_project_and_a_location_come_back_to_the_view_as_well(self, client, where):
        if where == "projects":
            aid = project(client)
        else:
            aid = client.post("/api/locations", json={"name": "Shelf", "kind": "shelf"}).json()[
                "asset_id"
            ]
        page = client.get(f"/{where}/{aid}?log=changes").text
        action = html.unescape(
            re.search(r'<form method="post" action="([^"]+/note[^"]*)"', panel(page)).group(1)
        )
        assert action == f"/{where}/{aid}/note?log=changes"
        r = client.post(action, data={"message": "tidied"}, follow_redirects=False)
        assert r.headers["location"] == f"/{where}/{aid}?log=changes"


class TestTheLatestTwenty:
    def test_a_long_history_shows_twenty_lines_and_show_all(self, client, db, computer):
        aid = computer()["asset_id"]
        write(db, aid, *[("note", f"note {i}") for i in range(25)])
        page = client.get(f"/computers/{aid}").text
        assert said(page) == [f"Note note {i}" for i in range(24, 4, -1)]
        href, words = show_all(page)
        assert words == "Show all 25"
        assert href.split("#")[0] == "?log=notes&full=1"

    def test_show_all_shows_them_all(self, client, db, computer):
        aid = computer()["asset_id"]
        write(db, aid, *[("note", f"note {i}") for i in range(25)])
        page = client.get(f"/computers/{aid}?log=notes&full=1").text
        assert len(said(page)) == 25
        assert show_all(page) is None
        assert shown_view(page) == "Notes"

    def test_twenty_or_fewer_has_no_show_all(self, client, db, computer):
        aid = computer()["asset_id"]
        write(db, aid, *[("note", f"note {i}") for i in range(20)])
        page = client.get(f"/computers/{aid}").text
        assert len(said(page)) == 20
        assert show_all(page) is None

    def test_a_folded_run_counts_as_one_line(self, client, db, computer):
        aid = computer()["asset_id"]
        db.query(LogEntry).filter(LogEntry.asset_id == aid).delete()
        at = datetime(2026, 1, 1, 12, 0)
        for i in range(30):
            db.add(
                LogEntry(
                    asset_id=aid,
                    kind="change",
                    message="deleted a photo",
                    created_at=at + timedelta(seconds=i),
                )
            )
        db.commit()
        page = client.get(f"/computers/{aid}?log=changes").text
        assert said(page) == ["deleted 30 photos"]
        assert show_all(page) is None

    def test_the_twenty_are_counted_in_the_view_being_read(self, client, db, computer):
        aid = computer()["asset_id"]
        write(
            db,
            aid,
            *[("note", f"note {i}") for i in range(5)],
            *[("change", f"edited field {i}") for i in range(30)],
        )
        page = client.get(f"/computers/{aid}").text
        assert len(said(page)) == 5
        assert show_all(page) is None
        assert show_all(client.get(f"/computers/{aid}?log=changes").text)[1] == "Show all 30"

    def test_on_a_tabbed_page_show_all_stays_on_the_tab(self, client, db, computer):
        aid = computer()["asset_id"]
        write(db, aid, *[("note", f"note {i}") for i in range(25)])
        page = client.get(f"/computers/{aid}?layout=tabs&tab=history").text
        assert show_all(page)[0].split("#")[0] == "?tab=history&log=notes&full=1"

    @pytest.mark.parametrize("where", ["projects", "locations"])
    def test_a_project_and_a_location_show_twenty_too(self, client, db, where):
        if where == "projects":
            aid = project(client)
        else:
            aid = client.post("/api/locations", json={"name": "Shelf", "kind": "shelf"}).json()[
                "asset_id"
            ]
        write(db, aid, *[("note", f"note {i}") for i in range(25)])
        page = client.get(f"/{where}/{aid}").text
        assert list(views(page)) == ["Notes", "Changes", "All"]
        assert len(said(page)) == 20
        assert show_all(page)[1] == "Show all 25"
