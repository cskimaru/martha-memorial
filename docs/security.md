# Security

## Accounts

* No public sign-up: accounts are created from single-use invitation links that expire after 14 days. The
  token travels in the URL fragment, so it never reaches server logs.
* Passwords are hashed with Argon2id; minimum 10 characters, may not contain the email name.
* Five failed sign-ins lock the account for 15 minutes; sign-in is also rate-limited per address. Unknown
  emails get the same answer and the same timing as wrong passwords.
* Access tokens last 15 minutes. Refresh tokens rotate on every use; reusing an old one ends every session in
  that chain (theft detection). Changing a password or removing a person ends all their sessions.
* Roles: **owner** (everything, including accounts) and **editor** (stories, photos, chapters, approving
  tributes). The last owner cannot be removed.

## Web

* Strict Content-Security-Policy (no inline script), `X-Frame-Options: DENY`, HSTS, `nosniff`, a restrictive
  Permissions-Policy, all set at the gateway.
* Cookie-authenticated writes from another origin are refused (in addition to `SameSite=Strict` cookies).
* All user text is escaped when rendered; uploaded photos are decoded and re-encoded as JPEG, which strips
  location data and neutralises anything hidden in the original file. Decompression bombs are refused.
* Visitors' tributes wait for family approval; tribute and candle forms have honeypots and rate limits.
* `/metrics`, `/healthz`, `/readyz` and API docs are not reachable from the internet.

## Platform

* Containers run as an unprivileged user on a read-only filesystem, with all Linux capabilities dropped and
  `no-new-privileges`.
* One database and one login per service; the Postgres and Redis networks have no internet access.
* Secrets are Docker secrets (files), never environment variables or images. `secrets/` is git-ignored and
  the CI scans every commit for leaked secrets (gitleaks).
* CI runs bandit (code), pip-audit (dependencies) and Trivy (images) and fails on high or critical findings.
  Dependabot proposes updates weekly.
* Monitoring dashboards are bound to `127.0.0.1` on the server; reach them through an SSH tunnel.
* Backups are encrypted with AES-256 before they leave the database container.
