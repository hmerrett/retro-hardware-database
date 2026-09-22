"""The settings page: what is kept because somebody prefers it (ADR-0023).

Everything else the register holds is a fact about a machine or a part. These are
the first things it keeps because the owner would rather have them that way, and
they arrive in three places at once -- the environment, the database and the
browser -- which is what most of what follows is about: which of the three wins,
and what the page says when it is not the one being edited.
"""

import re
from pathlib import Path

import pytest

from app import cards, main, photos, presets, settings, typefaces

STATIC = Path(__file__).parents[1] / "app" / "static"


def visitor(monkeypatch):
    """Turn the site into what an anonymous reader sees."""
    monkeypatch.setattr(main.auth, "AUTH_ENABLED", True)


def save(client, **fields):
    """Post the form the way the page does, with the defaults for everything the
    caller did not name -- a browser sends the whole form, not one field."""
    data = {
        "site_name": "",
        "theme": "system",
        "watermark": "1",
        # On by default, and a switch reads its silence -- so leaving it out of the
        # form here would have every save in this file turn the location memory off
        # and purge it (ADR-0027), which is not what any of them is about.
        "remember_locations": "1",
    } | {k: v for k, v in fields.items() if v is not None}
    for blank in [k for k, v in fields.items() if v is None]:
        data.pop(blank)
    r = client.post("/settings", data=data, follow_redirects=False)
    assert r.status_code == 303, r.text
    return r


class TestReachingThePage:
    def test_the_page_is_behind_the_login(self, client, monkeypatch):
        """It changes the site rather than reads it, so it goes where the new and
        edit forms go: nowhere a visitor can reach."""
        visitor(monkeypatch)
        r = client.get("/settings", follow_redirects=False)
        assert r.status_code == 303
        assert r.headers["location"].startswith("/login")

    def test_saving_is_behind_the_login_too(self, client, monkeypatch):
        """The gate is on the method as much as the path: a page nobody can open is
        still a page somebody can post to."""
        visitor(monkeypatch)
        r = client.post("/settings", data={"site_name": "Taken over"}, follow_redirects=False)
        assert r.status_code == 303
        assert r.headers["location"].startswith("/login")
        assert settings.value("site_name") == settings.DEFAULT_SITE_NAME

    def test_the_menu_offers_it_to_the_owner(self, client):
        assert '<a href="/settings"' in client.get("/").text

    def test_the_menu_does_not_offer_it_to_a_visitor(self, client, monkeypatch):
        """A link to a page that answers with the login is an invitation to a door
        that is not yours, and it is how the traffic link and the shortlist are
        already handled."""
        visitor(monkeypatch)
        assert '<a href="/settings"' not in client.get("/").text

    def test_a_phone_is_offered_it_as_well(self, client):
        """A control the desktop menu has and the phone's More sheet does not is a
        control that does not exist on half the devices the register is used from,
        and the sheet is where a phone looks for all of this."""
        page = client.get("/").text
        assert page.count('<a href="/settings"') == 2


class TestWhatTheSiteIsCalled:
    def test_it_starts_as_the_name_the_software_ships_with(self, client):
        assert settings.value("site_name") == "Retro Hardware Database"

    def test_the_name_reaches_the_banner_the_tab_and_the_foot_of_the_page(self, client):
        save(client, site_name="Henry's shelf")
        page = client.get("/").text
        assert "<title>Henry&#39;s shelf</title>" in page
        assert page.count("Henry&#39;s shelf") >= 3
        assert "Retro Hardware Database" not in page

    def test_the_name_reaches_a_shared_link(self, client, computer):
        """What a link unfolds into in a chat window is the site introducing itself
        to somebody who has never seen it."""
        save(client, site_name="Henry's shelf")
        page = client.get("/computers/" + computer()["asset_id"]).text
        assert '<meta property="og:site_name" content="Henry&#39;s shelf">' in page

    def test_an_empty_name_goes_back_to_the_shipped_one(self, client):
        """Blank is not a name, and a site with no name in its banner is a site
        that looks broken rather than one that looks unnamed."""
        save(client, site_name="Henry's shelf")
        save(client, site_name="   ")
        assert settings.value("site_name") == "Retro Hardware Database"

    def test_the_api_documentation_keeps_the_software_s_name(self, client):
        """The installation is renamed; the software is not. /docs describes the
        Retro Hardware Database wherever it is running."""
        save(client, site_name="Henry's shelf")
        assert client.get("/openapi.json").json()["info"]["title"] == "Retro Hardware Database API"


