"""The owner's call-flow editor: read, save, preview, reset."""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Request
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_current_merchant
from app.db.session import get_db
from app.models import Merchant
from app.pipeline.config import FlowConfigError
from app.schemas.agent_flow import AgentFlowPreview, AgentFlowSave
from app.services import agent_flow_service

router = APIRouter(prefix="/api/agent/flow", tags=["agent-flow"])


def config_error(exc: FlowConfigError) -> HTTPException:
    return HTTPException(status_code=422, detail={"errors": exc.errors, "locked": exc.locked})


@router.get("")
async def get_flow(merchant: Merchant = Depends(get_current_merchant)):
    return agent_flow_service.describe(merchant)


@router.put("")
async def save_flow(data: AgentFlowSave, request: Request, merchant: Merchant = Depends(get_current_merchant), db: AsyncSession = Depends(get_db)):
    try:
        return await agent_flow_service.save(
            db, merchant, data.config, base_hash=data.base_hash, actor={"type": "merchant", "id": str(merchant.id)}, request=request
        )
    except FlowConfigError as exc:
        raise config_error(exc) from exc


@router.post("/preview")
async def preview_flow(data: AgentFlowPreview, merchant: Merchant = Depends(get_current_merchant)):
    try:
        return agent_flow_service.preview(merchant, data.config, language=data.language)
    except FlowConfigError as exc:
        raise config_error(exc) from exc


@router.post("/reset")
async def reset_flow(request: Request, merchant: Merchant = Depends(get_current_merchant), db: AsyncSession = Depends(get_db)):
    """Back to the platform defaults (admin locks still apply)."""
    return await agent_flow_service.save(db, merchant, {}, base_hash=None, actor={"type": "merchant", "id": str(merchant.id)}, request=request)
