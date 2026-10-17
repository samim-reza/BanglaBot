"""Holiday / closure dates the agent never books (Settings → Closures): list them, replace the list.

Stored in ``merchants.vertical_config["closures"]`` (see ``app.flows.closures``). Every read
and save drops ended entries; a closure limited to a catalog item (a doctor, stylist or
resource) is only listed while that item still exists.
"""

from __future__ import annotations

from datetime import date
from typing import Any

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_current_merchant
from app.db.session import get_db
from app.flows import closures
from app.flows.timefmt import business_tz, local_now
from app.models import Merchant

router = APIRouter(prefix="/api/closures", tags=["closures"])


class ClosureIn(BaseModel):
    start: str = Field(max_length=10)
    #: Empty = a single day.
    end: str = Field(default="", max_length=10)
    label: str = Field(default="", max_length=200)
    #: A catalog item's id ("" = the whole business).
    item_id: str = Field(default="", max_length=64)


class ClosuresIn(BaseModel):
    closures: list[ClosureIn] = Field(default_factory=list, max_length=200)


class ClosureOut(BaseModel):
    start: date
    end: date
    label: str = ""
    item_id: str = ""


class ClosureItem(BaseModel):
    """A doctor / stylist / resource a closure can be limited to."""

    id: str
    name: str


class ClosuresOut(BaseModel):
    closures: list[ClosureOut]
    items: list[ClosureItem]
    #: The business's today (closures before it are gone).
    today: date


def _today(merchant: Merchant) -> date:
    from app.services.context_service import merchant_timezone

    return local_now(business_tz(merchant_timezone(merchant))).date()


async def _items(db: AsyncSession, merchant: Merchant) -> list[ClosureItem]:
    from app.services.context_service import load_catalog

    kind = closures.ITEM_KINDS.get(str(getattr(merchant, "vertical", "") or ""))
    if not kind:
        return []
    return [ClosureItem(id=item.id, name=item.name) for item in await load_catalog(db, merchant) if item.kind == kind]


def _view(merchant: Merchant, items: list[ClosureItem], today: date) -> ClosuresOut:
    known = {item.id for item in items}
    rows = [
        ClosureOut(**closure.as_json())
        for closure in closures.from_config(merchant.vertical_config, today=today)
        if not closure.item_id or closure.item_id in known
    ]
    return ClosuresOut(closures=rows, items=items, today=today)


@router.get("", response_model=ClosuresOut)
async def list_closures(merchant: Merchant = Depends(get_current_merchant), db: AsyncSession = Depends(get_db)):
    return _view(merchant, await _items(db, merchant), _today(merchant))


@router.put("", response_model=ClosuresOut)
async def save_closures(data: ClosuresIn, merchant: Merchant = Depends(get_current_merchant), db: AsyncSession = Depends(get_db)):
    items, today = await _items(db, merchant), _today(merchant)
    try:
        cleaned = closures.clean([entry.model_dump() for entry in data.closures], today=today, item_ids=[item.id for item in items])
    except closures.ClosureError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    config: dict[str, Any] = dict(merchant.vertical_config or {})
    if cleaned:
        config[closures.CONFIG_KEY] = cleaned
    else:
        config.pop(closures.CONFIG_KEY, None)
    merchant.vertical_config = config
    await db.commit()
    return _view(merchant, items, today)
