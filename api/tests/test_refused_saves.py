"""A save the form cannot take (MANUAL: "When a save is refused").

A few boxes take only one shape of answer. Given another, the save is refused
rather than quietly dropping what was typed -- which on an edit used to clear the
value already on file -- and the form comes back with everything as typed, what
there is to fix at the top, and each message under its own box."""

import io

import pytest
from PIL import Image

from app.models import Computer, Part, Project


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
    @pytest.mark.parametrize("bad", ["85", "1e3", "-1988", "19888", "²⁰⁰⁰"])
    def test_a_year_that_is_not_four_digits_is_refused(self, client, db, bad):
        """Superscript digits are among them because Python calls them digits and
        int() does not: that pair used to be a server error rather than a refusal."""
        assert new_computer(client, year=bad).status_code == 400
        assert db.query(Computer).count() == 0

    @pytest.mark.parametrize("bad", ["12.5", "-3", "lots", "²"])
    def test_a_topbench_score_that_is_not_a_whole_number_is_refused(self, client, db, bad):
        assert new_computer(client, topbench=bad).status_code == 400
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
    @pytest.mark.parametrize("field,bad", [("year", "85"), ("acquired_date", "last spring")])
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
