"""A new installation, and the way out of having no accounts (ADR-0032).

MANUAL section 17, "The first visit" and "What the log says at startup". A fresh
install is on the internet before its owner has visited it, so the first account
is made only by whoever holds the setup code the app wrote to its own log.
"""

import logging

import pytest

from app import main
from app.accounts import firstrun, store
from app.accounts.roles import ADMIN, VIEWER
from app.db import SessionLocal
from conftest import account

GOOD = "a password long enough"


def set_up(c, code=None, username="ada", password=GOOD, again=None):
    return c.post(
        "/setup",
        data={
            "code": firstrun.code() if code is None else code,
            "username": username,
            "password": password,
            "password2": password if again is None else again,
        },
        follow_redirects=False,
    )


@pytest.fixture
def said(caplog):
    """What the app logs at startup, for a given environment."""

    def start(user="", password="", open_=""):
        firstrun.forget()
        caplog.clear()
        with caplog.at_level(logging.INFO, logger=firstrun.log.name):
            firstrun.startup(user, password, open_)
        return caplog.records

    return start


class TestANewInstallation:
    def test_every_page_opens_on_set_up(self, fresh_client):
        for path in ("/", "/projects", "/files", "/login", "/computers/new", "/settings"):
            r = fresh_client.get(path, follow_redirects=False)
            assert r.status_code == 303, path
            assert r.headers["location"] == "/setup", path

    def test_nothing_can_be_written_before_it(self, fresh_client):
        r = fresh_client.post("/computers/new", data={"model": "X"}, follow_redirects=False)
        assert r.headers["location"] == "/setup"

    def test_the_api_says_the_site_is_not_set_up(self, fresh_client):
        r = fresh_client.get("/api/parts")
        assert r.status_code == 503
        assert "/setup" in r.text

    def test_the_health_check_answers_before_it(self, fresh_client):
        assert fresh_client.get("/healthz").status_code == 200

    def test_the_setup_page_is_drawn_with_its_stylesheet(self, fresh_client):
        assert fresh_client.get("/static/app.css").status_code == 200

    def test_set_up_asks_for_the_code_a_username_and_the_password_twice(self, fresh_client):
        page = fresh_client.get("/setup").text
        for box in ('name="code"', 'name="username"', 'name="password"', 'name="password2"'):
            assert box in page


class TestTheSetupCode:
    def test_it_is_written_to_the_log_at_startup(self, said):
        records = said()
        assert any(firstrun.code() in r.getMessage() for r in records)
        assert any("setup code" in r.getMessage() for r in records)

    def test_it_is_three_groups_of_four(self, said):
        said()
        groups = firstrun.code().split("-")
        assert [len(g) for g in groups] == [4, 4, 4]

    def test_a_new_one_is_written_every_start(self, said):
        said()
        first = firstrun.code()
        said()
        assert firstrun.code() != first

    def test_capitals_and_dashes_do_not_matter(self, fresh_client):
        typed = firstrun.code().lower().replace("-", " ")
        assert set_up(fresh_client, code=typed).status_code == 303

    def test_a_wrong_code_is_refused(self, fresh_client):
        r = set_up(fresh_client, code="AAAA-AAAA-AAAA")
        assert r.status_code == 400
        assert "not the setup code" in r.text
        with SessionLocal() as db:
            assert store.count(db) == 0

    def test_wrong_codes_count_against_the_login_limit(self, fresh_client, monkeypatch):
        monkeypatch.setattr(main.auth, "_login_limiter", main.auth._RateLimiter(2, 300))
        for _ in range(2):
            assert set_up(fresh_client, code="AAAA-AAAA-AAAA").status_code == 400
        # The right one is refused too while the block stands.
        assert set_up(fresh_client).status_code == 429


