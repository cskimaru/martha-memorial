#!/usr/bin/env bash
# Run the memorial on this computer and share it through Cloudflare.
#   ./scripts/share.sh          start, or update after `git pull` (keeps the current link)
#   ./scripts/share.sh new      start with a fresh quick link
#   ./scripts/share.sh stop     stop everything (data is kept)
# With CLOUDFLARE_TUNNEL_TOKEN and PUBLIC_HOSTNAME set in .env, the link is your own permanent address.
set -euo pipefail
cd "$(dirname "$0")/.."
FILES=(-f docker-compose.yml -f docker-compose.dev.yml -f docker-compose.tunnel.yml)
APP=(caddy web auth memorial media postgres redis)
compose() { docker compose --progress plain "${FILES[@]}" "$@"; }

if [ "${1:-}" = "stop" ]; then
  PUBLIC_URL=stopped compose stop
  echo "Stopped. Your data is kept; run 'make share' to start again."
  exit 0
fi

if [ ! -f .env ]; then
  cp .env.example .env
  sed -i.bak 's/^SITE_DOMAIN=.*/SITE_DOMAIN=localhost/' .env && rm -f .env.bak
fi
./scripts/init.sh >/dev/null
token=$(grep -E '^CLOUDFLARE_TUNNEL_TOKEN=' .env | cut -d= -f2- | tr -d '"' || true)
host=$(grep -E '^PUBLIC_HOSTNAME=' .env | cut -d= -f2- | awk '{print $1}' || true)

if [ -n "$token" ] && [ -n "$host" ]; then
  # Permanent address through a named tunnel on your own domain.
  url="https://$host"
  export TUNNEL_COMMAND="tunnel --no-autoupdate run" CLOUDFLARE_TUNNEL_TOKEN="$token"
  echo "Connecting $url ..."
  PUBLIC_URL="$url" compose up -d cloudflared >/dev/null
else
  # Free quick tunnel. Reuse the running one so the link stays the same across updates.
  current() { PUBLIC_URL=pending compose logs cloudflared 2>&1 | grep -oE 'https://[a-z0-9-]+\.trycloudflare\.com' | tail -1 || true; }
  running=$(PUBLIC_URL=pending compose ps --status running --services 2>/dev/null | grep -x cloudflared || true)
  url=""
  if [ "${1:-}" != "new" ] && [ -n "$running" ]; then
    url=$(current)
  fi
  if [ -z "$url" ]; then
    echo "Opening a new tunnel..."
    PUBLIC_URL=pending compose up -d --force-recreate cloudflared >/dev/null
    for _ in $(seq 60); do
      url=$(current)
      [ -n "$url" ] && break
      sleep 1
    done
  else
    echo "Keeping the current link."
  fi
  if [ -z "$url" ]; then
    echo "Cloudflare didn't give a link. Check your internet connection and try again." >&2
    echo "Details: docker compose logs cloudflared" >&2
    exit 1
  fi
fi

echo "Building the memorial (the first time this takes several minutes)..."
# Plain progress: the animated display needs a console and fails on some Docker Desktop versions.
PUBLIC_URL="$url" compose build web auth memorial media
echo "Starting the memorial..."
PUBLIC_URL="$url" compose up -d --no-build --wait "${APP[@]}"

echo
echo "The memorial is shared at:  $url"
if grep -qE '^SITE_PREVIEW=true' .env; then
  echo "Preview login:             user 'family', password '$(cat secrets/preview_password)'"
fi
echo "On this computer:          http://localhost:8080"
echo
echo "The link works while this computer is on and connected. 'make share-stop' stops it."
echo "First time? Create your family account:  make create-owner email=you@example.com name=\"Your Name\""
