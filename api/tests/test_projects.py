"""Projects: the work, as against the things it is done to.

A project is the third thing an id in the register can name, and almost everything
these tests are about follows from that. It keeps a history through the code the
machines use, it resolves at /items/<id>, and it cannot be handed an id an asset
already holds -- none of which is project code, which is exactly what is worth
having tests for.

The rest is what a project has that an asset does not: a list of things it is
about, a list of jobs, and a pile of things on order with what they cost.
"""

import io
from datetime import date

from conftest import log_out, served
from app import ids, main, projects
from app.models import Project, ProjectAsset, ProjectOrder, ProjectTask


def make(client, name="Recap the +2A", **fields):
    """A saved project; returns its asset id."""
    r = client.post("/projects/new", data={"name": name, **fields}, follow_redirects=False)
    assert r.status_code == 303, r.text
    return r.headers["location"].rsplit("/", 1)[-1]


def page(client, aid):
    r = client.get(f"/projects/{aid}")
    assert r.status_code == 200, r.text
    return r.text


def as_visitor(client):
    """Nobody signed in. The test database has no credentials configured, so the
    gate lets everything through until it is told there are some."""
    log_out(client)


class TestARegisterAsset:
    """The claim the whole design rests on: a project is an id in the same register,
    so the things keyed by a register id work on it without being taught to."""

    def test_the_allocator_will_not_reuse_a_projects_id(self, client, db, monkeypatch):
        aid = make(client)
        seq = iter([aid, "RH-ZZZ9"])
        monkeypatch.setattr(ids, "_random_id", lambda: next(seq))
        # Offered the project's id first, it must go round again: an id shared with
        # a project would put one record's history on the other's page.
        assert ids.next_asset_id(db) == "RH-ZZZ9"

    def test_items_resolves_a_project(self, client):
        aid = make(client)
        r = client.get(f"/items/{aid}", follow_redirects=False)
        assert r.status_code == 307
        assert r.headers["location"] == f"/projects/{aid}"

    def test_items_still_resolves_the_two_asset_kinds(self, client, computer, part):
        c, p = computer()["asset_id"], part()["asset_id"]
        assert (
            client.get(f"/items/{c}", follow_redirects=False).headers["location"]
            == f"/computers/{c}"
        )
        assert (
            client.get(f"/items/{p}", follow_redirects=False).headers["location"] == f"/parts/{p}"
        )

    def test_an_id_that_is_nothing_is_still_a_404(self, client):
        assert client.get("/items/RH-NONE", follow_redirects=False).status_code == 404


class TestItsHistory:
    """Written by add_log and read by _history, neither of which knows what a
    project is. These tests are here because that is a thing to keep true."""

    def test_a_new_project_says_it_was_created(self, client):
        assert "created" in page(client, make(client))

    def test_a_note_lands_on_it(self, client):
        aid = make(client)
        client.post(
            f"/projects/{aid}/note", data={"message": "ordered the caps"}, follow_redirects=False
        )
        html = page(client, aid)
        assert "ordered the caps" in html
        assert "note" in html

    def test_a_photograph_alone_is_an_entry(self, client):
        """The note bar's other half, which a project gets for the same free."""
        aid = make(client)
        buf = io.BytesIO()
        from PIL import Image

        Image.new("RGB", (200, 150), (80, 80, 80)).save(buf, "JPEG")
        buf.seek(0)
        client.post(
            f"/projects/{aid}/note",
            data={"message": ""},
            files={"photos": ("board.jpg", buf, "image/jpeg")},
            follow_redirects=False,
        )
        assert "logshots" in page(client, aid)

    def test_an_edit_is_recorded_as_a_diff(self, client):
        aid = make(client, name="Recap the +2A")
        client.post(
            f"/projects/{aid}/edit",
            data={"name": "Recap the +2A", "status": "active"},
            follow_redirects=False,
        )
        assert "status: planned → active" in page(client, aid)


class TestWhatItIsAbout:
    """Membership. A project need own nothing, and what it does own is a computer
    or a part -- which is why project_asset holds a bare register id."""

    def test_a_project_can_be_about_nothing(self, client):
        assert "Nothing attached." in page(client, make(client))

    def test_a_computer_goes_in_and_shows_on_both_pages(self, client, computer):
        aid, c = make(client), computer(model="Spectrum +2A")["asset_id"]
        client.post(f"/projects/{aid}/add-item", data={"asset_id": c}, follow_redirects=False)
        assert c in page(client, aid)
        # And the machine says what it is spoken for, which is the whole reason the
        # panel exists: you find out a board is promised while looking at the board.
        assert f"/projects/{aid}" in client.get(f"/computers/{c}").text

    def test_a_part_goes_in_the_same_way(self, client, part):
        aid, p = make(client), part(model="Gotek")["asset_id"]
        client.post(f"/projects/{aid}/add-item", data={"asset_id": p}, follow_redirects=False)
        assert p in page(client, aid)
        assert f"/projects/{aid}" in client.get(f"/parts/{p}").text

    def test_the_note_says_why_it_is_there(self, client, part):
        aid, p = make(client), part(model="A500 board")["asset_id"]
        client.post(
            f"/projects/{aid}/add-item",
            data={"asset_id": p, "note": "donor for the keyboard"},
            follow_redirects=False,
        )
        assert "donor for the keyboard" in page(client, aid)

    def test_adding_it_twice_leaves_it_in_once(self, client, db, part):
        aid, p = make(client), part()["asset_id"]
        for _ in range(2):
            client.post(f"/projects/{aid}/add-item", data={"asset_id": p}, follow_redirects=False)
        assert db.query(ProjectAsset).filter(ProjectAsset.project_id == aid).count() == 1

    def test_an_id_that_is_nothing_is_refused(self, client, db):
        """A project is about things that exist. A typo'd id stored here would be a
        membership that renders as nothing for ever."""
        aid = make(client)
        client.post(
            f"/projects/{aid}/add-item", data={"asset_id": "RH-XXXX"}, follow_redirects=False
        )
        assert db.query(ProjectAsset).count() == 0

    def test_a_project_is_not_an_item_of_another_project(self, client, db):
        """Members are computers and parts. Nesting projects is a different idea and
        the lookup would not find one anyway -- this pins that down."""
        one, two = make(client, "One"), make(client, "Two")
        client.post(f"/projects/{one}/add-item", data={"asset_id": two}, follow_redirects=False)
        assert db.query(ProjectAsset).count() == 0
        # The same request with a real asset does add one, so the zero above is the
        # rule refusing rather than the route being broken.
        c = (
            client.post("/computers/new", data={"model": "Real"}, follow_redirects=False)
            .headers["location"]
            .split("/computers/")[1]
            .split("?")[0]
        )
        client.post(f"/projects/{one}/add-item", data={"asset_id": c}, follow_redirects=False)
        assert db.query(ProjectAsset).count() == 1

    def test_taking_it_out_says_so_on_both(self, client, computer):
        aid, c = make(client), computer()["asset_id"]
        client.post(f"/projects/{aid}/add-item", data={"asset_id": c}, follow_redirects=False)
        client.post(f"/projects/{aid}/remove-item", data={"asset_id": c}, follow_redirects=False)
        assert "let go of" in page(client, aid)
        assert "no longer wanted for" in client.get(f"/computers/{c}").text

    def test_deleting_the_computer_forgets_the_membership(self, client, db, computer):
        """project_asset.asset_id has no foreign key behind it, so nothing in the
        database will do this. If the delete path stops calling forget_asset, the
        project keeps a row pointing at a machine that no longer exists."""
        aid, c = make(client), computer()["asset_id"]
        client.post(f"/projects/{aid}/add-item", data={"asset_id": c}, follow_redirects=False)
        # Or the count below would be zero for the wrong reason.
        assert db.query(ProjectAsset).count() == 1
        client.post(
            f"/computers/{c}/dispose", data={"disposed_note": "gone"}, follow_redirects=False
        )
        client.post(
            f"/computers/{c}/delete", data={"confirm": f"/computers/{c}"}, follow_redirects=False
        )
        from app.models import Computer

        assert db.get(Computer, c) is None
        assert db.query(ProjectAsset).count() == 0
        assert client.get(f"/projects/{aid}").status_code == 200

    def test_deleting_a_part_forgets_it_too(self, client, db, part):
        from app.models import Part

        aid, p = make(client), part()["asset_id"]
        client.post(f"/projects/{aid}/add-item", data={"asset_id": p}, follow_redirects=False)
        assert db.query(ProjectAsset).count() == 1
        client.post(f"/parts/{p}/dispose", data={"disposed_note": "gone"}, follow_redirects=False)
        client.post(f"/parts/{p}/delete", data={"confirm": f"/parts/{p}"}, follow_redirects=False)
        # The part really went, so the empty membership table means what it says.
        assert db.get(Part, p) is None
        assert db.query(ProjectAsset).count() == 0


