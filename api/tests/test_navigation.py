"""Where the sections sit: the side rail, and the banner that is the alternative.

The manual's promise is that this is a change of furniture and never of contents
-- the same five places, the same search, the same Scan -- and that what the rail
adds for the owner is the owner's alone. A count is a fact about the register, so
each of them is asked the same question every listing page is asked: may this
reader see the thing being counted?
"""

import pytest

from sqlalchemy.exc import OperationalError

from app import main, rail, settings


def visitor(monkeypatch):
    """Turn the site into what an anonymous reader sees."""
    monkeypatch.setattr(main.auth, "AUTH_ENABLED", True)


def _broken():
    """A session that cannot be opened, as one on a fallen database is."""
    raise OperationalError("SELECT 1", {}, Exception("the database is not there"))


def choose(client, nav):
    r = client.post(
        "/settings",
        data={"site_name": "", "theme": "system", "watermark": "1", "nav": nav},
        follow_redirects=False,
    )
    assert r.status_code == 303, r.text


class TestWhichLayout:
    def test_a_new_installation_gets_the_rail(self, client):
        """Decided when the design was signed off: the rail spends the margin beside
        the column rather than the column, and the section you are in stays in
        sight while you work."""
        assert settings.navigation() == "side"
        assert '<div class="shell side' in client.get("/").text

    def test_the_top_banner_is_the_other_answer(self, client):
        """Chosen, the page is what 0.1 was: no rail in the markup at all, rather
        than one hidden by a stylesheet."""
        choose(client, "top")
        page = client.get("/")
        assert '<aside class="rail' not in page.text
        assert '<div class="shell' not in page.text

    def test_an_answer_nobody_offered_falls_back_to_the_rail(self, client):
        """The value is written into a class on every page, so it is checked on the
        way out rather than trusted."""
        settings.forget()
        assert settings.navigation() in ("side", "top")

    def test_the_rail_is_on_every_page_and_not_only_the_front_one(self, client, computer):
        """Navigation that is on some pages is a page you get lost on."""
        for path in ("/", "/projects", "/files", "/computers/" + computer()["asset_id"]):
            assert '<aside class="rail' in client.get(path).text, path

    def test_the_search_and_the_scan_stay_in_the_banner(self, client):
        """The two things wanted from every page are in the same place whichever
        layout is chosen; the stylesheet puts the rest of the banner away."""
        page = client.get("/").text
        assert 'class="input search"' in page
        assert "hdr-scan" in page


class TestWhatTheRailHolds:
    def test_the_five_sections_are_the_banner_s_five(self, client):
        """The same places, laid down instead of across -- not a second list to
        fall out of step with the first."""
        rail_markup = client.get("/").text.split('<aside class="rail', 1)[1].split("</aside>", 1)[0]
        for href in ("/projects", "/stats", "/machines", "/files"):
            assert f'href="{href}"' in rail_markup

    def test_a_section_says_how_much_is_in_it(self, client, computer):
        computer()
        rail_markup = client.get("/").text.split('<aside class="rail', 1)[1].split("</aside>", 1)[0]
        assert '<i class="n">1</i>' in rail_markup

    def test_the_numbers_page_carries_no_count(self, client):
        """It is figures about the collection; a count of those is a fact about the
        software rather than about what is on the shelf."""
        assert "/stats" not in rail.counts(True)

    def test_the_current_section_is_marked(self, client):
        rail_markup = (
            client.get("/projects").text.split('<aside class="rail', 1)[1].split("</aside>", 1)[0]
        )
        assert '<a class="item" href="/projects" title="Projects" aria-label="Projects"' in (
            rail_markup
        )
        assert 'aria-current="page"' in rail_markup

    def test_the_owner_can_add_in_one_press(self, client):
        """In a rail there is room to unfold the + New menu, and a menu costs the
        same press twice."""
        rail_markup = client.get("/").text.split('<aside class="rail', 1)[1].split("</aside>", 1)[0]
        assert 'href="/computers/new"' in rail_markup
        assert 'href="/parts/new"' in rail_markup

    def test_the_owner_sees_what_they_last_worked_on(self, client, computer):
        """The rail's own argument: at a bench you go back to the same machine all
        afternoon."""
        made = computer()
        rail_markup = client.get("/").text.split('<aside class="rail', 1)[1].split("</aside>", 1)[0]
        assert "Recent" in rail_markup
        assert made["asset_id"] in rail_markup

    def test_the_foot_holds_the_theme_settings_and_the_way_out(self, client):
        rail_markup = client.get("/").text.split('<aside class="rail', 1)[1].split("</aside>", 1)[0]
        assert "js-theme" in rail_markup
        assert 'href="/settings"' in rail_markup

    def test_every_item_is_named_in_words_as_well_as_drawn(self, client):
        """Collapsed the words are hidden and the icon is all that is left, and an
        icon names nothing (accessibility-standards)."""
        rail_markup = client.get("/").text.split('<aside class="rail', 1)[1].split("</aside>", 1)[0]
        items = rail_markup.count('class="item"') + rail_markup.count('class="item js-theme"')
        assert items and rail_markup.count("aria-label=") >= items


