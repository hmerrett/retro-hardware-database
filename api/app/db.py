"""Database engine + session. MariaDB, from DATABASE_URL."""

import os
from collections.abc import Iterator

from sqlalchemy import create_engine
from sqlalchemy.orm import DeclarativeBase, Session, sessionmaker


def _resolve_database_url(url: str) -> str:
    """Where the database is. It used to fall back to the compose service on a
    guessable password, which compose itself never let anybody meet: DB_PASSWORD is
    `${VAR:?message}`, so a missing one stops the stack before this line runs.
    Nothing outside compose has that guard -- Kubernetes hands over whatever the
    Secret holds, and a missing key is simply an unset variable -- so there the
    default was not a convenience but a silent fallback onto retro:retro, on a host
    called db, with nothing said. Required explicitly, in the same spirit as the
    compose file (docker-environments)."""
    if url:
        return url
    raise RuntimeError(
        "DATABASE_URL must be set. The compose file supplies it; set it by hand if "
        "the app is started any other way, e.g. "
        "mysql+pymysql://retro:PASSWORD@db:3306/retro"
    )


DATABASE_URL = _resolve_database_url(os.getenv("DATABASE_URL", ""))

engine = create_engine(DATABASE_URL, pool_pre_ping=True, future=True)
SessionLocal = sessionmaker(bind=engine, autoflush=False, future=True)


class Base(DeclarativeBase):
    """The one declarative base. A class rather than ``declarative_base()`` because
    that is the form a type checker can follow: ``Mapped[...]`` on a model means
    something to mypy only when it can see what the model inherits from."""


def get_db() -> Iterator[Session]:
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