class TestTasks:
    def test_one_is_added_and_shown(self, client):
        aid = make(client)
        client.post(
            f"/projects/{aid}/task", data={"text": "order the caps"}, follow_redirects=False
        )
        assert "order the caps" in page(client, aid)

    def test_a_blank_one_is_not_a_task(self, client, db):
        aid = make(client)
        client.post(f"/projects/{aid}/task", data={"text": "   "}, follow_redirects=False)
        assert db.query(ProjectTask).count() == 0

    def test_ticking_it_dates_it(self, client, db):
        aid = make(client)
        client.post(f"/projects/{aid}/task", data={"text": "desolder"}, follow_redirects=False)
        t = db.query(ProjectTask).one()
        client.post(f"/projects/{aid}/task/{t.id}/toggle", follow_redirects=False)
        db.expire_all()
        t = db.query(ProjectTask).one()
        assert t.done and t.done_at is not None

    def test_putting_it_back_clears_the_date(self, client, db):
        """A job that is not done has no day it was done on. Leaving the old one
        behind would show a task as outstanding while still claiming a completion
        date."""
        aid = make(client)
        client.post(f"/projects/{aid}/task", data={"text": "desolder"}, follow_redirects=False)
        t = db.query(ProjectTask).one()
        for _ in range(2):
            client.post(f"/projects/{aid}/task/{t.id}/toggle", follow_redirects=False)
        db.expire_all()
        t = db.query(ProjectTask).one()
        assert not t.done and t.done_at is None

    def test_it_can_be_dropped(self, client, db):
        aid = make(client)
        client.post(f"/projects/{aid}/task", data={"text": "nonsense"}, follow_redirects=False)
        t = db.query(ProjectTask).one()
        client.post(f"/projects/{aid}/task/{t.id}/delete", follow_redirects=False)
        assert db.query(ProjectTask).count() == 0

    def test_another_projects_task_cannot_be_ticked_from_here(self, client, db):
        """A bare row id would otherwise reach across projects, the way a bare log
        entry id would reach across machines."""
        one, two = make(client, "One"), make(client, "Two")
        client.post(f"/projects/{one}/task", data={"text": "mine"}, follow_redirects=False)
        t = db.query(ProjectTask).one()
        r = client.post(f"/projects/{two}/task/{t.id}/toggle", follow_redirects=False)
        assert r.status_code == 404


class TestOrders:
    def test_one_is_added_with_what_it_cost(self, client, db):
        aid = make(client)
        client.post(
            f"/projects/{aid}/order",
            data={"description": "Gotek", "supplier": "eBay", "cost": "£12.99"},
            follow_redirects=False,
        )
        o = db.query(ProjectOrder).one()
        assert o.description == "Gotek" and o.cost_p == 1299
        html = page(client, aid)
        assert "Gotek" in html and "£12.99" in html

    def test_it_is_dated_today_unless_told_otherwise(self, client, db):
        from datetime import date

        aid = make(client)
        client.post(f"/projects/{aid}/order", data={"description": "caps"}, follow_redirects=False)
        assert db.query(ProjectOrder).one().ordered_at == date.today()

    def test_a_blank_description_is_not_an_order(self, client, db):
        aid = make(client)
        client.post(f"/projects/{aid}/order", data={"description": " "}, follow_redirects=False)
        assert db.query(ProjectOrder).count() == 0

    def test_marking_it_in_dates_it_and_back_again_clears_it(self, client, db):
        aid = make(client)
        client.post(f"/projects/{aid}/order", data={"description": "Gotek"}, follow_redirects=False)
        o = db.query(ProjectOrder).one()
        client.post(f"/projects/{aid}/order/{o.id}/delivered", follow_redirects=False)
        db.expire_all()
        assert db.query(ProjectOrder).one().delivered_at is not None
        client.post(f"/projects/{aid}/order/{o.id}/delivered", follow_redirects=False)
        db.expire_all()
        o = db.query(ProjectOrder).one()
        assert not o.delivered and o.delivered_at is None

    def test_nothing_becomes_a_part_by_arriving(self, client, db):
        """An order is a note about a purchase, not a half-made asset. What turns up
        is added to the register the ordinary way."""
        from app.models import Part

        aid = make(client)
        client.post(f"/projects/{aid}/order", data={"description": "Gotek"}, follow_redirects=False)
        o = db.query(ProjectOrder).one()
        client.post(f"/projects/{aid}/order/{o.id}/delivered", follow_redirects=False)
        assert db.query(Part).count() == 0

    def test_it_can_be_cancelled(self, client, db):
        aid = make(client)
        client.post(
            f"/projects/{aid}/order", data={"description": "wrong thing"}, follow_redirects=False
        )
        o = db.query(ProjectOrder).one()
        client.post(f"/projects/{aid}/order/{o.id}/delete", follow_redirects=False)
        assert db.query(ProjectOrder).count() == 0

    def test_another_projects_order_cannot_be_ticked_from_here(self, client, db):
        one, two = make(client, "One"), make(client, "Two")
        client.post(f"/projects/{one}/order", data={"description": "mine"}, follow_redirects=False)
        o = db.query(ProjectOrder).one()
        assert (
            client.post(
                f"/projects/{two}/order/{o.id}/delivered", follow_redirects=False
            ).status_code
            == 404
        )

    def test_the_total_says_how_much_of_it_is_a_total(self, client):
        """A figure quietly missing the unpriced lines would look exactly as
        authoritative as one that was not."""
        aid = make(client)
        client.post(
            f"/projects/{aid}/order",
            data={"description": "Gotek", "cost": "12.00"},
            follow_redirects=False,
        )
        client.post(f"/projects/{aid}/order", data={"description": "caps"}, follow_redirects=False)
        html = page(client, aid)
        assert "£12.00 so far" in html
        assert "1 unpriced" in html


