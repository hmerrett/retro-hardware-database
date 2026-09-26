"""The account pages (ADR-0032).

MANUAL section 17, "Adding people" and "Your account": Settings -> Accounts for
administrators, and a page of your own for everybody who is signed in.
"""

import re

import pytest

from app.accounts import store
from app.accounts.roles import ADMIN, VIEWER
from app.db import SessionLocal
from app.models import ApiToken, UserSession
from conftest import PASSWORD, account, as_viewer, log_out, sign_in

NEW = "a brand new password"


def user_id(username):
    with SessionLocal() as db:
        return store.find(db, username).id


def role(username):
    with SessionLocal() as db:
        return store.role_of(db, store.find(db, username))


def post(client, path, **data):
    return client.post(path, data=data, follow_redirects=False)


def token_for(username, name="a script"):
    with SessionLocal() as db:
        return store.make_token(db, store.find(db, username), name)


def token_ids(username):
    with SessionLocal() as db:
        return [t.id for t in store.tokens(db, user_id(username))]


class TestTheAccountsPage:
    def test_it_lists_every_account_with_its_role_and_state(self, client):
        account("ada", VIEWER)
        account("off", VIEWER, active=False)
        page = client.get("/settings/users").text
        assert "owner" in page and "ada" in page and "off" in page
        assert "Administrator" in page and "Viewer" in page
        assert "Switched off" in page

    def test_each_name_links_to_its_own_page(self, client):
        account("ada", VIEWER)
        assert f'href="/settings/users/{user_id("ada")}"' in client.get("/settings/users").text

    def test_it_is_an_administrators(self, client):
        as_viewer(client)
        assert client.get("/settings/users", follow_redirects=False).status_code == 403
        log_out(client)
        r = client.get("/settings/users", follow_redirects=False)
        assert r.headers["location"].startswith("/login")

    def test_it_is_reached_from_the_settings_page(self, client):
        page = client.get("/settings").text
        assert 'href="/settings/users"' in page and 'href="/settings/account"' in page

    def test_its_table_says_which_way_it_runs(self, client):
        page = client.get("/settings/users").text
        assert '<th scope="col">' in page


class TestAddingSomebody:
    def test_the_box_makes_an_account(self, client):
        r = post(
            client, "/settings/users", username="ada", role=VIEWER, password=NEW, password2=NEW
        )
        assert r.status_code == 303
        assert role("ada") == VIEWER
        log_out(client)
        assert post(client, "/login", username="ada", password=NEW).status_code == 303

    def test_the_two_passwords_must_agree(self, client):
        r = post(
            client, "/settings/users", username="ada", role=VIEWER, password=NEW, password2="x"
        )
        assert r.status_code == 400 and "not the same" in r.text

    def test_a_refusal_is_said_on_the_page_and_keeps_the_name(self, client):
        r = post(
            client,
            "/settings/users",
            username="ada",
            role=VIEWER,
            password="short",
            password2="short",
        )
        assert r.status_code == 400
        assert "10 characters" in r.text and 'value="ada"' in r.text

    def test_a_name_already_taken_is_refused(self, client):
        r = post(
            client, "/settings/users", username="OWNER", role=VIEWER, password=NEW, password2=NEW
        )
        assert r.status_code == 400 and "already" in r.text

    def test_a_viewer_cannot_add_anybody(self, client):
        as_viewer(client)
        r = post(client, "/settings/users", username="ada", role=ADMIN, password=NEW, password2=NEW)
        assert r.status_code == 403
        with SessionLocal() as db:
            assert store.find(db, "ada") is None


class TestAnAccountsOwnPage:
    def test_its_role_can_be_changed(self, client):
        account("ada", VIEWER)
        r = post(client, f"/settings/users/{user_id('ada')}/role", role=ADMIN)
        assert r.status_code == 303 and role("ada") == ADMIN

    def test_the_last_administrator_is_not_made_a_viewer_and_the_page_says_why(self, client):
        r = post(client, f"/settings/users/{user_id('owner')}/role", role=VIEWER)
        assert r.status_code == 400 and "only administrator" in r.text
        assert role("owner") == ADMIN

    def test_it_can_be_switched_off_and_on(self, client):
        account("ada", VIEWER)
        uid = user_id("ada")
        assert post(client, f"/settings/users/{uid}/active").status_code == 303
        with SessionLocal() as db:
            assert store.find(db, "ada").active is False
        assert post(client, f"/settings/users/{uid}/active", active="1").status_code == 303
        with SessionLocal() as db:
            assert store.find(db, "ada").active is True

    def test_the_last_administrator_is_not_switched_off(self, client):
        r = post(client, f"/settings/users/{user_id('owner')}/active")
        assert r.status_code == 400 and "only administrator" in r.text

    def test_a_forgotten_password_is_replaced(self, client):
        account("ada", VIEWER)
        r = post(client, f"/settings/users/{user_id('ada')}/password", password=NEW, password2=NEW)
        assert r.status_code == 303
        log_out(client)
        assert post(client, "/login", username="ada", password=NEW).status_code == 303

    def test_its_tokens_are_listed_and_revoked_one_at_a_time(self, client):
        account("ada", VIEWER)
        token_for("ada", "print desk")
        token_for("ada", "laptop")
        uid = user_id("ada")
        page = client.get(f"/settings/users/{uid}").text
        assert "print desk" in page and "laptop" in page
        first, second = token_ids("ada")
        assert post(client, f"/settings/users/{uid}/tokens/{first}/revoke").status_code == 303
        assert token_ids("ada") == [second]

    def test_an_account_nobody_has_is_not_found(self, client):
        assert client.get("/settings/users/99999").status_code == 404


