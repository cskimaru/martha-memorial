#!/usr/bin/env python3
"""Which part of the site is busiest? Reads the gateway's access log and totals, per service:
requests, data sent and time spent answering.

    make traffic              # last hour
    make traffic since=24h    # or 10m, 7d, ...
"""

import collections
import json
import subprocess
import sys

since = sys.argv[1] if len(sys.argv) > 1 else "1h"
if since.endswith("d"):
    since = f"{int(since[:-1]) * 24}h"
log = subprocess.run(
    ["docker", "logs", "--since", since, "martha-memorial-caddy-1"], capture_output=True, text=True, check=True
)


def service(uri: str) -> str:
    for prefix, name in [
        ("/api/auth", "auth (sign-in, accounts)"),
        ("/api/memorial", "memorial (stories, tributes, candles)"),
        ("/api/media", "media (photos)"),
        ("/static", "web (design files)"),
    ]:
        if uri.startswith(prefix):
            return name
    return "web (pages)"


reqs, size, secs = collections.Counter(), collections.Counter(), collections.Counter()
for line in (log.stdout + log.stderr).splitlines():
    if '"handled request"' not in line:
        continue
    try:
        d = json.loads(line)
    except ValueError:
        continue
    s = service(d["request"]["uri"])
    reqs[s] += 1
    size[s] += d.get("size", 0)
    secs[s] += d.get("duration", 0)

if not reqs:
    sys.exit(f"No visits in the last {since}.")
print(f"Traffic in the last {since}, busiest first:\n")
print(f"{'service':40} {'requests':>9} {'data sent':>11} {'time spent':>11}")
for s, n in reqs.most_common():
    print(f"{s:40} {n:9} {size[s] / 1024:9.0f} KB {secs[s]:9.2f} s")
print(f"{'total':40} {sum(reqs.values()):9} {sum(size.values()) / 1024:9.0f} KB {sum(secs.values()):9.2f} s")
