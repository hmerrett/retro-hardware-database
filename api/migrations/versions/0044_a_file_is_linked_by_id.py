"""a file is linked to the things it is for by their asset ids, and nothing else

ADR-0028. A file could be attached to one unit (`file_asset`) or to every item of a
model (`file_model`), and it carried tags that had decided nothing since 0039. This
keeps the first and retires the other two, moving what they held across so that no
item page loses a file on the day:

- every model link becomes a link to each item that answers to that model now --
  by catalogue key through `asset_variant`, or by the maker and model folded and
  joined -- held or disposed, since a disposed item's page shows its files too;
- a tag that only repeated what the file was linked to, read the way the name
  matcher read tags (folded, and found inside a model link's label or equal to a
  linked asset id), is dropped: the links say it. Any other tag is kept, added to
  the file's note after whatever the note already said.

The backfill is general and data-driven -- every row, no named ids -- which is the
kind database-standards allows in a migration. On a fresh install there is nothing
to move.

MariaDB auto-commits DDL, so every step is safe to run twice. Links are written
only where the pair is not there already; a tag already in a note is not added to
it again; each drop is conditional on the table still being there. The tags go
before the model links, because deciding which tags repeat a link reads the links.
A failure partway restarts from where it stopped.

Revision ID: 0044_a_file_is_linked_by_id
Revises: 0043_where_a_thing_is_kept
Create Date: 2026-09-24
"""
import sqlalchemy as sa
from alembic import op

revision = "0044_a_file_is_linked_by_id"
down_revision = "0043_where_a_thing_is_kept"
branch_labels = None
depends_on = None

NOTE_MAX = 255


def fold(text):
    """filesdb.fold, copied rather than imported: a migration says what it did on
    the day it ran, and must not change meaning when the application's folding is
    tuned."""
    return "".join((text or "").split()).lower()


def named_key(maker, model):
    return f"{fold(maker)}|{fold(model)}"


def upgrade():
    bind = op.get_bind()
    tables = set(sa.inspect(bind).get_table_names())
    links = {tuple(row) for row in bind.execute(sa.text(
        "SELECT file_id, asset_id FROM file_asset"))}
    labels = {}

    if "file_model" in tables:
        items = []
        for table in ("computers", "parts"):
            items += [dict(row._mapping) for row in bind.execute(sa.text(
                f"SELECT asset_id, manufacturer, model FROM {table}"))]
        by_name = {}
        for item in items:
            if fold(item["manufacturer"]) or fold(item["model"]):
                by_name.setdefault(named_key(item["manufacturer"], item["model"]),
                                   []).append(item["asset_id"])
        by_catalogue = {}
        for aid, key in bind.execute(sa.text("SELECT asset_id, model_key FROM asset_variant")):
            if (key or "").strip():
                by_catalogue.setdefault(key.strip(), []).append(aid)
        wanted = set()
        for file_id, kind, key, label in bind.execute(sa.text(
                "SELECT file_id, kind, model_key, label FROM file_model")):
            labels.setdefault(file_id, []).append(fold(label))
            reach = by_catalogue if kind == "catalogue" else by_name
            wanted |= {(file_id, aid) for aid in reach.get(key, [])}
        new = sorted(wanted - links)
        if new:
            op.bulk_insert(sa.table(
                "file_asset",
                sa.column("file_id", sa.Integer), sa.column("asset_id", sa.String)),
                [{"file_id": f, "asset_id": a} for f, a in new])
        links |= wanted

    if "file_tag" in tables:
        linked = {}
        for file_id, aid in links:
            linked.setdefault(file_id, set()).add(fold(aid))
        tags = {}
        for file_id, tag in bind.execute(sa.text(
                "SELECT file_id, tag FROM file_tag ORDER BY id")):
            tags.setdefault(file_id, []).append(tag)
        notes = dict(bind.execute(sa.text("SELECT id, note FROM files")).all())
        for file_id, written in tags.items():
            note = (notes.get(file_id) or "").strip()
            kept = [
                tag for tag in written
                if fold(tag)
                and not any(fold(tag) in label for label in labels.get(file_id, []))
                and fold(tag) not in linked.get(file_id, set())
                # A tag the note already says is not said twice, which is what
                # makes a second run after a failure add nothing.
                and fold(tag) not in fold(note)
            ]
            if kept:
                note = " — ".join(part for part in (note, ", ".join(kept)) if part)
                bind.execute(sa.text("UPDATE files SET note = :n WHERE id = :i"),
                             {"n": note[:NOTE_MAX], "i": file_id})
        op.drop_table("file_tag")

    if "file_model" in tables:
        op.drop_table("file_model")


def downgrade():
    """Puts the two tables back, empty, which is the shape 0043 expects. What they
    held is not recoverable from what is left -- a link to five cards does not say
    it was once a link to their model -- so a downgraded register offers each file
    on the items it is linked to, which is what it already showed."""
    op.create_table(
        "file_tag",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column("file_id", sa.Integer(), nullable=False),
        sa.Column("tag", sa.String(120), nullable=False),
        sa.Column("fold", sa.String(120), nullable=False),
        sa.ForeignKeyConstraint(["file_id"], ["files.id"], ondelete="CASCADE"),
    )
    op.create_index("ix_file_tag_file_id", "file_tag", ["file_id"])
    op.create_index("ix_file_tag_fold", "file_tag", ["fold"])
    op.create_table(
        "file_model",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column("file_id", sa.Integer(),
                  sa.ForeignKey("files.id", ondelete="CASCADE"), nullable=False),
        sa.Column("kind", sa.String(16), nullable=False),
        sa.Column("model_key", sa.String(160), nullable=False),
        sa.Column("label", sa.String(255), nullable=False, server_default=""),
        sa.UniqueConstraint("file_id", "kind", "model_key", name="uq_file_model_triple"),
    )
    op.create_index("ix_file_model_file_id", "file_model", ["file_id"])
    op.create_index("ix_file_model_model_key", "file_model", ["model_key"])
