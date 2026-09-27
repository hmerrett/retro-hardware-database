"""A save the form cannot take (MANUAL: "When a save is refused").

A few boxes take only one shape of answer. Given another, the save is refused
rather than quietly dropping what was typed -- which on an edit used to clear the
value already on file -- and the form comes back with everything as typed, what
there is to fix at the top, and each message under its own box."""

import io
import json
import re
from pathlib import Path

import pytest
from PIL import Image

from app.models import Computer, Part, Project

STATIC = Path(__file__).resolve().parents[1] / "app" / "static"


def flat(html):
    return " ".join(html.split())


def new_computer(client, files=None, **fields):
    data = {"manufacturer": "Acme", "model": "Test"} | fields
    return client.post("/computers/new", data=data, files=files, follow_redirects=False)


def new_part(client, **fields):
    data = {"type": "other", "model": "Widget"} | fields
    return client.post("/parts/new", data=data, follow_redirects=False)


def jpeg():
    buf = io.BytesIO()
    Image.new("RGB", (8, 8), "red").save(buf, "JPEG")
    return buf.getvalue()


class TestTheShapesAComputerIsHeldTo:
    @pytest.mark.parametrize(
        "bad",
        ["85", "1e3", "-1988", "19888", "99999", "²⁰⁰⁰", pytest.param("9" * 5000, id="5000 nines")],
    )
    def test_a_year_that_is_not_four_digits_is_refused(self, client, db, bad):
        """Superscript digits are among them because Python calls them digits and
        int() does not; 99999 because it is more than the column holds; and five
        thousand nines because int() will not read that many. Each used to be a
        server error rather than a refusal."""
        assert new_computer(client, year=bad).status_code == 400
        assert db.query(Computer).count() == 0

    @pytest.mark.parametrize("bad", ["12.5", "-3", "lots", "²"])
    def test_a_topbench_score_that_is_not_a_whole_number_is_refused(self, client, db, bad):
        assert new_computer(client, topbench=bad).status_code == 400
        assert db.query(Computer).count() == 0

    def test_a_topbench_score_too_big_to_keep_is_refused(self, client, db):
        """A whole number, but past what the column holds, which was a server error
        rather than a refusal."""
        assert new_computer(client, topbench="99999999999").status_code == 400
        assert db.query(Computer).count() == 0

    @pytest.mark.parametrize("bad", ["31/02/1994", "last spring", "1994-13-01"])
    def test_an_acquired_date_that_is_not_a_date_is_refused(self, client, db, bad):
        assert new_computer(client, acquired_date=bad).status_code == 400
        assert db.query(Computer).count() == 0

    def test_blank_is_always_accepted(self, client):
        r = new_computer(client, year="", topbench="", acquired_date="")
        assert r.status_code == 303

    @pytest.mark.parametrize("date", ["14/03/1994", "1994-03-14"])
    def test_answers_in_the_right_shape_are_saved(self, client, date):
        r = new_computer(client, year="1988", topbench="104", acquired_date=date)
        assert r.status_code == 303
        aid = r.headers["location"].split("/")[2].split("?")[0]
        c = client.get(f"/api/computers/{aid}").json()
        assert (c["year"], c["topbench"], c["acquired_date"]) == (1988, 104, "1994-03-14")

    def test_a_refused_edit_saves_nothing_and_keeps_the_date_on_file(self, client, computer):
        aid = computer(acquired_date="1994-03-14")["asset_id"]
        r = client.post(
            f"/computers/{aid}/edit",
            data={"manufacturer": "Acme", "model": "Changed", "acquired_date": "last spring"},
            follow_redirects=False,
        )
        assert r.status_code == 400
        c = client.get(f"/api/computers/{aid}").json()
        assert (c["model"], c["acquired_date"]) == ("Test", "1994-03-14")


