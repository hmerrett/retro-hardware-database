"""The quick way into a project, and the privacy that came with it.

An item used to carry a `project` flag and a `project_note`: a thing noticed,
private, gathered on /projects under "Wanting work". A project was the same idea
one size up, and getting from one to the other meant retyping it.

The flag is gone (migration 0031). The quick box makes a project directly -- the
item on it, the sentence as its first job -- and what the flag carried besides a
sentence, its privacy, is now a column on the project.

Most of what is worth testing here is that privacy, as it was before. The register
is a public catalogue with a login over the editing rather than over the data, so a
record that is meant to be unreadable has to be unreadable in every place a page
could show it. The class below that name is the point of the feature as much as the
quick box is: four of those five doors standing shut is a thing that is not private.
"""

import pytest

from app.models import Computer, Project, ProjectAsset, ProjectTask
from conftest import log_out


def quick(client, job="needs a belt", **extra):
    r = client.post("/projects/quick", data={"job": job, **extra}, follow_redirects=False)
    assert r.status_code == 303, r.text
    return r.headers["location"].rsplit("/", 1)[-1]


def hidden(client, job="a private job", name="Hidden", aid=None):
    """A private project. Nothing here is private by default any more (ADR-0004),
    so the tests below that are about privacy make one on purpose -- which is what
    an owner does, and the only way one comes to be private now.

    Through the API rather than by writing the column, so it goes down the same path
    the tick on the form does and the histories of its items are brought into line
    with it."""
    pid = quick(client, job, name=name, **({"aid": aid} if aid else {}))
    r = client.patch(f"/api/projects/{pid}", json={"private": True})
    assert r.status_code == 200, r.text
    return pid


def visitor(client):
    """Nobody logged in. The fixtures run with the login switched off, so the gate
    lets everything through until a test says otherwise."""
    log_out(client)


class TestNotingSomethingDown:
    def test_a_job_alone_makes_a_project(self, client, db):
        """A project need own nothing -- the idea comes before the hardware -- so
        the asset tag is the optional half of this box, not the required one."""
        aid = quick(client, "sort out the RIFA")
        p = db.get(Project, aid)
        assert p is not None and p.status == "planned"
        task = db.query(ProjectTask).filter(ProjectTask.project_id == aid).one()
        assert task.text == "sort out the RIFA" and not task.done

    def test_the_item_goes_on_it(self, client, db, part):
        pt = part(manufacturer="Chinon", model="FZ-357A")["asset_id"]
        aid = quick(client, "needs a belt", aid=pt)
        assert (
            db.query(ProjectAsset)
            .filter(ProjectAsset.project_id == aid, ProjectAsset.asset_id == pt)
            .count()
            == 1
        )

    def test_it_is_named_after_the_item_when_you_do_not_name_it(self, client, db, part):
        """One name for the gesture, whichever box it was typed in -- and the item's
        own name, not its tag. "Chinon FZ-357A" is a line that can be read down a
        list; RH-9QD4 is one that has to be looked up first."""
        pt = part(manufacturer="Chinon", model="FZ-357A")["asset_id"]
        assert db.get(Project, quick(client, "needs a belt", aid=pt)).name == "Chinon FZ-357A"

    def test_a_name_you_give_it_wins(self, client, db, part):
        pt = part(manufacturer="Chinon", model="FZ-357A")["asset_id"]
        aid = quick(client, "needs a belt", aid=pt, name="Drive belt swap")
        assert db.get(Project, aid).name == "Drive belt swap"

    def test_with_no_item_and_no_name_the_job_names_it(self, client, db):
        assert db.get(Project, quick(client, "sort out the RIFA")).name == "sort out the RIFA"

    def test_it_lands_on_the_project_it_just_made(self, client):
        r = client.post("/projects/quick", data={"job": "a job"}, follow_redirects=False)
        assert r.headers["location"].startswith("/projects/RH-")

    def test_a_mistyped_tag_comes_back_to_the_box(self, client, db):
        """A 404 page would lose what was typed, and a mistyped tag is the ordinary
        way to get this wrong."""
        r = client.post(
            "/projects/quick", data={"job": "a job", "aid": "RH-XXXX"}, follow_redirects=False
        )
        assert r.status_code == 400
        assert "RH-XXXX" in r.text
        assert db.query(Project).count() == 0

    def test_the_projects_own_history_records_what_it_took_on(self, client, part):
        pt = part(model="Widget")["asset_id"]
        aid = quick(client, "needs a belt", aid=pt)
        html = client.get(f"/projects/{aid}").text
        assert "took on" in html and "to do: needs a belt" in html

    def test_the_items_history_says_what_it_is_wanted_for(self, client, part):
        """A project made this way is public now, and an item's history names a
        project exactly while that project is public -- so the line goes in at the
        moment the project takes the item on."""
        pt = part(model="Widget")["asset_id"]
        quick(client, "needs a belt", aid=pt, name="Openzzz")
        assert "wanted for Openzzz" in client.get(f"/parts/{pt}").text

    def test_a_private_one_leaves_it_quiet(self, client, part):
        """An item page is public and so is its history, and the history is the part
        of the register nothing rewrites. A line naming a private project there
        would publish the name, and publish it for good."""
        pt = part(model="Widget")["asset_id"]
        hidden(client, "needs a belt", name="Hiddenzzz", aid=pt)
        page = client.get(f"/parts/{pt}").text
        assert "Hiddenzzz" not in page.split("History")[-1]

    def test_the_box_is_on_the_page_for_whoever_is_logged_in(self, client):
        assert "/projects/quick" in client.get("/projects").text

    def test_a_visitor_is_not_offered_it(self, client, monkeypatch):
        visitor(client)
        assert "/projects/quick" not in client.get("/projects").text


