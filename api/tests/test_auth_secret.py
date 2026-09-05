"""The session-cookie signing key.

It used to fall back to sha256 of the credentials when RHDB_SECRET_KEY was blank.
The signed cookie's payload is a constant, so that made a leaked cookie an offline
oracle for the password, with no rate limit to slow the guessing. The key must be
independent of the credentials: set explicitly when auth is on, throwaway when the
app runs open.
"""
import pytest

from app.main import _resolve_secret_key


def test_uses_the_configured_secret_when_present():
    assert _resolve_secret_key("sekret", auth_enabled=True) == "sekret"


def test_requires_a_secret_when_auth_is_enabled():
    with pytest.raises(RuntimeError, match="RHDB_SECRET_KEY"):
        _resolve_secret_key("", auth_enabled=True)


def test_generates_a_throwaway_secret_when_auth_is_disabled():
    # Open (local dev): the cookie gates nothing, so a random per-process key is
    # fine -- and must not be derived from anything guessable.
    first = _resolve_secret_key("", auth_enabled=False)
    second = _resolve_secret_key("", auth_enabled=False)
    assert first and second and first != second
