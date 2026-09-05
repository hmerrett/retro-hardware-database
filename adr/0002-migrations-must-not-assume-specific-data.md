# 0002 — Migrations must not assume specific data

**Status:** Accepted
**Date:** 2026-09-05

## Context

A clean `docker compose up` from the README crash-looped: `alembic upgrade head`
failed on an empty database. Several migrations carried data-cleanup steps
hard-coded to specific assets in the maintainer's own collection (e.g.
`INSERT INTO part_port ... VALUES ('RH-0015', ...)`). On an empty database those
parent rows don't exist, so the insert failed a foreign-key check. Because MariaDB
auto-commits DDL, a migration that added a column and then failed left the column
behind, so every restart then died on "duplicate column" — it didn't even fail
cleanly. The result: nobody but the maintainer, on their existing database, could
stand the app up.

The underlying cause is mixing two different jobs in one migration: a **schema
change**, and a **one-off correction to named rows in one particular database**.

## Decision

Migrations may contain schema changes (DDL) and **general, data-driven backfills**
required by them (transformations that apply to whatever rows exist). They must
**not** contain one-off corrections to specific, named rows. Such corrections
either:

- go in a `tools/` script run manually against the database that needs them, or
- are written to be a no-op when the target row is absent (an existence check /
  `WHERE EXISTS`), so a fresh database skips them.

Keep each migration's steps such that a partial failure can't wedge a restart
(mind MariaDB's non-transactional DDL).

## Consequences

- A fresh install migrates cleanly to head; the documented quick-start works for
  anyone.
- The migration history means the same thing on every database, not just the
  maintainer's.
- Existing databases are unaffected — where the rows exist, guarded steps behave
  exactly as before.
- Enforced by a CI job that runs `alembic upgrade head` against an empty MariaDB
  (see `.claude/rules/testing-standards.md`).