class TestYourAccount:
    def test_a_viewer_may_open_it(self, client):
        as_viewer(client)
        r = client.get("/settings/account")
        assert r.status_code == 200 and "viewer" in r.text

    def test_a_visitor_is_sent_to_log_in(self, client):
        log_out(client)
        r = client.get("/settings/account", follow_redirects=False)
        assert r.headers["location"].startswith("/login")

    def test_it_is_in_the_menu_for_anybody_signed_in(self, client):
        as_viewer(client)
        assert 'href="/settings/account"' in client.get("/").text
        log_out(client)
        assert 'href="/settings/account"' not in client.get("/").text


class TestChangingYourPassword:
    def test_it_asks_for_the_one_you_have_now(self, client):
        r = post(client, "/settings/account/password", current="wrong", password=NEW, password2=NEW)
        assert r.status_code == 400 and "not your password" in r.text

    def test_the_two_new_ones_must_agree(self, client):
        r = post(
            client, "/settings/account/password", current=PASSWORD, password=NEW, password2="x"
        )
        assert r.status_code == 400 and "not the same" in r.text

    def test_it_changes_and_this_browser_stays_signed_in(self, client):
        r = post(
            client, "/settings/account/password", current=PASSWORD, password=NEW, password2=NEW
        )
        assert r.status_code == 303
        assert client.get("/settings/account").status_code == 200
        log_out(client)
        assert post(client, "/login", username="owner", password=NEW).status_code == 303

    def test_every_other_browser_is_signed_out(self, client):
        elsewhere = sign_in(client)
        here = sign_in(client)
        post(client, "/settings/account/password", current=PASSWORD, password=NEW, password2=NEW)
        with SessionLocal() as db:
            left = {s.digest for s in db.query(UserSession)}
        assert store.digest(here) in left and store.digest(elsewhere) not in left

    def test_a_viewer_changes_their_own(self, client):
        as_viewer(client)
        r = post(
            client, "/settings/account/password", current=PASSWORD, password=NEW, password2=NEW
        )
        assert r.status_code == 303


class TestWhereYouAreSignedIn:
    def test_each_session_is_listed_and_this_one_is_marked(self, client):
        sign_in(client)  # an older one, somewhere else
        sign_in(client)
        page = client.get("/settings/account").text
        assert page.count('class="session') == 3
        assert "This browser" in page

    def test_signing_out_everywhere_else_leaves_this_browser_in(self, client):
        elsewhere = sign_in(client)
        here = sign_in(client)
        assert post(client, "/settings/account/sessions").status_code == 303
        with SessionLocal() as db:
            left = {s.digest for s in db.query(UserSession)}
        assert left == {store.digest(here)} and store.digest(elsewhere) not in left


class TestYourTokens:
    def test_a_new_token_is_shown_once(self, client):
        r = post(client, "/settings/account/tokens", name="tool server")
        assert r.status_code == 200
        [key] = re.findall(r"rhdb_[A-Za-z0-9_-]{20,}", r.text)
        assert store.digest(key) in {t.digest for t in SessionLocal().query(ApiToken)}
        again = client.get("/settings/account").text
        assert key not in again and "tool server" in again

    def test_it_needs_a_name(self, client):
        r = post(client, "/settings/account/tokens", name=" ")
        assert r.status_code == 400 and "name" in r.text

    def test_a_viewer_makes_one_of_their_own(self, client):
        as_viewer(client)
        assert post(client, "/settings/account/tokens", name="phone").status_code == 200
        assert len(token_ids("viewer")) == 1

    def test_your_own_is_revoked(self, client):
        token_for("owner")
        [tid] = token_ids("owner")
        assert post(client, f"/settings/account/tokens/{tid}/revoke").status_code == 303
        assert token_ids("owner") == []

    def test_somebody_elses_is_not_yours_to_revoke(self, client):
        account("ada", VIEWER)
        token_for("ada")
        [tid] = token_ids("ada")
        as_viewer(client)
        r = post(client, f"/settings/account/tokens/{tid}/revoke")
        assert r.status_code == 404
        assert token_ids("ada") == [tid]


@pytest.mark.parametrize("path", ["/settings/users", "/settings/account"])
def test_the_pages_carry_the_v0_2_components(client, path):
    page = client.get(path).text
    assert 'class="v2"' in page and 'class="heading"' in page
