"""The edit forms, as MANUAL.md sections 5, 8 and 9 promise them: in sections, a
line under a field tied to it, a heading naming what is being edited, Save and
Cancel in a bar at the foot, the drives table scrolling in its own box, and the
bezel drawn as a ladder beside its menus with the colour chart as a table.

Auth is off in these tests, so the client is the owner.
"""

import re

import pytest


def project(client, **fields):
    r = client.post(
        "/projects/new", data={"name": "Recap the +2A"} | fields, follow_redirects=False
    )
    assert r.status_code == 303, r.text
    return r.headers["location"].rsplit("/", 1)[1]


def display(client, **fields):
    """A display part made through its own form, which is what files a bezel."""
    body = {"type": "display", "manufacturer": "Philips", "model": "CM8833"} | fields
    r = client.post("/parts/new", data=body, follow_redirects=False)
    assert r.status_code == 303, r.text
    return r.headers["location"].rsplit("/", 1)[1]


def form_of(page: str) -> str:
    start = page.index('<form class="editform"')
    return page[start : page.index("</form>", start) + len("</form>")]


def bar(page: str) -> str:
    form = form_of(page)
    return form[form.index('<div class="actbar">') :]


@pytest.fixture
def forms(client, computer, part):
    """Every form, new and editing, keyed by kind."""
    cid = computer(name="Lounge PC")["asset_id"]
    pid = part(model="Widget")["asset_id"]
    jid = project(client)
    return {
        "computer new": "/computers/new",
        "computer edit": f"/computers/{cid}/edit",
        "part new": "/parts/new",
        "part edit": f"/parts/{pid}/edit",
        "project new": "/projects/new",
        "project edit": f"/projects/{jid}/edit",
    }


FORMS = pytest.mark.parametrize(
    "which",
    ["computer new", "computer edit", "part new", "part edit", "project new", "project edit"],
)


class TestTheLayout:
    @FORMS
    def test_every_form_is_on_the_v2_components(self, client, forms, which):
        page = client.get(forms[which]).text
        assert '<main id="main" tabindex="-1" class="v2">' in page
        assert '<form class="editform"' in page
        assert '<fieldset class="fieldset">' in form_of(page)

    def test_the_machine_form_is_in_its_sections(self, client, forms):
        legends = re.findall(r"<legend>([^<]+)</legend>", client.get(forms["computer new"]).text)
        assert legends == [
            "Identity",
            "Memory",
            "Drives",
            "Tracking",
            "Description",
            "Work needed",
            "Photographs",
        ]

    def test_photographs_are_only_a_section_on_a_new_machine(self, client, forms):
        assert "<legend>Photographs</legend>" not in client.get(forms["computer edit"]).text

    @FORMS
    def test_there_is_one_heading(self, client, forms, which):
        assert client.get(forms[which]).text.count("<h1") == 1

    def test_editing_a_machine_the_heading_names_it_and_its_tag(self, client, computer):
        aid = computer(name="Lounge PC")["asset_id"]
        page = client.get(f"/computers/{aid}/edit").text
        assert re.search(
            rf'<h1 class="heading">Edit Lounge PC <span class="tag muted">{aid}</span></h1>', page
        )

    def test_editing_a_part_the_heading_names_it_and_its_tag(self, client, part):
        aid = part(manufacturer="Sound Blaster", model="CT1350")["asset_id"]
        page = client.get(f"/parts/{aid}/edit").text
        assert re.search(
            rf'<h1 class="heading">Edit Sound Blaster CT1350 <span class="tag muted">{aid}</span></h1>',
            page,
        )

    def test_a_new_form_says_what_it_makes(self, client):
        assert '<h1 class="heading">New project</h1>' in client.get("/projects/new").text


class TestHints:
    def test_a_line_under_a_field_is_tied_to_it(self, client):
        page = client.get("/computers/new").text
        assert re.search(r'<input[^>]* id="serial"[^>]* aria-describedby="serial-hint"', page)
        assert '<p class="hint" id="serial-hint">as stamped on this machine' in page

    def test_a_field_with_nothing_to_explain_carries_no_description(self, client):
        page = client.get("/computers/new").text
        tag = re.search(r'<input[^>]* id="model"[^>]*>', page).group(0)
        assert "aria-describedby" not in tag

    def test_the_project_forms_explanations_are_tied_too(self, client):
        page = client.get("/projects/new").text
        assert re.search(r'<input[^>]* id="name"[^>]* aria-describedby="name-hint"', page)
        assert re.search(r'<input[^>]* id="private"[^>]* aria-describedby="private-hint"', page)


