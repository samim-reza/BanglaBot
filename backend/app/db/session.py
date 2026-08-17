"""Async SQLAlchemy engine/session bound to Supabase Postgres."""

import ssl

from sqlalchemy.engine.url import make_url
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from app.core.config import get_settings


def _connect_args(database_url: str) -> dict:
    """Keep asyncpg working against Supabase's pgbouncer session pooler.

    Default asyncpg SSL negotiation can hang until TimeoutError against the
    pooler. `ssl.create_default_context()` also hangs; a TLS client context
    with verification disabled encrypts without stalling. Prepared-statement
    caches must stay off for pgbouncer.
    """
    args: dict = {
        "timeout": 20,
        "command_timeout": 60,
        "statement_cache_size": 0,
        "prepared_statement_cache_size": 0,
        "server_settings": {"jit": "off", "application_name": "banglabot"},
    }
    host = (make_url(database_url).host or "").lower()
    if host not in {"localhost", "127.0.0.1", "::1"}:
        ctx = ssl.SSLContext(ssl.PROTOCOL_TLS_CLIENT)
        ctx.check_hostname = False
        ctx.verify_mode = ssl.CERT_NONE
        args["ssl"] = ctx
    else:
        args["ssl"] = False
    return args


_settings = get_settings()
engine = create_async_engine(
    _settings.database_url,
    pool_size=5,
    max_overflow=5,
    pool_pre_ping=True,
    pool_recycle=180,
    pool_timeout=30,
    connect_args=_connect_args(_settings.database_url),
)

AsyncSessionLocal = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)


async def get_db():
    async with AsyncSessionLocal() as session:
        yield session
