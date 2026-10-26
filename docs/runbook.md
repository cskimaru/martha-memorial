# Runbook

Commands run from the repository folder on the server.

## Everyday

| Task | Command |
|---|---|
| See what's running | `make ps` |
| Follow logs | `make logs s=memorial` (any service name) |
| Restart one service | `docker compose restart memorial` |
| Take a backup now | `make backup-now` |
| Check the public site | `make smoke url=https://<domain>` |

## First-time setup checklist

- [ ] `make init`, edit `.env`, `make init` again
- [ ] `make up`, then `make create-owner email=... name=...`
- [ ] Sign in at `/family`, invite family members (the invite link is shown once; send it privately)
- [ ] Fill in her details (Edit her details on the memorial page) and a portrait
- [ ] Copy `secrets/backup_passphrase` to a password manager or printed copy kept by two family members
- [ ] Set `OFFSITE_S3_*` and the two `secrets/offsite_s3_*` files so backups also leave the server
- [ ] Set `ALERT_EMAIL_TO`, `SMTP_*` and `secrets/smtp_password` so alerts are emailed; `make init && make up`
- [ ] Restore drill: restore last night's backup on a spare machine (below) and check the site

## Monitoring

Dashboards are only reachable from the server itself. From your computer:

```sh
ssh -L 3000:localhost:3000 -L 9090:localhost:9090 -L 9093:localhost:9093 you@server
```

Then open http://localhost:3000 (Grafana; user `admin`, password in `secrets/grafana_admin_password`),
http://localhost:9093 (current alerts).

| Alert | What to do |
|---|---|
| SiteDown / ServiceDown | `make ps`, `make logs s=<service>`; `docker compose up -d` restarts anything stopped |
| BackupMissing | `make logs s=backup`; then `make backup-now` |
| CertificateExpiringSoon | `make logs s=caddy`; check DNS still points at the server and port 80 is open |
| DiskFillingUp | `docker system prune`; lower `BACKUP_KEEP_DAYS`; grow the disk |

## Deploying a new version

Every push to `main` is tested, scanned and published as images tagged with the commit SHA.

1. GitHub → Actions → **Deploy** → Run workflow, with the commit SHA.
2. A reviewer approves the `production` environment.
3. The workflow takes a backup, switches to the new images, waits for every health check, runs the smoke
   test, and **rolls back automatically** if anything fails.

One-time GitHub setup: repository secrets `DEPLOY_HOST`, `DEPLOY_USER`, `DEPLOY_SSH_KEY`, `DEPLOY_KNOWN_HOSTS`;
variables `SITE_DOMAIN`, `DEPLOY_PATH`; an environment named `production` with required reviewers; and on the
server, `docker login ghcr.io` with a token that can read packages.

By hand on the server: `NEW_TAG=<sha> REGISTRY=ghcr.io/<owner>/<repo> ./scripts/deploy.sh`.

## Backups and restore

Every night at `BACKUP_HOUR_UTC` the backup container dumps each database, archives the photos, encrypts
everything with the backup passphrase, keeps `BACKUP_KEEP_DAYS` days locally, and copies each archive
off-site if configured. The `BackupMissing` alert fires if a night is missed.

To restore (this replaces current data):

```sh
ls backups/archive/
make restore file=backups/archive/20261021T000000Z.tar.gz.gpg
```

On a fresh server: clone, `make init`, put back the **same** `secrets/backup_passphrase`, copy the archive
into `backups/archive/`, `make up`, then `make restore file=...`.

## Rotating secrets

* JWT keys (signs everyone out): delete `secrets/jwt_*.pem`, `make init`, `docker compose up -d`.
* Database passwords: change the role password in Postgres first (`ALTER ROLE ... PASSWORD`), update
  `secrets/pg_<service>_password`, `make init` (regenerates the connection strings), `docker compose up -d`.

## Bringing over content from the first draft page

The first draft memorial (the claude.ai page) stored stories in its own storage. Family members can re-add
them through "Add to this chapter"; there were none yet when this site was built.
