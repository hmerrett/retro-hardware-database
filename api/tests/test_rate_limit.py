"""Login rate limiting: an internet-facing single-credential login must not be
guessable at unlimited speed. A small in-memory sliding-window limiter, keyed by
client IP, caps failed attempts.
"""

from app import main
from app.auth import _RateLimiter
from conftest import PASSWORD, account, log_out


def test_allows_up_to_the_limit_then_blocks():
    rl = _RateLimiter(max_attempts=3, window=60)
    now = 1000.0
    for _ in range(3):
        assert rl.check("ip", now) is True
        rl.record("ip", now)
    assert rl.check("ip", now) is False


def test_the_window_slides():
    rl = _RateLimiter(max_attempts=2, window=60)
    rl.record("ip", 1000.0)
    rl.record("ip", 1000.0)
    assert rl.check("ip", 1000.0) is False
    assert rl.check("ip", 1070.0) is True  # earlier hits have aged out


def test_keys_are_independent():
    rl = _RateLimiter(max_attempts=1, window=60)
    rl.record("a", 1000.0)
    assert rl.check("a", 1000.0) is False
    assert rl.check("b", 1000.0) is True


def test_reset_clears_a_key():
    rl = _RateLimiter(max_attempts=1, window=60)
    rl.record("ip", 1000.0)
    assert rl.check("ip", 1000.0) is False
    rl.reset("ip")
    assert rl.check("ip", 1000.0) is True


def test_login_blocks_after_too_many_failures(client, monkeypatch):
    log_out(client)
    account("admin")
    monkeypatch.setattr(main.auth, "_login_limiter", _RateLimiter(3, 300))

    for _ in range(3):
        r = client.post(
            "/login", data={"username": "admin", "password": "wrong"}, follow_redirects=False
        )
        assert r.status_code == 401
    # The fourth attempt is refused outright...
    r = client.post(
        "/login", data={"username": "admin", "password": "wrong"}, follow_redirects=False
    )
    assert r.status_code == 429
    # ...and the correct password is refused too while the block stands.
    r = client.post(
        "/login", data={"username": "admin", "password": PASSWORD}, follow_redirects=False
    )
    assert r.status_code == 429


def test_a_good_login_clears_the_count(client, monkeypatch):
    log_out(client)
    account("admin")
    monkeypatch.setattr(main.auth, "_login_limiter", _RateLimiter(3, 300))

    for _ in range(2):
        client.post(
            "/login", data={"username": "admin", "password": "wrong"}, follow_redirects=False
        )
    ok = client.post(
        "/login", data={"username": "admin", "password": PASSWORD}, follow_redirects=False
    )
    assert ok.status_code == 303
    # Count reset: a fresh run of failures is allowed again rather than instantly
    # blocked.
    r = client.post(
        "/login", data={"username": "admin", "password": "wrong"}, follow_redirects=False
    )
    assert r.status_code == 401
