# Database standards

MariaDB in production; SQLAlchemy + Alembic. British English.

## Models & sessions

- Models are SQLAlchemy declarative classes on the single `Base` in
  `api/app/db.py`. Keep them typed.
  - *Adopt next:* SQLAlchemy 2.0 typed ORM (`Mapped[...]` + `mapped_column`), so
    the models are covered by mypy strict.
- The engine and session come from `api/app/db.py` and read the URL from
  `DATABASE_URL` (the environment) — **never build an engine ad hoc**. Routes take
  a session via the `get_db` dependency and don't own its lifecycle.
- Use the ORM / parameterised queries only. Never build SQL by string
  interpolation.

## Migrations — the important part

- **Every schema change is an Alembic migration.** Never run `create_all`
  against a real database, never hand-edit a deployed schema.
- **A migration must not assume specific data exists.** This is the rule behind
  the fresh-install bug (ADR-0002). A schema change (DDL) and a one-off data tidy
  are two different jobs:
  - *Schema changes and general, data-driven backfills* belong in the migration
    (e.g. "for every row, move the old free-text column into the new typed one").
  - *One-off corrections to specific, named rows in one database* (e.g. "fix
    RH-0056") do **not** belong in the shared migration history — they mean
    nothing on any other database and break a fresh install. Put them in a
    `tools/` one-off script, or make them a no-op when the row is absent
    (`WHERE EXISTS` / an existence check).
  - Remember MariaDB **auto-commits DDL** and can't roll it back, so a migration
    that fails partway leaves a half-applied schema. Keep each migration's steps
    such that a failure can't wedge a restart.
- Every migration has a working `downgrade`.
- Autogenerate, then **review** — don't trust autogenerate blind.
- Migrations are applied via `alembic upgrade head` on container start
  (`entrypoint.sh`) and are exercised in CI against real MariaDB (testing-standards).
- `migrations/env.py` reads the URL from the environment and targets
  `Base.metadata`.

## Engine notes

- MariaDB has no `JSONB`; use `JSON`. There is no second engine to keep a model
  portable for -- the suite runs on MariaDB alone (ADR-0008, testing-standards) --
  so an engine-specific type is a decision about the product rather than about the
  tests.
