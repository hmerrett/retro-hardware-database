"""The settings page: what is kept because somebody prefers it (ADR-0023).

Everything else the register holds is a fact about a machine or a part. These are
the first things it keeps because the owner would rather have them that way, and
they arrive in three places at once -- the environment, the database and the
browser -- which is what most of what follows is about: which of the three wins,
and what the page says when it is not the one being edited.
"""

import pytest

from app import cards, main, photos, settings


def visitor(monkeypatch):
    """Turn the site into what an anonymous reader sees."""
    monkeypatch.setattr(main.auth, "AUTH_ENABLED", True)


def save(client, **fields):
    """Post the form the way the page does, with the defaults for everything the
    caller did not name -- a browser sends the whole form, not one field."""
    data = {"site_name": "", "theme": "system", "search_engines": "1", "watermark": "1"} | {
        k: v for k, v in fields.items() if v is not None
    }
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


class TestSearchEngines:
    def test_a_site_is_listed_by_default(self, client):
        """A catalogue meant to be found wants to be found."""
        assert '<meta name="robots" content="index, follow">' in client.get("/").text

    def test_turning_it_off_tells_every_page_not_to_be_filed(self, client, a_page_of_everything):
        save(client, search_engines=None)
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
        save(client, search_engines=None)
        body = client.get("/robots.txt").text
        assert "Disallow: /\n" not in body
        assert "Allow: /\n" in body

    def test_the_sitemap_stops_being_advertised(self, client):
        """Asking not to be listed while handing over a list of everything to list
        is two answers to one question."""
        assert "Sitemap:" in client.get("/robots.txt").text
        save(client, search_engines=None)
        assert "Sitemap:" not in client.get("/robots.txt").text


class TestPhotographs:
    def test_photographs_are_stamped_by_default(self, client):
        assert settings.on("watermark") is True
        assert photos._is_own_photo("computers/RH-0001.jpg") is True

    def test_turning_it_off_serves_the_photograph_unmarked(self, client):
        """The original on disk was never touched, so there is nothing to undo:
        the mark stops being composited in and what is served is the file."""
        save(client, watermark=None)
        assert photos._is_own_photo("computers/RH-0001.jpg") is False

    def test_a_reference_photograph_is_never_stamped_either_way(self, client):
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

    def test_the_menu_button_is_still_there(self, client):
        """The device's own choice is made where it always was, on any page, and
        goes on overruling the default."""
        save(client, theme="dark")
        assert 'class="js-theme"' in client.get("/").text

    def test_the_page_offers_the_device_its_choice_back(self, client):
        """Handing the choice back is the one thing the menu's theme button cannot
        do -- it only ever flips between the two -- so without this there is no way
        back to following the site's default."""
        assert 'id="theme-clear"' in client.get("/settings").text


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

    def test_the_page_says_which_variable_holds_it(self, client, monkeypatch):
        """A control that will not take an answer has to say why, or it is a bug
        report. This is the same rule ADR-0019 applies to the open site: a state
        that can only be inferred is a state nobody infers."""
        monkeypatch.setenv("RHDB_WATERMARK", "0")
        settings.forget()
        page = client.get("/settings").text
        assert "RHDB_WATERMARK" in page
        # Showing the pinned value, which is off, and refusing to be the control
        # for it: an unticked box that cannot be ticked.
        assert 'name="watermark" disabled' in page.replace('type="checkbox" ', "")

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
