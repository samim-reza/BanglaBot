"""BanglaBot — Bengali voice agent that confirms ecommerce orders by phone."""

from contextlib import asynccontextmanager

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware

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


@asynccontextmanager
async def lifespan(app: FastAPI):
    await connect_cache()
    await bootstrap()
    yield
    await close_cache()
    await engine.dispose()


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


@app.get("/health")
async def health():
    return {"status": "ok", "cache": cache_backend()}
