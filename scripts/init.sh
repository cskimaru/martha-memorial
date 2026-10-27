#!/usr/bin/env bash
# Prepare a server (or a laptop) to run the stack. Safe to run again: existing secrets are kept.
set -euo pipefail
cd "$(dirname "$0")/.."

if [ ! -f .env ]; then
  cp .env.example .env
  echo "Created .env from .env.example. Edit it (at least SITE_DOMAIN and ACME_EMAIL), then run 'make init' again."
  exit 0
fi
set -a
# shellcheck disable=SC1091
. ./.env
set +a

mkdir -p secrets deploy/generated/prometheus-targets "${BACKUP_DIR:-./backups}"
chmod 700 secrets

gen() { local f="secrets/$1"; if [ ! -s "$f" ]; then openssl rand -hex "${2:-32}" > "$f"; echo "  generated $f"; fi; }
placeholder() { [ -e "secrets/$1" ] || : > "secrets/$1"; }

echo "Secrets:"
for n in ip_hash_salt redis_password pg_superuser_password pg_auth_password \
         pg_memorial_password pg_media_password pg_exporter_password grafana_admin_password; do
  gen "$n"
done
gen backup_passphrase 48
for n in s3_secret_key offsite_s3_access_key offsite_s3_secret_key smtp_password rclone.conf; do
  placeholder "$n"
done
if [ ! -s secrets/jwt_private.pem ]; then
  openssl genpkey -algorithm RSA -pkeyopt rsa_keygen_bits:3072 -out secrets/jwt_private.pem 2>/dev/null
  openssl pkey -in secrets/jwt_private.pem -pubout -out secrets/jwt_public.pem
  echo "  generated JWT signing key pair"
fi
for svc in auth memorial media; do
  printf 'postgresql+asyncpg://%s:%s@postgres:5432/%s' "$svc" "$(cat "secrets/pg_${svc}_password")" "$svc" > "secrets/${svc}_database_url"
done
printf 'redis://:%s@redis:6379/0' "$(cat secrets/redis_password)" > secrets/redis_url
# Containers run as non-root users and read these through bind mounts; the secrets/ directory itself is 700.
chmod 644 secrets/*

echo "Config:"
if [ "${SITE_PREVIEW:-false}" = "true" ]; then
  [ -s secrets/preview_password ] || { openssl rand -base64 12 | tr -d '/+=' | cut -c1-14 > secrets/preview_password; chmod 644 secrets/preview_password; }
  hash=$(docker run --rm caddy:2.8.4-alpine caddy hash-password --plaintext "$(cat secrets/preview_password)")
  # Compose reads $ in env files as variables, so each $ in the hash is written as $$.
  printf 'SITE_MODE=preview\nPREVIEW_USER=family\nPREVIEW_PASSWORD_HASH=%s\n' "${hash//\$/\$\$}" > deploy/generated/caddy.env
  echo "  PRIVATE PREVIEW: user 'family', password '$(cat secrets/preview_password)' (in secrets/preview_password)"
else
  printf 'SITE_MODE=public\n' > deploy/generated/caddy.env
  echo "  public site: no password"
fi
printf -- '- targets: ["https://%s/"]\n' "${SITE_DOMAIN}" > deploy/generated/prometheus-targets/site.yml
if [ -n "${ALERT_EMAIL_TO:-}" ] && [ -n "${SMTP_HOST:-}" ]; then
  python3 -c 'import os,sys; sys.stdout.write(os.path.expandvars(open("deploy/alertmanager.yml.template").read()))' \
    > deploy/generated/alertmanager.yml
  echo "  alerts will be emailed to ${ALERT_EMAIL_TO}"
else
  printf 'route:\n  receiver: none\nreceivers:\n  - name: none\n' > deploy/generated/alertmanager.yml
  echo "  ALERT_EMAIL_TO / SMTP_HOST not set: alerts show in Alertmanager but are not emailed"
fi
echo "Done. Keep a copy of secrets/backup_passphrase somewhere safe OUTSIDE this server: backups cannot be restored without it."
