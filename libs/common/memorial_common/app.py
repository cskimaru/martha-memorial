"""Application factory used by every service."""

import logging
from collections.abc import AsyncIterator, Awaitable, Callable
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from prometheus_fastapi_instrumentator import Instrumentator
from redis.asyncio import Redis

from .config import CommonSettings
from .db import Database
from .logging import configure_logging
from .middleware import OriginCheckMiddleware, RequestContextMiddleware
from .ratelimit import RateLimiter
from .security import TokenVerifier

log = logging.getLogger(__name__)

Hook = Callable[[FastAPI], Awaitable[None]]


def create_app(
    settings: CommonSettings,
    *,
    title: str,
    db: Database | None = None,
    on_startup: Hook | None = None,
    on_shutdown: Hook | None = None,
) -> FastAPI:
    configure_logging(settings.service_name, settings.log_level)
    redis = Redis.from_url(settings.redis_url, decode_responses=True) if settings.redis_url else None

    @asynccontextmanager
    async def lifespan(app: FastAPI) -> AsyncIterator[None]:
        if settings.is_production and not settings.public_key_pem():
            log.warning("No JWT public key configured; all signed-in requests will be refused.")
        if on_startup:
            await on_startup(app)
        yield
        if on_shutdown:
            await on_shutdown(app)
        if db:
            await db.dispose()
        if redis:
            await redis.aclose()

    app = FastAPI(
        title=title,
        lifespan=lifespan,
        docs_url=None if settings.is_production else "/docs",
        redoc_url=None,
        openapi_url=None if settings.is_production else "/openapi.json",
    )
    app.state.settings = settings
    app.state.db = db
    app.state.redis = redis
    app.state.limiter = RateLimiter(redis, settings.service_name)
    app.state.verifier = TokenVerifier(settings.public_key_pem(), settings.jwt_issuer, settings.jwt_audience)

    app.add_middleware(OriginCheckMiddleware, allowed_origins=settings.allowed_origins)
    app.add_middleware(RequestContextMiddleware)

    Instrumentator(excluded_handlers=["/healthz", "/readyz", "/metrics"]).instrument(app).expose(
        app, include_in_schema=False
    )

    @app.exception_handler(RequestValidationError)
    async def _validation(_: Request, exc: RequestValidationError) -> JSONResponse:
        errors = [{"field": ".".join(str(p) for p in e["loc"][1:]), "message": e["msg"]} for e in exc.errors()]
        return JSONResponse({"detail": "Some fields need attention.", "errors": errors}, status_code=422)

    @app.exception_handler(Exception)
    async def _unhandled(_: Request, exc: Exception) -> JSONResponse:
        log.exception("Unhandled error", exc_info=exc)
        return JSONResponse({"detail": "Something went wrong on our side. Please try again."}, status_code=500)

    @app.get("/healthz", include_in_schema=False)
    async def healthz() -> dict:
        return {"status": "ok"}

    @app.get("/readyz", include_in_schema=False)
    async def readyz() -> JSONResponse:
        checks: dict[str, bool] = {}
        if db:
            checks["database"] = await db.ping()
        if redis:
            try:
                checks["redis"] = bool(await redis.ping())
            except Exception:
                checks["redis"] = False
        ok = all(checks.values())
        return JSONResponse({"ready": ok, "checks": checks}, status_code=200 if ok else 503)

    return app
