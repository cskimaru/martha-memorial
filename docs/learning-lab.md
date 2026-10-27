# Learning lab: microservices, scaling and operations on this site

Hands-on exercises using the memorial as a real system. Each lab says what to run (in the
Ubuntu terminal, in the project folder, with the site running through `make share`) and what
happened when it was tried. At the end is a table mapping each idea to its Kubernetes name, for
KCNA study.

This project runs on **Docker Compose**, not Kubernetes. The ideas are the same; Compose just
does less of the work for you, which makes the moving parts easier to see.

## Lab 1: What is running

```
docker ps --filter label=com.docker.compose.project=martha-memorial --format 'table {{.Names}}\t{{.Status}}'
docker stats --no-stream
```

With `make share`, **10 containers** run. On a real server (`make up`), monitoring adds 6 more
and the Cloudflare tunnel is not needed: **15**.

| Container | Kind | What it does |
|---|---|---|
| `cloudflared` | Edge | Tunnel that gives the public link (only with `make share`) |
| `caddy` | Edge | Gateway: HTTPS, security headers, preview password, sends each request to the right service |
| `web` | Stateless service | Renders the pages people see |
| `auth` | Stateless service | Accounts, sign-in, invitations; the only service that can issue sign-in tokens |
| `memorial` | Stateless service | Her story: profile, chapters, memories, tributes, candles |
| `media` | Stateless service* | Photo upload, resizing, serving; imports photos shared through pCloud |
| `postgres` | Stateful | One database per service (auth, memorial, media), each with its own login |
| `redis` | Stateful (cache) | Shared rate limits, so limits hold across every copy of a service |
| `backup` | Scheduled job | Daily encrypted backup, copy to pCloud |
| `inbox` | Worker | Fetches photos from pCloud's "Add to Gallery" every 15 minutes |
| `prometheus`, `alertmanager`, `grafana`, 3 exporters | Monitoring | Metrics, alerts, dashboards (server only) |

\* `media` keeps photo files on a volume; see Lab 7.

**Networks** separate them (`docker network ls`, `docker network inspect martha-memorial_backend`):

| Network | Who is on it | Internet access |
|---|---|---|
| `edge` | caddy, web, auth, memorial, media, backup, inbox, cloudflared | Yes |
| `backend` | postgres, redis, and the services that use them | **No** (internal) |
| `monitoring` | Prometheus and what it watches | No |

`web` is not on `backend`, so even if it were broken into it could not reach the database. It can
only ask `memorial` through its API.

## Lab 2: Scale a service

```
make share SCALE="web=3"
docker ps --format '{{.Names}}' | grep web
```

Three `web` containers appear. Send traffic and count which copy answered:

```
PW=$(cat secrets/preview_password)
for i in $(seq 60); do curl -s -o /dev/null -u family:$PW http://localhost:8080/family; done
for c in $(docker ps --format '{{.Names}}' | grep web | sort); do
  echo "$c served: $(docker logs --since 1m $c 2>&1 | grep -c family)"; done
```

Result: **20 / 20 / 20**.

The lesson: when first tried, the result was **60 / 0 / 0**. Starting more copies is not enough;
the load balancer has to know about them. Caddy looked up the name `web` once and kept using
the first answer. The fix (in `deploy/caddy/Caddyfile`, the `upstream` snippet) looks the name up
every 5 seconds and rotates requests between all copies (`lb_policy round_robin`). In
Kubernetes, a Service does this for you.

`make share` on its own goes back to one copy of everything.

## Lab 3: A copy dies while people are using the site

With three `web` copies running, send steady traffic and kill one in the middle:

```
(for i in $(seq 150); do curl -s -o /dev/null -w "%{http_code}\n" -u family:$PW http://localhost:8080/family; sleep 0.05; done | sort | uniq -c) &
sleep 2; docker kill martha-memorial-web-2; wait
```

Result: **150 × 200**, no errors. Caddy retries another copy (`lb_try_duration`) and stops
sending to the dead one for a while (`fail_duration`).

But `docker ps -a` shows `web-2` stays **Exited**. A manual `docker kill` counts as "stopped on
purpose", so the restart policy leaves it alone. Bring it back with `make share SCALE="web=3"`.

## Lab 4: A copy crashes on its own

```
docker exec martha-memorial-web-2 python -c "import os,signal; os.kill(1, signal.SIGTERM)"
sleep 8; docker inspect -f 'restarts={{.RestartCount}}' martha-memorial-web-2
```

