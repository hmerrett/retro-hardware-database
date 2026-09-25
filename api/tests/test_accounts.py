"""Accounts, roles, sessions and tokens (ADR-0032).

MANUAL section 17: administrators and viewers, adding people, a site only its
people can read, signing in and out, and API tokens. Each class is one of those
entries, and each test one thing it promises.
"""

import io

import pytest

from app import main
from app.accounts import __main__ as command
from app.accounts import store
from app.accounts.roles import (
    ADMIN,
    EDIT,
    MANAGE_ACCOUNTS,
    READ_PRIVATE,
    SITE,
    VIEWER,
    VISITOR,
    Principal,
    can,
)
from app.db import SessionLocal
from app.models import ApiToken, Part, UserSession
from conftest import PASSWORD, account, as_viewer, log_out, sign_in


def upload(client, aid, name="receipt.pdf"):
    r = client.post(
        "/files",
        files={"uploads": (name, b"%PDF-1.4 x")},
        data={"aid": aid},
        follow_redirects=False,
    )
    assert r.status_code == 303, r.text
    return client.get("/api/files").json()[0]["id"]


def token_for(username, name="a script"):
    with SessionLocal() as db:
        return store.make_token(db, store.find(db, username), name)


def bearer(key):
    return {"Authorization": f"Bearer {key}"}


def close_the_site(client, closed=True):
    data = {"site_name": "", "theme": "system", "watermark": "1", "remember_locations": "1"}
    if closed:
        data["login_to_read"] = "1"
    r = client.post("/settings", data=data, follow_redirects=False)
    assert r.status_code == 303, r.text


def login(client, username, password=PASSWORD):
    return client.post(
        "/login", data={"username": username, "password": password}, follow_redirects=False
    )


class TestRolesAreListsOfPermissions:
    def test_a_visitor_may_do_nothing_beyond_the_public_pages(self):
        assert not can(VISITOR, READ_PRIVATE) and not can(VISITOR, EDIT)

    def test_a_viewer_reads_what_is_kept_back_and_changes_nothing(self):
        viewer = Principal(user_id=1, username="v", role=VIEWER)
        assert can(viewer, READ_PRIVATE)
        assert not can(viewer, EDIT) and not can(viewer, MANAGE_ACCOUNTS)

    def test_an_administrator_may_do_everything(self):
        admin = Principal(user_id=1, username="a", role=ADMIN)
        assert all(can(admin, p) for p in (READ_PRIVATE, EDIT, MANAGE_ACCOUNTS))

    def test_a_role_on_one_site_grants_nothing_on_another(self):
        admin = Principal(user_id=1, username="a", role=ADMIN, site=SITE)
        assert not can(admin, READ_PRIVATE, site=SITE + 1)


class TestWhatAViewerSees:
    """Everything a visitor is not shown, and none of the controls."""

    def test_an_unpublished_file(self, client, part):
        fid = upload(client, part()["asset_id"])
        as_viewer(client)
        assert client.get(f"/files/{fid}").status_code == 200
        log_out(client)
        assert client.get(f"/files/{fid}").status_code == 404

    def test_a_private_project(self, client):
        aid = client.post("/api/projects", json={"name": "Secret", "private": True}).json()[
            "asset_id"
        ]
        as_viewer(client)
        assert client.get(f"/projects/{aid}").status_code == 200
        assert "Secret" in client.get("/projects").text
        log_out(client)
        assert client.get(f"/projects/{aid}").status_code == 404

    def test_where_a_thing_is_kept(self, client, computer):
        aid = computer(location="Loft, blue crate 3")["asset_id"]
        as_viewer(client)
        assert "blue crate 3" in client.get(f"/computers/{aid}").text
        log_out(client)
        assert "blue crate 3" not in client.get(f"/computers/{aid}").text

    def test_what_an_order_cost(self, client):
        aid = client.post("/api/projects", json={"name": "Recap"}).json()["asset_id"]
        client.post(f"/api/projects/{aid}/orders", json={"description": "caps", "cost_p": 1234})
        as_viewer(client)
        assert "£12.34" in client.get(f"/projects/{aid}").text
        log_out(client)
        assert "£12.34" not in client.get(f"/projects/{aid}").text

    def test_the_for_sale_shortlist(self, client, part):
        aid = part(model="Spare SIMM")["asset_id"]
        client.post(f"/parts/{aid}/for-sale", data={"for_sale": "1"}, follow_redirects=False)
        as_viewer(client)
        assert "Spare SIMM" in client.get("/for-sale").text
        log_out(client)
        assert client.get("/for-sale", follow_redirects=False).status_code == 303

    def test_no_editing_controls(self, client, part):
        aid = part()["asset_id"]
        as_viewer(client)
        page = client.get(f"/parts/{aid}").text
        assert f'href="/parts/{aid}/edit"' not in page
        assert 'href="/computers/new"' not in page
        assert 'href="/settings"' not in page

    def test_a_way_to_log_out(self, client):
        as_viewer(client)
        page = client.get("/").text
        assert 'action="/logout"' in page
        assert 'href="/login' not in page


