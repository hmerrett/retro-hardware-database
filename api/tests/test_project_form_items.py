"""The things a project is about, on its own form, as MANUAL.md section 12 ("What it
is about") promises: listed with Remove, added by tag or by the whole name of one
thing, nothing changed until Save, a tag left in the box added on Save, a name that
is nothing or two things refused under the box with the rest of the form kept, and
a thing on another project saying which and moving on Save.

Auth is off in these tests, so the client is the owner.
"""

import re

from app.models import ProjectAsset


def make(client, name="Recap the +2A", **fields):
    r = client.post("/projects/new", data={"name": name, **fields}, follow_redirects=False)
    assert r.status_code == 303, r.text
    return r.headers["location"].rsplit("/", 1)[-1]


def put_on(client, aid, item):
    client.post(f"/projects/{aid}/add-item", data={"asset_id": item}, follow_redirects=False)


def on(db, aid):
    return sorted(
        a for (a,) in db.query(ProjectAsset.asset_id).filter(ProjectAsset.project_id == aid)
    )


def items_of(page: str) -> str:
    start = page.index("<legend>Items</legend>")
    return page[start : page.index("</fieldset>", start)]


def listed(page: str) -> list[str]:
    """The tags the form carries, in order: what Save would make the membership."""
    return re.findall(r'<input type="hidden" name="items" value="([^"]+)">', page)


class TestTheList:
    def test_a_new_project_has_an_empty_list_and_the_box(self, client):
        box = items_of(client.get("/projects/new").text)
        assert listed(box) == []
        assert re.search(r'<input class="input"[^>]* id="add_item" name="add_item"', box)
        assert re.search(
            r'<button class="btn" type="submit" name="add" value="1"[^>]*>Add item</button>', box
        )

    def test_editing_lists_what_it_is_about_with_remove(self, client, computer):
        aid, c = make(client), computer(name="Lounge PC")["asset_id"]
        put_on(client, aid, c)
        box = items_of(client.get(f"/projects/{aid}/edit").text)
        assert listed(box) == [c]
        assert f"Lounge PC · {c}" in box
        assert re.search(
            rf'<button class="btn sm" type="submit" name="drop" value="{c}"[^>]*>Remove</button>',
            box,
        )

    def test_save_is_the_forms_default_button(self, client, computer):
        """Enter in any box submits with the first submit button in the form. With a
        Remove ahead of Save, Enter in the name would take the first item off."""
        aid, c = make(client), computer()["asset_id"]
        put_on(client, aid, c)
        page = client.get(f"/projects/{aid}/edit").text
        form = page[page.index('<form class="editform"') :]
        first = re.search(r"<button [^>]*>", form).group(0)
        assert 'type="submit"' in first and "name=" not in first

    def test_the_box_offers_suggestions_as_a_combobox(self, client):
        box = items_of(client.get("/projects/new").text)
        control = re.search(r'<input class="input"[^>]* id="add_item"[^>]*>', box).group(0)
        assert 'role="combobox"' in control and 'aria-expanded="false"' in control
        assert 'data-suggest="pick"' in control
        listbox = re.search(r'aria-controls="([\w-]+)"', control).group(1)
        assert f'id="{listbox}" role="listbox"' in box


class TestAddingBeforeSaving:
    def test_add_item_by_tag_lists_it_and_saves_nothing(self, client, db, computer):
        c = computer(name="Lounge PC")["asset_id"]
        r = client.post(
            "/projects/new",
            data={"name": "Tidy", "summary": "Kept", "add_item": c.lower(), "add": "1"},
            follow_redirects=False,
        )
        assert r.status_code == 200
        assert listed(items_of(r.text)) == [c]
        # The rest of the form comes back as typed, and nothing is made yet.
        assert 'value="Tidy"' in r.text and ">Kept</textarea>" in r.text
        assert db.query(ProjectAsset).count() == 0
        assert re.search(
            r'<input class="input"[^>]* id="add_item" name="add_item" value=""', r.text
        )

    def test_add_item_by_the_whole_name_of_one_thing(self, client, computer, part):
        p = part(manufacturer="Creative", model="Sound Blaster 16")["asset_id"]
        computer(name="Lounge PC")
        r = client.post(
            "/projects/new",
            data={"name": "Tidy", "add_item": "creative sound blaster 16", "add": "1"},
            follow_redirects=False,
        )
        assert listed(items_of(r.text)) == [p]

    def test_a_name_nothing_has_is_refused_under_the_box(self, client, computer):
        computer(name="Lounge PC")
        r = client.post(
            "/projects/new",
            data={"name": "Tidy", "add_item": "Lounge", "add": "1"},
            follow_redirects=False,
        )
        box = items_of(r.text)
        assert listed(box) == []
        assert re.search(
            r'id="add_item" name="add_item" value="Lounge"[^>]* aria-invalid="true"', box
        )
        assert (
            '<p class="err" id="add_item-err">Nothing in the register has that tag or name' in box
        )

    def test_a_name_two_things_share_asks_for_the_tag(self, client, computer):
        computer(name="Lounge PC")
        computer(name="Lounge PC")
        r = client.post(
            "/projects/new",
            data={"name": "Tidy", "add_item": "Lounge PC", "add": "1"},
            follow_redirects=False,
        )
        assert listed(items_of(r.text)) == []
        assert "Two things are called that — add it by its tag" in r.text

    def test_a_project_is_not_something_to_add(self, client):
        other = make(client, "Other")
        r = client.post(
            "/projects/new",
            data={"name": "Tidy", "add_item": other, "add": "1"},
            follow_redirects=False,
        )
        assert listed(items_of(r.text)) == []
        assert "is a project; a project is about computers and parts" in r.text

    def test_adding_what_is_already_listed_lists_it_once(self, client, computer):
        c = computer()["asset_id"]
        r = client.post(
            "/projects/new",
            data={"name": "Tidy", "items": c, "add_item": c, "add": "1"},
            follow_redirects=False,
        )
        assert listed(items_of(r.text)) == [c]

    def test_remove_takes_it_off_the_list_and_saves_nothing(self, client, db, computer):
        aid = make(client)
        a, b = computer()["asset_id"], computer()["asset_id"]
        put_on(client, aid, a)
        put_on(client, aid, b)
        r = client.post(
            f"/projects/{aid}/edit",
            data={"name": "Recap the +2A", "items": [a, b], "drop": a},
            follow_redirects=False,
        )
        assert r.status_code == 200
        assert listed(items_of(r.text)) == [b]
        assert on(db, aid) == sorted([a, b])

    def test_a_thing_on_another_project_says_which(self, client, computer):
        c = computer()["asset_id"]
        other = make(client, "The big rebuild")
        put_on(client, other, c)
        r = client.post(
            "/projects/new",
            data={"name": "Tidy", "add_item": c, "add": "1"},
            follow_redirects=False,
        )
        assert f'moves from <a href="/projects/{other}">The big rebuild</a>' in items_of(r.text)