class TestSettingUp:
    def test_it_makes_an_administrator_and_signs_them_in(self, fresh_client):
        r = set_up(fresh_client)
        assert r.status_code == 303 and r.headers["location"] == "/"
        with SessionLocal() as db:
            ada = store.find(db, "ada")
            assert ada is not None and store.role_of(db, ada) == ADMIN
        assert fresh_client.get("/settings", follow_redirects=False).status_code == 200

    def test_the_two_passwords_must_agree(self, fresh_client):
        r = set_up(fresh_client, again="something else entirely")
        assert r.status_code == 400
        assert "not the same" in r.text

    def test_a_short_password_is_refused(self, fresh_client):
        r = set_up(fresh_client, password="short")
        assert r.status_code == 400
        assert "10 characters" in r.text

    def test_the_username_is_kept_when_the_form_comes_back(self, fresh_client):
        assert 'value="grace"' in set_up(fresh_client, username="grace", password="x").text

    def test_it_is_gone_once_there_is_an_account(self, fresh_client):
        set_up(fresh_client)
        assert fresh_client.get("/setup").status_code == 404
        assert set_up(fresh_client, username="mallory").status_code == 404

    def test_it_is_gone_on_a_site_that_already_has_accounts(self, client):
        assert client.get("/setup").status_code == 404

    def test_a_viewer_alone_does_not_set_a_site_up(self, fresh_client):
        """A viewer made from the command line on a new install is an account, and
        one that can change nothing: the site is still waiting for somebody to run
        it."""
        account("reader", VIEWER)
        assert fresh_client.get("/", follow_redirects=False).headers["location"] == "/setup"
        assert set_up(fresh_client).status_code == 303

    def test_an_administrator_made_from_the_command_line_does(self, fresh_client):
        account("henry", ADMIN)
        assert fresh_client.get("/setup").status_code == 404


class TestUpgradingFromTheSingleLogin:
    def test_the_old_pair_becomes_the_first_administrator(self, said, fresh_client):
        said(user="henry", password="hunter2")
        with SessionLocal() as db:
            henry = store.find(db, "henry")
            assert henry is not None and store.role_of(db, henry) == ADMIN
        r = fresh_client.post(
            "/login", data={"username": "henry", "password": "hunter2"}, follow_redirects=False
        )
        assert r.status_code == 303

    def test_it_says_so(self, said):
        messages = [r.getMessage() for r in said(user="henry", password="hunter2")]
        assert any("Made an administrator" in m for m in messages)

    def test_set_up_is_skipped(self, said, fresh_client):
        said(user="henry", password="hunter2")
        assert fresh_client.get("/setup").status_code == 404

    def test_it_is_read_only_when_there_are_no_accounts(self, said):
        account("owner")
        said(user="henry", password="hunter2")
        with SessionLocal() as db:
            assert store.find(db, "henry") is None

    def test_a_reminder_is_logged_while_the_pair_is_still_set(self, said):
        account("owner")
        messages = [r.getMessage() for r in said(user="henry", password="hunter2")]
        assert any("no longer reads them" in m for m in messages)

    def test_a_username_the_accounts_cannot_hold_opens_on_set_up_instead(self, said):
        records = said(user="has a space", password="hunter2")
        assert any(r.levelno == logging.ERROR for r in records)
        with SessionLocal() as db:
            assert store.count(db) == 0


class TestWhatTheLogSays:
    def test_a_site_with_accounts_and_nothing_left_over_says_nothing(self, said):
        account("owner")
        assert said() == []

    def test_no_accounts_is_a_warning(self, said):
        assert [r.levelno for r in said()] == [logging.WARNING]

    def test_rhdb_open_is_said_to_do_nothing(self, said):
        account("owner")
        messages = [r.getMessage() for r in said(open_="1")]
        assert any("RHDB_OPEN" in m and "does nothing" in m for m in messages)

    def test_nothing_logged_carries_a_password(self, said):
        for accounts in (False, True):
            if accounts:
                account("owner")
            for r in said(user="henry", password="sentinel-pass-2b71", open_="1"):
                assert "sentinel-pass-2b71" not in r.getMessage()