class TestTheLook:
    """The preset: the one setting that dresses the whole installation rather than
    telling it a fact about itself (ADR-0028)."""

    def test_the_looks_offered_are_the_ones_there_is_a_stylesheet_for(self, client):
        """The page reads the design data rather than a list of its own, so it
        cannot come to offer a look nobody generated a stylesheet for -- which
        would be a face that paints the site in the default and says nothing."""
        page = client.get("/settings").text
        offered = re.findall(r'<input type="radio" name="preset" value="([^"]+)"', page)
        assert offered == list(presets.IDS)
        assert len(offered) == 7
        for name in offered:
            assert presets.NAMES[name] in page
            if name != presets.DEFAULT:
                assert (STATIC / "css" / "presets" / f"{name}.css").is_file()

    def test_a_site_wears_the_default_look_and_says_nothing(self, client):
        """No attribute, and no second stylesheet fetched to say what the tokens
        already say: the default preset is what tokens.css declares on :root."""
        page = client.get("/").text
        assert '<html lang="en">' in page
        assert "/static/css/presets/" not in page

    @pytest.mark.parametrize("chosen", [p for p in presets.IDS if p != presets.DEFAULT])
    def test_a_chosen_look_is_on_the_page_before_it_is_painted(self, client, chosen):
        """Server-rendered like the theme beside it, and for the same reason: a look
        applied after paint is the wrong colours flashing on every page."""
        save(client, preset=chosen)
        page = client.get("/").text
        assert f'<html lang="en" data-preset="{chosen}">' in page
        assert f"/static/css/presets/{chosen}.css" in page

    def test_the_look_and_the_theme_are_two_answers_and_not_one(self, client):
        """The preset says which pair of looks; the theme says which of the two. A
        page carries both, and neither displaces the other."""
        save(client, preset="phosphor", theme="dark")
        assert '<html lang="en" data-preset="phosphor" data-theme="dark">' in client.get("/").text

    def test_a_face_shows_both_a_light_and_a_dark_half(self, client):
        """A preset is two sets of colours and the reader's device picks between
        them, so a face showing one of them is a promise about half the site."""
        page = client.get("/settings").text
        for name in presets.IDS:
            for mode in ("light", "dark"):
                assert f'data-preset="{name}" data-theme="{mode}"' in page

    def test_the_chosen_face_says_so_in_words(self, client):
        """An outline is a colour, and somebody who cannot see the outline is left
        guessing which of seven is on -- so the answer is also written down."""
        save(client, preset="amber")
        page = client.get("/settings").text
        chosen = page.split('value="amber" checked', 1)[1].split("</label>", 1)[0]
        assert "Chosen" in chosen
        assert page.count("Chosen") == len(presets.IDS)

    def test_the_faces_are_one_group_of_radios(self, client):
        """Radios and not buttons: it posts with no script, it is one stop for the
        Tab key, and the arrow keys move the choice, all of which come free from
        the control the browser already has (accessibility-standards)."""
        page = client.get("/settings").text
        assert page.count('<input type="radio" name="preset"') == len(presets.IDS)
        assert page.count('name="preset"') == len(presets.IDS)

    def test_the_input_is_hidden_without_being_taken_off_the_page(self, client):
        """`display: none` would take the radios out of the tab order and leave the
        picker reachable by the mouse alone. They are painted over instead, and
        draw their own ring when the focus arrives (accessibility-standards)."""
        css = (STATIC / "css" / "components.css").read_text(encoding="utf-8")
        rule = css.split(".swatch-opt input {", 1)[1].split("}", 1)[0]
        assert "opacity: 0" in rule
        assert "display: none" not in rule
        assert ".swatch-opt input:focus-visible + .face { outline:" in css

    def test_a_visitor_is_not_offered_the_look_at_all(self, client, monkeypatch):
        """It is the installation's, not the device's. A visitor's own choice is
        light or dark, which is the theme button and nothing else."""
        save(client, preset="breadbin")
        visitor(monkeypatch)
        page = client.get("/").text
        assert 'data-preset="breadbin"' in page
        assert 'name="preset"' not in page

    def test_a_query_string_cannot_dress_the_site(self, client, monkeypatch):
        """The look comes from the setting and from nowhere a stranger can type."""
        visitor(monkeypatch)
        assert "data-preset" not in client.get("/?preset=phosphor").text

    def test_a_name_the_register_does_not_know_comes_up_in_the_default(
        self, client, db, monkeypatch
    ):
        """The value is spent on a stylesheet's path, so it is checked against what
        exists rather than trusted: a row edited by hand or a variable with a
        typo in it leaves the site in the default look, not in none at all."""
        monkeypatch.setenv("RHDB_PRESET", "../../etc/passwd")
        settings.forget()
        assert settings.preset() == presets.DEFAULT
        page = client.get("/").text
        assert '<html lang="en">' in page
        assert "/static/css/presets/" not in page

    def test_a_pinned_look_is_shown_and_refuses_an_answer(self, client, monkeypatch):
        """Like any other pinned setting: the environment is the deployment
        speaking, and the faces grey rather than take a click that a restart would
        forget."""
        monkeypatch.setenv("RHDB_PRESET", "ninetyfive")
        settings.forget()
        page = client.get("/settings").text
        faces = re.findall(r'<input type="radio" name="preset"[^>]*>', page)
        assert len(faces) == len(presets.IDS)
        assert 'value="ninetyfive" checked' in page
        assert [f for f in faces if "disabled" not in f] == []
        save(client, preset="amber")
        assert settings.preset() == "ninetyfive"


