"""Test fixtures: the whole app against a MariaDB database.

The engine is built from DATABASE_URL when app.db is imported, so the environment
has to be set before anything from app is imported -- hence the assignments above
the imports. The suite runs on MariaDB, the engine production uses, and builds its
schema by running the real Alembic migrations, so every run also proves the
migrations reach head and match the models. Point DATABASE_URL at a MariaDB
database the tests may build and empty (CI provides one; locally, the compose db).
"""
import os
import re
import tempfile
from pathlib import Path

_TMP = Path(tempfile.mkdtemp(prefix="rhdb-test-"))
_DB_URL = os.environ.get("DATABASE_URL", "")
if not _DB_URL or _DB_URL.startswith("sqlite"):
    raise RuntimeError(
        "The test suite runs against MariaDB. Set DATABASE_URL to a MariaDB "
        "database the tests can build and empty, e.g. "
        "mysql+pymysql://root:pw@db:3306/retro_test"
    )
os.environ["RHDB_IMAGES_DIR"] = str(_TMP / "images")
# An empty branding directory, which is what an installation that has not put its
# own logo in has. It must exist before the app is imported: the static mount is
# built at start-up and only looks here if there is a here to look in.
(_TMP / "branding").mkdir(parents=True, exist_ok=True)
os.environ["RHDB_BRANDING_DIR"] = str(_TMP / "branding")
os.environ["RHDB_FILES_DIR"] = str(_TMP / "files")
os.environ["RHDB_BASE_URL"] = "https://example.test"
os.environ.pop("RHDB_AUTH_USER", None)
os.environ.pop("RHDB_AUTH_PASSWORD", None)
# The suite runs with no login on purpose -- most of it is about what the owner can
# do, and popping the credentials is how it gets to be the owner. So it says so
# (ADR-0019), which is exactly what RHDB_OPEN is for: without it every page rendered
# in every test would carry the "no login" banner, and a few hundred assertions
# about page content would be reading a misconfiguration warning that is not one.
# The banner's own tests set the flag they are about rather than relying on this.
os.environ["RHDB_OPEN"] = "1"

import pytest
from alembic import command
from alembic.config import Config
from fastapi.testclient import TestClient
from sqlalchemy import event, text

from app import main
from app.db import Base, SessionLocal, engine

_ALEMBIC_INI = Path(__file__).resolve().parent.parent / "alembic.ini"


@event.listens_for(engine, "connect")
def _read_committed(dbapi_connection, _record):
        """Many tests hold the long-lived `db` fixture session and then make writes
        through the app's own session (the `client`). Under MariaDB's default
        REPEATABLE READ the `db` session keeps reading the snapshot its transaction
        opened with and never sees those writes. READ COMMITTED matches how the app
        actually behaves -- a fresh session per request -- so the observing session
        sees committed writes. SQLite's visibility model made this moot."""
        cur = dbapi_connection.cursor()
        cur.execute("SET SESSION TRANSACTION ISOLATION LEVEL READ COMMITTED")
        cur.close()


def _reset_and_migrate():
    """Empty the database, then bring it to head with the real migrations, so the
    schema under test is the one the migrations produce."""
    with engine.begin() as conn:
        conn.execute(text("SET FOREIGN_KEY_CHECKS=0"))
        for (name,) in conn.execute(text("SHOW TABLES")).all():
            conn.execute(text(f"DROP TABLE IF EXISTS `{name}`"))
        conn.execute(text("SET FOREIGN_KEY_CHECKS=1"))
    cfg = Config(str(_ALEMBIC_INI))
    # script_location is relative in alembic.ini and would otherwise resolve from
    # the working directory (the suite runs from the repo root, not api/).
    cfg.set_main_option("script_location", str(_ALEMBIC_INI.parent / "migrations"))
    command.upgrade(cfg, "head")


def served(client, page):
    """A page together with the static CSS/JS it links, so an assertion about a
    style or a script holds whether that content is inline or in a static file.
    Lets these tests keep checking what actually reaches the browser as the CSS
    and JS move out of the templates."""
    out = [page]
    for url in re.findall(r'(?:href|src)="(/static/[^"?#]+\.(?:css|js))', page):
        out.append(client.get(url).text)
    return "\n".join(out)


@pytest.fixture(scope="session", autouse=True)
def _schema():
    _reset_and_migrate()
    yield


@pytest.fixture(autouse=True)
def _clean_tables():
    """Every test starts with an empty register."""
    yield
    with engine.begin() as conn:
        for table in reversed(Base.metadata.sorted_tables):
            conn.execute(table.delete())


@pytest.fixture(autouse=True)
def _reset_login_limiter():
    """The login limiter is module-level, shared state; clear it so one test's
    failed logins don't count against another's."""
    # main.auth, not main: the gate and the login route read these from the auth
    # module's own globals, so that is the only place a patch or a reset bites.
    main.auth._login_limiter._hits.clear()
    yield


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


@pytest.fixture
def a_page_of_everything(client, computer, part):
    """One machine with a part on it, so the forms, the item pages and the lists
    all render the controls they only have when there is something to show."""
    made = computer(manufacturer="Amstrad", model="PC1512")
    card = part(manufacturer="Trident", model="TVGA8900", type="video",
                computer_id=made["asset_id"])
    return [
        "/", "/machines", "/projects", "/projects/new", "/files", "/stats", "/for-sale",
        f"/computers/{made['asset_id']}", f"/computers/{made['asset_id']}/edit",
        "/computers/new", "/parts/new",
        f"/parts/{card['asset_id']}", f"/parts/{card['asset_id']}/edit",
    ]
