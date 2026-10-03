"""FastAPI entry point: the multi-business voice & chat agent platform."""

import asyncio
import contextlib
import faulthandler
from contextlib import asynccontextmanager

import structlog
from fastapi import FastAPI, HTTPException, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from app.api.routes import addons, admin, agent, auth, calls, catalog, channels, integrations, orders, public, twilio
from app.core.config import get_settings
from app.core.logging import configure_logging
from app.core.redis import close_redis, connect_redis
from app.db.bootstrap import bootstrap
from app.db.session import engine
from app.services import call_service, dialer_service, sms_service
from app.voice import text_session
from app.voice.llm import close_shared_client, warm_connection

settings = get_settings()
# A hard crash (segfault in a C extension, fatal error) prints the Python stack
# instead of leaving the reloader with a silent dead worker.
faulthandler.enable()

#: Expired chat sessions (website widget, portal test) are finished this often.
CHAT_REAP_SECONDS = 300


async def _reap_chats() -> None:
    while True:
        await asyncio.sleep(CHAT_REAP_SECONDS)
        try:
            await text_session.reap()
        except Exception as exc:  # noqa: BLE001
            await structlog.get_logger(__name__).awarning("chat_reap_failed", error=str(exc))


@asynccontextmanager
async def lifespan(app: FastAPI):
    configure_logging()
    log = structlog.get_logger(__name__)
    await log.ainfo("starting", app=settings.app_name, environment=settings.environment, public_base_url=settings.public_base_url)
    await connect_redis()
    await bootstrap()
    if not settings.public_base_url:
        await log.awarning("public_base_url_missing", hint="set PUBLIC_BASE_URL (or TWILIO_PUBLIC_BASE_URL) before placing calls")
    # Open the OpenAI connection now so the first call's first turn skips the TLS handshake.
    asyncio.create_task(warm_connection(settings.openai_api_key))
    await call_service.configure_inbound_webhook()
    background = [
        # Fires accounts' scheduled "auto call" batches.
        asyncio.create_task(dialer_service.run_scheduler(), name="auto-call-scheduler"),
        asyncio.create_task(_reap_chats(), name="chat-reaper"),
        # SMS reminders before appointments / visits / viewings.
        asyncio.create_task(sms_service.run_reminders(), name="sms-reminders"),
    ]
    yield
    for task in background:
        task.cancel()
    for task in background:
        with contextlib.suppress(asyncio.CancelledError):
            await task
    with contextlib.suppress(Exception):
        from app.voice.tts import _tts

        if _tts is not None:
            _tts.cache.flush()
    await close_shared_client()
    await close_redis()
    await engine.dispose()


app = FastAPI(title=settings.app_name, version="2.0.0", lifespan=lifespan)

allowed_origins = [origin.strip() for origin in settings.frontend_origin.split(",") if origin.strip()]
for origin in ("http://localhost:3000", "http://localhost:5173"):
    if origin not in allowed_origins:
        allowed_origins.append(origin)
app.add_middleware(
    CORSMiddleware,
    allow_origins=allowed_origins,
    allow_origin_regex=r"https://.*\.(ngrok-free\.app|ngrok\.io|trycloudflare\.com)",
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.exception_handler(HTTPException)
async def http_exception_handler(request: Request, exc: HTTPException):
    return JSONResponse(status_code=exc.status_code, content={"detail": exc.detail}, headers=dict(exc.headers or {}))


@app.exception_handler(Exception)
async def unhandled_exception_handler(request: Request, exc: Exception):
    structlog.get_logger(__name__).warning("unhandled_exception", path=request.url.path, error=str(exc), error_type=type(exc).__name__)
    return JSONResponse(status_code=500, content={"detail": "Internal server error"})


app.include_router(public.router)
app.include_router(auth.router)
app.include_router(orders.router)
app.include_router(catalog.router)
app.include_router(calls.router)
app.include_router(agent.router)
app.include_router(integrations.router)
app.include_router(addons.router)
app.include_router(channels.router)
app.include_router(admin.router)
app.include_router(twilio.router)
