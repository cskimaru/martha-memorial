#!/bin/sh
# Encrypted backup of every database and all photographs.
# Output: /backups/archive/<timestamp>.tar.gz.gpg (AES-256, passphrase in the backup_passphrase secret).
set -eu
umask 077
STAMP=$(date -u +%Y%m%dT%H%M%SZ)
WORK=/backups/work/$STAMP
ARCHIVE_DIR=/backups/archive
KEEP_DAYS="${BACKUP_KEEP_DAYS:-30}"
mkdir -p "$WORK" "$ARCHIVE_DIR"

PGPASSWORD="$(cat /run/secrets/pg_superuser_password)"
export PGPASSWORD
echo "[$STAMP] Dumping databases"
pg_dumpall -h postgres -U postgres --globals-only > "$WORK/globals.sql"
for db in auth memorial media; do
  pg_dump -h postgres -U postgres -Fc -d "$db" -f "$WORK/$db.dump"
  pg_restore --list "$WORK/$db.dump" > /dev/null   # verify the dump is readable
done

echo "[$STAMP] Archiving photographs"
tar -C /media -cf "$WORK/media.tar" .

echo "[$STAMP] Encrypting"
OUT="$ARCHIVE_DIR/$STAMP.tar.gz.gpg"
tar -C "$WORK" -czf - . | gpg --batch --yes --quiet --symmetric --cipher-algo AES256 \
  --passphrase-file /run/secrets/backup_passphrase -o "$OUT"
sha256sum "$OUT" > "$OUT.sha256"
rm -rf "$WORK"

if [ -n "${OFFSITE_S3_ENDPOINT:-}" ] && [ -n "${OFFSITE_S3_BUCKET:-}" ] && [ -s /run/secrets/offsite_s3_access_key ]; then
  echo "[$STAMP] Copying off-site"
  RCLONE_CONFIG_OFFSITE_ACCESS_KEY_ID="$(cat /run/secrets/offsite_s3_access_key)"
  RCLONE_CONFIG_OFFSITE_SECRET_ACCESS_KEY="$(cat /run/secrets/offsite_s3_secret_key)"
  export RCLONE_CONFIG_OFFSITE_TYPE=s3 RCLONE_CONFIG_OFFSITE_PROVIDER=Other \
    RCLONE_CONFIG_OFFSITE_ENDPOINT="$OFFSITE_S3_ENDPOINT" \
    RCLONE_CONFIG_OFFSITE_ACCESS_KEY_ID RCLONE_CONFIG_OFFSITE_SECRET_ACCESS_KEY
  rclone copy --no-traverse "$OUT" "offsite:$OFFSITE_S3_BUCKET/archive/"
  rclone copy --no-traverse "$OUT.sha256" "offsite:$OFFSITE_S3_BUCKET/archive/"
fi

# Any rclone remote, for example a family member's pCloud (see docs/backups-to-pcloud.md).
if [ -n "${OFFSITE_REMOTE:-}" ] && [ -s /run/secrets/rclone_conf ]; then
  # rclone may refresh the access token, so give it a writable copy of the config.
  cp /run/secrets/rclone_conf /tmp/rclone.conf
  export RCLONE_CONFIG=/tmp/rclone.conf
  echo "[$STAMP] Copying to $OFFSITE_REMOTE"
  rclone copy --no-traverse "$OUT" "$OFFSITE_REMOTE/Backups (encrypted)/"
  rclone copy --no-traverse "$OUT.sha256" "$OFFSITE_REMOTE/Backups (encrypted)/"
  rclone delete --min-age "${OFFSITE_KEEP_DAYS:-90}d" "$OFFSITE_REMOTE/Backups (encrypted)/"

  # A plain copy of every photograph the family can open directly. Add-only: a photo removed
  # from the memorial stays here.
  STAGE=/backups/work/photos-$STAMP
  mkdir -p "$STAGE"
  for f in /media/photos/*/full.jpg; do
    [ -f "$f" ] || continue
    id=$(basename "$(dirname "$f")")
    ln -s "$f" "$STAGE/$(date -u -r "$f" +%Y-%m-%d)_$(echo "$id" | cut -c1-12).jpg"
  done
  rclone copy --copy-links --ignore-existing "$STAGE" "$OFFSITE_REMOTE/Photos/"
  rm -rf "$STAGE"
fi

find "$ARCHIVE_DIR" -name '*.gpg*' -mtime +"$KEEP_DAYS" -delete

SIZE=$(stat -c %s "$OUT")
cat > /metrics/backup.prom.tmp <<PROM
# HELP memorial_backup_last_success_timestamp_seconds Unix time of the last successful backup.
# TYPE memorial_backup_last_success_timestamp_seconds gauge
memorial_backup_last_success_timestamp_seconds $(date -u +%s)
# HELP memorial_backup_size_bytes Size of the last backup archive.
# TYPE memorial_backup_size_bytes gauge
memorial_backup_size_bytes $SIZE
PROM
mv /metrics/backup.prom.tmp /metrics/backup.prom
echo "[$STAMP] Backup complete: $OUT ($SIZE bytes)"
