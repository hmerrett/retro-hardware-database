"""A save the form cannot take (MANUAL: "When a save is refused").

A few boxes take only one shape of answer. Given another, the save is refused
rather than quietly dropping what was typed -- which on an edit used to clear the
value already on file -- and the form comes back with everything as typed, what
there is to fix at the top, and each message under its own box."""

import io
from html.parser import HTMLParser

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

    def test_photographs_chosen_for_a_new_part_are_asked_for_again(self, client, db):
        r = client.post(
            "/parts/new",
            data={"type": "other", "model": "Widget", "year": "85"},
            files=[("photos", ("front.jpg", jpeg(), "image/jpeg"))],
            follow_redirects=False,
        )
        assert r.status_code == 400
        assert "Choose them again" in r.text
        assert db.query(Part).count() == 0

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


class Controls(HTMLParser):
    """What a browser would send from the form that posts to `action`: each named
    control not switched off, with the value it shows, in page order."""

    def __init__(self, action):
        super().__init__(convert_charrefs=True)
        self.action, self.inside, self.pairs = action, False, []
        self.select = self.textarea = None

    def handle_starttag(self, tag, attrs):
        a = dict(attrs)
        if tag == "form":
            self.inside = a.get("action") == self.action
        elif not self.inside or "disabled" in a:
            return
        elif tag == "input" and a.get("name"):
            kind = (a.get("type") or "text").lower()
            ticked = kind in ("checkbox", "radio")
            if kind in ("submit", "button", "file", "image", "reset") or (
                ticked and "checked" not in a
            ):
                return
            value = a.get("value")
            self.pairs.append((a["name"], ("on" if ticked else "") if value is None else value))
        elif tag == "select" and a.get("name"):
            self.select = [a["name"], None, None]
        elif tag == "option" and self.select is not None:
            if self.select[2] is None:
                self.select[2] = a.get("value") or ""
            if "selected" in a:
                self.select[1] = a.get("value") or ""
        elif tag == "textarea" and a.get("name"):
            self.textarea = [a["name"], ""]

    def handle_data(self, data):
        if self.textarea is not None:
            self.textarea[1] += data

    def handle_endtag(self, tag):
        if tag == "form":
            self.inside = False
        elif tag == "select" and self.select is not None:
            name, picked, first = self.select
            self.pairs.append((name, first if picked is None else picked))
            self.select = None
        elif tag == "textarea" and self.textarea is not None:
            self.pairs.append(tuple(self.textarea))
            self.textarea = None


def controls(html, action):
    reader = Controls(action)
    reader.feed(html)
    return reader.pairs


def send(client, url, pairs):
    data = {}
    for k, v in pairs:
        data.setdefault(k, []).append(v)
    return client.post(url, data=data, follow_redirects=False)


def typed(pairs, **answers):
    return [(k, answers.get(k, v)) for k, v in pairs]


# A part of most types with its specifications filled in, as the register writes
# them. Most ask for them box by box, from a table of their own; a PSU and a
# peripheral in one box.
SPECS = {
    "sound": "Interface: 8-bit ISA",
    "video": "Chip: TVGA8900 | Interface: 16-bit ISA | Memory: 512 KiB",
    "io": "Interface: VLB | Ports: 2× Serial, Game, Floppy, 2× IDE",
    "network": "Chip: Realtek RTL8019AS | Interface: 16-bit ISA",
    "ram": "Type: Parity | Size: 128 KiB",
    "cpu": "Socket: Socket 7 | Speed: 133 MHz | FSB: 66 MHz | Cores: 1 | Cache: 16 KiB",
    "display": 'Type: CRT | Panel: Shadow mask | Screen size: 12" | Aspect: 4:3 | '
    "Resolution: 720×348 (Hercules) | Refresh: 50 Hz | Sync: 18 KHz | "
    "Interface: 9-pin TTL (MDA) | Picture: Green | Colour: Off-white",
    "storage": "Kind: Hard disk | Interface: IDE | Protocol: ATA | Capacity: 515592 KiB | "
    "CHS: 1023/16/63",
    "motherboard": "Chipset: Sirius AR810 | Form factor: Baby AT | Cache: 256 KiB",
    "psu": "Form factor: ATX | Output: 300W",
    "peripheral": "Type: Mouse | Interface: PS/2",
}


class TestAPartComesBackAsTyped:
    """A part's specifications are boxes of their own, written to tables of their
    own, and the refused form is drawn from what the save has just written. A box
    the refused form read back as empty was lost again when the owner put the
    refusal right and saved, as the manual tells them to."""

    @pytest.mark.parametrize("ptype", sorted(SPECS))
    def test_a_refused_edit_comes_back_with_everything_as_typed(self, client, part, ptype):
        aid = part(type=ptype, model="Test", year=1993, specs=SPECS[ptype])["asset_id"]
        url = f"/parts/{aid}/edit"
        sent = typed(controls(client.get(url).text, url), year="88")
        assert any(k.startswith("spec") and v for k, v in sent)
        r = send(client, url, sent)
        assert r.status_code == 400
        assert controls(r.text, url) == sent

    def test_so_does_a_refused_new_part(self, client):
        url = "/parts/new"
        form = controls(client.get("/parts/new?type=sound").text, url)
        assert {"spec_interface", "spec_chip"} <= {k for k, _ in form}
        sent = typed(
            form, model="Sound Blaster", year="88", spec_interface="8-bit ISA", spec_chip="YM3812"
        )
        r = send(client, url, sent)
        assert r.status_code == 400
        assert controls(r.text, url) == sent

    @pytest.mark.parametrize("ptype", sorted(SPECS))
    def test_putting_the_refusal_right_keeps_the_specs(self, client, part, ptype):
        made = part(type=ptype, model="Test", year=1993, specs=SPECS[ptype])
        url = f"/parts/{made['asset_id']}/edit"
        refused = send(client, url, typed(controls(client.get(url).text, url), year="88"))
        r = send(client, url, typed(controls(refused.text, url), year="1993"))
        assert r.status_code == 303
        assert client.get(f"/api/parts/{made['asset_id']}").json()["specs"] == made["specs"]


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
