"""Guards the command shapes the backup relies on: a mysqldump of the app schema
must restore cleanly into an empty database with its rows intact. This runs
against the same MariaDB the suite uses (DATABASE_URL); it is skipped when the
dump/restore client binaries are absent so it never fails a machine that lacks
them."""
import os
import shutil
import subprocess
from urllib.parse import urlparse

import pytest
from sqlalchemy import create_engine, text

DUMP = shutil.which("mariadb-dump") or shutil.which("mysqldump")
CLIENT = shutil.which("mariadb") or shutil.which("mysql")

pytestmark = pytest.mark.skipif(
    not (DUMP and CLIENT), reason="mariadb-dump/mariadb client not installed"
)


def _dsn():
    u = urlparse(os.environ["DATABASE_URL"])
    return u.hostname, u.port or 3306, u.username, u.password or "", (u.path or "/").lstrip("/")


def test_dump_and_restore_roundtrip():
    host, port, user, pw, db = _dsn()
    assert db, "DATABASE_URL must name a database"
    env = {**os.environ, "MYSQL_PWD": pw}
    eng = create_engine(os.environ["DATABASE_URL"], future=True)
    with eng.begin() as c:
        c.execute(text("DROP TABLE IF EXISTS backup_probe"))
        c.execute(text("CREATE TABLE backup_probe (id INT PRIMARY KEY, note VARCHAR(32))"))
        c.execute(text("INSERT INTO backup_probe VALUES (1, 'keep-me')"))

    dump = subprocess.run(
        [DUMP, "-h", host, "-P", str(port), "-u", user, db, "backup_probe"],
        env=env, capture_output=True, text=True, check=True,
    ).stdout

    with eng.begin() as c:
        c.execute(text("DROP TABLE backup_probe"))

    subprocess.run(
        [CLIENT, "-h", host, "-P", str(port), "-u", user, db],
        input=dump, env=env, text=True, check=True,
    )

    with eng.connect() as c:
        row = c.execute(text("SELECT note FROM backup_probe WHERE id=1")).scalar_one()
    assert row == "keep-me"

    with eng.begin() as c:
        c.execute(text("DROP TABLE backup_probe"))
