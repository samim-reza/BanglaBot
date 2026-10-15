"""FastAPI application factory; models load once in the lifespan (before the port serves)."""

from __future__ import annotations

import asyncio
import logging
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from fastapi import FastAPI

from . import __version__
from .config import get_settings
from .engines import Engines
from .routes_http import router as http_router
from .routes_ws import router as ws_router

log = logging.getLogger("speech")


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncIterator[None]:
    settings = get_settings()
    engines = await asyncio.to_thread(Engines.load, settings)
    app.state.engines = engines
    log.info(
        "speech server ready on %s:%d (stt=%s/%s %s, tts=%s, vram=%s MB, auth=%s)",
        settings.host,
        settings.port,
        engines.stt.device,
        engines.stt.precision,
        engines.stt.name,
        engines.tts.device,
        engines.vram_mb,
        "on" if settings.api_key else "off",
    )
    try:
        yield
    finally:
        engines.close()


def create_app() -> FastAPI:
    app = FastAPI(title="BanglaBot speech server", version=__version__, lifespan=lifespan)
    app.include_router(http_router)
    app.include_router(ws_router)
    return app