class TestMoney:
    """Pence as integers, for the reason every other quantity here is an integer in
    a small unit: it adds up and sorts exactly."""

    def test_what_gets_typed_into_a_cost_box(self):
        assert projects.parse_money("12.99") == 1299
        assert projects.parse_money("£12.99") == 1299
        assert projects.parse_money("1,250") == 125000
        assert projects.parse_money(" 12 ") == 1200
        assert projects.parse_money("12.5") == 1250
        assert projects.parse_money(".99") == 99

    def test_nothing_and_nonsense_are_both_not_recorded(self):
        for raw in ("", "   ", None, "free", "12.34.56", "-5", "."):
            assert projects.parse_money(raw) is None

    def test_not_recorded_is_not_zero(self):
        """The distinction the total depends on: a line with no price is unknown,
        and counting it as free would make the total smaller than the truth."""
        assert projects.parse_money("") is None
        assert projects.parse_money("0") == 0

    def test_it_is_written_back_the_way_it_is_read(self):
        assert projects.money(1299) == "£12.99"
        assert projects.money(1200) == "£12.00"
        assert projects.money(5) == "£0.05"
        assert projects.money(125000) == "£1,250.00"
        assert projects.money(None) == ""


class TestTheForm:
    def test_a_project_needs_a_name(self, client, db):
        """The only thing it can be found by: a machine falls back to its
        manufacturer and model and then to its id, and a project has neither."""
        r = client.post("/projects/new", data={"name": "  "}, follow_redirects=False)
        assert r.status_code == 200
        assert "Give it a name" in r.text
        assert db.query(Project).count() == 0

    def test_what_was_typed_survives_the_refusal(self, client):
        r = client.post(
            "/projects/new",
            data={"name": "", "summary": "the one with the bad caps"},
            follow_redirects=False,
        )
        assert "the one with the bad caps" in r.text

    def test_an_unknown_status_falls_back_rather_than_being_stored(self, client, db):
        aid = make(client, status="halfway")
        assert db.get(Project, aid).status == projects.DEFAULT_STATUS

    def test_the_three_dates_are_independent(self, client, db):
        """A project can be finished without ever having been started -- the part
        turned up and it took an evening. None is worked out from another."""
        aid = make(client, finished_at="2026-08-01")
        p = db.get(Project, aid)
        assert p.finished_at is not None
        assert p.started_at is None and p.target_date is None


class TestMarkingOneDone:
    """One click on a project still in hand and it is over: the status, the finish
    date where there is not one already, and a line in the history saying so."""

    def test_one_click_finishes_it(self, client, db):
        aid = make(client, status="active")
        r = client.post(f"/projects/{aid}/complete", follow_redirects=False)
        assert r.status_code == 303 and r.headers["location"] == f"/projects/{aid}"
        db.expire_all()
        assert db.get(Project, aid).status == "done"

    def test_the_finish_date_is_today_where_none_was_recorded(self, client, db):
        aid = make(client, status="active")
        client.post(f"/projects/{aid}/complete", follow_redirects=False)
        db.expire_all()
        assert db.get(Project, aid).finished_at == date.today()

    def test_a_finish_date_already_recorded_is_kept(self, client, db):
        """It says when the work actually stopped. A click a fortnight later is in
        no position to correct it, so today is written only into a blank."""
        aid = make(client, status="active", finished_at="2026-03-04")
        client.post(f"/projects/{aid}/complete", follow_redirects=False)
        db.expire_all()
        p = db.get(Project, aid)
        assert p.status == "done" and p.finished_at == date(2026, 3, 4)

    def test_it_is_written_into_the_history(self, client, db):
        from app.models import LogEntry

        aid = make(client, status="active")
        client.post(f"/projects/{aid}/complete", follow_redirects=False)
        said = [e.message for e in db.query(LogEntry).filter(LogEntry.asset_id == aid)]
        assert "finished" in said

    def test_the_button_is_there_while_there_is_something_to_finish(self, client):
        aid = make(client, status="active")
        html = page(client, aid)
        assert f'action="/projects/{aid}/complete"' in html
        assert "mark done" in html

    def test_there_is_no_button_once_it_is_over(self, client):
        """Done and abandoned both. Either is reopened on the edit form, and a
        button offering to finish something that is finished says nothing."""
        for status in projects.CLOSED:
            aid = make(client, status=status)
            assert f'action="/projects/{aid}/complete"' not in page(client, aid), status

    def test_a_visitor_is_not_offered_it(self, client, monkeypatch):
        aid = make(client, status="active")
        as_visitor(client)
        assert "/complete" not in client.get(f"/projects/{aid}").text

    def test_a_visitor_cannot_finish_one(self, client, db, monkeypatch):
        aid = make(client, status="active")
        as_visitor(client)
        r = client.post(f"/projects/{aid}/complete", follow_redirects=False)
        assert r.status_code == 303 and "/login" in r.headers["location"]
        db.expire_all()
        assert db.get(Project, aid).status == "active"

    def test_a_project_that_is_nothing_cannot_be_finished(self, client):
        assert client.post("/projects/RH-NONE/complete", follow_redirects=False).status_code == 404

    def test_a_finished_project_leaves_the_menu_of_projects_going(self, client, db):
        """The picker on the entry forms asks what a thing arriving today could be
        joining, and a finished project is not an answer to that."""
        aid = make(client, status="active")
        assert aid in [p.asset_id for p in projects.open_projects(db)]
        client.post(f"/projects/{aid}/complete", follow_redirects=False)
        db.expire_all()
        assert aid not in [p.asset_id for p in projects.open_projects(db)]


class TestTheList:
    def test_what_is_in_hand_comes_before_what_is_over(self, client):
        make(client, "Zebra job", status="active")
        make(client, "Alpha job", status="done")
        html = client.get("/projects").text
        assert html.index("Zebra job") < html.index("Alpha job")

    def test_it_counts_what_is_still_coming(self, client):
        aid = make(client)
        for d in ("one", "two"):
            client.post(f"/projects/{aid}/order", data={"description": d}, follow_redirects=False)
        assert "still coming" in page(client, aid)

    def test_an_empty_register_says_so(self, client):
        assert "No projects yet" in client.get("/projects").text


