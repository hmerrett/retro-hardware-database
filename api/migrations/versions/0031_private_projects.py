"""one list instead of two: the queue becomes projects, and a project can be private

0029 gave computers and parts a `project` flag and a `project_note`, and 0030 gave
the register a Project of its own. They were two sizes of one idea sharing a page
-- a thing noticed, and a piece of work committed to -- and the promotion from one
to the other was a thing you did by hand and by retyping.

So the flag goes and the project stays. Anything flagged becomes a project of its
own with the item attached and the note as its first job, which is what somebody
would have made of it by hand.

What the flag also carried was privacy. It was the one thing on a public item page
kept back from a visitor, and folding it into a public project would have published
it -- so `projects.private` arrives here in the same breath, and every project
converted from a flag is created private. A project is now the one record in the
register that can be either: what is being built is worth reading about, and what
is wrong with a machine is not finished being decided.

The ids for the new projects are allocated here in the same alphabet the app uses
(app/ids.py: no I, L or O), checked against all three tables. Doing it in SQL
rather than importing the app keeps the migration runnable against a database
whose code has already moved on.

Revision ID: 0031_private_projects
Revises: 0030_projects
Create Date: 2026-09-04
"""
import secrets
import string

import sqlalchemy as sa
from alembic import op

revision = "0031_private_projects"
down_revision = "0030_projects"
branch_labels = None
depends_on = None

# app/ids.py's alphabet, repeated rather than imported: a migration that imports
# the app is a migration that stops running the day the app changes shape.
ALPHABET = "".join(c for c in string.ascii_uppercase + string.digits
                   if c not in set("ILO"))


def _taken(bind):
    ids = set()
    for table in ("computers", "parts", "projects"):
        ids |= {r[0] for r in bind.execute(sa.text(f"SELECT asset_id FROM {table}"))}
    return ids


def _new_id(taken):
    for _ in range(10000):
        candidate = "RH-" + "".join(secrets.choice(ALPHABET) for _ in range(4))
        if candidate not in taken:
            taken.add(candidate)
            return candidate
    raise RuntimeError("could not allocate a free asset id")


def upgrade():
    op.add_column("projects",
                  sa.Column("private", sa.Boolean(), nullable=False,
                            server_default="0"))
    bind = op.get_bind()
    taken = _taken(bind)
    for table in ("computers", "parts"):
        rows = bind.execute(sa.text(
            f"SELECT asset_id, name, manufacturer, model, project_note "
            f"FROM {table} WHERE project = 1")).all()
        for asset_id, name, maker, model, note in rows:
            # What the item is called, by the same rule display_name follows: its
            # own name, else the maker and model, else the tag it is known by.
            called = (name or " ".join(x for x in (maker, model) if x).strip()
                      or asset_id)
            pid = _new_id(taken)
            bind.execute(sa.text(
                "INSERT INTO projects (asset_id, name, status, summary, notes,"
                " private) VALUES (:i, :n, 'planned', '', '', 1)"),
                {"i": pid, "n": called[:255]})
            bind.execute(sa.text(
                "INSERT INTO project_asset (project_id, asset_id, note)"
                " VALUES (:p, :a, '')"), {"p": pid, "a": asset_id})
            if (note or "").strip():
                bind.execute(sa.text(
                    "INSERT INTO project_task (project_id, text, done)"
                    " VALUES (:p, :t, 0)"), {"p": pid, "t": note.strip()})
            # The history the flag deliberately never wrote, written now: the plan
            # has stopped being private-by-omission and is a project with a page,
            # so there is no longer a reason for the register to be quiet about it.
            bind.execute(sa.text(
                "INSERT INTO log_entry (asset_id, created_at, kind, message)"
                " VALUES (:a, NOW(), 'change', :m)"),
                {"a": asset_id, "m": f"wanted for {called} ({pid})"})
    for table in ("computers", "parts"):
        op.drop_column(table, "project")
        op.drop_column(table, "project_note")


def downgrade():
    """Puts the columns back, empty.

    The projects made from them are left alone rather than being unpicked. A
    project that has since grown a second item, three jobs and something on order
    is not a flag any more, and turning it back into one would throw away
    everything it had become -- so going back gives you the columns and leaves the
    work where it is."""
    for table in ("computers", "parts"):
        op.add_column(table, sa.Column("project", sa.Boolean(), nullable=False,
                                       server_default="0"))
        op.add_column(table, sa.Column("project_note", sa.Text(), nullable=False))
    op.drop_column("projects", "private")
