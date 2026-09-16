"""Alembic environment. Reuses the app's engine + metadata so migrations and the
running app always agree on the schema, and reads the URL from DATABASE_URL."""
from logging.config import fileConfig

from alembic import context

from app.db import Base, engine
# Import models so their tables register on Base.metadata for autogenerate.
from app import models
_ = models

config = context.config
if config.config_file_name is not None:
    # disable_existing_loggers=False, and it matters more than it looks.
    #
    # fileConfig defaults to True, which switches off every logger that is not named
    # in alembic.ini -- and alembic.ini names root, sqlalchemy and alembic. In
    # production that costs nothing, because entrypoint.sh runs `alembic upgrade
    # head` as its own process and then execs uvicorn, so the app's loggers are
    # created afterwards in a process this never touched.
    #
    # In the test suite it is a trap. conftest brings the schema up in-process, by
    # which time `app.main` already exists, so it was disabled for the whole run and
    # every line the app logged went nowhere. Nothing failed -- logging that
    # silently stops is the kind of thing that fails by being absent -- and it was
    # found only when a test tried to assert on the startup warning that says this
    # site has no login (ADR-0019) and caught nothing at all.
    fileConfig(config.config_file_name, disable_existing_loggers=False)

target_metadata = Base.metadata


def run_migrations_offline():
    context.configure(url=str(engine.url), target_metadata=target_metadata,
                      literal_binds=True, dialect_opts={"paramstyle": "named"})
    with context.begin_transaction():
        context.run_migrations()


def run_migrations_online():
    with engine.connect() as connection:
        context.configure(connection=connection, target_metadata=target_metadata)
        with context.begin_transaction():
            context.run_migrations()


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