class TestTheComputerFormComesBackAsTyped:
    def test_the_summary_counts_what_to_fix_and_links_each_to_its_box(self, client):
        html = flat(new_computer(client, year="85", topbench="lots").text)
        assert "2 things to fix before this can be saved" in html
        assert '<a href="#year">Year</a> — Needs four digits, like 1988.' in html
        assert '<a href="#topbench">TopBench score</a>' in html

    def test_the_message_sits_under_its_box_tied_to_it(self, client):
        html = flat(new_computer(client, acquired_date="last spring").text)
        assert 'aria-invalid="true" aria-describedby="acquired_date-err"' in html
        assert '<p class="err" id="acquired_date-err">Needs a date, like 14/03/1994.</p>' in html

    def test_the_refused_answer_is_shown_as_it_was_typed(self, client):
        html = flat(new_computer(client, year="85").text)
        assert 'id="year" name="year" value="85"' in html

    def test_everything_else_typed_is_kept(self, client):
        html = flat(
            new_computer(
                client,
                year="85",
                model="Deskpro 386",
                serial="SN-4471",
                notes="Smells of the loft",
                **{"rammod:30p1m": "4", "drive0_model": "ST-225"},
                mach_model="zx-spectrum-48k",
                work_needed="recap",
            ).text
        )
        assert 'value="Deskpro 386"' in html
        assert 'value="SN-4471"' in html
        assert ">Smells of the loft</textarea>" in html
        assert 'name="rammod:30p1m" value="4"' in html
        assert 'name="drive0_model" value="ST-225"' in html
        assert 'value="zx-spectrum-48k" selected' in html
        assert ">recap</textarea>" in html

    def test_the_project_picked_for_the_work_is_still_picked(self, client):
        pid = client.post("/api/projects", json={"name": "Spring clean"}).json()["asset_id"]
        html = flat(new_computer(client, year="85", work_needed="recap", work_project=pid).text)
        assert f'<option value="{pid}" selected>' in html

    def test_a_new_machine_is_still_a_new_machine(self, client):
        html = flat(new_computer(client, year="85").text)
        assert 'action="/computers/new"' in html
        assert '<h1 class="heading">New computer</h1>' in html

    def test_an_edit_still_posts_to_its_own_machine(self, client, computer):
        aid = computer()["asset_id"]
        r = client.post(
            f"/computers/{aid}/edit",
            data={"manufacturer": "Acme", "model": "Test", "year": "85"},
            follow_redirects=False,
        )
        assert f'action="/computers/{aid}/edit"' in r.text

    def test_a_refused_new_machine_raises_no_project(self, client, db):
        new_computer(client, year="85", work_needed="recap")
        assert db.query(Project).count() == 0

    def test_photographs_chosen_are_asked_for_again(self, client, db):
        r = new_computer(client, year="85", files=[("photos", ("front.jpg", jpeg(), "image/jpeg"))])
        assert r.status_code == 400
        assert "Choose them again" in r.text
        assert db.query(Computer).count() == 0

    def test_a_form_nobody_got_wrong_says_nothing_of_it(self, client):
        html = client.get("/computers/new").text
        assert "errsum" not in html
        assert "Choose them again" not in html


class TestAPartIsHeldToTheSameShapes:
    @pytest.mark.parametrize(
        "field,bad", [("year", "85"), ("year", "99999"), ("acquired_date", "last spring")]
    )
    def test_a_year_or_date_in_the_wrong_shape_is_refused(self, client, db, field, bad):
        r = new_part(client, **{field: bad})
        assert r.status_code == 400
        assert db.query(Part).count() == 0
        assert f'<a href="#{field}">' in r.text

    def test_a_refused_edit_saves_nothing(self, client, part):
        aid = part()["asset_id"]
        r = client.post(
            f"/parts/{aid}/edit",
            data={"type": "other", "model": "Changed", "year": "85"},
            follow_redirects=False,
        )
        assert r.status_code == 400
        assert client.get(f"/api/parts/{aid}").json()["model"] == "Widget"
        assert f'action="/parts/{aid}/edit"' in r.text

    def test_a_storage_part_without_an_interface_comes_back_as_the_form(self, client, db):
        r = new_part(client, type="storage", kind="Hard disk", model="ST-225", spec_interface="")
        assert r.status_code == 400
        assert db.query(Part).count() == 0
        html = flat(r.text)
        assert '<a href="#spec_interface">Interface</a>' in html
        assert 'id="spec_interface-err"' in html
        assert 'value="ST-225"' in html
        assert 'action="/parts/new"' in html

    def test_the_interface_link_has_somewhere_to_land(self, client):
        html = flat(new_part(client, type="storage", kind="Hard disk", spec_interface="").text)
        assert 'id="spec_interface"' in html


def island(html):
    """What the part form's script is told: the data island beside the form."""
    found = re.search(
        r'<script type="application/json" id="part-form-data">(.*?)</script>', html, re.S
    )
    assert found, "the part form has no data island"
    return json.loads(found.group(1))


