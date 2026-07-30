"""Test fixtures: the whole app against a throwaway SQLite database.

The engine is built from DATABASE_URL when app.db is imported, so the environment
has to be set before anything from app is imported -- hence the assignments above
the imports. Tables come from the models rather than from Alembic: the migrations
are deliberately MariaDB-specific (REGEXP, STR_TO_DATE, MODIFY), and what these
tests check is the app's behaviour, not the migration path.
"""
import os
import tempfile
from pathlib import Path

_TMP = Path(tempfile.mkdtemp(prefix="rhdb-test-"))
os.environ["DATABASE_URL"] = f"sqlite:///{_TMP / 'test.db'}"
os.environ["RHDB_IMAGES_DIR"] = str(_TMP / "images")
os.environ["RHDB_BASE_URL"] = "https://example.test"
os.environ.pop("RHDB_AUTH_USER", None)
os.environ.pop("RHDB_AUTH_PASSWORD", None)

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import event

from app import main
from app.db import Base, SessionLocal, engine


@event.listens_for(engine, "connect")
def _sqlite_foreign_keys(dbapi_connection, _record):
    """SQLite ignores foreign keys unless asked, and ON DELETE SET NULL is one of
    the things under test."""
    dbapi_connection.execute("PRAGMA foreign_keys=ON")


@pytest.fixture(scope="session", autouse=True)
def _schema():
    Base.metadata.create_all(engine)
    yield
    Base.metadata.drop_all(engine)


@pytest.fixture(autouse=True)
def _clean_tables():
    """Every test starts with an empty register."""
    yield
    with engine.begin() as conn:
        for table in reversed(Base.metadata.sorted_tables):
            conn.execute(table.delete())


@pytest.fixture
def client():
    with TestClient(main.app) as c:
        yield c


@pytest.fixture
def db():
    session = SessionLocal()
    try:
        yield session
    finally:
        session.close()


@pytest.fixture
def computer(client):
    """A saved computer, as the API creates one."""
    def make(**fields):
        body = {"manufacturer": "Acme", "model": "Test"} | fields
        r = client.post("/api/computers", json=body)
        assert r.status_code == 200, r.text
        return r.json()
    return make


@pytest.fixture
def part(client):
    def make(**fields):
        body = {"type": "other", "model": "Widget"} | fields
        r = client.post("/api/parts", json=body)
        assert r.status_code == 200, r.text
        return r.json()
    return make
