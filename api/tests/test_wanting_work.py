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
from app import main
from app.models import Project, ProjectAsset, ProjectTask


def quick(client, job="needs a belt", **extra):
    r = client.post("/projects/quick", data={"job": job, **extra},
                    follow_redirects=False)
    assert r.status_code == 303, r.text
    return r.headers["location"].rsplit("/", 1)[-1]


def visitor(monkeypatch):
    """Nobody logged in. The fixtures run with the login switched off, so the gate
    lets everything through until a test says otherwise."""
    monkeypatch.setattr(main, "AUTH_ENABLED", True)


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
        assert db.query(ProjectAsset).filter(
            ProjectAsset.project_id == aid,
            ProjectAsset.asset_id == pt).count() == 1

    def test_it_is_named_after_the_item_when_you_do_not_name_it(self, client, db,
                                                                part):
        """A project called "Chinon FZ-357A" is at least findable. One called
        nothing is not."""
        pt = part(manufacturer="Chinon", model="FZ-357A")["asset_id"]
        assert db.get(Project, quick(client, "needs a belt",
                                     aid=pt)).name == "Chinon FZ-357A"

    def test_a_name_you_give_it_wins(self, client, db, part):
        pt = part(manufacturer="Chinon", model="FZ-357A")["asset_id"]
        aid = quick(client, "needs a belt", aid=pt, name="Drive belt swap")
        assert db.get(Project, aid).name == "Drive belt swap"

    def test_with_no_item_and_no_name_the_job_names_it(self, client, db):
        assert db.get(Project, quick(client, "sort out the RIFA")).name == \
            "sort out the RIFA"

    def test_it_lands_on_the_project_it_just_made(self, client):
        r = client.post("/projects/quick", data={"job": "a job"},
                        follow_redirects=False)
        assert r.headers["location"].startswith("/projects/RH-")

    def test_a_mistyped_tag_comes_back_to_the_box(self, client, db):
        """A 404 page would lose what was typed, and a mistyped tag is the ordinary
        way to get this wrong."""
        r = client.post("/projects/quick",
                        data={"job": "a job", "aid": "RH-XXXX"},
                        follow_redirects=False)
        assert r.status_code == 400
        assert "RH-XXXX" in r.text
        assert db.query(Project).count() == 0

    def test_the_projects_own_history_records_what_it_took_on(self, client, part):
        pt = part(model="Widget")["asset_id"]
        aid = quick(client, "needs a belt", aid=pt)
        html = client.get(f"/projects/{aid}").text
        assert "took on" in html and "to do: needs a belt" in html

    def test_the_items_history_stays_quiet_while_it_is_private(self, client, part):
        """An item page is public and so is its history, and the history is the part
        of the register nothing rewrites. A line naming a private project there
        would publish the name, and publish it for good."""
        pt = part(model="Widget")["asset_id"]
        quick(client, "needs a belt", aid=pt, name="Hiddenzzz")
        page = client.get(f"/parts/{pt}").text
        assert "wanted for" not in page and "Hiddenzzz" not in page.split(
            "History")[-1]

    def test_the_box_is_on_the_page_for_whoever_is_logged_in(self, client):
        assert "/projects/quick" in client.get("/projects").text

    def test_a_visitor_is_not_offered_it(self, client, monkeypatch):
        visitor(monkeypatch)
        assert "/projects/quick" not in client.get("/projects").text


