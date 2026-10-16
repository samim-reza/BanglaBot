"""FastAPI entry point: the multi-business voice & chat agent platform."""

import asyncio
import contextlib
import faulthandler
from contextlib import asynccontextmanager

import structlog
from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import JSONResponse

from app.api.routes import addons, admin, admin_audit, admin_users, auth, calls, catalog, channels, integrations, orders, public, telnyx, twilio
from app.api.routes import admin_flow, admin_system, agent_flow
from app.api.routes import admin_plans, plan, signup
from app.api.routes import admin_finance, payments
from app.core.config import get_settings
from app.core.http_security import BodySizeLimitMiddleware, SecurityHeadersMiddleware, SplitCORSMiddleware, cors_origins
from app.core.logging import configure_logging
from app.core.redis import close_redis, connect_redis
from app.core.security import boot_guard
from app.db.bootstrap import bootstrap
from app.db.session import engine
from app.services import billing_jobs, call_service, dialer_service, sms_service
from app.services.payments import holds as payment_holds
from app.finance import scheduler as finance_scheduler
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
    # Production refuses to start with default / weak secrets (development only warns).
    boot_guard.enforce(settings)
    log = structlog.get_logger(__name__)
    await log.ainfo("starting", app=settings.app_name, environment=settings.environment, public_base_url=settings.public_base_url)
    await connect_redis()
    await bootstrap()
    if not settings.public_base_url:
        await log.awarning("public_base_url_missing", hint="set PUBLIC_BASE_URL before placing calls")
    # Open the OpenAI connection now so the first call's first turn skips the TLS handshake.
    asyncio.create_task(warm_connection(settings.openai_api_key))
    await call_service.configure_inbound_webhook()
    background = [
        # Fires accounts' scheduled "auto call" batches.
        asyncio.create_task(dialer_service.run_scheduler(), name="auto-call-scheduler"),
        asyncio.create_task(_reap_chats(), name="chat-reaper"),
        # SMS reminders before appointments / visits / viewings.
        asyncio.create_task(sms_service.run_reminders(), name="sms-reminders"),
        # Plan catalog refresh (admin edits reach every worker) + ended subscription periods.
        asyncio.create_task(billing_jobs.run(), name="billing-jobs"),
        # Releases unpaid booking holds, expires stale payment links.
        asyncio.create_task(payment_holds.run_sweeper(), name="payment-sweeper"),
        # SMS metering, cost-guard refresh, ledger retention.
        asyncio.create_task(finance_scheduler.run_scheduler(), name="finance-jobs"),
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
    with contextlib.suppress(Exception):
        # Flush disk manifests and let background uploads to the shared audio cache finish.
        from app.voice.providers.tts import aclose_all

        await aclose_all()
    await close_shared_client()
    await close_redis()
    await engine.dispose()


# The interactive docs / schema map every route: off in production unless EXPOSE_API_DOCS=true.
_docs = boot_guard.api_docs_enabled(settings)
app = FastAPI(
    title=settings.app_name,
    version="2.0.0",
    lifespan=lifespan,
    docs_url="/docs" if _docs else None,
    redoc_url="/redoc" if _docs else None,
    openapi_url="/openapi.json" if _docs else None,
)

# Middleware, innermost first: body size cap → CORS (widget paths open to any site,
# the rest only to the portal's origins) → security headers on every response.
app.add_middleware(BodySizeLimitMiddleware, max_bytes=settings.max_request_bytes, max_small_bytes=settings.max_public_request_bytes)
allowed_origins, allowed_origin_regex = cors_origins(settings.frontend_origin, production=boot_guard.is_production(settings))
app.add_middleware(
    SplitCORSMiddleware,
    allow_origins=allowed_origins,
    allow_origin_regex=allowed_origin_regex,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
    # The console reads these cross-origin: "ask for the 2FA code" and rate-limit waits.
    expose_headers=["X-2FA-Required", "Retry-After"],
)
app.add_middleware(SecurityHeadersMiddleware, hsts=boot_guard.is_production(settings))


@app.exception_handler(HTTPException)
async def http_exception_handler(request: Request, exc: HTTPException):
    return JSONResponse(status_code=exc.status_code, content={"detail": exc.detail}, headers=dict(exc.headers or {}))


@app.exception_handler(Exception)
async def unhandled_exception_handler(request: Request, exc: Exception):
    structlog.get_logger(__name__).warning("unhandled_exception", path=request.url.path, error=str(exc), error_type=type(exc).__name__)
    return JSONResponse(status_code=500, content={"detail": "Internal server error"})


# Before public.router: its data-driven /api/public/catalog is the one served.
app.include_router(signup.router)
app.include_router(public.router)
app.include_router(auth.router)
app.include_router(orders.router)
app.include_router(catalog.router)
app.include_router(calls.router)
app.include_router(integrations.router)
app.include_router(addons.router)
app.include_router(channels.router)
app.include_router(admin.router)
app.include_router(admin_users.router)
app.include_router(admin_audit.router)
app.include_router(plan.router)
app.include_router(admin_plans.router)
app.include_router(agent_flow.router)
app.include_router(admin_flow.router)
app.include_router(admin_system.router)
app.include_router(payments.router)
app.include_router(admin_finance.router)
app.include_router(telnyx.router)
app.include_router(twilio.router)