class TestItIsPrivate:
    """Five doors, and a project is only private with all five shut.

    What has changed is how one comes to be private: by the tick on its own form,
    and not by having been typed quickly (ADR-0004). The doors themselves are what
    they were, and are what these test."""

    def test_what_the_quick_box_makes_is_public(self, client, db):
        """The register is a public catalogue of old machines, and what is wrong
        with one is a good part of what is interesting about it. A default that hid
        the work was undone by hand on nearly every project."""
        assert db.get(Project, quick(client, "a job")).private is False

    def test_what_the_form_makes_is_too(self, client, db):
        r = client.post("/projects/new", data={"name": "Recap the +2A"}, follow_redirects=False)
        aid = r.headers["location"].rsplit("/", 1)[-1]
        assert db.get(Project, aid).private is False

    def test_a_visitor_does_not_see_it_on_the_list(self, client, monkeypatch):
        hidden(client)
        client.post("/projects/new", data={"name": "Shown"}, follow_redirects=False)
        visitor(client)
        html = client.get("/projects").text
        assert "Shown" in html and "Hidden" not in html

    def test_its_own_page_answers_a_visitor_with_a_404(self, client, monkeypatch):
        """Not a 403 and not the login: somebody who guessed the tag should not be
        told there is something there to guess at."""
        aid = hidden(client)
        visitor(client)
        assert client.get(f"/projects/{aid}").status_code == 404

    def test_a_public_project_still_opens(self, client, monkeypatch):
        r = client.post("/projects/new", data={"name": "Shown"}, follow_redirects=False)
        aid = r.headers["location"].rsplit("/", 1)[-1]
        visitor(client)
        assert client.get(f"/projects/{aid}").status_code == 200

    def test_a_visitors_search_does_not_match_it(self, client, monkeypatch):
        hidden(client, "recapzzz", name="Hiddenzzz")
        visitor(client)
        # The project's name, not the query: the search box echoes the query back
        # into its own value, so looking for that would find it every time.
        assert "Hiddenzzz" not in client.get("/projects?q=recapzzz").text
        assert client.get("/suggest?q=recapzzz").json()["total"] == 0

    def test_the_same_search_finds_it_for_whoever_is_logged_in(self, client):
        hidden(client, "recapzzz")
        assert client.get("/suggest?q=recapzzz").json()["total"] == 1

    def test_the_gallery_does_not_count_it_for_a_visitor(self, client, monkeypatch):
        """The line above the gallery results says how many projects also matched.
        Counting a private one would say there is something there without showing
        it, which is the same leak said as a number."""
        hidden(client, "recapzzz", name="Hiddenzzz")
        visitor(client)
        note = client.get("/?q=recapzzz").text
        assert "/projects?q=recapzzz" not in note
        assert "Hiddenzzz" not in note

    def test_it_is_not_in_the_sitemap(self, client):
        """The one of the five read by machines rather than people, where a tag is
        an invitation."""
        kept_back = hidden(client)
        shown = (
            client.post("/projects/new", data={"name": "Shown"}, follow_redirects=False)
            .headers["location"]
            .rsplit("/", 1)[-1]
        )
        xml = client.get("/sitemap.xml").text
        assert f"/projects/{shown}</loc>" in xml
        assert kept_back not in xml

    def test_it_is_not_named_on_the_page_of_the_machine_it_is_about(
        self, client, part, monkeypatch
    ):
        """An item page is public. Without this, a project kept off the list, out of
        the search and out of the sitemap would name itself on the page of every
        machine it is about -- the whole of what was being kept back, said in the one
        place nobody thought to look."""
        pt = part(model="Widget")["asset_id"]
        hidden(client, "needs a belt", aid=pt)
        assert "Hidden" in client.get(f"/parts/{pt}").text
        visitor(client)
        # Nowhere on the page: not the panel, and not the history either.
        assert "Hidden" not in client.get(f"/parts/{pt}").text

    def test_publishing_one_shows_it_everywhere_at_once(self, client, db, monkeypatch):
        """Clearing the tick is the act of publishing, and it has to reach all five
        doors -- otherwise it half-publishes, which is worse than either."""
        aid = hidden(client, "a job")
        client.post(f"/projects/{aid}/edit", data={"name": "Hidden"}, follow_redirects=False)
        assert db.get(Project, aid).private is False
        visitor(client)
        assert client.get(f"/projects/{aid}").status_code == 200
        assert "Hidden" in client.get("/projects").text
        assert aid in client.get("/sitemap.xml").text


class TestPublishingAndWithdrawing:
    """An item's history names a project exactly while that project is public."""

    def test_publishing_writes_the_line_that_was_held_back(self, client, part):
        pt = part(model="Widget")["asset_id"]
        aid = hidden(client, "needs a belt", aid=pt, name="Nowpublic")
        assert "wanted for" not in client.get(f"/parts/{pt}").text
        client.post(f"/projects/{aid}/edit", data={"name": "Nowpublic"}, follow_redirects=False)
        assert "wanted for Nowpublic" in client.get(f"/parts/{pt}").text

    def test_withdrawing_takes_it_back_out(self, client, part):
        """The one place the register rewrites its own log, and the whole point: a
        name taken out of publication cannot be left behind in the one public place
        it was written."""
        pt = part(model="Widget")["asset_id"]
        r = client.post("/projects/new", data={"name": "Wasopen"}, follow_redirects=False)
        aid = r.headers["location"].rsplit("/", 1)[-1]
        client.post(f"/projects/{aid}/add-item", data={"asset_id": pt}, follow_redirects=False)
        assert "wanted for Wasopen" in client.get(f"/parts/{pt}").text
        client.post(
            f"/projects/{aid}/edit",
            data={"name": "Wasopen", "private": "1"},
            follow_redirects=False,
        )
        # The history, specifically. The panel above it still names the project,
        # and should: that panel is drawn for whoever is logged in and takes the
        # private ones out for everybody else.
        assert "Wasopen" not in client.get(f"/parts/{pt}").text.split("History")[-1]

    def test_the_api_does_the_same(self, client, part):
        pt = part(model="Widget")["asset_id"]
        p = client.post("/api/projects", json={"name": "Apipub"}).json()
        client.post(f"/api/projects/{p['asset_id']}/items", json={"asset_id": pt})
        assert "wanted for Apipub" in client.get(f"/parts/{pt}").text
        client.patch(f"/api/projects/{p['asset_id']}", json={"private": True})
        assert "Apipub" not in client.get(f"/parts/{pt}").text.split("History")[-1]


class TestTheApiCarriesIt:
    def test_it_reads_and_writes_like_any_other_column(self, client):
        """The API is behind the login entire, so there is nothing to hide from it;
        what `private` governs is what the public pages show."""
        p = client.post("/api/projects", json={"name": "X", "private": True}).json()
        assert p["private"] is True
        got = client.patch(f"/api/projects/{p['asset_id']}", json={"private": False}).json()
        assert got["private"] is False

    def test_the_api_lists_private_ones(self, client):
        client.post("/api/projects", json={"name": "X", "private": True})
        assert len(client.get("/api/projects").json()) == 1


class TestTheMigrationDidNotAnnounceThem:
    """0031 wrote "wanted for <name> (<tag>)" into the history of every item it
    converted, on the reasoning that a plan with a page of its own no longer needs
    the register to be quiet about it. The project it made was private, and an
    item's history is public -- so the line announced a private project, and its
    tag, on the page of the machine it was about. 0032 takes them back out.

    Tested through the app rather than through the migration, because what matters
    is the invariant the app is supposed to keep and not the SQL that broke it."""

    def test_no_public_history_names_a_private_project(self, client, db, part):
        from app.models import LogEntry

        pt = part(model="Widget")["asset_id"]
        aid = hidden(client, "a job", aid=pt, name="Hiddenzzz")
        written = " ".join(m for (m,) in db.query(LogEntry.message).filter(LogEntry.asset_id == pt))
        assert aid not in written and "Hiddenzzz" not in written

    def test_a_private_projects_tag_is_not_on_the_item_page(self, client, part, monkeypatch):
        """The tag alone is a disclosure: it says there is something there, and it
        is the one thing needed to try the door."""
        pt = part(model="Widget")["asset_id"]
        aid = hidden(client, "a job", aid=pt, name="Hiddenzzz")
        visitor(client)
        assert aid not in client.get(f"/parts/{pt}").text


