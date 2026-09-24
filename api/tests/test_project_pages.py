"""The projects list and a project's page, as MANUAL.md section 12 promises them: the
list says what is over by its status rather than fading it, and keeps what is on
order; the page reads like an item's -- the way back with the owner's Edit and
Delete beside it, the name, status and tag, a panel each for the details, items,
tasks, orders and history, and the Label panel last. A tick is sent at once, has a
Save button without script, and sets what the box shows rather than flipping it.

Auth is off in these tests, so the client is the owner; `visitor` turns it on.
"""

import re

from app import main
from app.models import ProjectTask


def visitor(monkeypatch):
    """Turn the site into what an anonymous reader sees."""
    monkeypatch.setattr(main.auth, "AUTH_ENABLED", True)


def make(client, name="Recap the +2A", **fields):
    r = client.post("/projects/new", data={"name": name, **fields}, follow_redirects=False)
    assert r.status_code == 303, r.text
    return r.headers["location"].rsplit("/", 1)[-1]


def task(client, pid, text, about=""):
    client.post(
        f"/projects/{pid}/task", data={"text": text, "asset": about}, follow_redirects=False
    )


def panel_titles(page: str) -> list[str]:
    return re.findall(r'<section class="panel[^"]*">\s*<header>\s*<h3>([^<]+)</h3>', page)


def panel(page: str, title: str) -> str:
    """The markup of the panel with this title, up to the next panel or the page's end."""
    m = re.search(
        rf"<section class=\"panel[^\"]*\">\s*<header>\s*<h3>{re.escape(title)}</h3>", page
    )
    if not m:
        return ""
    rest = page[m.end() :]
    stop = re.search(r'<section class="panel|</main>', rest)
    return rest[: stop.start()] if stop else rest


def list_row(html: str, name: str) -> str:
    table = html.split('<table class="table stack runon">')[1]
    return table.split(name)[1].split("</tr>")[0]


class TestTheList:
    def test_what_is_over_is_said_by_its_status_not_faded(self, client):
        make(client, "Built it", status="done")
        html = client.get("/projects").text
        row = html.split('<table class="table stack runon">')[1].split("Built it")[0]
        assert "closed" not in row.rsplit("<tr", 1)[1]
        assert '<span class="chip ok">' in list_row(html, "Built it")

    def test_what_is_still_coming_keeps_its_column(self, client):
        pid = make(client, "Gotek fit")
        client.post(f"/projects/{pid}/order", data={"description": "Gotek"}, follow_redirects=False)
        html = client.get("/projects").text
        assert '<th scope="col" class="tight">On order</th>' in html
        assert 'data-label="On order">1</td>' in list_row(html, "Gotek fit")

    def test_on_a_phone_each_value_says_what_it_is(self, client):
        """Stacked, the row has lost its headings."""
        make(client, "Counted", status="active")
        row = list_row(client.get("/projects").text, "Counted")
        cells = re.findall(r"<td[^>]*>", row)
        assert len(cells) == 4 and all("data-label=" in c for c in cells), cells

    def test_it_opens_on_a_heading_and_the_count(self, client):
        make(client, "One", status="active")
        html = client.get("/projects").text
        assert re.search(
            r'<div class="pagehead">\s*<h1 class="heading">Projects</h1>\s*'
            r'<span class="count">1 in hand</span>',
            html,
        ), html[html.find("pagehead") - 20 :][:300]


class TestThePageHead:
    def test_the_way_back_and_the_owners_edit_and_delete_come_first(self, client):
        pid = make(client)
        page = client.get(f"/projects/{pid}").text
        nav = page[page.index('<nav class="itemnav"') :].split("</nav>")[0]
        assert 'href="/projects"' in nav
        assert f'href="/projects/{pid}/edit"' in nav
        delete = re.search(rf'<form[^>]*action="/projects/{pid}/delete"[^>]*>', nav)
        assert delete and "data-confirm=" in delete.group(0)

    def test_a_visitor_gets_the_way_back_and_nothing_else(self, client, monkeypatch):
        pid = make(client)
        visitor(monkeypatch)
        page = client.get(f"/projects/{pid}").text
        nav = page[page.index('<nav class="itemnav"') :].split("</nav>")[0]
        assert "/edit" not in nav and "/delete" not in nav

    def test_then_the_name_its_status_and_its_tag(self, client):
        pid = make(client, "Recap the PC1512", status="stalled")
        page = client.get(f"/projects/{pid}").text
        assert re.search(
            r'<h1 class="title">Recap the PC1512</h1>\s*<span class="chip warn">[^<]+</span>\s*'
            rf'<span class="tag muted">{pid}</span>',
            page,
        )
        assert page.count("<h1") == 1