class TestWhatAViewerIsRefused:
    """Told so, with a 403 -- not sent to log in again as the same person."""

    @pytest.mark.parametrize("path", ["/computers/new", "/settings", "/traffic"])
    def test_an_administrators_page(self, client, path):
        as_viewer(client)
        r = client.get(path, follow_redirects=False)
        assert r.status_code == 403
        assert "Not for this account" in r.text

    def test_an_edit_form(self, client, part):
        aid = part()["asset_id"]
        as_viewer(client)
        assert client.get(f"/parts/{aid}/edit", follow_redirects=False).status_code == 403

    def test_any_write(self, client, part):
        aid = part()["asset_id"]
        as_viewer(client)
        r = client.post(f"/parts/{aid}/for-sale", data={"for_sale": "1"}, follow_redirects=False)
        assert r.status_code == 403
        with SessionLocal() as db:
            assert db.get(Part, aid).for_sale is False

    def test_a_visitor_is_still_sent_to_log_in(self, client):
        log_out(client)
        r = client.get("/computers/new", follow_redirects=False)
        assert r.status_code == 303 and r.headers["location"].startswith("/login")


class TestThereIsAlwaysAnAdministrator:
    def test_the_last_one_cannot_be_made_a_viewer(self, client):
        with SessionLocal() as db, pytest.raises(store.AccountError, match="only administrator"):
            store.set_role(db, store.find(db, "owner"), VIEWER)

    def test_the_last_one_cannot_be_switched_off(self, client):
        with SessionLocal() as db, pytest.raises(store.AccountError, match="only administrator"):
            store.set_active(db, store.find(db, "owner"), False)

    def test_with_a_second_the_first_can_step_down(self, client):
        account("second", ADMIN)
        with SessionLocal() as db:
            store.set_role(db, store.find(db, "owner"), VIEWER)
            assert store.role_of(db, store.find(db, "owner")) == VIEWER


class TestUsernamesAndPasswords:
    def test_a_username_is_matched_without_regard_to_case(self, client):
        log_out(client)
        assert login(client, "OWNER").status_code == 303

    def test_two_accounts_cannot_differ_only_by_case(self, client):
        with SessionLocal() as db, pytest.raises(store.AccountError, match="already"):
            store.create(db, "Owner", "a long enough password", VIEWER)

    def test_an_email_address_will_do_as_a_username(self, client):
        with SessionLocal() as db:
            store.create(db, "ada@example.com", "a long enough password", VIEWER)

    def test_a_username_with_a_space_is_refused(self, client):
        with SessionLocal() as db, pytest.raises(store.AccountError):
            store.create(db, "ada lovelace", "a long enough password", VIEWER)

    def test_a_password_is_at_least_ten_characters(self, client):
        with SessionLocal() as db, pytest.raises(store.AccountError, match="10 characters"):
            store.create(db, "ada", "123456789", VIEWER)

    def test_a_password_is_kept_as_an_argon2_hash(self, client):
        with SessionLocal() as db:
            ada = store.create(db, "ada", "a long enough password", VIEWER)
            assert ada.password_hash.startswith("$argon2id$")
            assert "a long enough password" not in ada.password_hash

    def test_a_wrong_username_and_a_wrong_password_look_the_same(self, client):
        log_out(client)
        wrong_user = login(client, "nobody")
        wrong_pass = login(client, "owner", "not the password")
        assert wrong_user.status_code == wrong_pass.status_code == 401
        assert wrong_user.text == wrong_pass.text


