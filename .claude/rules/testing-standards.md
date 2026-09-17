# Testing standards

pytest. British English. The suite is a genuine asset — keep it green.

## Test-first

For a feature or a bug fix, write a test that **fails before** the change and
**passes after**, then keep the whole suite green. A bug fix without a regression
test isn't finished.

Where the test comes from matters as much as its order: a feature's tests are
derived from the manual entry that describes it, one test to a promise, before
the code exists to shape them (manual-first).

## How the suite runs

- **The suite runs on MariaDB, and on nothing else** — the engine production uses
  (ADR-0008). `conftest.py` raises on a missing or SQLite `DATABASE_URL` rather
  than falling back, so a run cannot quietly test a different engine.
- **The schema under test is built by the real Alembic migrations**, from an empty
  database, not by `create_all` from the models. So every run also proves the
  migrations reach head and match the models — the check that was missing when the
  fresh-install bug reached a release (ADR-0002).
- **`READ COMMITTED` is set per connection.** MariaDB defaults to REPEATABLE READ,
  under which a long-lived test session never sees the app's committed writes.
  READ COMMITTED matches how the app behaves: a fresh session per request.
- **The tests need a database to run at all.** CI provides one as a service
  container; locally it is the compose `db`. Point `DATABASE_URL` at one the tests
  may build and empty — and say so in the contributing notes, so a first-time
  contributor reads it rather than meeting it as a traceback.

## Conventions

- Name tests for the behaviour they describe; they should read like a spec.
- Prefer real code over mocks; mock only at true I/O boundaries.
- Mark tests that need a live database/service so they skip cleanly when it's
  absent, rather than fail.
