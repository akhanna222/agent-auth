"""FastAPI app entry point."""
from __future__ import annotations

import time
from contextlib import asynccontextmanager
from datetime import datetime, timezone

from fastapi import FastAPI, Request
from fastapi.responses import HTMLResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates

from .config import settings
from .database import close_db, init_db
from .middleware import RateLimitMiddleware, RequestIDMiddleware, TenantMiddleware
from .routers import agents, audit, delegations, intent, revoke, stepup, verify
from .schemas.api.audit import HealthResponse

START_TIME = time.time()


@asynccontextmanager
async def lifespan(app: FastAPI):
    await init_db()
    yield
    await close_db()


app = FastAPI(
    title="KYA — Know Your Agent",
    description="Agent authentication & authorization platform",
    version="1.0.0",
    lifespan=lifespan,
)

# Middleware (order matters: last added = first executed)
app.add_middleware(RateLimitMiddleware)
app.add_middleware(TenantMiddleware)
app.add_middleware(RequestIDMiddleware)

# Routers
app.include_router(agents.router)
app.include_router(delegations.router)
app.include_router(intent.router)
app.include_router(verify.router)
app.include_router(revoke.router)
app.include_router(stepup.router)
app.include_router(audit.router)

# Templates
import os
template_dir = os.path.join(os.path.dirname(__file__), "templates")
templates = Jinja2Templates(directory=template_dir)


# Health endpoints
@app.get("/health")
async def health():
    return {"status": "healthy"}


@app.get("/health/ready", response_model=HealthResponse)
async def health_ready():
    db_ok = True
    try:
        from .database import engine
        from sqlalchemy import text
        async with engine.connect() as conn:
            await conn.execute(text("SELECT 1"))
    except Exception:
        db_ok = False

    redis_ok = True
    try:
        from .redis_client import cache
        await cache.ping()
    except Exception:
        redis_ok = False

    status = "healthy" if (db_ok and redis_ok) else "degraded"
    return HealthResponse(
        status=status,
        dependencies={"database": db_ok, "cache": redis_ok, "opa": True},
        version="1.0.0",
        uptime_seconds=round(time.time() - START_TIME, 1),
    )


@app.get("/health/detailed")
async def health_detailed():
    return {
        "status": "healthy",
        "environment": settings.ENVIRONMENT,
        "database_url": settings.DATABASE_URL.split("@")[-1] if "@" in settings.DATABASE_URL else "sqlite",
        "uptime_seconds": round(time.time() - START_TIME, 1),
        "timestamp": datetime.now(timezone.utc).isoformat(),
    }


# UI route
@app.get("/ui", response_class=HTMLResponse)
@app.get("/ui/{path:path}", response_class=HTMLResponse)
async def ui(request: Request, path: str = ""):
    return templates.TemplateResponse("index.html", {"request": request})