class TestSigningInAndOut:
    def test_signing_in_gives_a_session_cookie_for_30_days(self, client):
        log_out(client)
        r = login(client, "owner")
        cookie = r.headers["set-cookie"]
        assert "rhdb_session=" in cookie and "HttpOnly" in cookie
        assert f"Max-Age={30 * 24 * 3600}" in cookie

    def test_the_database_keeps_a_digest_and_never_the_key(self, client):
        key = sign_in(client)
        with SessionLocal() as db:
            digests = {s.digest for s in db.query(UserSession)}
        assert key not in digests and store.digest(key) in digests

    def test_logging_out_ends_the_session_on_the_server(self, client):
        key = client.cookies.get(main.auth.COOKIE)
        client.post("/logout", follow_redirects=False)
        client.cookies.set(main.auth.COOKIE, key)
        # The copy of the cookie taken before logging out opens nothing now.
        assert client.get("/computers/new", follow_redirects=False).status_code == 303

    def test_an_expired_session_opens_nothing(self, client):
        with SessionLocal() as db:
            for s in db.query(UserSession):
                s.expires_at = store._now() - store.SEEN_EVERY
            db.commit()
        assert client.get("/computers/new", follow_redirects=False).status_code == 303

    def test_switching_an_account_off_signs_it_out_everywhere(self, client):
        account("second", ADMIN)
        as_viewer(client)
        with SessionLocal() as db:
            store.set_active(db, store.find(db, "viewer"), False)
        assert 'action="/logout"' not in client.get("/").text

    def test_an_account_switched_off_cannot_sign_in(self, client):
        account("off", VIEWER, active=False)
        log_out(client)
        assert login(client, "off").status_code == 401

    def test_switching_it_back_on_restores_it(self, client):
        account("off", VIEWER, active=False)
        with SessionLocal() as db:
            store.set_active(db, store.find(db, "off"), True)
        log_out(client)
        assert login(client, "off").status_code == 303

    def test_a_new_password_signs_the_account_out_everywhere_else(self, client):
        keep = sign_in(client)
        other = sign_in(client)
        with SessionLocal() as db:
            store.set_password(db, store.find(db, "owner"), "a new long password", keep=keep)
            left = {s.digest for s in db.query(UserSession)}
        assert left == {store.digest(keep)}
        assert store.digest(other) not in left

    def test_http_basic_does_not_open_a_browser_page(self, client):
        log_out(client)
        r = client.get("/computers/new", auth=("owner", PASSWORD), follow_redirects=False)
        assert r.status_code == 303


class TestApiTokens:
    def test_a_token_opens_the_api(self, client):
        key = token_for("owner")
        log_out(client)
        assert client.get("/api/parts", headers=bearer(key)).status_code == 200
        r = client.post("/api/parts", json={"model": "X", "type": "other"}, headers=bearer(key))
        assert r.status_code == 200

    def test_it_starts_rhdb_(self, client):
        assert token_for("owner").startswith("rhdb_")

    def test_only_a_digest_of_it_is_kept(self, client):
        key = token_for("owner")
        with SessionLocal() as db:
            row = db.query(ApiToken).one()
        assert row.digest == store.digest(key) and key not in row.digest

    def test_a_viewers_token_reads_and_does_not_write(self, client):
        account("reader", VIEWER)
        key = token_for("reader")
        log_out(client)
        assert client.get("/api/parts", headers=bearer(key)).status_code == 200
        r = client.post("/api/parts", json={"model": "X", "type": "other"}, headers=bearer(key))
        assert r.status_code == 403

    def test_a_revoked_token_opens_nothing(self, client):
        key = token_for("owner")
        with SessionLocal() as db:
            store.revoke_token(db, db.query(ApiToken).one().id)
        log_out(client)
        assert client.get("/api/parts", headers=bearer(key)).status_code == 401

    def test_a_token_stops_when_its_account_is_switched_off(self, client):
        account("second", ADMIN)
        key = token_for("second")
        with SessionLocal() as db:
            store.set_active(db, store.find(db, "second"), False)
        log_out(client)
        assert client.get("/api/parts", headers=bearer(key)).status_code == 401

    def test_its_last_use_is_recorded(self, client):
        key = token_for("owner")
        log_out(client)
        client.get("/api/parts", headers=bearer(key))
        with SessionLocal() as db:
            assert db.query(ApiToken).one().last_used_at is not None

    def test_wrong_tokens_count_against_the_login_limit(self, client, monkeypatch):
        monkeypatch.setattr(main.auth, "_login_limiter", main.auth._RateLimiter(2, 300))
        log_out(client)
        for _ in range(2):
            assert client.get("/api/parts", headers=bearer("rhdb_wrong")).status_code == 401
        assert client.get("/api/parts", headers=bearer("rhdb_wrong")).status_code == 429

    def test_http_basic_with_an_accounts_password_still_works(self, client):
        log_out(client)
        assert client.get("/api/parts", auth=("owner", PASSWORD)).status_code == 200


