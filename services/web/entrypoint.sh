#!/bin/sh
set -eu
exec uvicorn app.main:app --host 0.0.0.0 --port 8000 \
  --proxy-headers --forwarded-allow-ips="*" \
  --workers "${WEB_CONCURRENCY:-1}" --no-server-header