class TestARefusedNewPartKeepsItsPlace:
    """A refused form is drawn from the part the save wrote and then rolled back. The
    form's script took that part for one that exists: a drive for a machine stopped
    being routed to its drives, and the Type menu saw nothing typed and fetched the
    form again from an address that no longer said which machine it was for."""

    def test_a_refused_new_drive_for_a_machine_still_goes_to_its_drives(self, client, computer):
        cid = computer()["asset_id"]
        r = new_part(client, type="storage", kind="Hard disk", computer_id=cid, year="88")
        assert r.status_code == 400
        assert island(r.text)["routes"] is True

    def test_so_does_a_part_started_from_another_for_a_machine(self, client, computer, part):
        cid, source = computer()["asset_id"], part(type="storage")["asset_id"]
        html = client.get(f"/parts/new?from={source}&computer_id={cid}").text
        assert island(html)["routes"] is True

    def test_an_edit_is_never_routed(self, client, computer, part):
        cid = computer()["asset_id"]
        aid = part(type="storage", computer_id=cid)["asset_id"]
        assert island(client.get(f"/parts/{aid}/edit").text)["routes"] is False

    def test_the_type_menu_is_told_the_form_was_refused(self, client):
        assert island(new_part(client, year="88").text)["refused"] is True
        assert island(client.get("/parts/new").text)["refused"] is False

    def test_the_type_menu_asks_on_a_refused_form_and_keeps_the_machine(self):
        """The rest is the script's, read from it as the stylesheet tests read CSS:
        a refused form counts as typed in, and the form fetched again takes the
        machine or part from the form's own boxes when the address has none."""
        script = (STATIC / "part-form.js").read_text(encoding="utf-8")
        assert "FORM.refused" in script
        assert re.search(r"\[\s*'computer_id',\s*'parent_id'\s*\]", script)


MODEL = {"computers": Computer, "parts": Part}


def made(kind, computer, part):
    return (computer if kind == "computers" else part)()["asset_id"]


def on_file(db, kind, aid, **values):
    """Put a value on the row the way the register once took it, since the forms
    now refuse a year like 85 and so cannot be what makes one."""
    row = db.get(MODEL[kind], aid)
    for k, v in values.items():
        setattr(row, k, v)
    db.commit()
    return aid


def edit(client, kind, aid, **fields):
    base = {"manufacturer": "Acme", "model": "Test"} if kind == "computers" else {"type": "other"}
    return client.post(f"/{kind}/{aid}/edit", data=base | fields, follow_redirects=False)


class TestWhatIsOnFileIsNeverTheReason:
    """The register did not always hold Year to four digits, so an older record can
    say 85 -- and its form puts the 85 back in the box, so every save of it, of
    anything, was refused until somebody noticed the year."""

    @pytest.mark.parametrize("kind", ["computers", "parts"])
    @pytest.mark.parametrize("year", [85, 0])
    def test_its_form_shows_the_year_as_it_is(self, client, db, computer, part, kind, year):
        aid = on_file(db, kind, made(kind, computer, part), year=year)
        html = flat(client.get(f"/{kind}/{aid}/edit").text)
        assert f'id="year" name="year" value="{year}"' in html

    @pytest.mark.parametrize("year", [85, 0])
    def test_a_machine_with_a_short_year_on_file_saves_a_change_to_something_else(
        self, client, db, computer, year
    ):
        aid = on_file(db, "computers", computer()["asset_id"], year=year)
        r = edit(client, "computers", aid, model="Changed", year=str(year))
        assert r.status_code == 303
        c = client.get(f"/api/computers/{aid}").json()
        assert (c["model"], c["year"]) == ("Changed", year)

    def test_so_does_a_part(self, client, db, part):
        aid = on_file(db, "parts", part()["asset_id"], year=85)
        assert edit(client, "parts", aid, model="Changed", year="85").status_code == 303
        p = client.get(f"/api/parts/{aid}").json()
        assert (p["model"], p["year"]) == ("Changed", 85)

    def test_changing_a_short_year_to_another_is_refused(self, client, db, computer):
        aid = on_file(db, "computers", computer()["asset_id"], year=85)
        assert edit(client, "computers", aid, year="86").status_code == 400
        assert client.get(f"/api/computers/{aid}").json()["year"] == 85

    def test_changing_it_to_the_year_in_full_saves_it_and_the_history_says_so(
        self, client, db, computer
    ):
        aid = on_file(db, "computers", computer()["asset_id"], year=85)
        assert edit(client, "computers", aid, year="1985").status_code == 303
        assert client.get(f"/api/computers/{aid}").json()["year"] == 1985
        messages = [e["message"] for e in client.get(f"/api/items/{aid}/log").json()]
        assert any("year: 85 → 1985" in m for m in messages)

    def test_a_topbench_score_on_file_is_let_off_the_same_way(self, client, db, computer):
        """The API takes any whole number, a negative one included, and the box is
        hidden on a catalogue machine but still posts: a score like that on file
        blocked every save with a message under a box nobody could see."""
        aid = on_file(db, "computers", computer()["asset_id"], topbench=-1)
        assert edit(client, "computers", aid, model="Changed", topbench="-1").status_code == 303
        c = client.get(f"/api/computers/{aid}").json()
        assert (c["model"], c["topbench"]) == ("Changed", -1)

    def test_a_part_started_from_one_with_a_short_year_is_asked_for_the_year_in_full(
        self, client, db, part
    ):
        """A new part has nothing on file, whatever it was started from."""
        src = on_file(db, "parts", part()["asset_id"], year=85)
        assert 'id="year" name="year" value="85"' in flat(client.get(f"/parts/new?from={src}").text)
        assert new_part(client, year="85").status_code == 400
        assert db.query(Part).count() == 1

    def test_a_year_padded_to_four_digits_is_refused(self, client, db):
        assert new_computer(client, year="0085").status_code == 400
        assert db.query(Computer).count() == 0

    @pytest.mark.parametrize("kind", ["computers", "parts"])
    def test_the_year_box_says_when_the_year_on_file_is_short(
        self, client, db, computer, part, kind
    ):
        aid = on_file(db, kind, made(kind, computer, part), year=85)
        html = flat(client.get(f"/{kind}/{aid}/edit").text)
        assert 'name="year" value="85" aria-describedby="year-hint"' in html
        assert (
            '<p class="hint" id="year-hint">'
            "On file as 85. Type the year in full when you know it.</p>"
        ) in html

    @pytest.mark.parametrize("kind", ["computers", "parts"])
    @pytest.mark.parametrize("year", [1985, None])
    def test_a_year_in_full_says_nothing_under_the_box(
        self, client, db, computer, part, kind, year
    ):
        aid = on_file(db, kind, made(kind, computer, part), year=year)
        assert 'id="year-hint"' not in client.get(f"/{kind}/{aid}/edit").text

    @pytest.mark.parametrize("kind", ["computers", "parts"])
    def test_a_refused_form_names_the_year_on_file_not_the_one_typed(
        self, client, db, computer, part, kind
    ):
        """The refused form is drawn from the row the save has just written, which
        by then holds the 86."""
        aid = on_file(db, kind, made(kind, computer, part), year=85)
        html = flat(edit(client, kind, aid, year="86").text)
        assert "On file as 85." in html
        assert "On file as 86." not in html
        new = (
            new_computer(client, year="85") if kind == "computers" else new_part(client, year="85")
        )
        html = flat(new.text)
        assert 'id="year-err"' in html
        assert 'id="year-hint"' not in html