class TestAClosedSite:
    """Visitors must log in."""

    @pytest.mark.parametrize(
        "path", ["/", "/projects", "/files", "/machines", "/api/machines", "/stats"]
    )
    def test_a_visitor_is_shown_the_login_and_nothing_else(self, client, path):
        close_the_site(client)
        log_out(client)
        r = client.get(path, follow_redirects=False)
        assert r.status_code in (303, 401), path
        if r.status_code == 303:
            assert r.headers["location"].startswith("/login")

    def test_an_item_page_goes_to_the_login_and_comes_back(self, client, part):
        aid = part()["asset_id"]
        close_the_site(client)
        log_out(client)
        r = client.get(f"/parts/{aid}", follow_redirects=False)
        assert r.headers["location"] == f"/login?next=/parts/{aid}"

    def test_the_photographs_are_behind_it_too(self, client):
        close_the_site(client)
        log_out(client)
        assert client.get("/images/parts/x.jpg", follow_redirects=False).status_code == 303

    @pytest.mark.parametrize("path", ["/login", "/healthz", "/static/app.css", "/robots.txt"])
    def test_what_has_to_stay_open_does(self, client, path):
        close_the_site(client)
        log_out(client)
        assert client.get(path, follow_redirects=False).status_code == 200, path

    def test_the_print_agents_door_stays_open(self, client, monkeypatch):
        monkeypatch.setenv("RHDB_PRINT_AGENTS", "desk:key-one:dymo-11355:pdf")
        close_the_site(client)
        log_out(client)
        assert client.post("/api/print/agent/claim", headers=bearer("key-one")).status_code == 204

    def test_the_sitemap_is_withdrawn(self, client):
        close_the_site(client)
        log_out(client)
        assert "Sitemap:" not in client.get("/robots.txt").text

    def test_a_viewer_reads_it_as_before(self, client, part):
        aid = part()["asset_id"]
        close_the_site(client)
        as_viewer(client)
        assert client.get(f"/parts/{aid}").status_code == 200

    def test_it_is_off_by_default(self, client, part):
        aid = part()["asset_id"]
        log_out(client)
        assert client.get(f"/parts/{aid}").status_code == 200

    def test_it_is_on_the_settings_page(self, client):
        assert "Visitors must log in" in client.get("/settings").text


class TestAnAgentsKeyIsNotAWrongGuess:
    def test_collecting_labels_does_not_count_against_the_limit(self, client, monkeypatch):
        """The agent's bearer is its own key, checked by its route; read at the gate
        as an account's token it would be a wrong guess every time a label came."""
        monkeypatch.setenv("RHDB_PRINT_AGENTS", "desk:key-one:dymo-11355:pdf")
        monkeypatch.setattr(main.auth, "_login_limiter", main.auth._RateLimiter(2, 300))
        for _ in range(4):
            assert (
                client.post("/api/print/agent/claim", headers=bearer("key-one")).status_code == 204
            )
        assert main.auth._login_limiter.check("testclient")


class TestTheAccountsCommand:
    def run(self, *argv, password=""):
        out = io.StringIO()
        code = command.run(list(argv), stdin=io.StringIO(password + "\n"), out=out)
        return code, out.getvalue()

    def test_add_and_list(self, client):
        assert self.run("add", "ada", "--role", "viewer", password="a long enough password")[0] == 0
        _, out = self.run("list")
        assert "ada" in out and "Viewer" in out and "owner" in out

    def test_the_password_is_read_from_standard_input_not_the_command_line(self, client):
        self.run("add", "ada", password="a long enough password")
        log_out(client)
        assert login(client, "ada", "a long enough password").status_code == 303

    def test_a_refusal_is_said_and_is_not_zero(self, client, capsys):
        code, _ = self.run("add", "ada", password="short")
        assert code == 1
        assert "10 characters" in capsys.readouterr().err

    def test_role_disable_and_enable(self, client):
        self.run("add", "ada", password="a long enough password")
        assert self.run("role", "ada", "admin")[0] == 0
        assert self.run("disable", "ada")[0] == 0
        assert "switched off" in self.run("list")[1]
        assert self.run("enable", "ada")[0] == 0

    def test_it_will_not_remove_the_last_administrator(self, client):
        assert self.run("disable", "owner")[0] == 1

    def test_password_resets_a_lost_one(self, client):
        assert self.run("password", "owner", password="a brand new password")[0] == 0
        log_out(client)
        assert login(client, "owner", "a brand new password").status_code == 303

    def test_a_token_is_printed_once_and_listed_without_its_key(self, client):
        code, out = self.run("token", "owner", "tool server")
        key = out.strip()
        assert code == 0 and key.startswith("rhdb_")
        listed = self.run("tokens")[1]
        assert "tool server" in listed and key not in listed

    def test_revoke(self, client):
        self.run("token", "owner", "tool server")
        with SessionLocal() as db:
            tid = db.query(ApiToken).one().id
        assert self.run("revoke", str(tid))[0] == 0
        assert self.run("revoke", str(tid))[0] == 1