class TestTheActionBar:
    @FORMS
    def test_save_and_cancel_close_the_form(self, client, forms, which):
        page = client.get(forms[which]).text
        actbar = bar(page)
        assert re.search(r'<button class="btn primary" type="submit">Save</button>', actbar)
        assert re.search(r'<a class="btn" href="[^"]+">Cancel</a>', actbar)
        # Last in the form, so it is what the sticky bar sits at the foot of.
        assert re.search(r"</div>\s*</form>$", actbar)

    @pytest.mark.parametrize(
        "which, back",
        [
            ("computer new", "/"),
            ("part new", "/"),
            ("project new", "/projects"),
        ],
    )
    def test_cancel_on_a_new_form_goes_back_to_the_list(self, client, forms, which, back):
        assert f'<a class="btn" href="{back}">Cancel</a>' in bar(client.get(forms[which]).text)

    @pytest.mark.parametrize("which", ["computer edit", "part edit", "project edit"])
    def test_cancel_when_editing_goes_back_to_the_thing(self, client, forms, which):
        path = forms[which].removesuffix("/edit")
        assert f'<a class="btn" href="{path}">Cancel</a>' in bar(client.get(forms[which]).text)

    def test_cancel_on_a_part_being_added_to_a_machine_goes_back_to_the_machine(
        self, client, computer
    ):
        cid = computer()["asset_id"]
        page = client.get(f"/parts/new?computer_id={cid}&type=video").text
        assert f'<a class="btn" href="/computers/{cid}">Cancel</a>' in bar(page)

    def test_cancel_on_a_part_being_added_to_a_card_goes_back_to_the_card(self, client, part):
        pid = part(type="motherboard")["asset_id"]
        page = client.get(f"/parts/new?parent_id={pid}&type=cpu").text
        assert f'<a class="btn" href="/parts/{pid}">Cancel</a>' in bar(page)


class TestDrivesAndBezels:
    def test_the_drives_table_scrolls_in_its_own_box(self, client):
        page = client.get("/computers/new").text
        assert re.search(r'<div class="hscroll">\s*<table class="table drives">', page)

    def test_nothing_recorded_is_one_hatched_swatch(self, client):
        page = client.get("/parts/new?type=display").text
        cell = re.search(r'<div class="bezel-cell">.*?</div>', page, re.S).group(0)
        assert re.search(r'<span class="bezel sm none" aria-hidden="true"></span>', cell)
        assert 'class="ladder"' not in cell

    def test_a_yellowing_with_no_shade_is_one_swatch_of_pale_plastic(self, client):
        aid = display(client, spec_yellowing="Yellowed")
        page = client.get(f"/parts/{aid}/edit").text
        cell = re.search(r'<div class="bezel-cell">.*?</div>', page, re.S).group(0)
        assert 'class="bezel sm bz-x-yellowed"' in cell
        assert 'class="ladder"' not in cell

    def test_a_chosen_shade_is_a_ladder_with_its_stage_outlined(self, client):
        aid = display(client, spec_colour="Beige", spec_yellowing="Yellowed")
        page = client.get(f"/parts/{aid}/edit").text
        ladder = re.search(r'<span class="ladder"[^>]*>(.*?)</span>\s*<select', page, re.S)
        steps = re.findall(r'class="bezel sm (bz-[\w-]+)( is-chosen)?"', ladder.group(1))
        assert [s for s, _ in steps] == [
            "bz-beige-x",
            "bz-beige-lightly-yellowed",
            "bz-beige-yellowed",
            "bz-beige-heavily-yellowed",
            "bz-beige-browned",
            "bz-beige-unevenly-yellowed",
        ]
        assert [s for s, chosen in steps if chosen] == ["bz-beige-yellowed"]

    def test_the_ladder_is_decoration_beside_the_words(self, client):
        aid = display(client, spec_colour="Beige")
        page = client.get(f"/parts/{aid}/edit").text
        assert '<span class="ladder" aria-hidden="true">' in page

    def test_the_colour_chart_is_shades_down_and_stages_across(self, client):
        page = client.get("/computers/new").text
        chart = re.search(r'<details class="colourchart">.*?</details>', page, re.S).group(0)
        assert re.search(r'<div class="hscroll">\s*<table class="table bezelchart">', chart)
        heads = re.findall(r'<th scope="col">([^<]+)', chart)
        assert heads == [
            "Shade",
            "As made",
            "Lightly yellowed",
            "Yellowed",
            "Heavily yellowed",
            "Browned",
            "Unevenly yellowed",
        ]
        rows = re.findall(r'<th scope="row">([^<]+)', chart)
        assert rows[0] == "Black" and rows[-1] == "Grey-beige" and len(rows) == 9

    def test_the_chart_keeps_what_each_shade_and_stage_looks_like(self, client):
        chart = client.get("/computers/new").text
        assert "a true white, no cream in it" in chart
        assert "plainly yellow, evenly across the bezel" in chart
