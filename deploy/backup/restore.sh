#!/bin/sh
# Restore from an encrypted archive.
#   docker compose run --rm --entrypoint restore.sh backup /backups/archive/<stamp>.tar.gz.gpg [--yes]
# Stop the application services first (make down-apps). This REPLACES the current data.
set -eu
ARCHIVE="${1:?Usage: restore.sh <archive.tar.gz.gpg> [--yes]}"
if [ "${2:-}" != "--yes" ]; then
  echo "This replaces all current memorial data with the contents of $ARCHIVE."
  echo "Re-run with --yes to continue."
  exit 1
fi
[ -f "$ARCHIVE.sha256" ] && sha256sum -c "$ARCHIVE.sha256"
WORK=$(mktemp -d /backups/restore.XXXXXX)
trap 'rm -rf "$WORK"' EXIT
gpg --batch --quiet --decrypt --passphrase-file /run/secrets/backup_passphrase "$ARCHIVE" | tar -C "$WORK" -xzf -

PGPASSWORD="$(cat /run/secrets/pg_superuser_password)"
export PGPASSWORD
for db in auth memorial media contributions; do
  echo "Restoring $db"
  pg_restore -h postgres -U postgres --clean --if-exists --no-owner --role="$db" -d "$db" "$WORK/$db.dump"
done

echo "Restoring photographs"
tar -C /media -xf "$WORK/media.tar"
chown -R 10001:10001 /media
echo "Restore complete. Start the services again with: make up"
