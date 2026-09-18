"""Database engine + session. MariaDB, from DATABASE_URL (defaulting to the docker
service)."""

import os

from sqlalchemy import create_engine
from sqlalchemy.orm import DeclarativeBase, sessionmaker

DATABASE_URL = os.getenv("DATABASE_URL", "mysql+pymysql://retro:retro@db:3306/retro")

engine = create_engine(DATABASE_URL, pool_pre_ping=True, future=True)
SessionLocal = sessionmaker(bind=engine, autoflush=False, future=True)


class Base(DeclarativeBase):
    """The one declarative base. A class rather than ``declarative_base()`` because
    that is the form a type checker can follow: ``Mapped[...]`` on a model means
    something to mypy only when it can see what the model inherits from."""


def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
