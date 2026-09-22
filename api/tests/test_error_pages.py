"""What a browser is shown when a request cannot be answered (MANUAL.md section 2,
"When a page is not there").

An address that leads nowhere is not an unusual event here: the register's whole
way in is a printed QR label, and a label from somebody else's collection scans to
an asset tag this one has never issued. So the answer is a page in the site's own
chrome, with the search box on it, rather than the `{"detail": ...}` FastAPI sends
by default -- which reads, to the person holding the machine, as the site being
broken.

It is the same page for all three: nothing there, nothing for you, and something
wrong at this end. What decides whether it is sent at all is who asked -- the API
and anything else that did not ask for HTML keeps the JSON it has always had.
"""

import pytest
from fastapi import HTTPException
from fastapi.testclient import TestClient

from app import main


# What a browser sends. The suite's ordinary client sends `*/*`, which is a
# program's question and keeps its JSON answer -- so every test that wants the page
# has to say so, and nothing already written changes meaning underneath.
HTML = {"accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8"}


@pytest.fixture
def faulty():
    """A copy of the app with two routes that fail on purpose.

    Nothing in the register answers 403 today -- a page a visitor may not see
    redirects to the login instead -- and nothing raises on purpose at all. Both
    handlers still have to be right on the day one does, so the pair is made here
    rather than waited for.
    """
    app = main.create_app()

    @app.get("/boom/forbidden", include_in_schema=False)
    def _forbidden() -> None:
        raise HTTPException(403, "not yours")

    @app.get("/boom/broken", include_in_schema=False)
    def _broken() -> None:
        raise RuntimeError("the database is on fire")

    # raise_server_exceptions=False: the middleware sends the page and re-raises
    # so the server logs it, and the test wants the response rather than the raise.
    with TestClient(app, raise_server_exceptions=False) as c:
        yield c


def test_a_missing_page_is_a_page(client):
    r = client.get("/no-such-address", headers=HTML)
    assert r.status_code == 404
    assert r.headers["content-type"].startswith("text/html")
    assert 'class="errorpage"' in r.text


def test_a_missing_page_arrives_in_the_site_chrome(client):
    """The search box above it is the way on from a dead end, so the page is the
    site's and not a bare sheet of its own."""
    page = client.get("/no-such-address", headers=HTML).text
    assert '<a class="skip" href="#main">' in page
    assert 'name="q"' in page


def test_a_missing_page_says_what_happened_and_offers_the_gallery(client):
    page = client.get("/no-such-address", headers=HTML).text
    assert '<p class="figure">404</p>' in page
    assert "Nothing here" in page
    assert 'href="/"' in page


def test_an_asset_tag_nothing_is_filed_under_gets_the_same_page(client):
    """The label way in: RH-9999 is somebody else's tag, or a typo of yours."""
    r = client.get("/computers/RH-9999", headers=HTML)
    assert r.status_code == 404
    assert 'class="errorpage"' in r.text


def test_a_page_that_is_not_open_says_so(faulty):
    r = faulty.get("/boom/forbidden", headers=HTML)
    assert r.status_code == 403
    assert '<p class="figure">403</p>' in r.text
    assert "Not for you" in r.text


def test_a_fault_at_this_end_says_so(faulty):
    r = faulty.get("/boom/broken", headers=HTML)
    assert r.status_code == 500
    assert '<p class="figure">500</p>' in r.text
    assert "Something went wrong" in r.text


def test_a_fault_says_nothing_about_itself(faulty):
    """What went wrong goes to the log. A stranger gets the number and a line."""
    page = faulty.get("/boom/broken", headers=HTML).text
    assert "the database is on fire" not in page
    assert "RuntimeError" not in page
    assert "Traceback" not in page


def test_a_fault_page_carries_the_content_policy(faulty):
    """The 500 is answered outside the middleware that sends the policy -- the
    exception has passed it by the time it is caught -- so the page sends its own."""
    r = faulty.get("/boom/broken", headers=HTML)
    assert r.headers["content-security-policy"].startswith("default-src 'self'")


def test_an_error_page_is_not_offered_to_a_search_engine(client):
    page = client.get("/no-such-address", headers=HTML).text
    assert '<meta name="robots" content="noindex, follow">' in page


def test_the_json_api_answers_an_error_as_it_always_has(client):
    """Asked for in a browser or by a script alike: /api is a program's surface."""
    r = client.get("/api/computers/RH-9999", headers=HTML)
    assert r.status_code == 404
    assert r.headers["content-type"].startswith("application/json")
    assert "detail" in r.json()


def test_a_client_that_did_not_ask_for_html_keeps_the_json(client):
    r = client.get("/no-such-address")
    assert r.status_code == 404
    assert r.headers["content-type"].startswith("application/json")
    assert "detail" in r.json()


def test_a_fault_outside_a_page_is_the_plain_answer_it_was(faulty):
    r = faulty.get("/boom/broken", headers={"accept": "application/json"})
    assert r.status_code == 500
    assert "<html" not in r.text