class TestSearchEngines:
    def test_a_site_is_listed_by_default(self, client):
        """A catalogue meant to be found wants to be found, so the box that would
        stop it is the one you have to tick."""
        assert settings.on("block_search_engines") is False
        assert '<meta name="robots" content="index, follow">' in client.get("/").text

    def test_blocking_tells_every_page_not_to_be_filed(self, client, a_page_of_everything):
        save(client, block_search_engines="1")
        for path in a_page_of_everything:
            assert 'name="robots" content="noindex' in client.get(path).text, path

    def test_a_page_that_was_already_private_stays_that_way(self, client, monkeypatch):
        """The login page has said noindex on its own since long before this
        setting, and leaving the setting on must not publish it."""
        visitor(monkeypatch)
        assert 'name="robots" content="noindex' in client.get("/login").text

    def test_the_crawler_is_still_let_in(self, client):
        """A crawler refused entry in robots.txt never reads the page, never sees
        the instruction not to list it, and files the address anyway from whatever
        links to it -- so asking to be left out means letting the crawler in."""
        save(client, block_search_engines="1")
        body = client.get("/robots.txt").text
        assert "Disallow: /\n" not in body
        assert "Allow: /\n" in body

    def test_the_sitemap_stops_being_advertised(self, client):
        """Asking not to be listed while handing over a list of everything to list
        is two answers to one question."""
        assert "Sitemap:" in client.get("/robots.txt").text
        save(client, block_search_engines="1")
        assert "Sitemap:" not in client.get("/robots.txt").text


