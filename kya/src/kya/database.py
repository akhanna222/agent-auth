"""Async SQLAlchemy engine and session management."""
from __future__ import annotations

import uuid
from contextlib import asynccontextmanager
from typing import AsyncGenerator

from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from .config import settings

engine = create_async_engine(
    settings.DATABASE_URL,
    echo=False,
    future=True,
)

async_session_factory = async_sessionmaker(engine, expire_on_commit=False)


@asynccontextmanager
async def get_db_session(tenant_id: uuid.UUID | None = None) -> AsyncGenerator[AsyncSession, None]:
    """Every DB session. Optionally sets tenant context for RLS."""
    async with async_session_factory() as session:
        if tenant_id and "postgresql" in settings.DATABASE_URL:
            from sqlalchemy import text
            await session.execute(text(f"SET app.current_tenant_id = '{tenant_id}'"))
        yield session


async def init_db() -> None:
    """Create all tables (for dev/SQLite mode)."""
    from .models.db.base import Base  # noqa
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)


async def close_db() -> None:
    await engine.dispose()
