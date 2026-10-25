"""Seed Martha's profile and the default life chapters.

Revision ID: 0002
Revises: 0001
"""

from datetime import UTC, datetime
from uuid import uuid4

import sqlalchemy as sa
from alembic import op

revision = "0002"
down_revision = "0001"
branch_labels = None
depends_on = None

CHAPTERS = [
    ("roots", "Roots", "Where her story began: her parents, her home village, the family she was born into."),
    ("growing-up", "Growing Up", "Her childhood and schooling, the friends she made and the young woman she became."),
    ("marriage", "Love and Marriage", "How she met her husband, their wedding, and the home they built together."),
    ("mother", "A Mother's Hands", "How Martha raised Anita and her siblings: the meals, the lessons, the discipline and the laughter."),
    ("faith", "Faith", "Her church, her prayers, the hymns she loved and the faith that carried her."),
    ("work", "Work and Service", "The work she did, the farm or business she kept, and the ways she served others."),
    ("community", "Friends and Community", "Her women's group, her neighbours, and the people whose lives she touched."),
    ("final-years", "Her Final Years", "Her later years, her grandchildren, and the people who cared for her at the end."),
    ("farewell", "The Farewell", "The burial service where family and friends gathered to lay her to rest."),
]


def upgrade() -> None:
    now = datetime.now(UTC)
    profile = sa.table(
        "profile",
        sa.column("id", sa.String), sa.column("full_name", sa.String), sa.column("known_as", sa.String),
        sa.column("born", sa.String), sa.column("died", sa.String), sa.column("birthplace", sa.String),
        sa.column("resting_place", sa.String), sa.column("epitaph", sa.Text), sa.column("service_date", sa.String),
        sa.column("service_venue", sa.String), sa.column("stream_url", sa.String),
        sa.column("created_at", sa.DateTime(timezone=True)), sa.column("updated_at", sa.DateTime(timezone=True)),
    )
    op.bulk_insert(profile, [{
        "id": "main", "full_name": "Martha Kemunto Ongosi", "known_as": "Mother of Anita",
        "born": "", "died": "", "birthplace": "", "resting_place": "",
        "epitaph": "“Blessed are those who mourn, for they will be comforted.” — Matthew 5:4",
        "service_date": "", "service_venue": "", "stream_url": "https://www.youtube.com/live/wOcYdCbTtgU",
        "created_at": now, "updated_at": now,
    }])
    chapters = sa.table(
        "chapters",
        sa.column("id", sa.String), sa.column("slug", sa.String), sa.column("title", sa.String),
        sa.column("prompt", sa.Text), sa.column("intro", sa.Text), sa.column("position", sa.Integer),
        sa.column("hidden", sa.Boolean), sa.column("created_at", sa.DateTime(timezone=True)),
        sa.column("updated_at", sa.DateTime(timezone=True)),
    )
    op.bulk_insert(chapters, [
        {"id": uuid4().hex, "slug": slug, "title": title, "prompt": prompt, "intro": "",
         "position": (i + 1) * 10, "hidden": False, "created_at": now, "updated_at": now}
        for i, (slug, title, prompt) in enumerate(CHAPTERS)
    ])


def downgrade() -> None:
    op.execute("DELETE FROM chapters WHERE intro = ''")
    op.execute("DELETE FROM profile WHERE id = 'main'")