class TestPhotographs:
    def test_photographs_are_watermarked_by_default(self, client):
        assert settings.on("watermark") is True
        assert photos._is_own_photo("computers/RH-0001.jpg") is True

    def test_turning_it_off_serves_the_photograph_unmarked(self, client):
        """The original on disk was never touched, so there is nothing to undo:
        the mark stops being composited in and what is served is the file."""
        save(client, watermark=None)
        assert photos._is_own_photo("computers/RH-0001.jpg") is False

    def test_a_reference_photograph_is_never_watermarked_either_way(self, client):
        """Marking somebody else's picture would be claiming it."""
        rel = "computers/RH-0001.jpg"
        sidecar = photos._ref_sidecar(rel)
        sidecar.parent.mkdir(parents=True, exist_ok=True)
        sidecar.write_text('{"note": "", "source": ""}', encoding="utf-8")
        try:
            assert photos._is_own_photo(rel) is False
            save(client, watermark=None)
            assert photos._is_own_photo(rel) is False
        finally:
            sidecar.unlink()

    def test_the_montage_is_rebuilt_rather_than_kept_as_it_was(self, client):
        """A share card made of four photographs has the mark composited into it
        too, and it is cached by content -- so the flag has to be part of what
        names the file, or turning it off leaves every card as it was."""
        before = cards._key([])
        save(client, watermark=None)
        assert cards._key([]) != before


class TestTheTheme:
    def test_a_site_follows_the_reader_s_system_by_default(self, client):
        """No attribute on the document element is what lets the stylesheet's
        prefers-color-scheme block decide, which is the rule it is guarded by."""
        assert '<html lang="en">' in client.get("/").text

    @pytest.mark.parametrize("chosen", ["light", "dark"])
    def test_a_chosen_default_is_on_the_page_before_it_is_painted(self, client, chosen):
        """Server-rendered rather than left to the script, because the script that
        reads the browser's own choice runs before paint for exactly this reason: a
        theme applied afterwards is a white flash on every page."""
        save(client, theme=chosen)
        assert f'<html lang="en" data-theme="{chosen}">' in client.get("/").text

    def test_the_default_is_chosen_from_a_menu(self, client):
        """A menu and not a row of buttons, because the list is expected to grow
        and a fourth choice should cost a line rather than a redesign."""
        page = client.get("/settings").text
        assert '<select class="select" id="theme" name="theme">' in page
        # The theme's own three. Counted on that menu rather than on the page, which
        # now holds other menus: the label destination's, whose length is a fact
        # about how many printers are configured rather than about this setting.
        menu = page.split('id="theme" name="theme">', 1)[1].split("</select>", 1)[0]
        assert menu.count("<option value=") == 3
        assert '<option value="system" selected>' in menu

    def test_the_menu_button_is_still_there(self, client):
        """The device's own choice is made where it always was, on any page, and
        goes on overruling the default."""
        save(client, theme="dark")
        assert 'class="js-theme"' in client.get("/").text


class TestSetInTheEnvironment:
    def test_the_environment_wins(self, client, monkeypatch):
        """A deployment that set the variable has said something deliberate, and a
        click that was forgotten at the next restart would be worse than one that
        never happened."""
        monkeypatch.setenv("RHDB_WATERMARK", "0")
        settings.forget()
        assert settings.on("watermark") is False

    def test_saving_cannot_overrule_it(self, client, monkeypatch):
        monkeypatch.setenv("RHDB_WATERMARK", "0")
        settings.forget()
        save(client, watermark="1")
        assert settings.on("watermark") is False

    def test_the_pinned_control_shows_the_value_and_refuses_to_be_changed(
        self, client, monkeypatch
    ):
        """The pinned value is off, so the box is unticked -- and cannot be
        ticked."""
        monkeypatch.setenv("RHDB_WATERMARK", "0")
        settings.forget()
        page = client.get("/settings").text
        assert 'name="watermark" value="1" disabled' in page.replace('type="checkbox" ', "")

    def test_the_page_says_once_what_greyed_means(self, client, monkeypatch):
        """A control that will not take an answer has to say why, or it is a bug
        report -- the same rule ADR-0019 applies to the open site. Once at the foot
        and not on every row: which variable holds which setting is a table in the
        manual, and a page of preferences should not read as a page of
        configuration (interface-text)."""
        monkeypatch.setenv("RHDB_WATERMARK", "0")
        settings.forget()
        page = client.get("/settings").text
        assert "Greyed options are set in <code>.env</code>" in page

    def test_nothing_pinned_says_nothing(self, client):
        """There is no such thing as a greyed option on this installation, so an
        explanation of what one would mean is noise."""
        assert "Greyed options" not in client.get("/settings").text

    def test_unsetting_it_hands_the_setting_back(self, client, monkeypatch):
        """Which is the way out the manual promises: change it where it is set, or
        unset it and the page has it again."""
        monkeypatch.setenv("RHDB_WATERMARK", "0")
        settings.forget()
        monkeypatch.delenv("RHDB_WATERMARK")
        settings.forget()
        assert settings.on("watermark") is True

    def test_an_empty_variable_is_not_a_pin(self, client, monkeypatch):
        """Compose passes `${RHDB_WATERMARK:-}`, so an unset variable arrives as an
        empty string rather than as nothing at all -- which is how a whole stack
        would otherwise come up pinned to a value nobody chose."""
        monkeypatch.setenv("RHDB_WATERMARK", "")
        settings.forget()
        assert settings.pinned(settings.BY_KEY["watermark"]) is None