class TestThePanels:
    def test_a_panel_each_in_the_order_the_manual_gives(self, client):
        pid = make(client)
        assert panel_titles(client.get(f"/projects/{pid}").text) == [
            "Details",
            "Items",
            "Tasks",
            "On order",
            "Files",
            "History",
            "Label",
        ]

    def test_the_label_panel_has_the_two_print_buttons(self, client):
        pid = make(client)
        label = panel(client.get(f"/projects/{pid}").text, "Label")
        assert f'href="/projects/{pid}/label.pdf?small=1"' in label
        assert f'href="/projects/{pid}/label.pdf?small=0"' in label

    def test_a_visitor_gets_no_label_panel(self, client, monkeypatch):
        pid = make(client)
        visitor(monkeypatch)
        assert "Label" not in panel_titles(client.get(f"/projects/{pid}").text)

    def test_the_details_are_the_status_the_dates_and_the_notes(self, client):
        pid = make(client, status="active", started_at="2026-09-01", notes="Two lines\nof notes")
        details = panel(client.get(f"/projects/{pid}").text, "Details")
        assert '<dl class="kv">' in details
        assert "<dt>Started</dt><dd>2026-09-01</dd>" in details
        assert '<dt>Notes</dt><dd class="lines">' in details


class TestATick:
    def test_each_job_is_a_tick_that_sends_itself(self, client, db):
        pid = make(client)
        task(client, pid, "desolder the caps")
        t = db.query(ProjectTask).one()
        tasks = panel(client.get(f"/projects/{pid}").text, "Tasks")
        form = re.search(
            rf'<form[^>]*action="/projects/{pid}/task/{t.id}/toggle"[^>]*>(.*?)</form>',
            tasks,
            re.S,
        )
        assert form and "data-ticksend" in form.group(0)
        assert re.search(r'<input type="checkbox" name="done" value="1"[^>]*aria-label=', form[1])
        # The button a browser running no script presses.
        assert re.search(r"<button[^>]*data-send-go[^>]*>Save</button>", form[1])

    def test_a_done_job_is_ticked_and_struck_through(self, client, db):
        pid = make(client)
        task(client, pid, "desolder the caps")
        t = db.query(ProjectTask).one()
        client.post(f"/projects/{pid}/task/{t.id}/toggle", follow_redirects=False)
        tasks = panel(client.get(f"/projects/{pid}").text, "Tasks")
        li = re.search(r'<li class="done">(.*?)</li>', tasks, re.S)
        assert li and " checked" in li[1]

    def test_a_tick_sets_what_the_box_shows_rather_than_flipping(self, client, db):
        """Sent twice -- a second tab, a double press -- it is still ticked."""
        pid = make(client)
        task(client, pid, "desolder the caps")
        t = db.query(ProjectTask).one()
        for _ in range(2):
            client.post(
                f"/projects/{pid}/task/{t.id}/toggle",
                data={"set": "1", "done": "1"},
                follow_redirects=False,
            )
        db.expire_all()
        assert db.get(ProjectTask, t.id).done is True
        for _ in range(2):
            client.post(
                f"/projects/{pid}/task/{t.id}/toggle", data={"set": "1"}, follow_redirects=False
            )
        db.expire_all()
        t = db.get(ProjectTask, t.id)
        assert t.done is False and t.done_at is None

    def test_a_visitor_sees_the_tick_and_cannot_send_it(self, client, db, monkeypatch):
        pid = make(client)
        task(client, pid, "desolder the caps")
        visitor(monkeypatch)
        tasks = panel(client.get(f"/projects/{pid}").text, "Tasks")
        assert '<ul class="tasks">' in tasks and "/toggle" not in tasks
        assert re.search(r'<input type="checkbox"[^>]*disabled', tasks)

    def test_the_item_pages_work_panel_ticks_the_same_way(self, client, db):
        pt = client.post("/api/parts", json={"model": "TM262"}).json()["asset_id"]
        client.post("/projects/quick", data={"aid": pt, "job": "recap"}, follow_redirects=False)
        t = db.query(ProjectTask).one()
        work = panel(client.get(f"/parts/{pt}").text, "Work")
        form = re.search(
            rf'<form[^>]*action="/projects/{t.project_id}/task/{t.id}/toggle"[^>]*>(.*?)</form>',
            work,
            re.S,
        )
        assert form and "data-ticksend" in form.group(0)
        assert f'name="next" value="/parts/{pt}"' in form[1]
        assert '<input type="checkbox" name="done"' in form[1]


class TestWhatAJobIsAbout:
    def setup(self, client):
        pt = client.post("/api/parts", json={"model": "TM262"}).json()["asset_id"]
        pid = make(client)
        client.post(f"/projects/{pid}/add-item", data={"asset_id": pt}, follow_redirects=False)
        task(client, pid, "recap the PSU", about=pt)
        return pid, pt

    def test_the_owner_chooses_it_from_a_menu_that_sends_itself(self, client):
        pid, pt = self.setup(client)
        tasks = panel(client.get(f"/projects/{pid}").text, "Tasks")
        form = re.search(r'<form[^>]*action="[^"]*/about"[^>]*>(.*?)</form>', tasks, re.S)
        assert form and "data-ticksend" in form.group(0)
        assert re.search(rf'<option value="{pt}" selected>', form[1])
        assert re.search(r"<button[^>]*data-send-go[^>]*>Set</button>", form[1])

    def test_a_visitor_reads_the_tag_of_the_thing(self, client, monkeypatch):
        pid, pt = self.setup(client)
        visitor(monkeypatch)
        tasks = panel(client.get(f"/projects/{pid}").text, "Tasks")
        assert f'<a class="tag" href="/items/{pt}">{pt}</a>' in tasks
        assert "<select" not in tasks
