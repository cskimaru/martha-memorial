#!/usr/bin/env bash
# Run the memorial on this computer and share it through a free Cloudflare quick tunnel.
#   ./scripts/share.sh        start (or restart) and print the link
#   ./scripts/share.sh stop   stop everything (data is kept)
set -euo pipefail
cd "$(dirname "$0")/.."
FILES=(-f docker-compose.yml -f docker-compose.dev.yml -f docker-compose.tunnel.yml)
APP=(caddy web auth memorial media postgres redis)

if [ "${1:-}" = "stop" ]; then
  PUBLIC_URL=stopped docker compose "${FILES[@]}" stop
  echo "Stopped. Your data is kept; run 'make share' to start again (you'll get a new link)."
  exit 0
fi

if [ ! -f .env ]; then
  cp .env.example .env
  sed -i.bak 's/^SITE_DOMAIN=.*/SITE_DOMAIN=localhost/' .env && rm -f .env.bak
fi
./scripts/init.sh >/dev/null

echo "Opening the tunnel..."
PUBLIC_URL=pending docker compose --progress plain "${FILES[@]}" up -d --force-recreate cloudflared >/dev/null
url=""
for _ in $(seq 60); do
  url=$(PUBLIC_URL=pending docker compose "${FILES[@]}" logs cloudflared 2>&1 | grep -oE 'https://[a-z0-9-]+\.trycloudflare\.com' | tail -1 || true)
  [ -n "$url" ] && break
  sleep 1
done
if [ -z "$url" ]; then
  echo "Cloudflare didn't give a link. Check your internet connection and try again." >&2
  echo "Details: docker compose logs cloudflared" >&2
  exit 1
fi

echo "Building the memorial (the first time this takes several minutes)..."
# Plain progress: the animated display needs a console and fails on some Docker Desktop versions.
PUBLIC_URL="$url" docker compose --progress plain "${FILES[@]}" build web auth memorial media
echo "Starting the memorial..."
PUBLIC_URL="$url" docker compose --progress plain "${FILES[@]}" up -d --no-build --wait "${APP[@]}"

echo
echo "The memorial is shared at:  $url"
if grep -qE '^SITE_PREVIEW=true' .env; then
  echo "Preview login:             user 'family', password '$(cat secrets/preview_password)'"
fi
echo "On this computer:          http://localhost:8080"
echo
echo "The link works while this computer is on and connected. 'make share-stop' stops it."
echo "First time? Create your family account:  make create-owner email=you@example.com name=\"Your Name\""
