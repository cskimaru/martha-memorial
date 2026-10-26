#!/usr/bin/env python3
"""Check that a running memorial site works end to end.

    python3 scripts/smoke_test.py https://martha.example.com

While the site is in private preview, set PREVIEW_PASSWORD so the checks can get past the password.
Exits non-zero if any check fails. Used after every deployment.
"""

import base64
import json
import os
import ssl
import sys
import time
import urllib.error
import urllib.request

BASE = (sys.argv[1] if len(sys.argv) > 1 else "http://localhost:8080").rstrip("/")
if not BASE.startswith(("http://", "https://")):
    sys.exit("Give an http:// or https:// address.")
CTX = ssl.create_default_context()
HEADERS = {"User-Agent": "memorial-smoke-test"}
if os.environ.get("PREVIEW_PASSWORD"):
    login = base64.b64encode(f"family:{os.environ['PREVIEW_PASSWORD']}".encode()).decode()
    HEADERS["Authorization"] = f"Basic {login}"
failures: list[str] = []


def get(path: str, retries: int = 1) -> tuple[int, dict, bytes]:
    for attempt in range(retries):
        try:
            req = urllib.request.Request(BASE + path, headers=HEADERS)  # noqa: S310
            with urllib.request.urlopen(req, timeout=15, context=CTX) as r:  # noqa: S310
                return r.status, dict(r.headers), r.read()
        except urllib.error.HTTPError as e:
            return e.code, dict(e.headers), e.read()
        except (urllib.error.URLError, TimeoutError, ConnectionError):
            if attempt == retries - 1:
                raise
            time.sleep(3)
    raise RuntimeError("unreachable")


def check(name: str, ok: bool, detail: str = "") -> None:
    print(("PASS " if ok else "FAIL ") + name + (f"  ({detail})" if detail and not ok else ""))
    if not ok:
        failures.append(name)


status, headers, body = get("/", retries=20)
check("home page loads", status == 200, f"status {status}")
check("home page shows her name", b"Martha Kemunto Ongosi" in body)
check("content security policy is set", "content-security-policy" in {k.lower() for k in headers})
check("clickjacking protection is set", headers.get("X-Frame-Options") == "DENY")

status, _, body = get("/api/memorial/story")
check("story API answers", status == 200, f"status {status}")
if status == 200:
    chapters = json.loads(body).get("chapters", [])
    check("chapters are present", len(chapters) >= 1, f"{len(chapters)} chapters")

status, _, _ = get("/api/auth/me")
check("auth API refuses anonymous access", status == 401, f"status {status}")

for internal in ("/metrics", "/healthz", "/docs"):
    status, _, _ = get(internal)
    check(f"{internal} is not public", status == 404, f"status {status}")

status, _, _ = get("/static/site.css")
check("stylesheet is served", status == 200, f"status {status}")

if failures:
    print(f"\n{len(failures)} check(s) failed.")
    sys.exit(1)
print("\nAll checks passed.")
