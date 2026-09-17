"""The liveness endpoint a deploy smoke check or an uptime monitor hits. It must be
public (the check has no credentials) and must actually touch the database, so a
box that is up but cannot reach MariaDB reports unhealthy rather than ok."""

from app import main
from app.db import get_db


def test_healthz_ok_when_db_reachable(client):
    r = client.get("/healthz")
    assert r.status_code == 200
    assert r.json() == {"status": "ok"}


def test_healthz_reports_503_when_db_unreachable(client):
    """A liveness check that returns 200 while the database is down is worse than
    useless -- it would let a broken deploy pass the smoke check. Force the DB
    dependency to fail and prove the route surfaces it as 503."""

    def broken_db():
        class _Boom:
            def execute(self, *_args, **_kwargs):
                raise RuntimeError("database unreachable")

        yield _Boom()

    main.app.dependency_overrides[get_db] = broken_db
    try:
        r = client.get("/healthz")
        assert r.status_code == 503
        assert r.json() == {"status": "unhealthy"}
    finally:
        main.app.dependency_overrides.pop(get_db, None)


def test_healthz_is_public_even_when_auth_is_enabled(client, monkeypatch):
    """The deploy smoke check has no credentials -- it runs before any exist for
    that box. If auth is enabled in production (it is: editing needs a login),
    an unauthenticated GET must still answer 200/503, never a login redirect."""
    monkeypatch.setattr(main.auth, "AUTH_ENABLED", True)
    r = client.get("/healthz", follow_redirects=False)
    assert r.status_code == 200
    assert r.json() == {"status": "ok"}
