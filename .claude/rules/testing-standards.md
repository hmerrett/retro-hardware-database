# Testing standards

pytest. British English. The suite is a genuine asset — keep it green.

## Test-first

For a feature or a bug fix, write a test that **fails before** the change and
**passes after**, then keep the whole suite green. A bug fix without a regression
test isn't finished.

## How the suite runs

- **Unit tests run on SQLite** by default — fast, no server, `pytest` just works.
  `conftest.py` builds the schema from the models and honours a pre-set
  `DATABASE_URL` so the same suite can also run on MariaDB.
- **The real engine is MariaDB**, and the two differ (dialect, date functions,
  and transaction isolation — MariaDB defaults to REPEATABLE READ, which is why
  the tests set READ COMMITTED to match how the app behaves per request). So:
- **CI runs the suite on MariaDB too**, and **runs the migrations** there
  (`alembic upgrade head` from an empty database) — the SQLite run alone never
  exercises the migration path, which is how the fresh-install bug slipped
  through. See workflow-and-ci.
  - *Decision still open:* whether to drop SQLite and run everything on MariaDB
    (simpler, higher fidelity, but tests then need a database to run at all). If
    taken, record it as an ADR and have the tests build their schema by running
    the real migrations.

## Conventions

- Name tests for the behaviour they describe; they should read like a spec.
- Prefer real code over mocks; mock only at true I/O boundaries.
- Mark tests that need a live database/service so they skip cleanly when it's
  absent, rather than fail.