class TestSaving:
    def test_a_new_project_is_made_with_its_items(self, client, db, computer, part):
        c, p = computer()["asset_id"], part()["asset_id"]
        aid = make(client, "Tidy", items=[c, p])
        assert on(db, aid) == sorted([c, p])
        history = client.get(f"/projects/{aid}").text
        assert history.count("took on") == 2
        assert "wanted for" in client.get(f"/computers/{c}").text

    def test_a_tag_left_in_the_box_is_added_on_save(self, client, db, computer):
        c = computer()["asset_id"]
        aid = make(client, "Tidy", add_item=c)
        assert on(db, aid) == [c]

    def test_a_name_left_in_the_box_that_is_nothing_stops_the_save(self, client, db):
        r = client.post(
            "/projects/new", data={"name": "Tidy", "add_item": "Nothing"}, follow_redirects=False
        )
        # A refusal like any other: one of the things to fix, at the top.
        assert r.status_code == 400
        assert '<a href="#add_item">' in r.text
        assert "Nothing in the register has that tag or name" in r.text
        assert db.query(ProjectAsset).count() == 0

    def test_saving_an_edit_adds_and_removes_the_difference(self, client, db, computer):
        aid = make(client)
        keep, drop, new = (computer()["asset_id"] for _ in range(3))
        put_on(client, aid, keep)
        put_on(client, aid, drop)
        r = client.post(
            f"/projects/{aid}/edit",
            data={"name": "Recap the +2A", "items": [keep, new], "items_listed": "1"},
            follow_redirects=False,
        )
        assert r.status_code == 303
        assert on(db, aid) == sorted([keep, new])
        history = client.get(f"/projects/{aid}").text
        assert "let go of" in history
        assert "no longer wanted for" in client.get(f"/computers/{drop}").text

    def test_saving_untouched_changes_no_membership(self, client, db, computer):
        aid = make(client)
        c = computer()["asset_id"]
        client.post(
            f"/projects/{aid}/add-item",
            data={"asset_id": c, "note": "the patient"},
            follow_redirects=False,
        )
        before = client.get(f"/projects/{aid}").text.count("took on")
        client.post(
            f"/projects/{aid}/edit",
            data={"name": "Recap the +2A", "items": [c], "items_listed": "1"},
            follow_redirects=False,
        )
        # Kept, not re-added: the note beside it survives and no second line is written.
        assert "the patient" in client.get(f"/projects/{aid}").text
        assert client.get(f"/projects/{aid}").text.count("took on") == before

    def test_saving_moves_a_thing_from_another_project(self, client, db, computer):
        c = computer()["asset_id"]
        other = make(client, "The big rebuild")
        put_on(client, other, c)
        aid = make(client, "Tidy", items=[c])
        assert on(db, aid) == [c]
        assert on(db, other) == []

    def test_an_edit_posted_without_the_list_leaves_the_membership_alone(
        self, client, db, computer
    ):
        """A post that never carried the list -- an older page, a script -- says nothing
        about what the project is about, and is not read as "about nothing"."""
        aid, c = make(client), computer()["asset_id"]
        put_on(client, aid, c)
        client.post(f"/projects/{aid}/edit", data={"name": "Renamed"}, follow_redirects=False)
        assert on(db, aid) == [c]

    def test_the_form_says_it_carries_the_list(self, client):
        assert '<input type="hidden" name="items_listed" value="1">' in items_of(
            client.get("/projects/new").text
        )

    def test_cancel_leaves_the_list_as_it_was(self, client, db, computer):
        """Cancel is a link: nothing is posted, so the membership is what it was."""
        aid, c = make(client), computer()["asset_id"]
        put_on(client, aid, c)
        page = client.get(f"/projects/{aid}/edit").text
        assert f'<a class="btn" href="/projects/{aid}">Cancel</a>' in page
        assert on(db, aid) == [c]