class TestTheBoxOnAnItemsOwnPage:
    """The panel on a computer's or a part's page. The same route the projects page
    posts to, and now the same two questions the entry forms ask: what needs doing,
    and whether it is a piece of work of its own."""

    def note(self, client, aid, job, **extra):
        r = client.post(
            "/projects/quick", data={"aid": aid, "job": job, **extra}, follow_redirects=False
        )
        assert r.status_code == 303, r.text
        return r.headers["location"].rsplit("/", 1)[-1]

    def test_a_line_is_a_job_here_too(self, client, db, part):
        pt = part(model="Widget")["asset_id"]
        pid = self.note(client, pt, "recap\nnew belt")
        assert [
            t.text
            for t in db.query(ProjectTask)
            .filter(ProjectTask.project_id == pid)
            .order_by(ProjectTask.id)
        ] == ["recap", "new belt"]

    def test_the_jobs_can_go_on_a_project_already_going(self, client, db, part):
        """The question this page is the right one to ask: you are looking at the
        board, and whether it is spoken for is a fact about the board."""
        pt = part(model="Widget")["asset_id"]
        existing = client.post("/api/projects", json={"name": "A500"}).json()["asset_id"]
        assert self.note(client, pt, "fit it", project=existing) == existing
        assert db.query(Project).count() == 1

    def test_the_picker_offers_the_projects_in_hand(self, client, part):
        pt = part(model="Widget")["asset_id"]
        live = client.post("/api/projects", json={"name": "Livezzz"}).json()["asset_id"]
        done = client.post("/api/projects", json={"name": "Donezzz", "status": "done"}).json()[
            "asset_id"
        ]
        page = client.get(f"/parts/{pt}").text
        assert live in page and done not in page

    def test_a_visitor_is_not_asked(self, client, part, monkeypatch):
        """The panel is a form, and the picker would name every open project --
        including the private ones -- on a public page."""
        pt = part(model="Widget")["asset_id"]
        client.post("/api/projects", json={"name": "Privatezzz", "private": True})
        visitor(client)
        assert "Privatezzz" not in client.get(f"/parts/{pt}").text


# --- the same gesture, one step earlier ---------------------------------------
# Noting what a thing needs is a check-in gesture: it is thought at the moment the
# machine comes off the doorstep and is typed into the form that files it. The quick
# box above needs an asset tag, which is a thing that does not exist yet while that
# form is on screen -- so the note waited for a second visit, and a note that waits
# is a note that is lost. The box on the entry forms is the same note taken there.


def new_computer(client, **extra):
    """A machine through the entry form, as somebody checking one in files it."""
    r = client.post(
        "/computers/new",
        data={"manufacturer": "Acme", "model": "PC", **extra},
        follow_redirects=False,
    )
    assert r.status_code == 303, r.text
    return r.headers["location"].split("?")[0].rsplit("/", 1)[-1]


def new_part(client, **extra):
    r = client.post(
        "/parts/new", data={"type": "other", "model": "Widget", **extra}, follow_redirects=False
    )
    assert r.status_code == 303, r.text
    return r.headers["location"].split("?")[0].rsplit("/", 1)[-1]


def tasks_of(db, project_id):
    return [
        t.text
        for t in db.query(ProjectTask)
        .filter(ProjectTask.project_id == project_id)
        .order_by(ProjectTask.id)
    ]


def project_of(db, asset_id):
    """The one project an item is in, or None. Asserts there are not two, because
    every test below is about a single gesture and a second project would mean the
    gesture ran twice."""
    rows = db.query(ProjectAsset).filter(ProjectAsset.asset_id == asset_id).all()
    assert len(rows) <= 1, [r.project_id for r in rows]
    return db.get(Project, rows[0].project_id) if rows else None


class TestNotingWorkWhileCheckingIn:
    def test_a_machine_arrives_with_its_faults_written_down(self, client, db):
        aid = new_computer(client, work_needed="recap the PSU")
        p = project_of(db, aid)
        assert p is not None
        assert tasks_of(db, p.asset_id) == ["recap the PSU"]

    def test_the_project_is_named_after_the_item(self, client, db):
        """The form has no name box: what is being described is the work, and the
        only thing known about it at that moment is which item it is for. So the
        item names it, by what it is called."""
        aid = new_computer(client, work_needed="recap the PSU")
        assert project_of(db, aid).name == "Acme PC"

    def test_a_thing_with_no_name_yet_falls_back_to_its_tag(self, client, db):
        """A machine entered with nothing filled in but a fault has no name to be
        called after. Its tag is what it has, and a project named after nothing at
        all is a row nobody will recognise again."""
        r = client.post("/computers/new", data={"work_needed": "recap"}, follow_redirects=False)
        aid = r.headers["location"].split("?")[0].rsplit("/", 1)[-1]
        assert project_of(db, aid).name == aid

    def test_two_of_the_same_machine_are_told_apart_by_their_own_tags(self, client, db):
        """Two projects can come out with the same name, where the collection holds
        two of the same model. That is what the project's own tag beside it on every
        list is for; inventing a distinction in the name would be inventing it in
        the wrong place."""
        first = project_of(db, new_computer(client, work_needed="recap"))
        second = project_of(db, new_computer(client, work_needed="recap"))
        assert first.name == second.name and first.asset_id != second.asset_id

    def test_it_is_public(self, client, db):
        """The same rule the quick box follows, and the register is a public
        catalogue: what a machine needs doing is a fact about it worth reading, and
        the tick on the project's own form is there for the one that is not."""
        assert project_of(db, new_computer(client, work_needed="recap")).private is False

    def test_it_starts_planned(self, client, db):
        """Nothing has been done to it yet -- it has only just come through the
        door -- and calling that 'in progress' would make the in-hand list a lie."""
        assert project_of(db, new_computer(client, work_needed="recap")).status == "planned"

    def test_a_line_is_a_job(self, client, db):
        """What somebody types while looking at a machine is a list, because faults
        arrive as a list. One box, one job to a line, in the order they were seen."""
        aid = new_computer(client, work_needed="recap\nnew belt\n\nkeyboard sticks")
        assert tasks_of(db, project_of(db, aid).asset_id) == [
            "recap",
            "new belt",
            "keyboard sticks",
        ]

    def test_an_empty_box_makes_nothing(self, client, db):
        """Most machines are checked in with nothing wrong with them, and a project
        per arrival would make the projects page useless."""
        new_computer(client, work_needed="   ")
        assert db.query(Project).count() == 0

    def test_a_part_is_checked_in_the_same_way(self, client, db):
        pid = new_part(client, work_needed="pins bent")
        assert tasks_of(db, project_of(db, pid).asset_id) == ["pins bent"]

    def test_the_machine_is_saved_either_way(self, client, db):
        """The note is a second thing the form does, not a condition of the first.
        A machine entered with a fault is still a machine."""
        aid = new_computer(client, work_needed="recap")
        assert db.get(Computer, aid).model == "PC"