def table_row(html, name):
    """One project's row out of the list, by the name in it."""
    table = html.split('<table class="projtable">')[1]
    return table.split(name)[1].split("</tr>")[0]


class TestTheListOnAPhone:
    """Five columns across a 390px screen gave the name a fifth of it, and three of
    the four columns taking that width were usually saying nothing. The rows stack
    on a phone instead -- which turns on the count cells being genuinely empty."""

    def test_a_count_of_nothing_is_an_empty_cell_not_a_dash(self, client):
        """The dash is drawn by the stylesheet. Written into the cell it would be
        content, and content is not something `:empty` can see past -- so the phone
        rule that drops the cell would never match and the row would carry three
        columns of nothing across the narrowest screen."""
        make(client, "Bare")
        html = client.get("/projects").text
        # From the table, not the page: the suggestion above it names a project too
        # (see the "Something to do today" panel), and the first "Bare" on the page
        # is as likely to be that one.
        row = table_row(html, "Bare")
        # Nothing at all between the tags, not even a space: a whitespace text node
        # is a child, and a cell with a child is not :empty.
        for label in ("items", "tasks", "on order"):
            assert f'data-label="{label}"></td>' in row
        assert "—" not in row

    def test_a_count_that_exists_is_written_in(self, client):
        aid = make(client, "Busy")
        client.post(f"/projects/{aid}/task", data={"text": "a job"}, follow_redirects=False)
        row = table_row(client.get("/projects").text, "Busy")
        assert 'data-label="tasks">0/1</td>' in row

    def test_the_columns_are_labelled_for_the_stacked_view(self, client):
        """Stacked, a bare "0/1" under a name says nothing. The label the column
        heading carried is put back on the cell, and the stylesheet shows it only
        at the width where the heading row is hidden."""
        make(client, "Labelled")
        html = client.get("/projects").text
        for label in ("items", "tasks", "on order"):
            assert f'data-label="{label}"' in html


class TestTheRestOfTheSiteKnows:
    """Public means findable. A section anybody may read but no crawler is told
    about is public in the auth rules and private in practice."""

    def test_the_sitemap_carries_the_projects(self, client):
        aid = make(client)
        xml = client.get("/sitemap.xml").text
        assert "/projects</loc>" in xml
        assert f"/projects/{aid}</loc>" in xml

    def test_a_projects_lastmod_comes_from_its_own_history(self, client):
        """Its history is log_entry keyed by its own register id, so it reads out of
        the same query the machines do rather than needing one of its own."""
        aid = make(client)
        xml = client.get("/sitemap.xml").text
        block = xml.split(f"/projects/{aid}</loc>")[1].split("</url>")[0]
        assert "<lastmod>" in block

    def test_the_new_project_form_is_kept_out_of_the_index(self, client):
        assert "Disallow: /projects/new" in client.get("/robots.txt").text


class TestDeleting:
    def test_it_takes_its_own_history_with_it(self, client, db):
        """log_entry is keyed by a plain register id with nothing to cascade from,
        so the route clears it by hand. Left behind, the entries would attach
        themselves to whatever asset was next given that id."""
        from app.models import LogEntry

        aid = make(client)
        client.post(f"/projects/{aid}/note", data={"message": "a note"}, follow_redirects=False)
        client.post(f"/projects/{aid}/delete", follow_redirects=False)
        assert db.query(LogEntry).filter(LogEntry.asset_id == aid).count() == 0

    def test_it_takes_its_tasks_and_orders(self, client, db):
        aid = make(client)
        client.post(f"/projects/{aid}/task", data={"text": "a job"}, follow_redirects=False)
        client.post(
            f"/projects/{aid}/order", data={"description": "a thing"}, follow_redirects=False
        )
        client.post(f"/projects/{aid}/delete", follow_redirects=False)
        assert db.query(ProjectTask).count() == 0
        assert db.query(ProjectOrder).count() == 0

    def test_it_leaves_the_hardware_alone(self, client, db, computer):
        """Deleting the plan is not disposing of the machine."""
        from app.models import Computer

        aid, c = make(client), computer()["asset_id"]
        client.post(f"/projects/{aid}/add-item", data={"asset_id": c}, follow_redirects=False)
        client.post(f"/projects/{aid}/delete", follow_redirects=False)
        assert db.get(Computer, c) is not None
        assert db.query(ProjectAsset).count() == 0

    def test_there_is_no_disposal_step_in_front_of_it(self, client, db):
        """Unlike a machine. Abandoning a project is already a status it can be left
        in, so the only thing delete is left to mean is that it was a mistake."""
        aid = make(client)
        assert client.post(f"/projects/{aid}/delete", follow_redirects=False).status_code == 303
        assert db.query(Project).count() == 0


class TestWhoSeesWhat:
    """Projects read like the rest of the site. What a visitor is not shown is what
    a thing cost -- which is on the page rather than in the auth rules."""

    def test_a_visitor_may_read_the_list(self, client, monkeypatch):
        aid = make(client)
        as_visitor(client)
        assert client.get("/projects").status_code == 200
        assert client.get(f"/projects/{aid}").status_code == 200

    def test_a_visitor_is_sent_to_the_login_to_edit(self, client, monkeypatch):
        aid = make(client)
        as_visitor(client)
        for url in ("/projects/new", f"/projects/{aid}/edit"):
            r = client.get(url, follow_redirects=False)
            assert r.status_code == 303 and "/login" in r.headers["location"]

    def test_a_visitor_cannot_write(self, client, monkeypatch):
        aid = make(client)
        as_visitor(client)
        for url in (
            f"/projects/{aid}/task",
            f"/projects/{aid}/order",
            f"/projects/{aid}/add-item",
            f"/projects/{aid}/delete",
            f"/projects/{aid}/note",
        ):
            r = client.post(url, data={}, follow_redirects=False)
            assert r.status_code == 303 and "/login" in r.headers["location"], url

    def test_what_it_cost_is_not_shown_to_a_visitor(self, client, monkeypatch):
        """The projects are public because what is being built is worth reading
        about. What it cost is between the owner and the receipt."""
        aid = make(client)
        client.post(
            f"/projects/{aid}/order",
            data={"description": "Gotek", "cost": "12.99"},
            follow_redirects=False,
        )
        as_visitor(client)
        html = client.get(f"/projects/{aid}").text
        assert "Gotek" in html
        assert "12.99" not in html

    def test_a_visitor_sees_whether_it_has_arrived(self, client, monkeypatch):
        """The rest of the row is as public as the machine it is destined for."""
        aid = make(client)
        client.post(f"/projects/{aid}/order", data={"description": "Gotek"}, follow_redirects=False)
        as_visitor(client)
        assert "on order" in client.get(f"/projects/{aid}").text


