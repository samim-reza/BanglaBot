"""BanglaBot — Bengali voice agent that confirms ecommerce orders by phone."""

import asyncio
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from loguru import logger

from app.api.routes import (
    admin,
    admin_billing,
    admin_finance,
    admin_platform,
    admin_support,
    auth,
    billing,
    orders,
    public,
    support,
    twilio,
)
from app.core.cache import cache_backend, close_cache, connect_cache
from app.core.config import get_settings
from app.db.bootstrap import bootstrap
from app.db.session import engine
from app.voice.tts_cache import cache as tts_audio_cache


async def _sweep_tts_cache():
    """Reconcile the TTS audio ledger with the disk in the background.

    Self-heals after crashes, manual deletions or deploys: lost clips are
    ledgered as rebuildable, orphan files are adopted, counters made truthful.
    Never blocks startup and never fails it.
    """
    try:
        report = await asyncio.to_thread(tts_audio_cache.sweep)
        if report["newly_missing"] or report["adopted_orphans"]:
            logger.info(f"tts-cache sweep: {report}")
    except Exception as exc:  # noqa: BLE001
        logger.warning(f"tts-cache sweep failed: {exc}")


@asynccontextmanager
async def lifespan(app: FastAPI):
    await connect_cache()
    await bootstrap()
    if get_settings().tts_cache_enabled:
        app.state.tts_sweep_task = asyncio.create_task(_sweep_tts_cache())
    yield
    await close_cache()
    await engine.dispose()
    tts_audio_cache.close()


app = FastAPI(title="BanglaBot", lifespan=lifespan)


@app.middleware("http")
async def security_headers(request: Request, call_next):
    response = await call_next(request)
    response.headers.setdefault("X-Content-Type-Options", "nosniff")
    response.headers.setdefault("X-Frame-Options", "DENY")
    response.headers.setdefault("Referrer-Policy", "no-referrer")
    response.headers.setdefault("Permissions-Policy", "camera=(), microphone=(), geolocation=()")
    if request.url.scheme == "https":
        response.headers.setdefault(
            "Strict-Transport-Security", "max-age=31536000; includeSubDomains"
        )
    return response


settings = get_settings()
# With allow_credentials a wildcard origin would let any site call the API with
# a user's token — only the configured frontend origin(s) are allowed.
allowed_origins = [o.strip() for o in settings.frontend_origin.split(",") if o.strip()]
app.add_middleware(
    CORSMiddleware,
    allow_origins=allowed_origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(auth.router)
app.include_router(public.router)
app.include_router(orders.router)
app.include_router(billing.router)
app.include_router(support.router)
app.include_router(admin.router)
app.include_router(admin_billing.router)
app.include_router(admin_finance.router)
app.include_router(admin_support.router)
app.include_router(admin_platform.router)
app.include_router(twilio.router)

# Dev-only cost lab: unauthenticated, and a cache miss spends real TTS credits.
if settings.environment != "production":
    from app.api.routes import tts_lab

    app.include_router(tts_lab.router)


@app.get("/health")
async def health():
    return {"status": "ok", "cache": cache_backend()}
