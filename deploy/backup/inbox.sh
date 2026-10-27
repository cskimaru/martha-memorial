#!/bin/sh
# Every few minutes, fetch photos dropped in "<OFFSITE_REMOTE>/Add to Gallery" into /inbox, where
# the media service imports them for a family member to approve. Files it couldn't use come back
# to pCloud in "Add to Gallery/Could not be added".
set -u
INTERVAL="${INBOX_INTERVAL_SECONDS:-900}"
DROP="${OFFSITE_REMOTE:-}/Add to Gallery"
mkdir -p /inbox/.incoming

fetch() {
  [ -n "${OFFSITE_REMOTE:-}" ] && [ -s /run/secrets/rclone_conf ] || return 0
  cp /run/secrets/rclone_conf /tmp/rclone.conf
  export RCLONE_CONFIG=/tmp/rclone.conf
  rclone mkdir "$DROP" || return 1
  # Download into a hidden folder, then hand each file over whole so a half-copied file is never imported.
  rclone move "$DROP" /inbox/.incoming --max-depth 1 --ignore-case \
    --include "*.{jpg,jpeg,png,webp,gif,heic,heif}" || return 1
  for f in /inbox/.incoming/*; do
    [ -f "$f" ] || continue
    name=$(basename "$f")
    target="/inbox/$name"
    [ -e "$target" ] && target="/inbox/$(date +%s%N | cut -c1-13)-$name"
    mv "$f" "$target"
  done
  if [ -d /inbox/.failed ] && [ -n "$(ls -A /inbox/.failed)" ]; then
    rclone move /inbox/.failed "$DROP/Could not be added" || return 1
  fi
}

echo "Checking for shared photos every $INTERVAL seconds"
while true; do
  fetch || echo "Couldn't fetch shared photos from pCloud; will try again" >&2
  sleep "$INTERVAL"
done
