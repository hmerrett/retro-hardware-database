"""The models describe the schema the migrations build, and nothing else.

conftest brings the database to head with the real migrations, and the rest of
the suite then queries it through the models -- which proves the two agree only
where a test happens to touch. A column the models call NOT NULL and the
migrations left nullable fails nothing until somebody stores a None.

So this asks Alembic the question directly: given the migrated database and
``Base.metadata``, what would ``alembic revision --autogenerate`` write? The
answer has to be nothing. It is what held the move to ``Mapped[...]`` to its
promise -- that annotating a column changes what mypy can see and not what
MariaDB stores -- since ``Mapped[str]`` without ``Optional`` means NOT NULL, and
most of these columns never said either way.

Server defaults are left out of the comparison on purpose. Several migrations
gave a new NOT NULL column a server default so that the rows already there had
something to hold, and the models state the same default on the Python side
instead; MariaDB also hands ``''`` back quoted, which Alembic reads as a change.
Neither is a difference in what a row may contain.
"""

from alembic.autogenerate import compare_metadata
from alembic.migration import MigrationContext

from app import models
from app.db import Base, engine

_ = models


def _what_autogenerate_would_write():
    with engine.connect() as conn:
        ctx = MigrationContext.configure(conn, opts={"compare_type": True})
        return compare_metadata(ctx, Base.metadata)


def test_autogenerate_against_the_migrated_schema_finds_nothing_to_do():
    assert _what_autogenerate_would_write() == []


def test_a_column_that_changes_nullability_is_caught():
    """The check above is only worth having if it can fail. Flip one column the
    way a careless ``Mapped[str]`` would and see that it is reported."""
    column = models.Computer.__table__.c.notes
    assert column.nullable, "pick a column the schema leaves nullable"
    column.nullable = False
    try:
        diff = _what_autogenerate_would_write()
    finally:
        column.nullable = True
    assert any(d[0][0] == "modify_nullable" and d[0][3] == "notes" for d in diff if d)
