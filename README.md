# Martha Kemunto Ongosi — Memorial

A memorial website for Martha Kemunto Ongosi, mother of Anita. Her life is told in chapters that invited
family members fill with stories and photographs. Visitors can leave tributes (approved by the family)
and light candles. It is a place of remembrance only: no money is collected.

## What's in the box

| Part | What it does |
|---|---|
| `services/web` | Renders the memorial page on the server (fast on phones, link previews on WhatsApp), the family area, and invitation sign-up |
| `services/auth` | Family accounts by invitation, sign-in with lockout, rotating sessions, roles (owner, editor) |
| `services/memorial` | Her profile, life chapters, family stories, tributes with moderation, candles |
| `services/media` | Photo uploads: every image is re-encoded, resized, and stripped of location data |
| `libs/common` | Shared config, logging, auth checks, rate limiting, health and metrics |
| `deploy/` | Caddy gateway (HTTPS), Postgres, backups, Prometheus, Alertmanager, Grafana |

Read [docs/architecture.md](docs/architecture.md) for how the pieces fit, [docs/security.md](docs/security.md)
for the protections, and [docs/runbook.md](docs/runbook.md) for day-to-day operation.

## Run it on your computer

Needs Docker with Compose v2.24+.

```sh
make init                 # creates .env; edit it if you like, then run again to generate secrets
make init
make dev                  # http://localhost:8080
docker compose exec auth python -m app.cli create-owner --email you@example.com --name "Anita"
```

Sign in at http://localhost:8080/family, invite family members, and start filling in the chapters.

## Put it on the internet

1. A small Linux server (2 vCPU, 4 GB RAM, 40 GB disk is plenty) with Docker installed.
2. A domain name with an `A` record pointing at the server. Open ports 80 and 443.
3. On the server: clone this repository, `make init`, set `SITE_DOMAIN` and `ACME_EMAIL` in `.env`, `make init` again.
4. `make up`. Caddy fetches the HTTPS certificate automatically.
5. `make create-owner email=you@example.com name="Anita"`.
6. Copy `secrets/backup_passphrase` somewhere safe away from the server.

After that, deployments go through GitHub Actions: see [docs/runbook.md](docs/runbook.md#deploying-a-new-version).

## Develop

```sh
python3 -m venv .venv && . .venv/bin/activate
pip install -e libs/common -r requirements-dev.txt -r services/<service>/requirements.txt
make test lint
```
