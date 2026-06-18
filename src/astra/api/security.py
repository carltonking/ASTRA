"""FastAPI API-key guard for production deployments."""

import os
import time
from collections.abc import Awaitable, Callable

from fastapi import Request, Response
from starlette.middleware.base import BaseHTTPMiddleware


class OptionalApiKeyMiddleware(BaseHTTPMiddleware):
    """Require `x-astra-api-key` only when ASTRA_API_KEY is configured."""

    def __init__(self, app):
        super().__init__(app)
        self._hits: dict[str, list[float]] = {}

    async def dispatch(
        self,
        request: Request,
        call_next: Callable[[Request], Awaitable[Response]],
    ) -> Response:
        expected = os.environ.get("ASTRA_API_KEY", "")
        if not expected:
            return await call_next(request)
        if request.url.path in {"/api/health"} or request.url.path.startswith("/static"):
            return await call_next(request)
        supplied = request.headers.get("x-astra-api-key", "")
        if supplied != expected:
            return Response("Unauthorized", status_code=401)
        limited = self._rate_limited(request)
        if limited:
            return Response("Rate limit exceeded", status_code=429)
        return await call_next(request)

    def _rate_limited(self, request: Request) -> bool:
        limit = int(os.environ.get("ASTRA_RATE_LIMIT_PER_MINUTE", "120"))
        if limit <= 0:
            return False
        actor = request.headers.get("x-astra-api-key", "")[:12] or (request.client.host if request.client else "unknown")
        now = time.monotonic()
        window_start = now - 60.0
        hits = [ts for ts in self._hits.get(actor, []) if ts >= window_start]
        hits.append(now)
        self._hits[actor] = hits
        return len(hits) > limit