class TestBeingFound:
    """A project is searched by the same words a machine is, and reached from the
    same box. What it does not do is become a card in the gallery: the grid is a
    wall of photographs of things owned, and a plan is not one of those."""

    def test_the_suggestion_list_offers_a_project(self, client):
        make(client, "Recap the +2A")
        items = client.get("/suggest?q=recap").json()["items"]
        assert any(i["cat"] == "Project" and "Recap" in i["name"] for i in items)

    def test_a_suggested_project_links_to_its_page(self, client):
        aid = make(client, "Recap the +2A")
        item = next(
            i for i in client.get("/suggest?q=recap").json()["items"] if i["cat"] == "Project"
        )
        assert item["url"] == f"/projects/{aid}"
        assert item["icon"].endswith("project.svg")

    def test_a_project_is_found_by_something_on_order(self, client):
        """The question somebody stood in front of a parcel actually asks."""
        aid = make(client, "Amiga floppy swap")
        client.post(
            f"/projects/{aid}/order", data={"description": "Gotek SFR1M44"}, follow_redirects=False
        )
        assert any(i["cat"] == "Project" for i in client.get("/suggest?q=gotek").json()["items"])

    def test_a_project_is_found_by_a_job_on_its_list(self, client):
        aid = make(client, "Nondescript")
        client.post(
            f"/projects/{aid}/task", data={"text": "desolder the RIFA"}, follow_redirects=False
        )
        assert any(i["cat"] == "Project" for i in client.get("/suggest?q=rifa").json()["items"])

    def test_a_project_is_found_by_its_status_in_words(self, client):
        """'active' is what the column holds; 'in progress' is what a person types."""
        make(client, "Halfway house", status="active")
        assert any(
            i["cat"] == "Project" for i in client.get("/suggest?q=in+progress").json()["items"]
        )

    def test_the_projects_page_sifts_itself(self, client):
        make(client, "Recap the +2A")
        make(client, "486 DOS build")
        html = client.get("/projects?q=recap").text
        assert "Recap the +2A" in html
        assert "486 DOS build" not in html

    def test_sifting_reaches_the_orders_too(self, client):
        aid = make(client, "Nondescript")
        client.post(f"/projects/{aid}/order", data={"description": "Gotek"}, follow_redirects=False)
        make(client, "Something else")
        html = client.get("/projects?q=gotek").text
        assert "Nondescript" in html and "Something else" not in html

    def test_a_search_matching_nothing_says_so(self, client):
        make(client)
        assert "Nothing matches that" in served(client, client.get("/projects?q=zzzz").text)

    def test_the_gallery_says_when_projects_match_as_well(self, client, computer):
        """A search bar that says 'anything' and quietly means 'the shelf' would be
        a search bar that lies."""
        computer(model="Spectrum")
        make(client, "Spectrum recap")
        html = client.get("/?q=spectrum").text
        assert "project" in html
        assert "/projects?q=spectrum" in html

    def test_the_gallery_stays_a_gallery(self, client):
        """The project matched, and did not become a card."""
        aid = make(client, "Recap the +2A")
        html = client.get("/?q=recap").text
        assert f'href="/projects/{aid}"' not in html.split('class="grid"')[1]

    def test_a_project_does_not_leak_into_a_machines_search_text(self, client, computer):
        """Both are keyed by a register id, so a history read for the wrong one
        would put a project's notes in a machine's haystack."""
        c = computer(model="Unrelated")["asset_id"]
        aid = make(client, "Distinctivewording")
        client.post(
            f"/projects/{aid}/note", data={"message": "peculiarphrase"}, follow_redirects=False
        )
        rows = client.get("/?q=peculiarphrase").text.split('class="grid"')[1]
        assert c not in rows


class TestTheFigures:
    def test_the_projects_show_up_among_the_facts(self, client, db):

        aid = make(client, status="active")
        client.post(f"/projects/{aid}/task", data={"text": "a job"}, follow_redirects=False)
        client.post(
            f"/projects/{aid}/order", data={"description": "a thing"}, follow_redirects=False
        )
        facts = main._facts_projects(db, {})
        headings = {f["k"] for f in facts}
        assert "Projects on the go" in headings
        assert "Jobs still on the list" in headings
        assert "Things in the post" in headings

    def test_an_empty_register_contributes_no_project_figures(self, client, db):
        """A figure is omitted rather than shown as a zero, the rule the whole
        pool follows."""

        assert main._facts_projects(db, {}) == []

    def test_no_figure_says_what_anything_cost(self, client, db):
        """/stats is public and the cost column on a project page is not. A total
        spent would put on the most public page of the site the one figure the item
        page takes care to withhold."""

        aid = make(client)
        client.post(
            f"/projects/{aid}/order",
            data={"description": "Gotek", "cost": "999.99"},
            follow_redirects=False,
        )
        blob = " ".join(f"{f['k']} {f['v']} {f['s']}" for f in main._facts_projects(db, {}))
        assert "999" not in blob and "£" not in blob
        # The rendered figure, not a bare "999": the chip's border-radius is 999px
        # and a substring test on the whole page would fail on the stylesheet.
        assert projects.money(99999) not in client.get("/stats").text

    def test_the_longest_note_tile_survives_it_being_on_a_project(self, client, db):
        """log_entry is keyed by a register id, so the longest note can perfectly
        well be on a project. Looked for in two tables only, the tile would vanish
        on the day it was."""

        aid = make(client, "Wordy")
        client.post(f"/projects/{aid}/note", data={"message": "x" * 300}, follow_redirects=False)
        facts = main._facts_register(db, {"portraits": {}, "n_parts": 0})
        tile = next(f for f in facts if f["k"] == "The longest note anyone has written")
        assert tile["href"] == f"/projects/{aid}"
        assert tile["s"] == "Wordy"


