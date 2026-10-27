#!/bin/sh
# Run backup.sh once a day at BACKUP_HOUR_UTC.
set -eu
HOUR="${BACKUP_HOUR_UTC:-0}"
echo "Backups scheduled daily at ${HOUR}:00 UTC"
if [ "${BACKUP_ON_START:-false}" = "true" ]; then
  # A laptop is often asleep at the scheduled hour, so also back up shortly after each start.
  sleep 60
  /usr/local/bin/backup.sh || echo "Backup failed" >&2
fi
while true; do
  now=$(date -u +%s)
  next=$(date -u -d "$(date -u +%Y-%m-%d) ${HOUR}:00:00" +%s)
  [ "$next" -le "$now" ] && next=$((next + 86400))
  sleep $((next - now))
  /usr/local/bin/backup.sh || echo "Backup failed" >&2
done
