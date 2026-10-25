"""Fetches page content from the memorial and contributions services.

The rendered page for anonymous visitors is cached briefly so a burst of
visitors (for example after the link is shared on the day of the burial)
costs the backend one request every few seconds. If a service is down, the
last good copy is served instead of an error.
"""

import asyncio
import logging
import time
from dataclasses import dataclass, field

import httpx

from .config import Settings

log = logging.getLogger("content")


@dataclass
class PageData:
    story: dict | None = None
    tributes: list = field(default_factory=list)
    candles: dict = field(default_factory=lambda: {"count": 0, "candles": []})
    giving: dict | None = None
    degraded: bool = False


class ContentClient:
    def __init__(self, settings: Settings, transport: httpx.AsyncBaseTransport | None = None) -> None:
        self.s = settings
        self.http = httpx.AsyncClient(timeout=settings.upstream_timeout_seconds, transport=transport)
        self._cache: tuple[float, PageData] | None = None
        self._last_good: PageData | None = None
        self._lock = asyncio.Lock()

    async def close(self) -> None:
        await self.http.aclose()

    async def _get(self, url: str, headers: dict) -> dict | list:
        r = await self.http.get(url, headers=headers)
        r.raise_for_status()
        return r.json()

    async def fetch(self, headers: dict | None = None) -> PageData:
        h = {k: v for k, v in (headers or {}).items() if v}
        m, c = self.s.memorial_url, self.s.contributions_url
        results = await asyncio.gather(
            self._get(f"{m}/api/memorial/story", h),
            self._get(f"{m}/api/memorial/tributes", h),
            self._get(f"{m}/api/memorial/candles", h),
            self._get(f"{c}/api/contributions/summary", h),
            return_exceptions=True,
        )
        data = PageData()
        names = ("story", "tributes", "candles", "giving")
        for name, res in zip(names, results, strict=True):
            if isinstance(res, Exception):
                log.warning("Upstream fetch failed", extra={"fields": {"part": name, "error": repr(res)}})
                data.degraded = True
            else:
                setattr(data, name, res)
        return data

    async def page(self, auth_headers: dict | None = None) -> PageData:
        # Signed-in family members always see fresh content (their own edits, hidden chapters).
        if auth_headers:
            return await self.fetch(auth_headers)
        now = time.monotonic()
        if self._cache and now - self._cache[0] < self.s.page_cache_seconds:
            return self._cache[1]
        async with self._lock:
            if self._cache and time.monotonic() - self._cache[0] < self.s.page_cache_seconds:
                return self._cache[1]
            data = await self.fetch()
            if data.story is None and self._last_good is not None:
                data = self._last_good
                data.degraded = True
            elif data.story is not None and not data.degraded:
                self._last_good = data
            self._cache = (time.monotonic(), data)
            return data
