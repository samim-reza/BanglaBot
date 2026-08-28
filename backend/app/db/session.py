"""One async engine + session factory built from ``settings.database_url``.

``postgres://`` / ``postgresql://`` URLs are rewritten to the asyncpg driver
and libpq's ``sslmode`` query option is stripped (asyncpg rejects it; TLS is
configured through ``connect_args`` from ``database_ssl`` instead).
"""

from __future__ import annotations

import ssl
from collections.abc import AsyncGenerator

from sqlalchemy.engine import make_url
from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession, async_sessionmaker, create_async_engine

from app.core.config import get_settings


def normalized_database_url(raw_url: str) -> str:
    url = make_url(raw_url)
    if url.drivername in {"postgres", "postgresql"}:
        url = url.set(drivername="postgresql+asyncpg")
    query = dict(url.query)
    query.pop("sslmode", None)
    return url.set(query=query).render_as_string(hide_password=False)


def _connect_args() -> dict:
    settings = get_settings()
    args: dict = {}
    if settings.database_ssl:
        args["ssl"] = ssl.create_default_context() if settings.database_ssl_verify else ssl._create_unverified_context()
    host = make_url(settings.database_url).host or ""
    if "pooler" in host or "pgbouncer" in host:
        # Transaction poolers cannot hold asyncpg's server-side prepared statements.
        args["statement_cache_size"] = 0
    return args


def build_engine() -> AsyncEngine:
    settings = get_settings()
    return create_async_engine(
        normalized_database_url(settings.database_url),
        echo=False,
        pool_pre_ping=True,
        pool_size=settings.database_pool_size,
        max_overflow=settings.database_pool_max_overflow,
        pool_recycle=1800,
        connect_args=_connect_args(),
    )


engine: AsyncEngine = build_engine()
AsyncSessionLocal = async_sessionmaker(engine, expire_on_commit=False, class_=AsyncSession)


async def get_db() -> AsyncGenerator[AsyncSession, None]:
    async with AsyncSessionLocal() as session:
        yield session
