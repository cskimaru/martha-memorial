# Architecture

```
                         Internet
                            │ 80/443
                      ┌─────▼─────┐   HTTPS, security headers, request size limits,
                      │   Caddy   │   hides /metrics /healthz /docs
                      └─────┬─────┘
     ┌──────────┬───────────┼────────────┬───────────────┐
     │/         │/api/auth  │/api/memorial│/api/media     │/api/contributions
┌────▼───┐ ┌────▼───┐ ┌─────▼────┐ ┌──────▼──┐ ┌──────────▼────┐   ┌──────────────┐
│  web   │ │  auth  │ │ memorial │ │  media  │ │ contributions │◄──┤  reconciler  │
└───┬────┘ └───┬────┘ └────┬─────┘ └────┬────┘ └───────┬───────┘   └──────┬───────┘
    │ reads    │           │            │              │   Daraja API      │
    │ memorial │     ┌─────▼────────────▼──────────────▼─────┐  (Safaricom)  │
    │ + contrib│     │ PostgreSQL: one database + login per service │◄─────┘
    └──────────┘     └─────────────────────────────────────────┘
                     Redis (rate limits)   media volume (photos)
```

## Services

Each service is a small FastAPI application with its own database and its own database login. A service
cannot read another service's data; they talk over HTTP only where needed (the web service reads the
memorial and contributions APIs to render the page).

* **auth** owns accounts. It is the only service holding the JWT private key. It issues a short-lived
  (15 minute) access token and a rotating refresh token, both in `HttpOnly; Secure; SameSite=Strict`
  cookies. Every other service verifies tokens with the public key only.
* **memorial** owns the story: profile, chapters, entries, tributes and candles. Entries are soft-deleted.
* **media** owns photographs. Files go to the `media-data` volume (or S3-compatible storage if
  `STORAGE_BACKEND=s3`). The database stores an index; photos are served with year-long immutable caching.
* **contributions** owns money. Every status change is written to `contribution_events`, which is never
  updated or deleted. The **reconciler** is the same image run as a separate process.
* **web** renders HTML with Jinja (autoescaped). Anonymous page renders are cached for 15 seconds and the
  last good copy is served if a backend service is down, so a burst of visitors on the day of the burial
  costs the backend almost nothing.

## Data and ownership

| Service | Database | Main tables |
|---|---|---|
| auth | `auth` | users, refresh_tokens, invitations, audit_log |
| memorial | `memorial` | profile, chapters, entries, tributes, candles, audit_log |
| media | `media` | media_objects (+ files on the media volume) |
| contributions | `contributions` | contributions, contribution_events, mpesa_callbacks |

Schema changes are Alembic migrations in each service's `migrations/` folder. They run automatically when a
service starts; a Postgres advisory lock stops two replicas migrating at once. CI applies, rolls back and
re-applies every migration on real PostgreSQL.

## Why these choices

* **Microservices, but few.** The services split along the lines that matter for safety: money, accounts,
  files and content each fail and scale independently, and a bug in one cannot touch another's data.
  There are five, not fifteen, so one person can run the whole thing on one server.
* **One server with Docker Compose** rather than Kubernetes. A memorial gets bursts of traffic, not sustained
  load. Compose with health checks, restart policies, resource limits and automatic rollback gives the
  reliability that matters here at a fraction of the cost and complexity. The images are ordinary OCI images
  and move to Kubernetes unchanged if that is ever needed.
* **Photos on a volume** by default. Fewer moving parts than an object store, backed up nightly with
  everything else. Switch to managed S3 storage with environment variables alone.
