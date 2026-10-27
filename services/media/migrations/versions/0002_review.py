"""Review status for photos shared through the pCloud "Add to Gallery" folder.

Revision ID: 0002
Revises: 0001
"""

import sqlalchemy as sa
from alembic import op

revision = "0002"
down_revision = "0001"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("media_objects", sa.Column("review_status", sa.String(length=16), nullable=False, server_default=""))
    op.add_column("media_objects", sa.Column("reviewed_by", sa.String(length=32), nullable=True))
    op.add_column("media_objects", sa.Column("reviewed_at", sa.DateTime(timezone=True), nullable=True))
    op.create_index("ix_media_objects_review_status", "media_objects", ["review_status"])


def downgrade() -> None:
    op.drop_index("ix_media_objects_review_status", table_name="media_objects")
    op.drop_column("media_objects", "reviewed_at")
    op.drop_column("media_objects", "reviewed_by")
    op.drop_column("media_objects", "review_status")