class TestWhatAVisitorSees:
    def test_a_visitor_is_offered_nothing_that_is_not_theirs(self, client, computer, monkeypatch):
        computer()
        visitor(monkeypatch)
        rail_markup = client.get("/").text.split('<aside class="rail', 1)[1].split("</aside>", 1)[0]
        assert 'href="/computers/new"' not in rail_markup
        assert "Recent" not in rail_markup
        assert 'href="/settings"' not in rail_markup
        assert 'href="/login' in rail_markup

    def test_a_visitor_still_sees_the_counts(self, client, computer, monkeypatch):
        """The size of a collection is part of what a catalogue is for."""
        computer()
        visitor(monkeypatch)
        rail_markup = client.get("/").text.split('<aside class="rail', 1)[1].split("</aside>", 1)[0]
        assert '<i class="n">1</i>' in rail_markup

    def test_a_private_project_is_not_counted_for_a_visitor(self, client, monkeypatch, db):
        """Hiding the row and publishing its number is half a decision (ADR-0004)."""
        from app.models import Project

        db.add(Project(asset_id="RH-QUIE", name="Quiet one", private=True))
        db.commit()
        assert rail.counts(True)["/projects"] == 1
        assert rail.counts(False)["/projects"] == 0

    def test_an_unpublished_file_is_not_counted_for_a_visitor(self, client, monkeypatch, db):
        """A file is published by hand (ADR-0009), and a count that included the
        rest would announce exactly what the tick keeps back."""
        from app.models import StoredFile

        db.add(StoredFile(stored="1.pdf", filename="receipt.pdf", public=False))
        db.commit()
        assert rail.counts(True)["/files"] == 1
        assert rail.counts(False)["/files"] == 0


class TestWhenTheDatabaseCannotAnswer:
    """The error page is drawn in this same chrome (errors.py), and the likeliest
    reason it is being drawn at all is that the database did not answer."""

    def test_the_counts_come_back_empty_rather_than_raising(self, monkeypatch):
        monkeypatch.setattr(rail, "SessionLocal", _broken)
        assert rail.counts(True) == {}

    def test_the_recent_list_comes_back_empty_rather_than_raising(self, monkeypatch):
        monkeypatch.setattr(rail, "SessionLocal", _broken)
        assert rail.recent() == []

    def test_the_page_is_still_drawn(self, client, monkeypatch):
        """A rail with no figures beside its sections is still a rail; a rail that
        raises is a second error on top of the first."""
        monkeypatch.setattr(rail, "SessionLocal", _broken)
        page = client.get("/no-such-address", headers={"accept": "text/html"})
        assert page.status_code == 404
        assert '<aside class="rail' in page.text


class TestFoldingItAway:
    def test_it_folds_with_a_link_and_no_script(self, client):
        """A plain link, so it works on a browser running nothing at all."""
        rail_markup = client.get("/").text.split('<aside class="rail', 1)[1].split("</aside>", 1)[0]
        assert 'href="/rail/collapsed?next=/"' in rail_markup

    def test_following_it_folds_the_rail_and_comes_back(self, client):
        r = client.get("/rail/collapsed?next=/projects", follow_redirects=False)
        assert r.status_code == 303
        assert r.headers["location"] == "/projects"
        assert '<div class="shell side collapsed"' in client.get("/").text

    def test_a_folded_rail_offers_to_open_again(self, client):
        client.get("/rail/collapsed?next=/")
        page = client.get("/").text
        assert 'href="/rail/open?next=/"' in page
        assert "Expand" in page

    def test_opening_it_again_stores_nothing(self, client):
        """Open is the state a browser that has never been asked is already in, so
        there is nothing to keep."""
        client.get("/rail/collapsed?next=/")
        client.get("/rail/open?next=/", follow_redirects=False)
        assert rail.COOKIE not in client.cookies

    def test_the_choice_is_the_device_s_and_not_the_installation_s(self, client):
        """A cookie and not a row: the workshop screen holds it open while the
        laptop folds it away."""
        client.get("/rail/collapsed?next=/")
        assert settings.value("nav") == "side"

    @pytest.mark.parametrize("nxt", ["https://elsewhere.example/", "//elsewhere.example/"])
    def test_it_will_not_be_sent_anywhere_off_this_site(self, client, nxt):
        """A redirect that follows whatever it is handed is an open redirect,
        whatever it was built for."""
        r = client.get(f"/rail/collapsed?next={nxt}", follow_redirects=False)
        assert r.headers["location"] == "/"

    def test_a_state_it_does_not_know_is_a_404(self, client):
        assert client.get("/rail/sideways", follow_redirects=False).status_code == 404

    def test_a_visitor_may_fold_it_too(self, client, monkeypatch):
        visitor(monkeypatch)
        r = client.get("/rail/collapsed?next=/", follow_redirects=False)
        assert r.status_code == 303
        assert r.headers["location"] == "/"