class TestTheType:
    """Which of the three faces does which of the three jobs.

    The pairings themselves are `test_typefaces.py`; these are the promises the
    page makes about them."""

    def test_the_pairings_offered_are_the_ones_there_are_rules_for(self, client):
        page = client.get("/settings").text
        menu = page.split('id="type" name="type">', 1)[1].split("</select>", 1)[0]
        offered = re.findall(r'<option value="([^"]*)"', menu)
        assert offered == list(typefaces.IDS)

    def test_a_fresh_install_wears_the_preset_s_own_faces(self, client):
        """No attribute, and no stylesheet fetched to say what the preset already
        says."""
        page = client.get("/").text
        assert "data-type=" not in page
        assert "/static/css/type.css" not in page

    @pytest.mark.parametrize("chosen", ["catalogue", "plain", "ledger"])
    def test_a_chosen_pairing_is_on_the_page_before_it_is_painted(self, client, chosen):
        """Server-rendered like the preset and the theme beside it: faces swapped
        after paint are a page that reflows while it is being read."""
        save(client, type=chosen)
        page = client.get("/").text
        assert f'data-type="{chosen}"' in page
        assert "/static/css/type.css?v=" in page

    def test_the_pairing_is_linked_after_the_preset_that_named_the_faces(self, client):
        """Both selectors are a root and an attribute, so the order of the links is
        what decides -- and an owner who asked for Ledger has asked to overrule
        Phosphor's own monospace, not to be overruled by it."""
        save(client, preset="phosphor", type="catalogue")
        page = client.get("/").text
        assert page.index("/static/css/presets/phosphor.css") < page.index("/static/css/type.css")

    def test_a_pairing_nobody_offered_leaves_the_preset_s_faces_standing(self, client):
        """Saved through the form it cannot happen; in a row somebody edited by hand
        it can, and the page is what has to answer for it."""
        save(client, type="blackletter")
        assert settings.typeface() == "preset"


class TestTheButtonText:
    """Capitalised or lower case, and on the controls alone (interface-text).

    0.1 wrote its buttons in lower case and its labels capitalised, on a
    distinction no reader was ever told about; v0.2 capitalises both and keeps the
    quieter voice as an answer rather than as a fork of the templates."""

    def test_a_new_installation_capitalises_its_controls(self, client):
        assert ">Save</button>" in client.get("/settings").text

    def test_lower_case_lowers_the_first_word_of_a_control(self, client):
        """The same button, the other voice. Done as the page is built rather than
        by text-transform, which is what lets the acronyms below survive it."""
        save(client, button_case="lower")
        assert ">save</button>" in client.get("/settings").text

    def test_a_label_a_legend_and_a_heading_keep_their_capitals(self, client):
        """They name a thing rather than ask for an action, and a page that
        lower-cased them would read as a page with a fault."""
        save(client, button_case="lower")
        page = client.get("/settings").text
        assert "<legend>Appearance</legend>" in page
        assert '<label for="site_name">Name</label>' in page
        assert ">Settings</h1>" in page

    def test_an_acronym_keeps_its_capitals_either_way(self, client):
        """`API docs` and `OK` are spelt that way on purpose. A browser's own
        lower-casing cannot tell one from an ordinary word; this can."""
        save(client, button_case="lower")
        page = client.get("/").text
        assert "API docs" in page
        assert "api docs" not in page

    def test_the_case_is_chosen_from_a_menu_of_two(self, client):
        page = client.get("/settings").text
        assert '<select class="select" id="button_case" name="button_case">' in page
        menu = page.split('id="button_case" name="button_case">', 1)[1].split("</select>", 1)[0]
        assert menu.count("<option value=") == 2
        assert '<option value="cap" selected>' in menu

    def test_the_filter_asks_the_setting_on_every_page(self, client):
        """Not read once at import: the page saved a moment ago is the page the next
        render is written in, the way the site's name already is."""
        save(client, button_case="lower")
        assert ">save</button>" in client.get("/settings").text
        save(client, button_case="cap")
        assert ">Save</button>" in client.get("/settings").text


