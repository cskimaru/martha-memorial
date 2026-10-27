#!/usr/bin/env bash
# Connect a pCloud account for backups. Run once: `make connect-pcloud`.
# The account owner signs in to pCloud in the browser; only an access key is kept, in
# secrets/rclone.conf on this computer. See docs/backups-to-pcloud.md.
set -euo pipefail
cd "$(dirname "$0")/.."
FOLDER="${1:-Martha Memoir}"
CONF=secrets/rclone.conf

[ -f .env ] || { cp .env.example .env; sed -i.bak 's/^SITE_DOMAIN=.*/SITE_DOMAIN=localhost/' .env && rm -f .env.bak; }
./scripts/init.sh >/dev/null
if ! command -v rclone >/dev/null; then
  echo "Installing rclone (the tool that copies backups to pCloud); your Ubuntu password may be asked..."
  sudo apt-get update -qq && sudo apt-get install -y -qq rclone
fi

echo
echo "A pCloud sign-in link will appear below as http://127.0.0.1:53682/auth?state=..."
echo "Open it in your browser (copy and paste it into Chrome or Edge on this computer),"
echo "sign in with the pCloud account to use, and click Allow. Then come back here."
echo
rclone config delete pcloud --config "$CONF" >/dev/null 2>&1 || true
# rclone prints the new config, access key included, on stdout: keep it off the screen.
rclone config create pcloud pcloud --config "$CONF" >/dev/null

if ! grep -q '^token' "$CONF"; then
  echo "pCloud wasn't connected (no sign-in was completed). Run 'make connect-pcloud' to try again." >&2
  exit 1
fi
rclone mkdir "pcloud:$FOLDER" --config "$CONF"

if grep -qE '^OFFSITE_REMOTE=' .env; then
  sed -i.bak "s|^OFFSITE_REMOTE=.*|OFFSITE_REMOTE=\"pcloud:$FOLDER\"|" .env && rm -f .env.bak
else
  echo "OFFSITE_REMOTE=\"pcloud:$FOLDER\"" >> .env
fi

echo
echo "Connected. Backups will go to the '$FOLDER' folder in pCloud:"
echo "  $FOLDER/Photos               every photograph, ready to open (photos removed from the site stay here)"
echo "  $FOLDER/Backups (encrypted)  full backups of stories, tributes and photos, for restoring the site"
echo
echo "Now run 'make share'. The first backup runs about a minute after it starts, then once a day."
