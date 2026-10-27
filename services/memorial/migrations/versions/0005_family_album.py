"""A chapter at the end for photos the family shares through the pCloud "Add to Gallery" folder.

Revision ID: 0005
Revises: 0004
"""

from datetime import UTC, datetime
from uuid import uuid4

import sqlalchemy as sa
from alembic import op

revision = "0005"
down_revision = "0004"
branch_labels = None
depends_on = None

SLUG = "family-album"


def upgrade() -> None:
    conn = op.get_bind()
    if conn.execute(sa.text("SELECT 1 FROM chapters WHERE slug = :s"), {"s": SLUG}).first():
        return
    position = conn.execute(sa.text("SELECT COALESCE(MAX(position), 0) FROM chapters")).scalar() + 10
    now = datetime.now(UTC)
    chapters = sa.table(
        "chapters",
        sa.column("id", sa.String), sa.column("slug", sa.String), sa.column("title", sa.String),
        sa.column("prompt", sa.Text), sa.column("intro", sa.Text), sa.column("position", sa.Integer),
        sa.column("hidden", sa.Boolean), sa.column("created_at", sa.DateTime(timezone=True)),
        sa.column("updated_at", sa.DateTime(timezone=True)),
    )  # fmt: skip
    op.bulk_insert(chapters, [{
        "id": uuid4().hex, "slug": SLUG, "title": "From the family album",
        "prompt": "Photographs the family has gathered and shared.", "intro": "",
        "position": position, "hidden": False, "created_at": now, "updated_at": now,
    }])  # fmt: skip


def downgrade() -> None:
    op.execute(sa.text("DELETE FROM chapters WHERE slug = :s AND id NOT IN (SELECT chapter_id FROM entries)").bindparams(s=SLUG))