class TestCheckingInOntoAProjectAlreadyGoing:
    """The other half of check-in: the thing that has just arrived is often the
    thing an existing project was waiting for. Retyping it into a new project of its
    own would leave the PSU and the machine it was bought for on two lists."""

    def existing(self, client, **fields):
        body = {"name": "A500 restoration"} | fields
        return client.post("/api/projects", json=body).json()["asset_id"]

    def test_the_item_joins_the_project_that_was_named(self, client, db):
        pid = self.existing(client)
        aid = new_computer(client, work_needed="test it", work_project=pid)
        assert project_of(db, aid).asset_id == pid

    def test_no_second_project_is_made(self, client, db):
        pid = self.existing(client)
        new_computer(client, work_needed="test it", work_project=pid)
        assert [p.asset_id for p in db.query(Project)] == [pid]

    def test_the_jobs_go_on_that_project(self, client, db):
        pid = self.existing(client)
        new_computer(client, work_needed="test it\nfit the PSU", work_project=pid)
        assert tasks_of(db, pid) == ["test it", "fit the PSU"]

    def test_a_project_can_be_named_with_no_job_at_all(self, client, db):
        """ "This is for that" is a complete thought. The part that has just arrived
        is spoken for, and there is nothing to do to it yet."""
        pid = self.existing(client)
        aid = new_part(client, work_project=pid)
        assert project_of(db, aid).asset_id == pid and tasks_of(db, pid) == []

    def test_a_public_project_says_so_on_the_item(self, client, db):
        """Membership writes the item's side of the history exactly as adding it
        from the project's own page does -- and only for a project anybody may
        read, which is the invariant _member_log keeps."""
        from app.models import LogEntry

        pid = self.existing(client, private=False)
        aid = new_computer(client, work_project=pid)
        written = " ".join(
            m for (m,) in db.query(LogEntry.message).filter(LogEntry.asset_id == aid)
        )
        assert "wanted for" in written and pid in written

    def test_a_private_project_stays_quiet(self, client, db):
        from app.models import LogEntry

        pid = self.existing(client, private=True)
        aid = new_computer(client, work_project=pid)
        written = " ".join(
            m for (m,) in db.query(LogEntry.message).filter(LogEntry.asset_id == aid)
        )
        assert pid not in written

    def test_a_tag_that_names_no_project_still_keeps_the_note(self, client, db):
        """The picker cannot produce this; a hand-made post can. Losing the machine
        that was being entered -- photographs and all -- because of it would be a
        poor trade, so the note becomes a project of its own and the entry stands."""
        aid = new_computer(client, work_needed="recap", work_project="RH-ZZZZ")
        p = project_of(db, aid)
        assert p is not None and tasks_of(db, p.asset_id) == ["recap"]

    def test_the_form_offers_the_projects_in_hand(self, client):
        """A closed project is not something a machine arriving today is joining,
        and a picker of every project ever finished is a picker nobody reads."""
        live = self.existing(client, name="Livezzz")
        done = self.existing(client, name="Donezzz", status="done")
        page = client.get("/computers/new").text
        assert live in page and done not in page


class TestNotingWorkOnAnItemThatExists:
    """The same box on the edit form. Redundant with the panel on the item's own
    page, and there because the form is where somebody is already typing."""

    def test_the_edit_form_notes_work_too(self, client, db):
        aid = new_computer(client)
        r = client.post(
            f"/computers/{aid}/edit",
            data={"manufacturer": "Acme", "model": "PC", "work_needed": "recap"},
            follow_redirects=False,
        )
        assert r.status_code == 303
        assert tasks_of(db, project_of(db, aid).asset_id) == ["recap"]

    def test_saving_again_does_not_write_it_twice(self, client, db):
        """The box is write-only: it is never filled in with what is already on the
        project, so an ordinary save leaves the jobs alone. A box that echoed them
        back would add every job a second time on the next save."""
        aid = new_computer(client, work_needed="recap")
        client.post(f"/computers/{aid}/edit", data={"manufacturer": "Acme", "model": "PC2"})
        assert tasks_of(db, project_of(db, aid).asset_id) == ["recap"]

    def test_a_part_edit_notes_work_too(self, client, db):
        pid = new_part(client)
        r = client.post(
            f"/parts/{pid}/edit",
            data={"type": "other", "model": "Widget", "work_needed": "pins bent"},
            follow_redirects=False,
        )
        assert r.status_code == 303
        assert tasks_of(db, project_of(db, pid).asset_id) == ["pins bent"]


class TestNotingWorkThroughTheApi:
    """Check-in happens through the MCP server as often as through the form -- a
    machine dictated at the bench rather than typed -- and the note has to travel
    with it there too, or the same second visit is needed."""

    def test_a_computer_arrives_with_its_faults(self, client, db):
        aid = client.post(
            "/api/computers", json={"manufacturer": "Acme", "model": "PC", "work_needed": "recap"}
        ).json()["asset_id"]
        assert tasks_of(db, project_of(db, aid).asset_id) == ["recap"]

    def test_a_part_does_too(self, client, db):
        pid = client.post(
            "/api/parts", json={"type": "other", "model": "Widget", "work_needed": "pins bent"}
        ).json()["asset_id"]
        assert tasks_of(db, project_of(db, pid).asset_id) == ["pins bent"]

    def test_an_existing_project_can_be_named(self, client, db):
        pid = client.post("/api/projects", json={"name": "A500"}).json()["asset_id"]
        aid = client.post(
            "/api/computers", json={"manufacturer": "Acme", "model": "PC", "work_project": pid}
        ).json()["asset_id"]
        assert project_of(db, aid).asset_id == pid

    def test_a_project_that_does_not_exist_is_refused(self, client, db):
        """Unlike the form, which cannot mistype one. A caller that named a project
        meant that project, and quietly filing the work somewhere else would be a
        worse answer than being told."""
        r = client.post(
            "/api/computers",
            json={"manufacturer": "Acme", "model": "PC", "work_project": "RH-ZZZZ"},
        )
        assert r.status_code == 404

    def test_nothing_is_created_when_it_is_refused(self, client, db):
        """The refusal comes before the machine is written, so a typo'd project tag
        does not leave a half-entered computer behind."""
        client.post(
            "/api/computers",
            json={"manufacturer": "Acme", "model": "PC", "work_project": "RH-ZZZZ"},
        )
        assert db.query(Computer).count() == 0

    def test_the_item_reads_back_with_its_project(self, client, db):
        """What the note did, said in the reply -- otherwise a caller that has just
        raised a project has no way to reach it but a search. One tag and not a
        list of them: a thing is on one project (ADR-0016)."""
        aid = client.post(
            "/api/computers", json={"manufacturer": "Acme", "model": "PC", "work_needed": "recap"}
        ).json()["asset_id"]
        got = client.get(f"/api/computers/{aid}").json()
        assert got["project"] == project_of(db, aid).asset_id

    def test_the_list_reads_back_with_it_as_well(self, client, db):
        aid = client.post(
            "/api/computers", json={"manufacturer": "Acme", "model": "PC", "work_needed": "recap"}
        ).json()["asset_id"]
        rows = client.get("/api/computers").json()
        assert rows[0]["project"] == project_of(db, aid).asset_id