class TestTheApi:
    """The same things the pages do, for the tool server and for scripts."""

    def new(self, client, **fields):
        r = client.post("/api/projects", json={"name": "API project", **fields})
        assert r.status_code == 200, r.text
        return r.json()

    def test_a_project_is_created_and_read_back(self, client):
        p = self.new(client, summary="the one with the caps")
        got = client.get(f"/api/projects/{p['asset_id']}").json()
        assert got["name"] == "API project"
        assert got["summary"] == "the one with the caps"
        assert got["items"] == [] and got["tasks"] == [] and got["orders"] == []

    def test_the_status_reads_back_in_words_as_well(self, client):
        """A caller should not have to hold this module's vocabulary to know that
        'active' reads 'in progress'."""
        p = self.new(client, status="active")
        assert p["status"] == "active" and p["status_label"] == "in progress"

    def test_an_unknown_status_is_stored_as_planned(self, client):
        assert self.new(client, status="halfway")["status"] == "planned"

    def test_a_project_needs_a_name(self, client):
        assert client.post("/api/projects", json={"name": "  "}).status_code == 422
        assert client.post("/api/projects", json={}).status_code == 422

    def test_a_patch_changes_only_what_it_names(self, client):
        p = self.new(client, summary="kept")
        r = client.patch(f"/api/projects/{p['asset_id']}", json={"status": "active"})
        assert r.status_code == 200
        assert r.json()["status"] == "active" and r.json()["summary"] == "kept"

    def test_a_patch_cannot_take_the_name_away(self, client):
        p = self.new(client)
        assert client.patch(f"/api/projects/{p['asset_id']}", json={"name": ""}).status_code == 422

    def test_a_patch_is_written_into_the_history(self, client):
        p = self.new(client)
        client.patch(f"/api/projects/{p['asset_id']}", json={"status": "done"})
        log = client.get(f"/api/items/{p['asset_id']}/log").json()
        assert any("status: planned → done" in e["message"] for e in log)

    def test_the_list_can_be_narrowed_to_what_is_open(self, client):
        self.new(client, name="Going", status="active")
        self.new(client, name="Over", status="done")
        names = {p["name"] for p in client.get("/api/projects", params={"open": True}).json()}
        assert names == {"Going"}
        shut = {p["name"] for p in client.get("/api/projects", params={"open": False}).json()}
        assert shut == {"Over"}

    def test_the_list_can_be_narrowed_to_one_status(self, client):
        self.new(client, name="Stuck", status="stalled")
        self.new(client, name="Going", status="active")
        got = client.get("/api/projects", params={"status": "stalled"}).json()
        assert [p["name"] for p in got] == ["Stuck"]

    def test_deleting_takes_the_history_and_leaves_the_hardware(self, client, db, computer):
        from app.models import Computer, LogEntry

        p = self.new(client)
        c = computer()["asset_id"]
        client.post(f"/api/projects/{p['asset_id']}/items", json={"asset_id": c})
        assert client.delete(f"/api/projects/{p['asset_id']}").status_code == 200
        assert db.query(LogEntry).filter(LogEntry.asset_id == p["asset_id"]).count() == 0
        assert db.get(Computer, c) is not None
        assert db.query(ProjectAsset).count() == 0


class TestTheApiLists:
    def new(self, client, **fields):
        return client.post("/api/projects", json={"name": "API project", **fields}).json()

    def test_an_item_goes_in_and_reads_back_with_its_kind(self, client, computer):
        p = self.new(client)
        c = computer(model="Spectrum")["asset_id"]
        got = client.post(
            f"/api/projects/{p['asset_id']}/items", json={"asset_id": c, "note": "the patient"}
        ).json()
        assert got["items"] == [
            {"asset_id": c, "kind": "computers", "name": "Acme Spectrum", "note": "the patient"}
        ]

    def test_a_part_reads_back_under_its_own_kind(self, client, part):
        """So a caller can build a link without knowing which table holds it."""
        p = self.new(client)
        pt = part(model="Gotek")["asset_id"]
        got = client.post(f"/api/projects/{p['asset_id']}/items", json={"asset_id": pt}).json()
        assert got["items"][0]["kind"] == "parts"

    def test_an_asset_that_is_nothing_is_refused(self, client):
        p = self.new(client)
        r = client.post(f"/api/projects/{p['asset_id']}/items", json={"asset_id": "RH-XXXX"})
        assert r.status_code == 404

    def test_adding_the_same_one_twice_is_not_an_error(self, client, part):
        """A caller retrying a request wants the state it asked for, not a row
        about how it got there."""
        p = self.new(client)
        pt = part()["asset_id"]
        for _ in range(2):
            r = client.post(f"/api/projects/{p['asset_id']}/items", json={"asset_id": pt})
            assert r.status_code == 200
        assert len(r.json()["items"]) == 1

    def test_an_item_comes_out_again(self, client, part):
        p = self.new(client)
        pt = part()["asset_id"]
        client.post(f"/api/projects/{p['asset_id']}/items", json={"asset_id": pt})
        got = client.delete(f"/api/projects/{p['asset_id']}/items/{pt}").json()
        assert got["items"] == []

    def test_a_task_is_added_ticked_and_dropped(self, client):
        p = self.new(client)
        t = client.post(f"/api/projects/{p['asset_id']}/tasks", json={"text": "desolder"}).json()
        assert t["done"] is False and t["done_at"] is None
        ticked = client.patch(
            f"/api/projects/{p['asset_id']}/tasks/{t['id']}", json={"done": True}
        ).json()
        assert ticked["done"] and ticked["done_at"]
        back = client.patch(
            f"/api/projects/{p['asset_id']}/tasks/{t['id']}", json={"done": False}
        ).json()
        assert not back["done"] and back["done_at"] is None
        assert client.delete(f"/api/projects/{p['asset_id']}/tasks/{t['id']}").status_code == 200
        assert client.get(f"/api/projects/{p['asset_id']}").json()["tasks"] == []

    def test_a_blank_task_is_refused(self, client):
        p = self.new(client)
        assert (
            client.post(f"/api/projects/{p['asset_id']}/tasks", json={"text": "  "}).status_code
            == 422
        )

    def test_another_projects_task_is_not_reachable(self, client):
        one, two = self.new(client, name="One"), self.new(client, name="Two")
        t = client.post(f"/api/projects/{one['asset_id']}/tasks", json={"text": "mine"}).json()
        assert (
            client.patch(
                f"/api/projects/{two['asset_id']}/tasks/{t['id']}", json={"done": True}
            ).status_code
            == 404
        )

    def test_an_order_carries_its_cost_in_pence(self, client):
        """Pence as an integer, because that is what the column holds and what it
        holds is exact."""
        p = self.new(client)
        o = client.post(
            f"/api/projects/{p['asset_id']}/orders",
            json={"description": "Gotek", "supplier": "eBay", "cost_p": 1299, "qty": 2},
        ).json()
        assert o["cost_p"] == 1299 and o["qty"] == 2
        assert o["ordered_at"] and not o["delivered"]

    def test_an_order_with_no_price_reads_back_as_null_not_zero(self, client):
        p = self.new(client)
        o = client.post(
            f"/api/projects/{p['asset_id']}/orders", json={"description": "braid"}
        ).json()
        assert o["cost_p"] is None

    def test_an_order_is_marked_in_and_back_out(self, client):
        p = self.new(client)
        o = client.post(
            f"/api/projects/{p['asset_id']}/orders", json={"description": "Gotek"}
        ).json()
        got = client.patch(
            f"/api/projects/{p['asset_id']}/orders/{o['id']}", json={"delivered": True}
        ).json()
        assert got["delivered"] and got["delivered_at"]
        back = client.patch(
            f"/api/projects/{p['asset_id']}/orders/{o['id']}", json={"delivered": False}
        ).json()
        assert not back["delivered"] and back["delivered_at"] is None

    def test_marking_it_in_writes_the_history(self, client):
        p = self.new(client)
        o = client.post(
            f"/api/projects/{p['asset_id']}/orders", json={"description": "Gotek"}
        ).json()
        client.patch(f"/api/projects/{p['asset_id']}/orders/{o['id']}", json={"delivered": True})
        log = client.get(f"/api/items/{p['asset_id']}/log").json()
        assert any("arrived: Gotek" in e["message"] for e in log)

    def test_a_blank_order_is_refused(self, client):
        p = self.new(client)
        assert (
            client.post(
                f"/api/projects/{p['asset_id']}/orders", json={"description": ""}
            ).status_code
            == 422
        )

    def test_an_order_is_cancelled(self, client):
        p = self.new(client)
        o = client.post(
            f"/api/projects/{p['asset_id']}/orders", json={"description": "wrong thing"}
        ).json()
        client.delete(f"/api/projects/{p['asset_id']}/orders/{o['id']}")
        assert client.get(f"/api/projects/{p['asset_id']}").json()["orders"] == []

    def test_another_projects_order_is_not_reachable(self, client):
        one, two = self.new(client, name="One"), self.new(client, name="Two")
        o = client.post(
            f"/api/projects/{one['asset_id']}/orders", json={"description": "mine"}
        ).json()
        assert client.delete(f"/api/projects/{two['asset_id']}/orders/{o['id']}").status_code == 404

    def test_the_whole_api_is_private(self, client, monkeypatch):
        """Unlike the pages. The register's JSON is behind the login and the
        projects are no exception -- which is also what keeps the costs in it from
        being readable by anyone who guessed the URL."""
        p = self.new(client)
        as_visitor(client)
        assert client.get("/api/projects").status_code == 401
        assert client.get(f"/api/projects/{p['asset_id']}").status_code == 401


