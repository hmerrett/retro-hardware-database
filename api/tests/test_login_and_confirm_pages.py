"""The three pages that ask one question and nothing else: the login page
(MANUAL.md section 17, "Logging in"), the delete confirmation (section 15,
"Deletion") and the board detach (section 5, "Detaching the board").

They share a shape -- a narrow column, a heading, a banner in the tone of what is
about to happen, and one row of buttons -- and they differ in the tone, which is
the point: `danger` where something is destroyed and `warning` where nothing is.
A page that asks is a page and not a dialog, so it works with no script and has
an address somebody can be sent.

Auth is off in these tests, so the client is the owner; `signed_out` turns it on.
"""

import re
from pathlib import Path

import pytest

from app import machinedb, machines, main
from app.auth import _RateLimiter
from app.models import Computer

STYLESHEET = Path(__file__).parents[1] / "app" / "static" / "app.css"


def signed_out(monkeypatch, user="admin", password="correct-horse"):
    """A site with a login, and nobody logged in."""
    monkeypatch.setattr(main.auth, "AUTH_ENABLED", True)
    monkeypatch.setattr(main.auth, "AUTH_USER", user)
    monkeypatch.setattr(main.auth, "AUTH_PASS", password)
    monkeypatch.setattr(main.auth, "_login_limiter", _RateLimiter(3, 300))


def banner(page: str) -> str:
    """The first banner on the page, markup and all."""
    m = re.search(r'<div class="banner[^"]*"[^>]*>.*?</div>', page, re.S)
    return m.group(0) if m else ""


def body(page: str) -> str:
    """The page's own markup, without the chrome around it -- the header carries a
    banner of its own when the site is running open, and the footer carries links."""
    return page.split("<main", 1)[-1].split("</main>", 1)[0]


def disposed(client, kind, aid):
    """An item marked gone, which is the precondition of deleting it."""
    r = client.post(f"/{kind}/{aid}/dispose", data={"note": "skipped"}, follow_redirects=False)
    assert r.status_code == 303, r.text
    return aid


@pytest.fixture
def spectrum(client, db):
    """A Spectrum the catalogue names, with a board issue and a chip on it, so the
    detach page has something to say will move."""
    c = db.get(
        Computer,
        client.post(
            "/api/computers", json={"manufacturer": "Sinclair", "model": "ZX Spectrum 48K"}
        ).json()["asset_id"],
    )
    machinedb.write(
        db,
        c,
        model_key="zx-spectrum-48k",
        issue="Issue 4B",
        style="rubber keys",
        region="PAL (UK/Europe)",
        chips={"ula": "6C001E-7"},
        sockets={"ula": True},
    )
    db.commit()
    return c


class TestTheLoginPage:
    def test_it_says_that_browsing_needs_no_login(self, client, monkeypatch):
        """The page is where somebody lands who followed a link they did not mean
        to, and the useful thing to tell them is that they never needed it."""
        signed_out(monkeypatch)
        assert "Browsing needs no login" in body(client.get("/login").text)

    def test_it_says_that_signing_in_keeps_one_cookie(self, client, monkeypatch):
        signed_out(monkeypatch)
        assert "one cookie" in body(client.get("/login").text)

    def test_a_wrong_name_and_a_wrong_password_are_answered_the_same(self, client, monkeypatch):
        """Which half was wrong would tell a stranger whether a guessed name exists."""
        signed_out(monkeypatch)
        wrong_name = client.post("/login", data={"username": "nobody", "password": "correct-horse"})
        wrong_pass = client.post("/login", data={"username": "admin", "password": "nope"})
        assert wrong_name.status_code == wrong_pass.status_code == 401
        assert banner(wrong_name.text) == banner(wrong_pass.text) != ""

    def test_the_refusal_is_a_danger_banner_a_screen_reader_announces(self, client, monkeypatch):
        signed_out(monkeypatch)
        b = banner(client.post("/login", data={"username": "admin", "password": "nope"}).text)
        assert 'class="banner danger"' in b and 'role="alert"' in b

    def test_being_turned_away_for_trying_too_often_says_so(self, client, monkeypatch):
        """Not "incorrect": nothing was read. Saying the pair was wrong reads as
        though the next attempt would be looked at, and it would not."""
        signed_out(monkeypatch)
        for _ in range(3):
            client.post("/login", data={"username": "admin", "password": "nope"})
        r = client.post("/login", data={"username": "admin", "password": "correct-horse"})
        assert r.status_code == 429
        assert "Too many attempts" in banner(r.text)
        assert "not recognised" not in banner(r.text).lower()

    def test_the_password_manager_is_told_which_box_is_which(self, client, monkeypatch):
        signed_out(monkeypatch)
        page = client.get("/login").text
        assert 'autocomplete="username"' in page and 'autocomplete="current-password"' in page

    def test_the_refusal_stands_between_the_boxes_and_the_button(self, client, monkeypatch):
        """Read in the order it is met: what went wrong, then the thing to press."""
        signed_out(monkeypatch)
        page = client.post("/login", data={"username": "admin", "password": "nope"}).text
        assert page.index('autocomplete="current-password"') < page.index('class="banner danger"')
        assert page.index('class="banner danger"') < page.index('type="submit"')

    def test_it_is_the_v0_2_login_box(self, client, monkeypatch):
        signed_out(monkeypatch)
        page = body(client.get("/login").text)
        assert 'class="loginbox"' in page and '<h1 class="heading">' in page
        assert 'class="input"' in page and "login-box" not in page


