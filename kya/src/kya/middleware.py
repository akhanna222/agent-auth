"""FastAPI middleware: tenant resolution, request ID, rate limiting."""
from __future__ import annotations

import time
import uuid

from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import JSONResponse

from .redis_client import cache

RATE_LIMITS = {
    "/v1/verify-agent-action": {"requests": 1000, "window_seconds": 60},
    "/v1/agents/register": {"requests": 100, "window_seconds": 60},
    "/v1/intent/issue": {"requests": 500, "window_seconds": 60},
    "default": {"requests": 300, "window_seconds": 60},
}


class RequestIDMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next):
        request_id = request.headers.get("X-Request-ID", str(uuid.uuid4()))
        request.state.request_id = request_id
        response = await call_next(request)
        response.headers["X-Request-ID"] = request_id
        return response


class TenantMiddleware(BaseHTTPMiddleware):
    EXEMPT_PATHS = {"/", "/health", "/health/ready", "/health/detailed", "/docs", "/openapi.json", "/ui"}

    async def dispatch(self, request: Request, call_next):
        path = request.url.path
        # Skip tenant check for exempt paths and static files
        if path in self.EXEMPT_PATHS or path.startswith("/static") or path.startswith("/ui"):
            request.state.tenant = None
            request.state.tenant_id = None
            return await call_next(request)

        tenant_id = request.headers.get("X-Tenant-ID")
        if not tenant_id:
            return JSONResponse(
                status_code=403,
                content={"detail": "Missing X-Tenant-ID header"},
            )

        request.state.tenant_id = tenant_id
        return await call_next(request)


class RateLimitMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next):
        tenant_id = getattr(request.state, "tenant_id", None)
        if tenant_id:
            path = request.url.path
            config = RATE_LIMITS.get(path, RATE_LIMITS["default"])
            window = int(time.time()) // config["window_seconds"]
            key = f"kya:rate:{tenant_id}:{path}:{window}"
            count = await cache.incr(key)
            if count == 1:
                await cache.expire(key, config["window_seconds"])
            if count > config["requests"]:
                return JSONResponse(
                    status_code=429,
                    content={"detail": "Rate limit exceeded"},
                )
        return await call_next(request)