def new_project(client, **fields):
    data = {"name": "Recap the +2A", "items_listed": "1"} | fields
    return client.post("/projects/new", data=data, follow_redirects=False)


class TestAProjectIsRefusedTheSameWay:
    def test_one_with_no_name_is_told_so_under_the_name_box(self, client, db):
        r = new_project(client, name="  ")
        assert r.status_code == 400
        assert db.query(Project).count() == 0
        html = flat(r.text)
        assert '<a href="#name">Name</a>' in html
        assert 'id="name-err"' in html
        # The banner is for a save that failed for a reason that is not the owner's.
        assert "Not saved" not in html

    @pytest.mark.parametrize("field", ["started_at", "target_date", "finished_at"])
    def test_a_date_that_is_not_a_date_is_refused(self, client, db, field):
        r = new_project(client, **{field: "last spring"})
        assert r.status_code == 400
        assert db.query(Project).count() == 0
        assert f'<a href="#{field}">' in r.text

    def test_the_refused_date_is_shown_as_it_was_typed(self, client):
        html = flat(new_project(client, started_at="last spring").text)
        assert 'id="started_at" name="started_at" value="last spring"' in html

    def test_a_refused_edit_saves_nothing_and_keeps_the_date_on_file(self, client):
        pid = client.post(
            "/api/projects", json={"name": "Recap the +2A", "started_at": "2026-03-14"}
        ).json()["asset_id"]
        r = client.post(
            f"/projects/{pid}/edit",
            data={"name": "Changed", "started_at": "last spring"},
            follow_redirects=False,
        )
        assert r.status_code == 400
        p = client.get(f"/api/projects/{pid}").json()
        assert (p["name"], p["started_at"]) == ("Recap the +2A", "2026-03-14")
        assert f'action="/projects/{pid}/edit"' in r.text

    def test_an_item_it_cannot_find_left_in_the_box_on_save_is_a_thing_to_fix(self, client, db):
        r = new_project(client, add_item="RH-ZZZZ")
        assert r.status_code == 400
        assert db.query(Project).count() == 0
        assert '<a href="#add_item">' in r.text

    def test_add_item_says_so_under_the_box_and_nothing_else(self, client):
        """Adding to the list saves nothing, so there is nothing yet to refuse --
        not even a name that has not been typed yet."""
        r = new_project(client, name="", add="1", add_item="RH-ZZZZ")
        assert r.status_code == 200
        html = flat(r.text)
        assert 'id="add_item-err"' in html
        assert "errsum" not in html
        assert 'id="name-err"' not in html
