#!/usr/bin/env sh
# Create the Alembic skeleton for a service: scripts/scaffold_alembic.sh <service>
set -eu
svc="$1"; d="services/$svc"
mkdir -p "$d/migrations/versions"
cat > "$d/alembic.ini" <<'INI'
[alembic]
script_location = migrations
prepend_sys_path = .
file_template = %%(rev)s_%%(slug)s

[loggers]
keys = root
[handlers]
keys = console
[formatters]
keys = generic
[logger_root]
level = WARNING
handlers = console
[handler_console]
class = StreamHandler
args = (sys.stderr,)
formatter = generic
[formatter_generic]
format = %(levelname)s %(name)s %(message)s
INI
cat > "$d/migrations/env.py" <<'PY'
from alembic import context
from sqlalchemy import create_engine, pool, text

from app import models  # noqa: F401  (registers tables on Base.metadata)
from app.config import get_settings
from memorial_common.db import Base, sync_url

url = sync_url(get_settings().database_url)
target_metadata = Base.metadata


def run_offline() -> None:
    context.configure(url=url, target_metadata=target_metadata, literal_binds=True)
    with context.begin_transaction():
        context.run_migrations()


def run_online() -> None:
    engine = create_engine(url, poolclass=pool.NullPool)
    with engine.connect() as conn:
        if conn.dialect.name == "postgresql":
            # Several replicas may start at once; only one migrates at a time.
            conn.execute(text("SELECT pg_advisory_lock(7272741)"))
            conn.commit()
        context.configure(connection=conn, target_metadata=target_metadata, compare_type=True)
        with context.begin_transaction():
            context.run_migrations()


if context.is_offline_mode():
    run_offline()
else:
    run_online()
PY
cat > "$d/migrations/script.py.mako" <<'MAKO'
"""${message}

Revision ID: ${up_revision}
Revises: ${down_revision | comma,n}
"""

from alembic import op
import sqlalchemy as sa
${imports if imports else ""}

revision = ${repr(up_revision)}
down_revision = ${repr(down_revision)}
branch_labels = ${repr(branch_labels)}
depends_on = ${repr(depends_on)}


def upgrade() -> None:
    ${upgrades if upgrades else "pass"}


def downgrade() -> None:
    ${downgrades if downgrades else "pass"}
MAKO
cat > "$d/entrypoint.sh" <<'SH'
#!/bin/sh
set -eu
if [ "${RUN_MIGRATIONS:-1}" = "1" ] && [ -f alembic.ini ]; then
  alembic upgrade head
fi
exec uvicorn app.main:app --host 0.0.0.0 --port 8000 \
  --proxy-headers --forwarded-allow-ips="*" \
  --workers "${WEB_CONCURRENCY:-1}" --no-server-header
SH
