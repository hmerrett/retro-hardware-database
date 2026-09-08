# 0008 — The suite runs on MariaDB, and builds its schema from the migrations

**Status:** Accepted
**Date:** 2026-09-08

## Context

`testing-standards` held this open: whether to drop SQLite and run everything on
MariaDB — simpler and higher fidelity, but the tests then need a database to run
at all. The suite had run on SQLite by default for speed, building its schema
from the models, with CI additionally running it on MariaDB.

Two engines meant two behaviours to hold in mind, and the differences were not
cosmetic. Dialect and date functions diverge. So does isolation: MariaDB defaults
to REPEATABLE READ, so a long-lived test session keeps reading the snapshot its
transaction opened with and never sees the app's committed writes, which is why
the suite sets READ COMMITTED to match a fresh session per request. SQLite's
visibility model made that moot — so a test could pass on SQLite for a reason
that does not hold in production.

The sharper problem was coverage. A schema built by `create_all` from the models
never exercises the migration path, and that is how the fresh-install bug
(ADR-0002) reached a release: the models were right and the migrations were not.

This decision has in fact already been taken in the code — `conftest.py` refuses
a SQLite URL and runs the real migrations — but it was never recorded, so it
existed only as a fact about a file. That is the second time in this project the
reasoning for a decision lived somewhere other than `adr/` (see ADR-0006), which
is what ADR-0001 exists to prevent. This record catches it up.

## Decision

The suite runs on MariaDB, and on nothing else. `conftest.py` raises on a missing
or SQLite `DATABASE_URL` rather than falling back, so a run cannot quietly test a
different engine than the one that will serve the request.

The schema under test is built by running the real Alembic migrations from an
empty database, not by `create_all` from the models. Every run therefore proves
what CI alone used to: that the migrations reach head, and that the schema they
produce is the one the models expect.

READ COMMITTED is set per connection, for the reason above.

The cost is accepted deliberately: `pytest` no longer works on a bare checkout,
because it needs a database. CI provides one as a service container; locally it is
the compose `db`.

## Consequences

- One engine to reason about. A passing test means passing on the engine
  production uses, not on an approximation of it.
- The migration path is exercised on every run rather than only in CI, so
  ADR-0002's class of bug cannot reach a release through a green suite.
- `pytest` needs `DATABASE_URL` pointed at a MariaDB database it may build and
  empty. That is a barrier to a first-time contributor and has to be said plainly
  in the contributing notes, not discovered from a traceback.
- Slower than SQLite. Accepted: for a suite this size, fidelity is worth more
  than the seconds.
- Revisit if a full reset-and-migrate per run becomes the bottleneck. The answer
  then is a faster reset, not a second engine.