class TestItIsPrivate:
    """Five doors, and the feature is only private with all five shut."""

    def test_what_the_quick_box_makes_starts_private(self, client, db):
        """A line typed in five seconds has not been considered for publication,
        and the safe default for something unconsidered is that nobody reads it."""
        assert db.get(Project, quick(client, "a job")).private is True

    def test_what_the_form_makes_does_not(self, client, db):
        """The deliberate kind. Filling in a form is the considering."""
        r = client.post("/projects/new", data={"name": "Recap the +2A"},
                        follow_redirects=False)
        aid = r.headers["location"].rsplit("/", 1)[-1]
        assert db.get(Project, aid).private is False

    def test_a_visitor_does_not_see_it_on_the_list(self, client, monkeypatch):
        quick(client, "a private job", name="Hidden")
        client.post("/projects/new", data={"name": "Shown"},
                    follow_redirects=False)
        visitor(monkeypatch)
        html = client.get("/projects").text
        assert "Shown" in html and "Hidden" not in html

    def test_its_own_page_answers_a_visitor_with_a_404(self, client, monkeypatch):
        """Not a 403 and not the login: somebody who guessed the tag should not be
        told there is something there to guess at."""
        aid = quick(client, "a private job")
        visitor(monkeypatch)
        assert client.get(f"/projects/{aid}").status_code == 404

    def test_a_public_project_still_opens(self, client, monkeypatch):
        r = client.post("/projects/new", data={"name": "Shown"},
                        follow_redirects=False)
        aid = r.headers["location"].rsplit("/", 1)[-1]
        visitor(monkeypatch)
        assert client.get(f"/projects/{aid}").status_code == 200

    def test_a_visitors_search_does_not_match_it(self, client, monkeypatch):
        quick(client, "recapzzz", name="Hiddenzzz")
        visitor(monkeypatch)
        # The project's name, not the query: the search box echoes the query back
        # into its own value, so looking for that would find it every time.
        assert "Hiddenzzz" not in client.get("/projects?q=recapzzz").text
        assert client.get("/suggest?q=recapzzz").json()["total"] == 0

    def test_the_same_search_finds_it_for_whoever_is_logged_in(self, client):
        quick(client, "recapzzz")
        assert client.get("/suggest?q=recapzzz").json()["total"] == 1

    def test_the_gallery_does_not_count_it_for_a_visitor(self, client, monkeypatch):
        """The line above the gallery results says how many projects also matched.
        Counting a private one would say there is something there without showing
        it, which is the same leak said as a number."""
        quick(client, "recapzzz", name="Hiddenzzz")
        visitor(monkeypatch)
        note = client.get("/?q=recapzzz").text
        assert "/projects?q=recapzzz" not in note
        assert "Hiddenzzz" not in note

    def test_it_is_not_in_the_sitemap(self, client):
        """The one of the five read by machines rather than people, where a tag is
        an invitation."""
        hidden = quick(client, "a private job")
        shown = client.post("/projects/new", data={"name": "Shown"},
                            follow_redirects=False
                            ).headers["location"].rsplit("/", 1)[-1]
        xml = client.get("/sitemap.xml").text
        assert f"/projects/{shown}</loc>" in xml
        assert hidden not in xml

    def test_it_is_not_named_on_the_page_of_the_machine_it_is_about(
            self, client, part, monkeypatch):
        """An item page is public. Without this, a project kept off the list, out of
        the search and out of the sitemap would name itself on the page of every
        machine it is about -- the whole of what was being kept back, said in the one
        place nobody thought to look."""
        pt = part(model="Widget")["asset_id"]
        quick(client, "needs a belt", aid=pt, name="Hidden")
        assert "Hidden" in client.get(f"/parts/{pt}").text
        visitor(monkeypatch)
        # Nowhere on the page: not the panel, and not the history either.
        assert "Hidden" not in client.get(f"/parts/{pt}").text

    def test_publishing_one_shows_it_everywhere_at_once(self, client, db,
                                                        monkeypatch):
        """Clearing the tick is the act of publishing, and it has to reach all five
        doors -- otherwise it half-publishes, which is worse than either."""
        aid = quick(client, "a job", name="Hidden")
        client.post(f"/projects/{aid}/edit", data={"name": "Hidden"},
                    follow_redirects=False)
        assert db.get(Project, aid).private is False
        visitor(monkeypatch)
        assert client.get(f"/projects/{aid}").status_code == 200
        assert "Hidden" in client.get("/projects").text
        assert aid in client.get("/sitemap.xml").text


class TestPublishingAndWithdrawing:
    """An item's history names a project exactly while that project is public."""

    def test_publishing_writes_the_line_that_was_held_back(self, client, part):
        pt = part(model="Widget")["asset_id"]
        aid = quick(client, "needs a belt", aid=pt, name="Nowpublic")
        assert "wanted for" not in client.get(f"/parts/{pt}").text
        client.post(f"/projects/{aid}/edit", data={"name": "Nowpublic"},
                    follow_redirects=False)
        assert "wanted for Nowpublic" in client.get(f"/parts/{pt}").text

    def test_withdrawing_takes_it_back_out(self, client, part):
        """The one place the register rewrites its own log, and the whole point: a
        name taken out of publication cannot be left behind in the one public place
        it was written."""
        pt = part(model="Widget")["asset_id"]
        r = client.post("/projects/new", data={"name": "Wasopen"},
                        follow_redirects=False)
        aid = r.headers["location"].rsplit("/", 1)[-1]
        client.post(f"/projects/{aid}/add-item", data={"asset_id": pt},
                    follow_redirects=False)
        assert "wanted for Wasopen" in client.get(f"/parts/{pt}").text
        client.post(f"/projects/{aid}/edit",
                    data={"name": "Wasopen", "private": "1"},
                    follow_redirects=False)
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
        p = client.post("/api/projects",
                        json={"name": "X", "private": True}).json()
        assert p["private"] is True
        got = client.patch(f"/api/projects/{p['asset_id']}",
                           json={"private": False}).json()
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
        aid = quick(client, "a job", aid=pt, name="Hiddenzzz")
        written = " ".join(
            m for (m,) in db.query(LogEntry.message).filter(LogEntry.asset_id == pt))
        assert aid not in written and "Hiddenzzz" not in written

    def test_a_private_projects_tag_is_not_on_the_item_page(self, client, part,
                                                            monkeypatch):
        """The tag alone is a disclosure: it says there is something there, and it
        is the one thing needed to try the door."""
        pt = part(model="Widget")["asset_id"]
        aid = quick(client, "a job", aid=pt, name="Hiddenzzz")
        visitor(monkeypatch)
        assert aid not in client.get(f"/parts/{pt}").text