class TestHowThePageReads:
    def test_a_control_says_what_it_is_and_the_reason_is_behind_it(self, client):
        """The rule the whole page is built on: the label is a few words and the
        paragraph that used to sit under it is a tooltip on the row. A page of
        settings each carrying an explanation is a page nobody reads
        (interface-text)."""
        page = client.get("/settings").text
        assert '<label for="site_name">Name</label>' in page
        assert 'class="field" title="In the banner, the browser&#39;s tab' in page

    def test_the_settings_are_grouped_into_named_sections(self, client):
        """A flat list of four is a list; a flat list of fifteen is a search. The
        grouping is on the definitions rather than in the template, so a new
        setting names its section and lands in it."""
        page = client.get("/settings").text
        assert "<legend>Appearance</legend>" in page
        assert "<legend>Server options</legend>" in page
        assert [s for s, _ in settings.grouped()] == ["Appearance", "Labels", "Server options"]

    def test_a_setting_written_out_of_place_joins_its_own_section(self, client):
        """Rather than opening a second fieldset with the same legend, which is what
        filtering per section would do and nothing would have caught."""
        names = [s for s, _ in settings.grouped()]
        assert len(names) == len(set(names))

    def test_every_row_carries_its_reason(self, client):
        """One tooltip per setting, so none of them is the one that was forgotten
        and left a control with nothing behind it."""
        page = client.get("/settings").text
        # One per setting, and one more: what the browser remembers for itself,
        # which is a row on this page without being a setting -- it is kept in the
        # browser and never posted (ADR-0023). The look's is on the group of faces
        # rather than on a row, since the row is the group.
        rows = page.count('class="field" title="') + page.count('class="swatches" title="')
        assert rows == len(settings.DEFINITIONS) + 1


class TestSaving:
    def test_a_saved_setting_survives_the_page(self, client, db):
        """It is in the database and not in the process, which is the difference
        between a preference and a mood."""
        save(client, site_name="Henry's shelf")
        settings.forget()
        assert settings.value("site_name") == "Henry's shelf"

    def test_saving_says_so(self, client):
        r = save(client, site_name="Henry's shelf")
        assert r.headers["location"] == "/settings?saved=1"
        assert "Saved" in client.get("/settings?saved=1").text

    def test_a_setting_is_written_once_rather_than_row_upon_row(self, client, db):
        """A key and a value, not a log. What a setting used to be is not a fact
        the register keeps -- the change log is about the collection."""
        from app.models import Setting

        save(client, site_name="One")
        save(client, site_name="Two")
        rows = db.query(Setting).filter(Setting.name == "site_name").all()
        assert len(rows) == 1
        assert rows[0].value == "Two"

    def test_an_unknown_field_in_the_form_is_ignored(self, client, db):
        """The form is read through the definitions rather than written from, so a
        posted name that is not one of them cannot make a row."""
        from app.models import Setting

        client.post("/settings", data={"site_name": "Kept", "nonsense": "1"})
        assert db.query(Setting).filter(Setting.name == "nonsense").count() == 0

    def test_a_choice_outside_its_list_is_refused(self, client):
        """Every choice on the page comes back as one of the words it was offered,
        and anything else is a form that did not come from the page."""
        client.post("/settings", data={"theme": "chartreuse", "site_name": ""})
        assert settings.value("theme") == "system"
