"""The half of the collection that is a list of intentions.

An item can be flagged as something waiting to be worked on, with a note saying
what needs doing, and /projects gathers them into the one page that is written in
the future tense.

Most of what is worth testing here is that it is private. The register is a public
catalogue with a login over the editing, and a plan is the first thing on it that
is neither -- so a column that would otherwise reach the change log, the search
index and the item's own page by default has to be kept out of all three. The
class below that name is the point of the feature as much as the flag is: three of
those four doors standing shut is a thing that is not private.
"""
import re

from app import main


def flag(client, aid, note="", **extra):
    r = client.post(f"/items/{aid}/project", data={"note": note, **extra},
                    follow_redirects=False)
    assert r.status_code == 303, r.text
    return r


def unflag(client, aid, **extra):
    r = client.post(f"/items/{aid}/unproject", data=extra, follow_redirects=False)
    assert r.status_code == 303, r.text
    return r


def listed(client):
    """The asset tags on the project page, in the order it draws them."""
    return re.findall(r'<a href="/(?:computers|parts)/([A-Z0-9-]+)">\1</a>',
                      client.get("/projects").text)


def visitor(monkeypatch):
    """Nobody logged in. The fixtures run with the login switched off, so the gate
    lets everything through until a test says otherwise."""
    monkeypatch.setattr(main, "AUTH_ENABLED", True)


class TestFlaggingSomething:
    def test_a_machine_joins_the_list_with_its_note(self, client, computer):
        c = computer(model="A500")
        flag(client, c["asset_id"], "recap, one leg already green")
        got = client.get(f"/api/computers/{c['asset_id']}").json()
        assert got["project"] is True
        assert got["project_note"] == "recap, one leg already green"

    def test_a_part_does_too(self, client, part):
        """One route for both kinds, because what is flagged is an asset in the
        shared register rather than a row in one of the two tables."""
        p = part(model="FD-235HF", type="storage")
        flag(client, p["asset_id"], "needs a belt")
        got = client.get(f"/api/parts/{p['asset_id']}").json()
        assert got["project"] is True and got["project_note"] == "needs a belt"

    def test_saving_again_rewrites_the_note(self, client, computer):
        c = computer(model="A500")
        flag(client, c["asset_id"], "recap")
        flag(client, c["asset_id"], "recapped; now the floppy")
        got = client.get(f"/api/computers/{c['asset_id']}").json()
        assert got["project_note"] == "recapped; now the floppy"

    def test_taking_it_off_takes_the_note_with_it(self, client, computer):
        """A plan nobody is following is not worth keeping, and one left behind a
        cleared flag would be silently inherited by the next flagging."""
        c = computer(model="A500")
        flag(client, c["asset_id"], "recap")
        unflag(client, c["asset_id"])
        got = client.get(f"/api/computers/{c['asset_id']}").json()
        assert got["project"] is False and got["project_note"] == ""

    def test_it_lands_back_on_the_item_it_was_done_from(self, client, part):
        p = part(model="FD-235HF")
        r = flag(client, p["asset_id"], "belt")
        assert r.headers["location"] == f"/parts/{p['asset_id']}"

    def test_it_lands_where_it_was_told_to(self, client, part):
        """The same pair of buttons is on the item page and on the list, so where
        it goes back to is whatever the form carried."""
        p = part(model="FD-235HF")
        r = flag(client, p["asset_id"], "belt", next="/projects")
        assert r.headers["location"] == "/projects"

    def test_a_tag_that_is_not_an_asset_is_not_found(self, client):
        assert client.post("/items/ZZ-9999/project", data={"note": "x"}).status_code == 404