# --- the ones already written -------------------------------------------------


def _migration_0033():
    """The rename migration, loaded from its file. Migrations are not a package on
    the path, and importing it by name here would mean adding one just to be able
    to test what it does -- which is worth testing: it is the only code in the
    register that rewrites something somebody could have typed."""
    import importlib.util
    from pathlib import Path

    path = (
        Path(__file__).resolve().parent.parent
        / "migrations"
        / "versions"
        / "0033_work_projects_named_after_the_thing.py"
    )
    spec = importlib.util.spec_from_file_location("m0033", path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def run_migration(db, direction="upgrade"):
    """Run it against the session's own connection, the way alembic runs one."""
    from alembic.migration import MigrationContext
    from alembic.operations import Operations

    module = _migration_0033()
    ctx = MigrationContext.configure(db.connection())
    with Operations.context(ctx):
        getattr(module, direction)()
    db.commit()


class TestRenamingTheOnesAlreadyWritten:
    """Migration 0033. The projects raised before the name changed still say the
    tag, and nothing about them says to leave them that way -- so it brings them
    into line, on whatever database it is run against and on none in particular.
    """

    def old_style(self, client, db, **fields):
        """An item and a project named after its tag, as the app used to write it."""
        aid = client.post(
            "/api/computers", json={"manufacturer": "Amstrad", "model": "PC1640"} | fields
        ).json()["asset_id"]
        pid = client.post("/api/projects", json={"name": f"Work required by item: {aid}"}).json()[
            "asset_id"
        ]
        client.post(f"/api/projects/{pid}/items", json={"asset_id": aid})
        return aid, pid

    def test_it_says_what_the_thing_is(self, client, db):
        _, pid = self.old_style(client, db)
        run_migration(db)
        assert db.get(Project, pid).name == "Work required by item: Amstrad PC1640"

    def test_a_name_somebody_chose_is_left_alone(self, client, db):
        """The rule is narrow on purpose: only the exact old form, built from the
        tag of an item the project is actually about. A project called something
        else that happens to start with those words was named by a person."""
        aid, _ = self.old_style(client, db)
        pid = client.post(
            "/api/projects", json={"name": "Work required by item: the beige one"}
        ).json()["asset_id"]
        client.post(f"/api/projects/{pid}/items", json={"asset_id": aid})
        run_migration(db)
        assert db.get(Project, pid).name == "Work required by item: the beige one"

    def test_a_project_naming_another_items_tag_is_left_alone(self, client, db):
        """Named after one thing and about another is not a project this migration
        knows anything about."""
        other = client.post("/api/computers", json={"model": "X"}).json()["asset_id"]
        aid, _ = self.old_style(client, db)
        pid = client.post("/api/projects", json={"name": f"Work required by item: {other}"}).json()[
            "asset_id"
        ]
        client.post(f"/api/projects/{pid}/items", json={"asset_id": aid})
        run_migration(db)
        assert db.get(Project, pid).name == f"Work required by item: {other}"

    def test_a_thing_with_no_name_keeps_its_tag(self, client, db):
        """There is nothing else to call it, and a rename to the same thing is not
        a rename."""
        aid = client.post("/api/computers", json={}).json()["asset_id"]
        pid = client.post("/api/projects", json={"name": f"Work required by item: {aid}"}).json()[
            "asset_id"
        ]
        client.post(f"/api/projects/{pid}/items", json={"asset_id": aid})
        run_migration(db)
        assert db.get(Project, pid).name == f"Work required by item: {aid}"

    def test_running_it_twice_changes_nothing_the_second_time(self, client, db):
        _, pid = self.old_style(client, db)
        run_migration(db)
        once = db.get(Project, pid).name
        run_migration(db)
        db.expire_all()
        assert db.get(Project, pid).name == once

    def test_it_goes_back(self, client, db):
        """A downgrade reads the tag off the membership, because the name no longer
        holds one to read -- which is the whole of what changed."""
        aid, pid = self.old_style(client, db)
        run_migration(db)
        run_migration(db, "downgrade")
        db.expire_all()
        assert db.get(Project, pid).name == f"Work required by item: {aid}"

    def test_an_empty_database_is_left_alone(self, db):
        """A fresh install has none of these, and a migration that assumes rows
        exist is the bug ADR-0002 is about."""
        run_migration(db)
        assert db.query(Project).count() == 0


# --- dropping the prefix ------------------------------------------------------


def _migration_0036():
    """The prefix-dropping migration, loaded from its file, for the reason
    _migration_0033 is."""
    import importlib.util
    from pathlib import Path

    path = (
        Path(__file__).resolve().parent.parent
        / "migrations"
        / "versions"
        / "0036_work_projects_drop_the_prefix.py"
    )
    spec = importlib.util.spec_from_file_location("m0036", path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def run_0036(db, direction="upgrade"):
    from alembic.migration import MigrationContext
    from alembic.operations import Operations

    ctx = MigrationContext.configure(db.connection())
    with Operations.context(ctx):
        getattr(_migration_0036(), direction)()
    db.commit()


class TestDroppingThePrefixFromTheOnesAlreadyWritten:
    """Migration 0036. The projects raised while the name carried "Work required by
    item: " still carry it, and a list with both forms in it reads as two kinds of
    project rather than one -- so it brings them into line, the way 0033 did."""

    def prefixed(self, client, db, **fields):
        """An item and a project named the way the app used to name one."""
        aid = client.post(
            "/api/computers", json={"manufacturer": "Amstrad", "model": "PC1640"} | fields
        ).json()["asset_id"]
        pid = client.post(
            "/api/projects", json={"name": "Work required by item: Amstrad PC1640"}
        ).json()["asset_id"]
        client.post(f"/api/projects/{pid}/items", json={"asset_id": aid})
        return aid, pid

    def test_it_says_what_the_thing_is_called_and_nothing_else(self, client, db):
        _, pid = self.prefixed(client, db)
        run_0036(db)
        assert db.get(Project, pid).name == "Amstrad PC1640"

    def test_a_name_somebody_chose_is_left_alone(self, client, db):
        """The same narrow rule 0033 used: only the exact generated form for the
        item the project is actually about. Anything else was typed by a person."""
        aid, _ = self.prefixed(client, db)
        pid = client.post(
            "/api/projects", json={"name": "Work required by item: the beige one"}
        ).json()["asset_id"]
        client.post(f"/api/projects/{pid}/items", json={"asset_id": aid})
        run_0036(db)
        assert db.get(Project, pid).name == "Work required by item: the beige one"

    def test_a_thing_with_no_name_comes_out_as_its_tag(self, client, db):
        """display_name falls back to the tag, so the prefixed form for a nameless
        item held its tag -- and what it should say now is that tag alone."""
        aid = client.post("/api/computers", json={}).json()["asset_id"]
        pid = client.post("/api/projects", json={"name": f"Work required by item: {aid}"}).json()[
            "asset_id"
        ]
        client.post(f"/api/projects/{pid}/items", json={"asset_id": aid})
        run_0036(db)
        assert db.get(Project, pid).name == aid

    def test_a_project_about_two_things_is_left_alone(self, client, db):
        """A project with two items on it was never named this way."""
        _, pid = self.prefixed(client, db)
        other = client.post("/api/computers", json={"model": "X"}).json()["asset_id"]
        client.post(f"/api/projects/{pid}/items", json={"asset_id": other})
        run_0036(db)
        assert db.get(Project, pid).name == "Work required by item: Amstrad PC1640"

    def test_running_it_twice_changes_nothing_the_second_time(self, client, db):
        _, pid = self.prefixed(client, db)
        run_0036(db)
        once = db.get(Project, pid).name
        run_0036(db)
        db.expire_all()
        assert db.get(Project, pid).name == once

    def test_it_goes_back(self, client, db):
        _, pid = self.prefixed(client, db)
        run_0036(db)
        run_0036(db, "downgrade")
        db.expire_all()
        assert db.get(Project, pid).name == "Work required by item: Amstrad PC1640"

    def test_an_empty_database_is_left_alone(self, db):
        """ADR-0002: a migration that assumes rows exist is the fresh-install bug."""
        run_0036(db)
        assert db.query(Project).count() == 0


# --- one project to a thing ---------------------------------------------------


def tasks_against(db, asset_id):
    return [
        t.text
        for t in db.query(ProjectTask)
        .filter(ProjectTask.asset_id == asset_id)
        .order_by(ProjectTask.id)
    ]


class TestOneProjectToAThing:
    """ADR-0016. A project is about many things; a thing is on one project."""

    def test_the_database_refuses_a_second_one(self, client, db):
        """The rule is a unique constraint and not only a habit in the code, so a
        path nobody thought of cannot quietly put a thing in two places."""
        from sqlalchemy.exc import IntegrityError

        pt = client.post("/api/parts", json={"model": "TM262"}).json()["asset_id"]
        first = quick(client, "recap", aid=pt)
        other = quick(client, "something else")
        db.add(ProjectAsset(project_id=other, asset_id=pt))
        with pytest.raises(IntegrityError):
            db.flush()
        db.rollback()
        assert project_of(db, pt).asset_id == first

    def test_putting_it_on_another_project_moves_it(self, client, db):
        """Picking a project for a thing already on one can only mean moving it.
        Refusing would leave the older answer standing and say nothing about it."""
        pt = client.post("/api/parts", json={"model": "TM262"}).json()["asset_id"]
        quick(client, "recap", aid=pt)
        second = quick(client, "strip the chassis")
        quick(client, "and the belt", aid=pt, project=second)
        assert project_of(db, pt).asset_id == second

    def test_its_jobs_move_with_it(self, client, db):
        """A job naming a thing that is not on its own project would show on the
        item's page under work it has no part in."""
        pt = client.post("/api/parts", json={"model": "TM262"}).json()["asset_id"]
        quick(client, "recap", aid=pt)
        second = quick(client, "strip the chassis")
        quick(client, "and the belt", aid=pt, project=second)
        moved = db.query(ProjectTask).filter(ProjectTask.asset_id == pt).all()
        assert {t.text for t in moved} == {"recap", "and the belt"}
        assert {t.project_id for t in moved} == {second}

    def test_a_second_note_lands_on_the_project_it_already_has(self, client, db):
        """The box on an item's page asks for no project, and the thing already
        answers the question: a second project about the same thing is the one
        answer that cannot be right."""
        pt = client.post("/api/parts", json={"model": "TM262"}).json()["asset_id"]
        first = quick(client, "recap", aid=pt)
        again = quick(client, "new belt", aid=pt)
        assert again == first
        assert tasks_of(db, first) == ["recap", "new belt"]

    def test_a_note_on_a_thing_with_no_project_raises_one(self, client, db):
        pt = client.post("/api/parts", json={"manufacturer": "Tandon", "model": "TM262"}).json()[
            "asset_id"
        ]
        pid = quick(client, "recap", aid=pt)
        assert project_of(db, pt).asset_id == pid
        assert db.get(Project, pid).name == "Tandon TM262"

    def test_a_job_typed_on_an_item_names_that_item(self, client, db):
        """Which is what lets the item's own page list it."""
        pt = client.post("/api/parts", json={"model": "TM262"}).json()["asset_id"]
        quick(client, "recap\nnew belt", aid=pt)
        assert tasks_against(db, pt) == ["recap", "new belt"]

    def test_a_job_with_no_item_names_none(self, client, db):
        pid = quick(client, "order the caps")
        assert db.query(ProjectTask).filter(ProjectTask.project_id == pid).one().asset_id is None


class TestAJobMayNameAThing:
    def test_it_may_name_one_the_project_holds(self, client, db):
        pt = client.post("/api/parts", json={"model": "TM262"}).json()["asset_id"]
        pid = quick(client, "recap", aid=pt)
        r = client.post(f"/api/projects/{pid}/tasks", json={"text": "new belt", "asset_id": pt})
        assert r.status_code == 200, r.text
        assert r.json()["asset_id"] == pt

    def test_it_may_name_nothing(self, client, db):
        """Most of a project's list is about the project -- 'order the caps',
        'find a service manual' -- and a column that insisted would make those lie."""
        pid = quick(client, "recap")
        r = client.post(f"/api/projects/{pid}/tasks", json={"text": "order the caps"})
        assert r.status_code == 200 and r.json()["asset_id"] is None

    def test_it_may_not_name_something_the_project_is_not_about(self, client, db):
        """That row would surface on the item's page under work it has no part in,
        which is worse than no link at all."""
        pid = quick(client, "recap")
        other = client.post("/api/parts", json={"model": "X"}).json()["asset_id"]
        r = client.post(f"/api/projects/{pid}/tasks", json={"text": "new belt", "asset_id": other})
        assert r.status_code == 422

    def test_an_item_lists_its_own_jobs_and_not_the_projects_others(self, client, db):
        pt = client.post("/api/parts", json={"model": "TM262"}).json()["asset_id"]
        pid = quick(client, "recap", aid=pt)
        client.post(f"/api/projects/{pid}/tasks", json={"text": "order the caps"})
        assert tasks_against(db, pt) == ["recap"]
        assert tasks_of(db, pid) == ["recap", "order the caps"]


class TestWhenTheThingGoesAway:
    def test_its_jobs_are_kept_but_lose_the_name(self, client, db):
        """'Recap the PSU' was work somebody planned and may have done, and it
        belongs to the project's record of itself. The thing going away does not
        unmake it; it loses the link, which is all that was ever true about it."""
        pt = client.post("/api/parts", json={"model": "TM262"}).json()["asset_id"]
        pid = quick(client, "recap", aid=pt)
        assert client.delete(f"/api/parts/{pt}").status_code in (200, 204)
        db.expire_all()
        assert tasks_of(db, pid) == ["recap"]
        assert tasks_against(db, pt) == []


class TestKeepingTheEarliestMembership:
    """Migration 0037's one decision, on its own: once the constraint is on, the
    database will not hold a duplicate for a test to resolve."""

    def rule(self):
        import importlib.util
        from pathlib import Path

        path = (
            Path(__file__).resolve().parent.parent
            / "migrations"
            / "versions"
            / "0037_one_project_to_a_thing.py"
        )
        spec = importlib.util.spec_from_file_location("m0037", path)
        mod = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(mod)
        return mod.extras

    def test_a_thing_on_one_project_is_left_alone(self):
        assert self.rule()([(1, "RH-P1", "RH-A")]) == []

    def test_the_earliest_is_kept_and_the_rest_dropped(self):
        rows = [(1, "RH-P1", "RH-A"), (5, "RH-P2", "RH-A"), (9, "RH-P3", "RH-A")]
        assert self.rule()(rows) == [(5, "RH-P2", "RH-A"), (9, "RH-P3", "RH-A")]

    def test_things_do_not_interfere_with_each_other(self):
        rows = [(1, "RH-P1", "RH-A"), (2, "RH-P1", "RH-B"), (3, "RH-P2", "RH-B")]
        assert self.rule()(rows) == [(3, "RH-P2", "RH-B")]

    def test_nothing_at_all_is_nothing_to_do(self):
        assert self.rule()([]) == []


class TestAPrivateProjectsJobsAreNotOnTheItemPage:
    """The sixth door. The panel showing jobs rather than project names moved what
    a private project is hiding: the name was the leak before, the jobs are now."""

    def test_a_visitor_sees_neither_the_name_nor_the_jobs(self, client, db, monkeypatch):
        pt = client.post("/api/parts", json={"model": "TM262"}).json()["asset_id"]
        hidden(client, "the RIFA went bang", aid=pt)
        visitor(client)
        page = client.get(f"/parts/{pt}").text
        assert "the RIFA went bang" not in page
        assert "Hidden" not in page

    def test_the_owner_sees_them(self, client, db):
        pt = client.post("/api/parts", json={"model": "TM262"}).json()["asset_id"]
        hidden(client, "the RIFA went bang", aid=pt)
        assert "the RIFA went bang" in client.get(f"/parts/{pt}").text

    def test_a_public_project_is_shown_to_a_visitor(self, client, db, monkeypatch):
        """The filter is about privacy and not about hiding work in general."""
        pt = client.post("/api/parts", json={"model": "TM262"}).json()["asset_id"]
        quick(client, "needs a belt", aid=pt)
        visitor(client)
        assert "needs a belt" in client.get(f"/parts/{pt}").text


class TestSayingWhatAnExistingJobIsAbout:
    """The jobs written before a job could name anything are the ones that most
    need saying. Without this the only way to attach one is to delete it and type
    it again, which loses the tick and the day it was done."""

    def setup_project(self, client):
        pt = client.post("/api/parts", json={"model": "TM262"}).json()["asset_id"]
        pid = quick(client, "recap", aid=pt)
        tid = client.post(f"/api/projects/{pid}/tasks", json={"text": "test it"}).json()["id"]
        return pt, pid, tid

    def test_the_api_attaches_it(self, client, db):
        pt, pid, tid = self.setup_project(client)
        r = client.patch(f"/api/projects/{pid}/tasks/{tid}", json={"asset_id": pt})
        assert r.status_code == 200 and r.json()["asset_id"] == pt
        assert "test it" in tasks_against(db, pt)

    def test_it_keeps_the_tick_and_the_day(self, client, db):
        """Which is the whole reason this is not delete-and-retype."""
        pt, pid, tid = self.setup_project(client)
        client.patch(f"/api/projects/{pid}/tasks/{tid}", json={"done": True})
        was = client.get(f"/api/projects/{pid}").json()
        done_at = next(t for t in was["tasks"] if t["id"] == tid)["done_at"]
        r = client.patch(f"/api/projects/{pid}/tasks/{tid}", json={"asset_id": pt})
        assert r.json()["done"] is True and r.json()["done_at"] == done_at

    def test_null_detaches_it(self, client, db):
        pt, pid, tid = self.setup_project(client)
        client.patch(f"/api/projects/{pid}/tasks/{tid}", json={"asset_id": pt})
        r = client.patch(f"/api/projects/{pid}/tasks/{tid}", json={"asset_id": None})
        assert r.json()["asset_id"] is None
        assert "test it" not in tasks_against(db, pt)

    def test_leaving_it_out_changes_nothing(self, client, db):
        """exclude_unset: a PATCH that only rewords must not quietly detach."""
        pt, pid, tid = self.setup_project(client)
        client.patch(f"/api/projects/{pid}/tasks/{tid}", json={"asset_id": pt})
        r = client.patch(f"/api/projects/{pid}/tasks/{tid}", json={"text": "test it "})
        assert r.json()["asset_id"] == pt

    def test_it_may_not_name_something_the_project_is_not_about(self, client, db):
        _, pid, tid = self.setup_project(client)
        other = client.post("/api/parts", json={"model": "X"}).json()["asset_id"]
        r = client.patch(f"/api/projects/{pid}/tasks/{tid}", json={"asset_id": other})
        assert r.status_code == 422

    def test_the_form_on_the_project_page_does_it_too(self, client, db):
        pt, pid, tid = self.setup_project(client)
        r = client.post(
            f"/projects/{pid}/task/{tid}/about", data={"asset": pt}, follow_redirects=False
        )
        assert r.status_code == 303
        assert "test it" in tasks_against(db, pt)

    def test_the_form_can_detach_it_as_well(self, client, db):
        pt, pid, tid = self.setup_project(client)
        client.post(f"/projects/{pid}/task/{tid}/about", data={"asset": pt}, follow_redirects=False)
        client.post(f"/projects/{pid}/task/{tid}/about", data={"asset": ""}, follow_redirects=False)
        assert tasks_against(db, pt) == ["recap"]

    def test_the_add_form_can_name_one_on_the_way_in(self, client, db):
        pt, pid, _ = self.setup_project(client)
        client.post(
            f"/projects/{pid}/task", data={"text": "new belt", "asset": pt}, follow_redirects=False
        )
        assert tasks_against(db, pt) == ["recap", "new belt"]


class TestTheProjectsOwnJobsShowOnItsThings:
    """A job naming nothing is a job about the project, and a project is about its
    things -- so it bears on the machine in your hand as much as on the next one."""

    def setup(self, client):
        pt = client.post("/api/parts", json={"model": "TM262"}).json()["asset_id"]
        pid = quick(client, "recap", aid=pt)
        client.post(f"/api/projects/{pid}/tasks", json={"text": "order the caps"})
        return pt, pid

    def test_they_show_beneath_the_things_own(self, client):
        pt, _ = self.setup(client)
        page = client.get(f"/parts/{pt}").text
        assert "recap" in page and "order the caps" in page

    def test_they_are_marked_as_the_projects_and_not_the_things(self, client):
        """Run together they would attribute to a machine something nobody said
        about it."""
        pt, _ = self.setup(client)
        assert "Whole project" in client.get(f"/parts/{pt}").text

    def test_a_job_naming_another_thing_does_not_show(self, client):
        """Inheriting the project's own jobs is not inheriting everybody's."""
        pt, pid = self.setup(client)
        other = client.post("/api/parts", json={"model": "X"}).json()["asset_id"]
        client.post(f"/api/projects/{pid}/items", json={"asset_id": other})
        tid = client.post(
            f"/api/projects/{pid}/tasks", json={"text": "align the heads", "asset_id": other}
        ).json()["id"]
        assert tid
        assert "align the heads" not in client.get(f"/parts/{pt}").text

    def test_they_show_on_every_thing_the_project_is_about(self, client):
        _, pid = self.setup(client)
        other = client.post("/api/parts", json={"model": "X"}).json()["asset_id"]
        client.post(f"/api/projects/{pid}/items", json={"asset_id": other})
        assert "order the caps" in client.get(f"/parts/{other}").text

    def test_a_private_projects_are_not_inherited_by_a_visitor(self, client, monkeypatch):
        """project_for withholds the project, so there is none to take jobs from."""
        pt = client.post("/api/parts", json={"model": "TM262"}).json()["asset_id"]
        pid = hidden(client, "the RIFA went bang", aid=pt)
        client.post(f"/api/projects/{pid}/tasks", json={"text": "order the caps"})
        visitor(client)
        page = client.get(f"/parts/{pt}").text
        assert "order the caps" not in page and "the RIFA went bang" not in page


class TestTickingAJobOffFromTheItemPage:
    """A job is shown in two places -- its project's list, and the page of the thing
    it is about. Ticking one where you are standing should leave you there."""

    def setup(self, client):
        pt = client.post("/api/parts", json={"model": "TM262"}).json()["asset_id"]
        pid = quick(client, "recap", aid=pt)
        own = client.get(f"/api/projects/{pid}").json()["tasks"][0]["id"]
        wide = client.post(f"/api/projects/{pid}/tasks", json={"text": "order the caps"}).json()[
            "id"
        ]
        return pt, pid, own, wide

    def test_the_things_own_job_ticks_off(self, client, db):
        pt, pid, own, _ = self.setup(client)
        r = client.post(
            f"/projects/{pid}/task/{own}/toggle",
            data={"next": f"/parts/{pt}"},
            follow_redirects=False,
        )
        assert r.status_code == 303
        assert db.get(ProjectTask, own).done is True

    def test_it_comes_back_to_the_item_page(self, client):
        """Not to the project's. Ticking a job at the bench, looking at the machine,
        used to throw you onto a different page."""
        pt, pid, own, _ = self.setup(client)
        r = client.post(
            f"/projects/{pid}/task/{own}/toggle",
            data={"next": f"/parts/{pt}"},
            follow_redirects=False,
        )
        assert r.headers["location"] == f"/parts/{pt}"

    def test_the_projects_own_job_ticks_off_from_here_too(self, client, db):
        """A job you can read and not tick is one you have to go elsewhere to
        finish, which is the trip this panel exists to save."""
        pt, pid, _, wide = self.setup(client)
        client.post(
            f"/projects/{pid}/task/{wide}/toggle",
            data={"next": f"/parts/{pt}"},
            follow_redirects=False,
        )
        assert db.get(ProjectTask, wide).done is True

    def test_the_item_page_offers_a_tick_for_both_kinds(self, client):
        pt, pid, own, wide = self.setup(client)
        page = client.get(f"/parts/{pt}").text
        assert f"/projects/{pid}/task/{own}/toggle" in page
        assert f"/projects/{pid}/task/{wide}/toggle" in page

    def test_without_a_next_it_still_goes_to_the_project(self, client):
        """The project's own page posts no next, and must keep working."""
        _pt, pid, own, _ = self.setup(client)
        r = client.post(f"/projects/{pid}/task/{own}/toggle", follow_redirects=False)
        assert r.headers["location"] == f"/projects/{pid}"

    def test_it_will_not_be_sent_off_the_site(self, client):
        """_safe_next: the field is on a page, so it is a field somebody can edit."""
        _pt, pid, own, _ = self.setup(client)
        r = client.post(
            f"/projects/{pid}/task/{own}/toggle",
            data={"next": "//evil.example.com/"},
            follow_redirects=False,
        )
        assert r.headers["location"] == "/"

    def test_a_visitor_gets_no_tick(self, client, monkeypatch):
        pt, _pid, _own, _wide = self.setup(client)
        visitor(client)
        assert "/toggle" not in client.get(f"/parts/{pt}").text


class TestWhatAProjectsSharedLinkShows:
    """A project had no picture of its own, so every project posted anywhere looked
    like every other one. It is about things, and those things are photographed."""

    def og_image(self, client, url):
        import re

        m = re.search(r'<meta property="og:image" content="([^"]+)"', client.get(url).text)
        return m.group(1) if m else None

    def test_with_no_items_it_falls_back_to_the_site_card(self, client):
        pid = quick(client, "sort out the RIFA")
        assert "/static/og-image.png" in self.og_image(client, f"/projects/{pid}")

    def test_an_item_with_no_photograph_does_not_supply_one(self, client):
        """detect_images hands back a placeholder for a thing never photographed,
        and a generic outline of a computer reads as a broken image in a share
        preview -- worse than the site's own card."""
        pt = client.post("/api/parts", json={"model": "TM262"}).json()["asset_id"]
        pid = quick(client, "recap", aid=pt)
        assert "/static/og-image.png" in self.og_image(client, f"/projects/{pid}")

    def test_an_items_photograph_becomes_the_card(self, client, tmp_path, monkeypatch):
        # Patched on the module the route reads it from: the project pages bind
        # detect_images into their own globals at import, so patching photos -- or
        # the copy main re-exports -- would leave the real lookup running.
        from app.routers import projects as project_pages

        pt = client.post("/api/parts", json={"model": "TM262"}).json()["asset_id"]
        pid = quick(client, "recap", aid=pt)
        monkeypatch.setattr(
            project_pages, "detect_images", lambda kind, aid: [f"/images/{kind}/{aid}.jpg"]
        )
        assert f"/images/parts/{pt}.jpg" in self.og_image(client, f"/projects/{pid}")

    def test_a_placeholder_is_skipped_for_a_real_photograph_behind_it(self, client, monkeypatch):
        """The first thing with a real photo, not the first thing."""
        a = client.post("/api/parts", json={"model": "A"}).json()["asset_id"]
        b = client.post("/api/parts", json={"model": "B"}).json()["asset_id"]
        pid = quick(client, "recap", aid=a)
        client.post(f"/api/projects/{pid}/items", json={"asset_id": b})
        from app.routers import projects as project_pages

        monkeypatch.setattr(
            project_pages,
            "detect_images",
            lambda kind, aid: (
                ["/static/placeholders/storage.svg"] if aid == a else [f"/images/{kind}/{aid}.jpg"]
            ),
        )
        assert f"/images/parts/{b}.jpg" in self.og_image(client, f"/projects/{pid}")
