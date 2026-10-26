"""Fixed-window rate limiting backed by Redis (in-memory fallback for dev/tests)."""

import hashlib
import logging
import time

from fastapi import HTTPException, Request, status
from redis.asyncio import Redis

log = logging.getLogger(__name__)


class RateLimiter:
    def __init__(self, redis: Redis | None, prefix: str) -> None:
        self.redis = redis
        self.prefix = prefix
        self._mem: dict[str, tuple[int, float]] = {}

    async def hit(self, key: str, limit: int, window_s: int) -> bool:
        """Count one hit; return False when the limit is exceeded."""
        bucket = int(time.time() // window_s)
        full = f"rl:{self.prefix}:{key}:{bucket}"
        if self.redis is not None:
            try:
                pipe = self.redis.pipeline()
                pipe.incr(full)
                pipe.expire(full, window_s + 5)
                count, _ = await pipe.execute()
                return int(count) <= limit
            except Exception:
                # On a Redis outage, fall back to per-process limits rather than take the site down.
                log.warning("Rate limiter falling back to memory: Redis unavailable")
        now = time.time()
        count, exp = self._mem.get(full, (0, now + window_s))
        count += 1
        self._mem[full] = (count, exp)
        if len(self._mem) > 10_000:
            self._mem = {k: v for k, v in self._mem.items() if v[1] > now}
        return count <= limit


def client_ip(request: Request) -> str:
    # The gateway (Caddy) is the only thing that can reach the services. It sets X-Real-IP to the
    # visitor's address (the real visitor behind a trusted Cloudflare Tunnel); fall back to the last
    # X-Forwarded-For entry, which is the address Caddy saw.
    real = request.headers.get("x-real-ip")
    if real:
        return real.strip()
    xff = request.headers.get("x-forwarded-for")
    if xff:
        return xff.split(",")[-1].strip()
    return request.client.host if request.client else "unknown"


def hash_value(value: str, salt: str) -> str:
    return hashlib.sha256(f"{salt}:{value}".encode()).hexdigest()


def rate_limit(name: str, limit: int, window_s: int):
    async def dep(request: Request) -> None:
        limiter: RateLimiter = request.app.state.limiter
        key = f"{name}:{hash_value(client_ip(request), 'rl')}"
        if not await limiter.hit(key, limit, window_s):
            raise HTTPException(
                status.HTTP_429_TOO_MANY_REQUESTS,
                "Too many requests. Please wait a little and try again.",
            )

    return dep