class TestTheList:
    def test_it_gathers_machines_and_parts_into_one_queue(self, client, computer,
                                                          part):
        """What is next at the bench is next whether it is a computer or the card
        out of one, so they are one list rather than two."""
        c = computer(model="A500")
        p = part(model="FD-235HF")
        flag(client, c["asset_id"], "recap")
        flag(client, p["asset_id"], "belt")
        assert sorted(listed(client)) == sorted([c["asset_id"], p["asset_id"]])

    def test_what_is_not_flagged_is_not_on_it(self, client, computer):
        computer(model="A500")
        flagged = computer(model="A1200")
        flag(client, flagged["asset_id"], "recap")
        assert listed(client) == [flagged["asset_id"]]

    def test_the_notes_are_on_it(self, client, computer):
        c = computer(model="A500")
        flag(client, c["asset_id"], "recap, one leg already green")
        assert "recap, one leg already green" in client.get("/projects").text

    def test_an_empty_list_says_so(self, client, computer):
        computer(model="A500")
        assert "Nothing is on the list" in client.get("/projects").text

    def test_something_can_be_added_by_its_tag(self, client, part):
        """The other way in: sitting with the list open, remembering the drive in
        the box under the desk."""
        p = part(model="FD-235HF")
        r = client.post("/projects/add",
                        data={"aid": p["asset_id"], "note": "belt"},
                        follow_redirects=False)
        assert r.status_code == 303 and r.headers["location"] == "/projects"
        assert listed(client) == [p["asset_id"]]

    def test_a_tag_is_read_however_it_is_typed(self, client, part):
        p = part(model="FD-235HF")
        client.post("/projects/add", data={"aid": f"  {p['asset_id'].lower()}  "},
                    follow_redirects=False)
        assert listed(client) == [p["asset_id"]]

    def test_a_tag_that_is_not_an_asset_says_so_and_adds_nothing(self, client,
                                                                 computer):
        computer(model="A500")
        r = client.post("/projects/add", data={"aid": "ZZ-9999", "note": "x"})
        assert r.status_code == 400
        assert "ZZ-9999" in r.text and "no item with the tag" in r.text
        assert listed(client) == []

    def test_adding_one_already_on_the_list_keeps_its_note(self, client, part):
        """Typing a tag and nothing else means "this too", not "and forget what it
        said"."""
        p = part(model="FD-235HF")
        flag(client, p["asset_id"], "belt")
        client.post("/projects/add", data={"aid": p["asset_id"], "note": ""},
                    follow_redirects=False)
        got = client.get(f"/api/parts/{p['asset_id']}").json()
        assert got["project_note"] == "belt"


class TestItIsPrivate:
    """Four doors, and the feature is only private with all four shut."""

    def test_a_visitor_is_sent_to_the_login(self, client, monkeypatch):
        visitor(monkeypatch)
        r = client.get("/projects", follow_redirects=False)
        assert r.status_code == 303 and "/login" in r.headers["location"]

    def test_a_visitor_may_not_flag_or_unflag_anything(self, client, computer,
                                                       monkeypatch):
        c = computer(model="A500")
        visitor(monkeypatch)
        for path in (f"/items/{c['asset_id']}/project",
                     f"/items/{c['asset_id']}/unproject", "/projects/add"):
            r = client.post(path, data={}, follow_redirects=False)
            assert r.status_code == 303 and "/login" in r.headers["location"], path

    def test_an_item_page_keeps_the_plan_from_a_visitor(self, client, computer,
                                                        monkeypatch):
        """The item's own page is public. The plan is the one thing on the record
        that is not on it."""
        c = computer(model="A500")
        flag(client, c["asset_id"], "recap, one leg already green")
        visitor(monkeypatch)
        page = client.get(f"/computers/{c['asset_id']}").text
        assert "recap, one leg already green" not in page
        assert "Future project" not in page

    def test_the_same_page_shows_it_to_whoever_is_logged_in(self, client, computer):
        c = computer(model="A500")
        flag(client, c["asset_id"], "recap, one leg already green")
        page = client.get(f"/computers/{c['asset_id']}").text
        assert "recap, one leg already green" in page
        assert "Future project" in page

    def test_a_part_page_is_the_same_both_ways(self, client, part, monkeypatch):
        p = part(model="FD-235HF")
        flag(client, p["asset_id"], "needs a belt")
        assert "needs a belt" in client.get(f"/parts/{p['asset_id']}").text
        visitor(monkeypatch)
        assert "needs a belt" not in client.get(f"/parts/{p['asset_id']}").text

    def test_a_visitors_search_does_not_match_the_note(self, client, computer,
                                                       monkeypatch):
        """The search reads every field of every item, which is what makes "any
        field" true -- and would hand back the private half of the register a word
        at a time if it read these two as well."""
        c = computer(model="A500")
        flag(client, c["asset_id"], "recapzzz")
        visitor(monkeypatch)
        assert c["asset_id"] not in client.get("/?q=recapzzz").text

    def test_the_same_search_finds_it_for_whoever_is_logged_in(self, client,
                                                               computer):
        c = computer(model="A500")
        flag(client, c["asset_id"], "recapzzz")
        assert c["asset_id"] in client.get("/?q=recapzzz").text

    def test_the_suggestion_list_keeps_it_back_too(self, client, computer,
                                                   monkeypatch):
        """The box under the search bar performs the same match as the bar itself,
        so it had to learn the same manners."""
        c = computer(model="A500")
        flag(client, c["asset_id"], "recapzzz")
        assert client.get("/suggest?q=recapzzz").json()["total"] == 1
        visitor(monkeypatch)
        assert client.get("/suggest?q=recapzzz").json()["total"] == 0

    def test_nothing_about_it_reaches_the_history(self, client, computer):
        """The history is shown to anybody who opens the item's page, and is the
        part of the register nothing rewrites -- so a line about the plan would put
        it on the public page for good."""
        c = computer(model="A500")
        flag(client, c["asset_id"], "recap, one leg already green")
        unflag(client, c["asset_id"])
        log = client.get(f"/api/items/{c['asset_id']}/log").json()
        written = " ".join(e["message"] for e in log)
        assert "recap" not in written and "project" not in written

    def test_a_patch_through_the_api_writes_nothing_to_the_history_either(
            self, client, computer):
        """The same rule, at the other door. The diff is taken in one place for
        exactly this reason."""
        c = computer(model="A500")
        client.patch(f"/api/computers/{c['asset_id']}",
                     json={"project": True, "project_note": "recap"})
        log = client.get(f"/api/items/{c['asset_id']}/log").json()
        written = " ".join(e["message"] for e in log)
        assert "recap" not in written and "project" not in written

    def test_an_ordinary_edit_beside_it_is_still_logged(self, client, computer):
        """Only the two columns are kept out of the log, not the change they
        arrived with."""
        c = computer(model="A500")
        client.patch(f"/api/computers/{c['asset_id']}",
                     json={"project": True, "project_note": "recap",
                           "condition": "working"})
        written = " ".join(e["message"] for e in
                           client.get(f"/api/items/{c['asset_id']}/log").json())
        assert "condition" in written and "recap" not in written

    def test_a_visitor_is_not_offered_the_page_in_the_menu(self, client,
                                                           monkeypatch):
        visitor(monkeypatch)
        assert 'href="/projects"' not in client.get("/").text

    def test_whoever_is_logged_in_is(self, client):
        assert 'href="/projects"' in client.get("/").text


