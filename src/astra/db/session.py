"""Async SQLAlchemy database session management."""

import os
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession, async_sessionmaker, create_async_engine


def get_database_url() -> str:
    """Return async database URL.

    Production default is Postgres. Tests may pass sqlite+aiosqlite explicitly.
    """
    return os.environ.get(
        "ASTRA_DATABASE_URL",
        "postgresql+asyncpg://astra:astra@localhost:5432/astra",
    )


class Database:
    def __init__(self, url: str | None = None):
        self.url = url or get_database_url()
        engine_kwargs: dict[str, object] = {"pool_pre_ping": True}
        if not self.url.startswith("sqlite"):
            engine_kwargs.update(
                {
                    "pool_size": int(os.environ.get("ASTRA_DB_POOL_SIZE", "5")),
                    "max_overflow": int(os.environ.get("ASTRA_DB_MAX_OVERFLOW", "10")),
                }
            )
        self.engine: AsyncEngine = create_async_engine(
            self.url,
            **engine_kwargs,
        )
        self.session_factory = async_sessionmaker(
            self.engine,
            expire_on_commit=False,
            class_=AsyncSession,
        )

    @asynccontextmanager
    async def session(self) -> AsyncIterator[AsyncSession]:
        async with self.session_factory() as session:
            try:
                yield session
                await session.commit()
            except Exception:
                await session.rollback()
                raise

    async def create_all(self) -> None:
        from astra.db.models import Base

        async with self.engine.begin() as conn:
            await conn.run_sync(Base.metadata.create_all)

    async def dispose(self) -> None:
        await self.engine.dispose()
