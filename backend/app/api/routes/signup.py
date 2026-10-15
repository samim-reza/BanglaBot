"""Self-serve purchase (public): the catalog, quotes, signup → checkout, email verification.

Registered before ``public.router`` so this data-driven ``/api/public/catalog``
(same keys as before, plus prices / limits / billing) is the one served.
"""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Query, Request
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.addons import public_catalog as addon_catalog
from app.core.plans import ANNUAL_MONTHS
from app.core.ratelimit import rate_limit
from app.core.regions import regions_json
from app.db.session import get_db
from app.schemas.signup import QuoteIn, SignupIn, VerifyEmailIn
from app.services import catalog_plans, signup_service
from app.services.pricing import CURRENCY, INTERVALS, QuoteError, build_quote

router = APIRouter(tags=["signup"])


def _vertical(key: str) -> str | None:
    vertical = key.strip().lower() or None
    if vertical and vertical not in catalog_plans.offered_verticals():
        raise HTTPException(status_code=422, detail="That business type isn't offered")
    return vertical


@router.get("/api/public/catalog")
async def public_catalog(vertical: str = Query(default="", max_length=32)):
    """Verticals open for signup, visible tiers and add-ons (optionally for one vertical), regions."""
    from app.verticals import VERTICALS

    await catalog_plans.ensure_fresh()
    chosen = _vertical(vertical)
    return {
        "verticals": [
            {"key": v.key, "label": v.label, "description": v.description, "directions": v.directions}
            for key, v in VERTICALS.items()
            if key in catalog_plans.offered_verticals()
        ],
        "plans": catalog_plans.tiers_json(include_hidden=False, vertical=chosen),
        "addons": addon_catalog(vertical=chosen),
        "regions": regions_json(),
        "billing": {"currency": CURRENCY, "intervals": list(INTERVALS), "annual_months": ANNUAL_MONTHS},
    }


@router.post("/api/public/signup/quote")
async def signup_quote(data: QuoteIn, request: Request):
    await rate_limit(request, "signup-quote", max_hits=120, per_seconds=600)
    await catalog_plans.ensure_fresh()
    try:
        return build_quote(data.tier, data.interval, data.addons, vertical=_vertical(data.vertical)).as_json()
    except QuoteError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc


@router.post("/api/public/signup", status_code=201)
async def signup(data: SignupIn, request: Request, db: AsyncSession = Depends(get_db)):
    """Creates the account (inactive) + a pending subscription; returns where to pay."""
    return await signup_service.signup(db, request, data)


@router.post("/api/public/signup/verify-email")
async def verify_email(data: VerifyEmailIn, request: Request, db: AsyncSession = Depends(get_db)):
    return await signup_service.verify_email(db, request, data.token)


@router.get("/api/public/signup/status")
async def signup_status(request: Request, reference: str = Query(min_length=8, max_length=64), db: AsyncSession = Depends(get_db)):
    """For the page the buyer lands on after checkout (``reference`` from the signup answer)."""
    await rate_limit(request, "signup-status", max_hits=60, per_seconds=600)
    return await signup_service.status_of(db, reference)
