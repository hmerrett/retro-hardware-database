"""A form field that arrives as a file is treated as blank, not as a crash.

A multipart form lets any field be a file part, whatever the page that drew the
form intended. The handlers read fields expecting text and call ``.strip()`` on
what they get, so an upload posted under a text field's name was an
AttributeError and a 500 -- found by mypy, which reads ``form.get`` as
``UploadFile | str`` and was right to.
"""

from app import main


def test_an_order_whose_description_is_a_file_is_an_order_with_no_description(client):
    made = client.post("/api/projects", json={"name": "Recap the Amiga"})
    pid = made.json()["asset_id"]
    r = client.post(
        f"/projects/{pid}/order",
        files={"description": ("x.txt", b"not text", "text/plain")},
        follow_redirects=False,
    )
    # A blank description is how the form already says "nothing to add".
    assert r.status_code == 303
    assert client.get(f"/api/projects/{pid}").json()["orders"] == []


def test_a_login_whose_password_is_a_file_is_a_failed_login(client, monkeypatch):
    """The one form a stranger can post to. Comparing a file with the password
    raised inside ``compare_digest`` before it could answer no."""
    monkeypatch.setattr(main.auth, "AUTH_ENABLED", True)
    monkeypatch.setattr(main.auth, "AUTH_USER", "admin")
    monkeypatch.setattr(main.auth, "AUTH_PASS", "correct-horse")
    r = client.post(
        "/login",
        data={"username": "admin"},
        files={"password": ("x.txt", b"correct-horse", "text/plain")},
        follow_redirects=False,
    )
    assert r.status_code == 401