Result: `restarts=1`, and the container is up again. `restart: unless-stopped` restarts crashed
containers. Compare Lab 3: Compose only restarts; it does not keep a promised number of copies
running. Kubernetes does (a ReplicaSet recreates a deleted pod).

## Lab 5: Health checks and graceful degradation

Each service reports whether it is ready, including its dependencies:

```
R='import urllib.request as u
try: r=u.urlopen("http://localhost:8000/readyz"); print(r.status, r.read().decode())
except Exception as e: print(e.code, e.read().decode())'
docker compose exec memorial python -c "$R"
docker compose stop redis
docker compose exec memorial python -c "$R"
curl -s -o /dev/null -w '%{http_code}\n' -u family:$PW http://localhost:8080/
docker compose start redis
```

Result: `200 ready` → with Redis stopped `503 {"redis": false}` → the site itself still answers
**200**. Readiness tells the platform "don't send me traffic", while the service keeps
working as best it can. `/readyz` and `/healthz` are blocked at the gateway, so only the
platform can see them, never visitors.

## Lab 6: Follow one page view through every service

```
RID=$(curl -s -o /dev/null -D - -u family:$PW http://localhost:8080/ | grep -i x-request-id | awk '{print $2}' | tr -d '\r')
docker compose logs | grep "$RID" | awk '{print $1}' | sort | uniq -c
```

Result: `caddy-1 1`, `web-1 4`, `memorial-1 3`. Caddy gives each request an ID, every
service logs it, and `web` passes it on when it calls `memorial`.

The lesson: at first the ID stopped at `web`. One page view became three calls to `memorial`
that couldn't be connected to it. With many services, debugging depends on this kind of
plumbing. Larger systems use distributed tracing (OpenTelemetry, Jaeger) for the same job.

## Lab 7: What does not scale by adding copies

**Background jobs.** `media` also imports photos from the shared inbox. With
`SCALE="media=2"` and 30 photos dropped in at once, the first version produced **31 records for
30 photos** and 25 false "couldn't import" warnings: both copies grabbed the same files. Now each
copy first claims a file by renaming it into its own folder (an atomic operation, so only one can
win). Result after the fix: **30 records, split 17 / 13**, no warnings. The general rule: anything
that runs on a timer inside a scaled service needs coordination, or belongs in a single worker.

**Databases.** Never run `--scale postgres=2`. Two database servers would share one data volume
and corrupt it. Scaling a database means replication (a primary plus read replicas), which is a
project of its own. Here it is one container with daily backups.

**Files on a volume.** Copies of `media` on the same computer share the `media-data` volume.
Copies on different servers could not, which is why `media` can also store photos in S3-compatible
object storage (`STORAGE_BACKEND=s3`).

**Per-copy memory.** Each `web` copy caches the page for 15 seconds in its own memory, so for a
few seconds two copies can show slightly different versions. Shared state (rate limits) lives in
Redis, so it holds across copies.

## Lab 8: Each service has its own database login

Three services store data, each in its own database with its own login: `auth`, `memorial`,
`media`. `web` has none; it only asks `memorial` through its API.

```
docker exec martha-memorial-postgres-1 psql -U postgres -c "\l"
docker exec martha-memorial-postgres-1 psql -U postgres -c "\du"
```

Now try to use `memorial`'s login on another service's database:

```
docker exec martha-memorial-postgres-1 psql -U memorial -d memorial -c "\dt"
docker exec martha-memorial-postgres-1 psql -U memorial -d auth -c "\dt"
```

Result: the first lists memorial's 7 tables; the second is refused with
`permission denied for database "auth"` and `User does not have CONNECT privilege`.
The same happened with memorial's real password from inside its container. So a bug or break-in
in `memorial` cannot read accounts and passwords in `auth`. This is set up once, in
`deploy/postgres/init-databases.sh`.

Also notice: `docker exec martha-memorial-web-1 ls /run/secrets` fails, because `web` was given no
secrets at all, and the containers' own files are read-only
(`docker inspect -f '{{.HostConfig.ReadonlyRootfs}}' martha-memorial-memorial-1` prints `true`).

## Lab 9: Which part is busiest

```
make traffic              # last hour
make traffic since=24h
```

It totals the gateway's log per service. With 6 photos on the page and 10 simulated visitors
(each scrolling the page, opening a photo, some leaving a tribute or candle):

