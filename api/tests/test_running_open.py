"""The app says which of its two states it came up in (ADR-0019).

Blank credentials make every visitor the owner. That is a supported way to run and
a very easy way to arrive by accident -- a `.env` that did not come across when the
checkout moved gives exactly it -- and the two were byte-identical, so the only
outward sign was the traffic link and the log out button quietly absent from a
menu. Which is how it was found: somebody asked where the traffic page had gone.

`RHDB_OPEN` is the missing bit of information, and these are the four states it
makes possible.
"""
import logging

import pytest

from app import main


@pytest.fixture
def said(caplog):
    """What _announce_auth logs for one pair of flags, and whether it asks for the
    banner. A pure function rather than a side effect at import, so the suite can
    ask it what it says instead of racing it."""
    def ask(enabled, on_purpose):
        caplog.clear()
        with caplog.at_level(logging.INFO, logger=main.log.name):
            banner = main._announce_auth(enabled, on_purpose)
        return banner, caplog.records
    return ask


class TestWhatItSaysAtStartup:

    def test_a_site_with_a_login_says_nothing(self, said):
        """The state nearly every installation is in. It was quiet before and stays
        quiet; a warning everybody sees every start is a warning nobody reads."""
        banner, records = said(enabled=True, on_purpose=False)
        assert banner is False
        assert records == []

    def test_no_credentials_and_no_opt_in_warns(self, said):
        banner, records = said(enabled=False, on_purpose=False)
        assert banner is True
        assert [r.levelno for r in records] == [logging.WARNING]

    def test_the_warning_says_what_is_wrong_and_what_to_set(self, said):
        """It is read by somebody who has just found their site open, so it has to
        carry the consequence and both ways out without them going to look."""
        _banner, records = said(enabled=False, on_purpose=False)
        said_it = records[0].getMessage()
        assert "RHDB_AUTH_USER" in said_it and "RHDB_AUTH_PASSWORD" in said_it
        assert "RHDB_OPEN" in said_it
        assert "edit" in said_it.lower() and "delete" in said_it.lower()

    def test_opting_in_is_said_once_and_calmly(self, said):
        """An operator who has opted in has said what they want. A line saying which
        state the process came up in is still what makes a log worth reading later."""
        banner, records = said(enabled=False, on_purpose=True)
        assert banner is False
        assert [r.levelno for r in records] == [logging.INFO]

    def test_opting_in_while_a_login_is_configured_warns_it_is_doing_nothing(
            self, said):
        """Silently ignoring a variable somebody deliberately set is the same fault
        as the one this whole change is about."""
        banner, records = said(enabled=True, on_purpose=True)
        assert banner is False
        assert [r.levelno for r in records] == [logging.WARNING]
        assert "RHDB_OPEN" in records[0].getMessage()

    def test_nothing_logged_carries_a_credential(self, said, monkeypatch):
        """It names the variables; it must never reach for their values. Enforced by
        putting sentinels in the module's own globals and looking for them: the
        function takes booleans today, and this is what stops somebody making the
        message friendlier by pasting the username into it."""
        monkeypatch.setattr(main, "AUTH_USER", "sentinel-user-9f3a")
        monkeypatch.setattr(main, "AUTH_PASS", "sentinel-pass-2b71")
        for enabled in (True, False):
            for on_purpose in (True, False):
                _banner, records = said(enabled, on_purpose)
                blob = " ".join(r.getMessage() for r in records)
                assert "sentinel-user-9f3a" not in blob
                assert "sentinel-pass-2b71" not in blob


class TestHowItIsRead:

    @pytest.mark.parametrize("value,meant", [
        ("1", True), ("true", True), ("TRUE", True), ("yes", True), ("on", True),
        ("", False), ("0", False), ("false", False), ("no", False), ("off", False),
    ])
    def test_the_opt_in_reads_the_usual_words(self, value, meant, monkeypatch):
        monkeypatch.setenv("RHDB_OPEN", value)
        assert main._open_on_purpose() is meant

    def test_it_is_off_when_unset(self, monkeypatch):
        """Unset means not opted in, which is what makes the loud state the default
        -- a missing .env is far likelier than a deliberate open install."""
        monkeypatch.delenv("RHDB_OPEN", raising=False)
        assert main._open_on_purpose() is False


class TestTheBannerOnThePage:

    def test_the_pages_carry_it_when_the_site_is_open_by_accident(
            self, client, monkeypatch):
        monkeypatch.setitem(main.templates.env.globals, "auth_open_warning", True)
        page = client.get("/").text
        assert "No login" in page
        assert "RHDB_OPEN" in page

    def test_the_pages_do_not_when_it_was_meant(self, client, monkeypatch):
        monkeypatch.setitem(main.templates.env.globals, "auth_open_warning", False)
        page = client.get("/").text
        assert "No login" not in page

    def test_it_is_on_an_item_page_too_and_not_only_the_gallery(
            self, client, part, monkeypatch):
        """Every page, because the pages somebody edits from are the item pages and
        a warning only on the front door is a warning most visits never see."""
        aid = part()["asset_id"]
        monkeypatch.setitem(main.templates.env.globals, "auth_open_warning", True)
        assert "No login" in client.get(f"/parts/{aid}").text

    def test_the_banner_is_the_one_the_stylesheet_already_warns_with(
            self, client, monkeypatch):
        """Reusing .banner rather than inventing a class: it is already the site's
        warning colour, and the stylesheet's contrast tests already cover it in both
        themes, so this adds no rule for them to have missed
        (accessibility-standards)."""
        monkeypatch.setitem(main.templates.env.globals, "auth_open_warning", True)
        assert '<div class="banner" id="openwarn">' in client.get("/").text


class TestTheWiring:

    def test_the_app_decided_the_banner_from_the_two_flags(self):
        """The global the templates read is what _announce_auth returned, rather than
        a second reading of the environment that could come to disagree with it."""
        assert main.templates.env.globals["auth_open_warning"] == (
            not main.AUTH_ENABLED and not main._open_on_purpose())

    def test_the_suite_itself_runs_open_and_says_so(self):
        """conftest pops both credentials -- that is how the suite gets to be the
        owner -- and then sets RHDB_OPEN, because it meant to. Worth asserting: if
        the opt-in ever stops being set, every page rendered in every test grows a
        banner and a few hundred assertions about page content start reading a
        warning that is not about them."""
        assert main.AUTH_ENABLED is False
        assert main._open_on_purpose() is True
        assert main.templates.env.globals["auth_open_warning"] is False

    def test_the_decision_is_written_down(self):
        from pathlib import Path
        root = Path(__file__).parents[2]
        adr = root / "adr" / "0019-running-open-is-supported-but-never-silent.md"
        assert adr.exists()
        assert "0019" in (root / "adr" / "README.md").read_text(encoding="utf-8")
        assert "RHDB_OPEN" in (root / ".env.example").read_text(encoding="utf-8")
