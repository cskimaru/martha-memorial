#!/bin/sh
# Runs once, on first start of an empty data volume.
# One database and one login role per service: a service can only ever touch its own data.
set -eu
for svc in auth memorial media; do
  pw="$(cat "/run/secrets/pg_${svc}_password")"
  psql -v ON_ERROR_STOP=1 --username "$POSTGRES_USER" --dbname postgres <<SQL
CREATE ROLE ${svc} LOGIN PASSWORD '${pw}';
CREATE DATABASE ${svc} OWNER ${svc};
REVOKE ALL ON DATABASE ${svc} FROM PUBLIC;
SQL
  psql -v ON_ERROR_STOP=1 --username "$POSTGRES_USER" --dbname "${svc}" -c "REVOKE CREATE ON SCHEMA public FROM PUBLIC; ALTER SCHEMA public OWNER TO ${svc};"
done
pw="$(cat /run/secrets/pg_exporter_password)"
psql -v ON_ERROR_STOP=1 --username "$POSTGRES_USER" --dbname postgres <<SQL
CREATE ROLE exporter LOGIN PASSWORD '${pw}';
GRANT pg_monitor TO exporter;
SQL