| Service | Requests | Data sent | Time spent |
|---|---|---|---|
| media (photos) | 144 | 441 KB | 5.6 s |
| auth (sign-in check) | 61 | 1 KB | 1.7 s |
| web (design files) | 48 | 349 KB | 0.7 s |
| web (pages) | 24 | 65 KB | 1.4 s |
| memorial (tributes, candles) | 20 | 4 KB | 0.3 s |

**`media` is the busiest**: every visitor loads every photo on the page, and photos are the
heaviest files. It is the first candidate for more copies, or for a CDN (Cloudflare caching) in
front of it. The photos are served with a one-year cache, so returning visitors don't download
them again.

`memorial` looks quiet from outside, but `web` calls it three times for every page it builds.
Those internal calls don't pass the gateway; count them with
`docker logs --since 1h martha-memorial-memorial-1 | grep -c '"logger": "access"'`. `web` keeps the
page for 15 seconds, so a crowd of visitors costs `memorial` very little.

Measuring also found waste: each visitor's page asked `auth` "who is signed in?" and then tried
to renew a session twice. Now it is once.

## Watching it in Docker Desktop

Docker Desktop shows the same things live, with no commands:

* **Containers**: open the `martha-memorial` group. Each service is a row, with status, CPU and
  memory. With `make share SCALE="web=3"` you see `web-1`, `web-2`, `web-3` appear.
* Click a container, then:
  * **Logs**: its requests as they happen. Paste a request ID in the search box (Lab 6).
  * **Inspect**: networks, volumes, the read-only setting, memory limit.
  * **Exec**: a terminal inside it. In `postgres`, try the Lab 8 commands
    (`psql -U memorial -d auth`).
  * **Stats**: live CPU, memory, network and disk graphs. Leave it open on `media` while
    scrolling the gallery to watch it work.
* **Volumes**: `postgres-data`, `media-data` (the photos), `photo-inbox`: where data survives
  container restarts.
* Stop a container with its stop button and watch the site keep working (Lab 3), then start it.

## What the design makes easy, and what it makes hard

| Easy | Hard |
|---|---|
| Scale one busy part (`web=3`) without touching the rest | 10 to 15 containers to watch instead of 1 |
| One part fails, the rest keep working (Labs 3, 5) | Every network hop can fail; each call needs timeouts and fallbacks |
| Update one service without redeploying the others | Changes across services must stay compatible (API versions) |
| Each service has its own database login: a bug in one can't read another's data | Data spread over 3 databases: no simple joins, backups must cover all |
| Small codebases, each with its own tests | Debugging needs request IDs and central logs (Lab 6) |
| Limits per service (`docker stats` shows them) | Background jobs need coordination when scaled (Lab 7) |
| | The load balancer must be told about new copies (Lab 2) |

For a single family memorial, honestly, one well-built application would also have been enough.
The microservice split pays off when many memorials are hosted together, or when parts grow
at different speeds.

## Kubernetes names for the same ideas (KCNA)

| Here (Docker Compose) | Kubernetes |
|---|---|
| A service in `docker-compose.yml` | Deployment |
| A container | Pod |
| `--scale web=3` | `replicas: 3`; automatic: HorizontalPodAutoscaler |
| Caddy finding and balancing copies | Service (ClusterIP, kube-proxy) |
| Caddy as the public entry point | Ingress / Gateway API |
| `restart: unless-stopped` | kubelet restartPolicy, plus ReplicaSet keeping the count |
| `/healthz`, `/readyz` | liveness and readiness probes |
| `deploy.resources.limits` | resources.limits and requests |
| Files in `secrets/` | Secret |
| `.env` settings | ConfigMap |
| Named volumes (`media-data`, `postgres-data`) | PersistentVolumeClaim |
| `postgres` | StatefulSet (or a managed database) |
| `backup` (daily loop) | CronJob |
| `inbox` (single worker) | Deployment with `replicas: 1`, or a queue |
| `backend` network marked internal | NetworkPolicy |
| Prometheus, Alertmanager, Grafana | Same tools; Prometheus is a CNCF graduated project |
| Request IDs in JSON logs | OpenTelemetry tracing, Fluent Bit / Loki for logs |
| `cloudflared` tunnel | LoadBalancer Service / Ingress controller |
| GitHub Actions building images | CI/CD; Argo CD or Flux for GitOps |

## Clean up

```
make share
```

Back to one copy of each service, same link, data kept.