class TestItsLabel:
    """A sticker for a project, so a thing bought for one can say what it is for.

    The same label the machines and parts get, from the same code and carrying the
    same /items/<id> code -- which is what the register id was for."""

    def test_a_project_has_one(self, client):
        aid = make(client)
        r = client.get(f"/projects/{aid}/label.pdf")
        assert r.status_code == 200
        assert r.headers["content-type"] == "application/pdf"
        assert r.content[:4] == b"%PDF"

    def test_it_comes_small_by_default(self, client):
        """A machine's is the 6x4 by default because it is read across a room. This
        one is going on a jiffy bag."""
        aid = make(client)
        small = client.get(f"/projects/{aid}/label.pdf").content
        explicit = client.get(f"/projects/{aid}/label.pdf?small=1").content
        assert len(small) == len(explicit)
        assert client.get(f"/projects/{aid}/label.pdf?small=0").content != small

    def test_the_full_one_is_offered_too(self, client):
        aid = make(client)
        r = client.get(f"/projects/{aid}/label.pdf?small=0")
        assert r.status_code == 200 and r.content[:4] == b"%PDF"

    def test_the_page_offers_both(self, client):
        aid = make(client)
        html = page(client, aid)
        assert f"/projects/{aid}/label.pdf?small=1" in html
        assert f"/projects/{aid}/label.pdf?small=0" in html

    def test_the_code_on_it_is_the_register_address(self, client):
        """Not /projects/<id>. The label carries /items/<id>, as every other label
        here does, so a sticker printed today still resolves if the page it leads to
        is ever moved."""
        from app import labels

        aid = make(client)
        assert labels.item_url(aid).endswith(f"/items/{aid}/")

    def test_scanning_it_reaches_the_project(self, client):
        aid = make(client)
        r = client.get(f"/items/{aid}", follow_redirects=False)
        assert r.status_code == 307
        assert r.headers["location"] == f"/projects/{aid}"

    def test_a_label_is_not_public(self, client, monkeypatch):
        """Printing is an owner's action, and the label carries the summary. The
        same rule the machines' labels follow."""
        aid = make(client)
        as_visitor(client)
        r = client.get(f"/projects/{aid}/label.pdf", follow_redirects=False)
        assert r.status_code == 303 and "/login" in r.headers["location"]

    def test_no_such_project_has_no_label(self, client):
        assert client.get("/projects/RH-NONE/label.pdf").status_code == 404

    def test_the_small_one_carries_the_state(self):
        """What you want to know with the parcel in your hand, months later."""
        from app import labels

        name, tags = labels.small_body(
            {"name": "Recap the +2A", "status": "active"}, labels.PROJECT
        )
        assert name == "Recap the +2A" and tags == ["in progress"]

    def test_the_full_one_carries_the_dates_it_has(self, client):
        from app import labels

        lines = labels.project_lines(
            {
                "name": "X",
                "status": "active",
                "started_at": "2026-08-14",
                "summary": "the caps are gone",
            }
        )
        assert "Status: in progress" in lines
        assert "Started: 2026-08-14" in lines
        assert "the caps are gone" in lines
        # Nothing counted: how many jobs are left is true this afternoon and false
        # next week, and a label lives on a box for a year.
        assert not any("task" in x.lower() or "order" in x.lower() for x in lines)


