#!/bin/sh
# Run backup.sh once a day at BACKUP_HOUR_UTC.
set -eu
HOUR="${BACKUP_HOUR_UTC:-0}"
echo "Backups scheduled daily at ${HOUR}:00 UTC"
while true; do
  now=$(date -u +%s)
  next=$(date -u -d "$(date -u +%Y-%m-%d) ${HOUR}:00:00" +%s)
  [ "$next" -le "$now" ] && next=$((next + 86400))
  sleep $((next - now))
  /usr/local/bin/backup.sh || echo "Backup failed" >&2
done
