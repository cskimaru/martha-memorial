"""Request id, access logging, and cross-site write protection."""

import logging
import time
import uuid

from starlette.middleware.base import BaseHTTPMiddleware, RequestResponseEndpoint
from starlette.requests import Request
from starlette.responses import JSONResponse, Response

from .logging import log_fields, request_id_var
from .security import ACCESS_COOKIE, REFRESH_COOKIE

UNSAFE = {"POST", "PUT", "PATCH", "DELETE"}
access_log = logging.getLogger("access")


class RequestContextMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next: RequestResponseEndpoint) -> Response:
        rid = request.headers.get("x-request-id") or uuid.uuid4().hex
        rid = rid[:64]
        token = request_id_var.set(rid)
        start = time.perf_counter()
        status = 500
        try:
            response = await call_next(request)
            status = response.status_code
            response.headers["X-Request-ID"] = rid
            return response
        finally:
            if request.url.path not in ("/healthz", "/readyz", "/metrics"):
                log_fields(
                    access_log,
                    logging.INFO,
                    "request",
                    method=request.method,
                    path=request.url.path,
                    status=status,
                    ms=round((time.perf_counter() - start) * 1000, 1),
                )
            request_id_var.reset(token)


class OriginCheckMiddleware(BaseHTTPMiddleware):
    """Reject cookie-authenticated writes that come from another site (CSRF).

    Cookies are also SameSite=Strict; this is a second, independent check.
    Requests without the session cookie, such as visitors' tributes and candles,
    are not affected.
    """

    def __init__(self, app, site_origin: str) -> None:
        super().__init__(app)
        self.site_origin = site_origin

    async def dispatch(self, request: Request, call_next: RequestResponseEndpoint) -> Response:
        has_session = ACCESS_COOKIE in request.cookies or REFRESH_COOKIE in request.cookies
        if request.method in UNSAFE and has_session:
            origin = request.headers.get("origin") or ""
            if origin.rstrip("/") != self.site_origin:
                return JSONResponse({"detail": "Cross-site request blocked."}, status_code=403)
        return await call_next(request)
