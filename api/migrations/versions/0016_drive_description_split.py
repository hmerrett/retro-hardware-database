"""a drive's description, split into the fields that now ask for it

Originally split the free-text description into Form factor and Size on eight
specific drives in the original database. Those were one-off, per-asset
corrections, so they have been removed from the migration history (a one-off tidy
of specific rows belongs with its own database, not the shared schema history; see
ADR-0002). They were applied to the live database by the first run of this
migration. The drivedb parser fix that accompanied it lives in the app code, not
here, so it is unaffected.

The revision is kept as a no-op so the migration chain and the applied history
stay intact.

Revision ID: 0016_drive_description_split
Revises: 0015_bezel_yellowing
Create Date: 2026-08-07
"""
revision = "0016_drive_description_split"
down_revision = "0015_bezel_yellowing"
branch_labels = None
depends_on = None


def upgrade():
    pass


def downgrade():
    pass