class TestADuplicateIsNotASecondPlan:
    def test_a_copied_machine_starts_off_the_list(self, client, computer):
        """A duplicate is a record of a second object, and nobody has looked at that
        one yet -- inheriting the note would assert a fault that has not been seen.
        The same reason the serial and the disposal do not come across."""
        c = computer(model="A500")
        flag(client, c["asset_id"], "recap")
        r = client.post(f"/computers/{c['asset_id']}/duplicate",
                        follow_redirects=False)
        copy = r.headers["location"].rsplit("/", 1)[1]
        got = client.get(f"/api/computers/{copy}").json()
        assert got["project"] is False and got["project_note"] == ""

    def test_a_copied_part_does_too(self, client, part):
        p = part(model="FD-235HF")
        flag(client, p["asset_id"], "belt")
        r = client.post(f"/parts/{p['asset_id']}/duplicate", follow_redirects=False)
        copy = r.headers["location"].rsplit("/", 1)[1]
        got = client.get(f"/api/parts/{copy}").json()
        assert got["project"] is False and got["project_note"] == ""


class TestTheApiCarriesThem:
    """The whole of the API is behind the login, so there they read and write like
    any other pair of columns."""

    def test_a_machine_can_be_created_on_the_list(self, client, computer):
        c = computer(model="A500", project=True, project_note="recap")
        assert c["project"] is True and c["project_note"] == "recap"

    def test_a_part_can_be_patched_onto_it(self, client, part):
        p = part(model="FD-235HF")
        got = client.patch(f"/api/parts/{p['asset_id']}",
                           json={"project": True, "project_note": "belt"}).json()
        assert got["project"] is True and got["project_note"] == "belt"

    def test_an_item_starts_off_the_list(self, client, computer):
        assert computer(model="A500")["project"] is False

    def test_a_patch_that_says_nothing_about_it_leaves_it_alone(self, client,
                                                                computer):
        c = computer(model="A500", project=True, project_note="recap")
        got = client.patch(f"/api/computers/{c['asset_id']}",
                           json={"condition": "working"}).json()
        assert got["project"] is True and got["project_note"] == "recap"


class TestTheEditFormLeavesItAlone:
    def test_saving_the_edit_form_does_not_clear_the_plan(self, client, computer):
        """The form has no box for it, and a field the form does not carry is a
        field the save loop skips -- but the plan is the first column where that
        going wrong would silently throw something away."""
        c = computer(model="A500")
        flag(client, c["asset_id"], "recap")
        r = client.post(f"/computers/{c['asset_id']}/edit",
                        data={"model": "A500", "condition": "working"},
                        follow_redirects=False)
        assert r.status_code == 303
        got = client.get(f"/api/computers/{c['asset_id']}").json()
        assert got["project"] is True and got["project_note"] == "recap"
