"""Let the family word the heading above her name and the website title.

Revision ID: 0004
Revises: 0003
"""

import sqlalchemy as sa
from alembic import op

revision = "0004"
down_revision = "0003"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "profile", sa.Column("heading", sa.String(length=120), nullable=False, server_default="In loving memory")
    )
    op.add_column("profile", sa.Column("site_title", sa.String(length=160), nullable=False, server_default=""))


def downgrade() -> None:
    op.drop_column("profile", "site_title")
    op.drop_column("profile", "heading")