class TestTheWordUpTheEnd:
    """Every label says which of the three things it is for, up one end.

    A tag answers "which one is this?" and the code answers "tell me everything";
    neither answers "what am I holding?", which is the first question a box of
    mixed stickers raises.
    """

    def test_each_kind_has_its_own_word(self):
        from app import labels

        assert labels.KIND_WORDS[labels.COMPUTER] == "COMPUTER"
        assert labels.KIND_WORDS[labels.PART] == "PART"
        assert labels.KIND_WORDS[labels.PROJECT] == "PROJECT"

    def test_the_word_is_on_both_sizes_of_every_kind(self, client, computer, part):
        """Rendered rather than asserted on a string: the word is drawn as glyphs,
        so what this checks is that a label with one differs from the same label
        without, at both sizes and for all three kinds."""
        from app import labels

        rows = (
            (labels.COMPUTER, {"asset_id": "RH-0001", "model": "A"}),
            (labels.PART, {"asset_id": "RH-0002", "type": "video", "model": "B"}),
            (labels.PROJECT, {"asset_id": "RH-0003", "name": "C", "status": "active"}),
        )
        for kind, asset in rows:
            for small in (True, False):
                with_word = labels.render_pdf(asset, [], kind, small=small)
                without = labels.render_pdf(asset, [], None, small=small)
                assert len(with_word) != len(without), f"{kind} small={small}"

    def test_a_computer_no_longer_says_its_type_twice(self):
        """The bullet went when the word arrived: it was saying the same thing in
        the most valuable line on the label. A part keeps its Type line, which says
        which sort of part and so completes the word rather than repeating it."""
        from app import labels

        comp = labels.computer_lines({"asset_id": "RH-0001", "manufacturer": "Acme"}, [])
        assert not any(x.startswith("Type:") for x in comp)
        part = labels.part_lines({"asset_id": "RH-0002", "type": "storage"})
        assert part[0] == "Type: Storage"

    def test_the_word_is_centred_by_measurement_not_by_eye(self):
        """The glyphs stand to one side of the baseline, so the offset that centres
        them changes with the type size. A hand-picked offset would stop centring
        the moment anybody changed the size.

        The ascent is asked of the surface rather than worked out from a font name
        written here, which also covers the branch that matters: if the display TTF
        is missing the surface falls back to Helvetica and answers for that instead.
        A name guessed here would pass while the fallback crashed."""
        from reportlab.pdfgen import canvas

        from app import surfaces

        page = surfaces.PdfSurface(canvas.Canvas("/dev/null"))
        for size in (5.5, 15, 30):
            ascent = page.ascent(surfaces.HEAD, size)
            assert ascent > 0
            # What PdfSurface.vertical computes for a 10pt strip: centred, and
            # inside it whenever it fits at all.
            left = (10 - ascent) / 2
            assert abs(left - (10 - ascent - left)) < 1e-9
            if ascent <= 10:
                assert left >= 0 and left + ascent <= 10

    def test_the_word_is_black(self):
        """Not grey, which was the first attempt. A category is quieter than a fact
        on a screen; on a thermal printer there is no grey to be quiet in -- the
        head is on or off, so grey prints as a dither, and a dithered word at five
        point is a smudge."""
        import re
        from app import labels

        pdf = labels.render_pdf(
            {"asset_id": "RH-0001", "name": "X", "status": "active"}, [], labels.PROJECT, small=True
        )
        # No non-black fill is set anywhere in the content stream.
        greys = re.findall(rb"([\d.]+) ([\d.]+) ([\d.]+) rg", pdf)
        assert all(r == g == b and float(r) == 0 for r, g, b in greys), greys

    def test_the_word_keeps_a_wider_margin_than_the_body(self, client):
        """A line of words can afford to lose a hair off a descender at the edge of
        the tape. A single word set across it cannot: half a letter missing makes it
        unreadable rather than merely tight, so it keeps its own margin."""
        from app import labels

        assert labels.MEDIA[labels.SMALL]["safe_mm"] == 3
        # The body stops at mx; the word stops a millimetre further in again.
        pdf = labels.render_pdf(
            {"asset_id": "RH-0001", "name": "X", "status": "active"}, [], labels.PROJECT, small=True
        )
        assert pdf[:4] == b"%PDF"

    def test_the_code_still_scans_with_the_word_beside_it(self, client):
        """The strip is taken out of the text column and not out of the QR: a code
        below the size a phone can see is worth less than a name that wraps."""
        from app import labels

        aid = make(client)
        big = labels.render_pdf(
            {"asset_id": aid, "name": "X", "status": "active"}, [], labels.PROJECT, small=False
        )
        assert big[:4] == b"%PDF" and len(big) > 5000


class TestASmallLabelStaysOnTheLabel:
    """The name was measured against the width available and the spec lines were
    not, on the assumption that a spec is short. True of a floppy's `3.5" 1.44MB`
    and false of a monitor's `320x200 (CGA) 50 Hz, 60 Hz`, which is wider than the
    label -- and an unmeasured line is not stopped by the edge, it is drawn straight
    through whatever else is printed and off the side.
    """

    def specs(self, **pairs):
        return list(pairs.items())

    def lines_for(self, spec_pairs, name="Digivision XCD12/008/A3", ptype="display"):
        """What the small label would actually print, at the size it would use."""
        from reportlab.pdfgen import canvas
        from app import labels

        from app import surfaces

        page = surfaces.PdfSurface(canvas.Canvas("/dev/null"))
        asset = {"asset_id": "RH-MN11", "type": ptype, "name": name, "spec_pairs": spec_pairs}
        title, tags = labels.small_body(asset, labels.PART, spec_pairs)
        # The column the renderer itself leaves for the body on a 51x19mm tape with
        # the word up the end, asked of the renderer rather than worked out again
        # here from the same constants.
        tape = labels.MEDIA[labels.SMALL]
        W, H = labels.layout_size(tape)
        column = labels.small_text_column(W, H, tape["safe_mm"])
        size, lines = labels._small_body_lines(page, title, tags, column.tw, H - 2 * column.my - 11)
        return size, lines, column.tw, surfaces.BODY, page

    def test_a_monitors_specs_all_fit_inside_the_label(self):
        """RH-MN11's own label, which is what showed this up: the resolution line
        ran off the end and through the word at the other end on the way."""
        size, lines, tw, font, page = self.lines_for(
            self.specs(
                **{
                    "Screen size": '12"',
                    "Panel": "Shadow mask",
                    "Type": "CRT",
                    "Resolution": "320x200 (CGA)",
                    "Refresh": "50 Hz, 60 Hz",
                    "Interface": "DE9 RGB",
                }
            )
        )
        for line in lines:
            assert page.width_of(line, font, size) <= tw, line

    def test_the_refresh_gets_a_line_of_its_own(self):
        """Joined to the resolution it wrapped mid-figure -- "320x200 (CGA) 50" and
        then "Hz, 60 Hz" -- which reads as a fault rather than as two facts."""
        from app import labels

        _, tags = labels.small_body(
            {"asset_id": "RH-MN11", "type": "display"},
            labels.PART,
            [("Resolution", "320x200 (CGA)"), ("Refresh", "50 Hz, 60 Hz")],
        )
        assert "320x200 (CGA)" in tags and "50 Hz, 60 Hz" in tags

    def test_a_drives_specs_are_unchanged(self):
        """The joining that does hold: a floppy is "a 3.5-inch 1.44MB", one thing
        said and not two."""
        from app import labels

        _, tags = labels.small_body(
            {"asset_id": "RH-KP3D", "type": "storage"},
            labels.PART,
            [("Form factor", '3.5"'), ("Size", "1.44MB")],
        )
        assert tags == ['3.5" 1.44MB']

    def test_a_run_with_nowhere_to_break_is_cut_and_says_so(self):
        """A resolution or a part number has no space in it to wrap at. Losing the
        end of one is bad; drawing it off the side of the label is worse, because
        there it is lost with nothing to say so."""
        size, lines, tw, font, page = self.lines_for([("Resolution", "1" * 40)], name="X Y")
        assert any(x.endswith("…") for x in lines), lines
        for line in lines:
            assert page.width_of(line, font, size) <= tw, line

    def test_every_kind_of_part_stays_inside(self):
        for ptype, pairs in (
            ("storage", [("Capacity", "42.8MB"), ("CHS", "820/6/17"), ("Speed", "3600 rpm")]),
            ("storage", [("Form factor", '3.5"'), ("Size", "1.44MB")]),
            (
                "display",
                [
                    ("Screen size", '21"'),
                    ("Panel", "Aperture grille"),
                    ("Type", "CRT"),
                    ("Resolution", "1600x1200"),
                    ("Refresh", "60 Hz, 75 Hz, 85 Hz"),
                    ("Interface", "BNC, DE15"),
                ],
            ),
        ):
            size, lines, tw, font, page = self.lines_for(
                pairs, name="A Rather Long Manufacturer Name XYZ-9000", ptype=ptype
            )
            for line in lines:
                assert page.width_of(line, font, size) <= tw, (ptype, line)
