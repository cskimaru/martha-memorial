#!/usr/bin/env bash
# Run on the server by the Deploy workflow (or by hand): NEW_TAG=<sha> REGISTRY=ghcr.io/owner/repo ./scripts/deploy.sh
# Takes a backup, switches to the new images, waits for health, and rolls back if anything fails.
set -euo pipefail
cd "$(dirname "$0")/.."
: "${NEW_TAG:?set NEW_TAG}"
: "${REGISTRY:?set REGISTRY}"

./scripts/init.sh >/dev/null
PREV_TAG=$(grep -E '^IMAGE_TAG=' .env | cut -d= -f2-)
set_tag() { sed -i "s|^IMAGE_TAG=.*|IMAGE_TAG=$1|; s|^REGISTRY=.*|REGISTRY=${REGISTRY}|" .env; }

echo "Deploying $NEW_TAG (currently $PREV_TAG)"
if docker compose ps --status running --services | grep -qx backup; then
  echo "Taking a backup first"
  docker compose exec -T backup backup.sh
fi

set_tag "$NEW_TAG"
docker compose pull --quiet
DOMAIN=$(grep -E '^SITE_DOMAIN=' .env | cut -d= -f2- | awk '{print $1}')
if docker compose up -d --remove-orphans --wait --wait-timeout 180 \
   && python3 scripts/smoke_test.py "https://${DOMAIN}"; then
  echo "Deployed $NEW_TAG"
  docker image prune -f >/dev/null
  exit 0
fi

echo "Deployment of $NEW_TAG failed. Rolling back to $PREV_TAG." >&2
set_tag "$PREV_TAG"
docker compose up -d --remove-orphans --wait --wait-timeout 180
exit 1
