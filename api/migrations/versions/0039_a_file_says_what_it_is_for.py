"""a file is attached to what it is for, rather than matched to it by name

ADR-0006 and ADR-0020. Until now a file carried tags and an item offered every
file whose tag was *contained* in one of the item's names. That reached across a
range on purpose -- one "Creative Labs Sound Blaster" tag covering the AWE32, the
16 and the Pro -- and across the whole register by accident, since a tag of "16"
is inside a great many names. It also moved a file the day somebody corrected a
maker, and left the privacy gate resting on a recomputation rather than on a fact.

So: `file_asset` names the one unit a file is about, and `file_model` names a model
every item of which is about it. Then the old matcher is run one last time here and
what it finds is written down, which is what keeps the day of the change quiet.

The backfill is general and data-driven -- every row, no named ids -- which is the
kind database-standards allows in a migration. It is also faithful rather than
clever: it preserves what the matcher got *wrong* as carefully as what it got
right, because a migration that quietly corrected the mistakes would be a migration
nobody could check. Read `/files` afterwards; it now says what each file is
attached to.

Which link a tag becomes:

- a tag that folds to an item's asset id pins the file to that unit, which is what
  it already meant;
- any other tag that reaches an item becomes a link to that item's model -- the
  catalogue key where the catalogue names the machine, the folded maker and model
  otherwise, and both where the item has both;
- a tag reaching an item with no maker and no model at all falls back to a link to
  that unit, since there is no model to name.

A tag matching nothing leaves its file unfiled, which is a state and not a loss:
the bytes are untouched and the files page says so.

MariaDB auto-commits DDL, so a failure between the two creates leaves one table
behind. That restarts safely: both creates are conditional on the table not being
there, and the backfill writes with the unique constraints in place, so running it
twice adds nothing.

Revision ID: 0039_a_file_says_what_it_is_for
Revises: 0038_items_may_be_for_sale
Create Date: 2026-09-16
"""
import sqlalchemy as sa
from alembic import op

revision = "0039_a_file_says_what_it_is_for"
down_revision = "0038_items_may_be_for_sale"
branch_labels = None
depends_on = None

CATALOGUE, NAMED = "catalogue", "named"


def fold(text):
    """filesdb.fold, copied rather than imported: a migration says what it did on
    the day it ran, and must not change meaning when the application's own folding
    is tuned."""
    return "".join((text or "").split()).lower()


def keys_for(row):
    """The folded names an item answered to under the old matcher."""
    maker = (row["manufacturer"] or "").strip()
    model = (row["model"] or "").strip()
    names = [row["name"] or "", model, f"{maker} {model}".strip(), row["asset_id"] or ""]
    return {fold(name) for name in names if fold(name)}


def upgrade():
    bind = op.get_bind()
    tables = set(sa.inspect(bind).get_table_names())

    if "file_asset" not in tables:
        op.create_table(
            "file_asset",
            sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
            sa.Column("file_id", sa.Integer(),
                      sa.ForeignKey("files.id", ondelete="CASCADE"), nullable=False),
            sa.Column("asset_id", sa.String(16), nullable=False),
            sa.UniqueConstraint("file_id", "asset_id", name="uq_file_asset_pair"),
        )
        op.create_index("ix_file_asset_file_id", "file_asset", ["file_id"])
        op.create_index("ix_file_asset_asset_id", "file_asset", ["asset_id"])

    if "file_model" not in tables:
        op.create_table(
            "file_model",
            sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
            sa.Column("file_id", sa.Integer(),
                      sa.ForeignKey("files.id", ondelete="CASCADE"), nullable=False),
            sa.Column("kind", sa.String(16), nullable=False),
            sa.Column("model_key", sa.String(160), nullable=False),
            sa.Column("label", sa.String(255), nullable=False, server_default=""),
            sa.UniqueConstraint("file_id", "kind", "model_key",
                                name="uq_file_model_triple"),
        )
        op.create_index("ix_file_model_file_id", "file_model", ["file_id"])
        op.create_index("ix_file_model_model_key", "file_model", ["model_key"])

    items = []
    for table in ("computers", "parts"):
        items += [dict(row._mapping) for row in bind.execute(sa.text(
            f"SELECT asset_id, name, manufacturer, model FROM {table}"))]
    if not items:
        return

    variants = {row[0]: (row[1] or "").strip() for row in bind.execute(
        sa.text("SELECT asset_id, model_key FROM asset_variant"))}
    tags = [dict(row._mapping) for row in bind.execute(sa.text(
        "SELECT file_id, fold FROM file_tag"))]
    if not tags:
        return

    assets, models = set(), set()
    for item in items:
        keys = keys_for(item)
        if not keys:
            continue
        own = fold(item["asset_id"])
        identities = []
        catalogue_key = variants.get(item["asset_id"], "")
        if catalogue_key:
            identities.append((CATALOGUE, catalogue_key, catalogue_key))
        maker = (item["manufacturer"] or "").strip()
        model = (item["model"] or "").strip()
        if fold(maker) or fold(model):
            identities.append((NAMED, f"{fold(maker)}|{fold(model)}",
                               " ".join(word for word in (maker, model) if word)))
        for tag in tags:
            folded = tag["fold"]
            if not folded or not any(folded in key for key in keys):
                continue
            if folded == own or not identities:
                assets.add((tag["file_id"], item["asset_id"]))
            else:
                for kind, key, label in identities:
                    models.add((tag["file_id"], kind, key, label[:255]))

    if assets:
        op.bulk_insert(sa.table(
            "file_asset",
            sa.column("file_id", sa.Integer), sa.column("asset_id", sa.String)),
            [{"file_id": f, "asset_id": a} for f, a in sorted(assets)])
    if models:
        op.bulk_insert(sa.table(
            "file_model",
            sa.column("file_id", sa.Integer), sa.column("kind", sa.String),
            sa.column("model_key", sa.String), sa.column("label", sa.String)),
            [{"file_id": f, "kind": k, "model_key": key, "label": label}
             for f, k, key, label in sorted(models)])


def downgrade():
    """Takes the links away and leaves the tags, which is what the old matcher ran
    on -- so the register goes back to offering a file wherever its tag is inside a
    name. What is lost is every link made by hand since the upgrade, including the
    corrections somebody made after reading what the backfill wrote."""
    op.drop_table("file_model")
    op.drop_table("file_asset")