class TestConfirmingADelete:
    def test_it_counts_what_will_go(self, client, computer):
        aid = disposed(client, "computers", computer()["asset_id"])
        page = body(client.get(f"/computers/{aid}/delete").text)
        assert "history entr" in page

    def test_the_destructive_button_is_the_danger_one(self, client, computer):
        """Never `primary`. Only destruction gets that colour, which is what makes
        it mean something on the one page that has it."""
        aid = disposed(client, "computers", computer()["asset_id"])
        row = body(client.get(f"/computers/{aid}/delete").text)
        assert 'class="btn danger"' in row and 'class="btn primary"' not in row

    def test_cancel_stands_beside_it_at_the_same_size(self, client, computer):
        """The same size, because an escape made small is an escape made hard."""
        aid = disposed(client, "computers", computer()["asset_id"])
        row = re.search(
            r'<p class="row[^"]*">.*?</p>', body(client.get(f"/computers/{aid}/delete").text), re.S
        )
        assert row, "the buttons are not in one row"
        assert 'class="btn danger"' in row.group(0)
        assert f'class="btn" href="/computers/{aid}"' in row.group(0)

    def test_it_asks_for_the_item_s_own_url(self, client, computer):
        aid = disposed(client, "computers", computer()["asset_id"])
        page = body(client.get(f"/computers/{aid}/delete").text)
        assert 'name="confirm"' in page and f"/computers/{aid}" in page

    def test_a_paste_that_went_wrong_comes_back_as_a_danger_banner(self, client, computer):
        aid = disposed(client, "computers", computer()["asset_id"])
        r = client.post(f"/computers/{aid}/delete", data={"confirm": "/computers/RH-NOPE"})
        assert r.status_code == 400
        assert 'class="banner danger"' in banner(r.text)
        assert "Nothing was deleted" in banner(r.text)

    def test_there_is_one_way_back_and_it_is_the_cancel_button(self, client, computer):
        """A crumb above the heading and a Cancel below it are two ways to the same
        place; the way out belongs with the decision."""
        aid = disposed(client, "computers", computer()["asset_id"])
        page = body(client.get(f"/computers/{aid}/delete").text)
        assert "crumbnav" not in page
        assert page.count(f'href="/computers/{aid}"') == 1

    def test_it_is_the_v0_2_confirm_page(self, client, computer):
        aid = disposed(client, "computers", computer()["asset_id"])
        page = body(client.get(f"/computers/{aid}/delete").text)
        assert 'class="confirm"' in page and '<h1 class="heading">' in page
        assert "danger-box" not in page and "lede" not in page

    def test_a_part_s_page_asks_the_same_way(self, client, part):
        aid = disposed(client, "parts", part()["asset_id"])
        page = body(client.get(f"/parts/{aid}/delete").text)
        assert 'class="confirm"' in page and 'class="btn danger"' in page


class TestConfirmingADetach:
    def test_it_is_the_same_page_with_a_warning_banner(self, client, spectrum):
        """Nothing is destroyed: the machine keeps its tag, its history and its
        photographs, and one more thing gets a tag of its own."""
        page = body(client.get(f"/computers/{spectrum.asset_id}/detach-board").text)
        assert 'class="confirm"' in page and 'class="banner warning"' in page
        assert 'class="banner danger"' not in page

    def test_its_button_is_primary_because_nothing_is_lost(self, client, spectrum):
        page = body(client.get(f"/computers/{spectrum.asset_id}/detach-board").text)
        assert 'class="btn primary"' in page and 'class="btn danger"' not in page

    def test_it_still_says_what_moves_and_what_stays(self, client, spectrum):
        page = body(client.get(f"/computers/{spectrum.asset_id}/detach-board").text)
        assert "Issue 4B" in page and "6C001E-7" in page
        assert "rubber keys" in page and "PAL (UK/Europe)" in page

    def test_the_portrait_can_still_be_taken_here(self, client, spectrum):
        """The board is out and on the bench, which is the one moment it can be
        photographed. A file picker needs a form, and this is the form."""
        page = body(client.get(f"/computers/{spectrum.asset_id}/detach-board").text)
        assert 'type="file"' in page and 'enctype="multipart/form-data"' in page

    def test_there_is_one_way_back_and_it_is_the_cancel_button(self, client, spectrum):
        aid = spectrum.asset_id
        page = body(client.get(f"/computers/{aid}/detach-board").text)
        assert "crumbnav" not in page
        assert page.count(f'href="/computers/{aid}"') == 1


class TestWhatTheStylesheetNoLongerCarries:
    @pytest.mark.parametrize(
        "rule", [".danger-box", ".detach-box", ".confirm-url", ".login-box", ".crumbnav", ".lede"]
    )
    def test_the_rule_these_pages_were_the_last_users_of_is_gone(self, rule):
        """0.1's app.css shrinks by what each migrated group stops using; a rule left
        behind is a rule that has to be reasoned about at the end of the phase."""
        css = STYLESHEET.read_text(encoding="utf-8")
        assert rule not in css


def test_the_catalogue_still_names_the_spectrum():
    """The detach page reads the catalogue, so these tests assume it is there."""
    assert machines.model("zx-spectrum-48k") is not None
