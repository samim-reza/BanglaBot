"""Admin: view or edit an account's call flow, lock settings, override its providers."""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Request
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import require_admin
from app.api.routes.agent_flow import config_error
from app.db.session import get_db
from app.models import Merchant
from app.pipeline.config import FlowConfigError
from app.schemas.agent_flow import AgentFlowLocks, AgentFlowSave, ProviderOverrides
from app.services import agent_flow_service, audit_service
from app.voice.providers.llm.endpoints import ENDPOINTS
from app.voice.providers.settings import parse_chain

router = APIRouter(prefix="/api/admin/merchants", tags=["admin-flow"])

STT_PROVIDERS = frozenset({"local", "deepgram", "groq", "openai"})
TTS_PROVIDERS = frozenset({"local", "deepgram", "azure", "gemini", "edge"})


async def _merchant(db: AsyncSession, merchant_id: str) -> Merchant:
    merchant = await db.get(Merchant, merchant_id)
    if merchant is None:
        raise HTTPException(status_code=404, detail="Account not found")
    return merchant


def _actor(admin) -> dict[str, str]:  # noqa: ANN001
    return {"type": "admin", "id": str(getattr(admin, "id", "") or "")}


@router.get("/{merchant_id}/agent-flow")
async def get_flow(merchant_id: str, admin=Depends(require_admin), db: AsyncSession = Depends(get_db)):  # noqa: ANN001
    merchant = await _merchant(db, merchant_id)
    return {**agent_flow_service.describe(merchant), "locks": (merchant.agent_flow_locks or {}).get("locks", {})}


@router.put("/{merchant_id}/agent-flow")
async def save_flow(merchant_id: str, data: AgentFlowSave, request: Request, admin=Depends(require_admin("superadmin", "support")), db: AsyncSession = Depends(get_db)):  # noqa: ANN001
    merchant = await _merchant(db, merchant_id)
    try:
        return await agent_flow_service.save(db, merchant, data.config, base_hash=data.base_hash, actor=_actor(admin), request=request, enforce_locks=False)
    except FlowConfigError as exc:
        raise config_error(exc) from exc


@router.put("/{merchant_id}/agent-flow-locks")
async def save_locks(merchant_id: str, data: AgentFlowLocks, request: Request, admin=Depends(require_admin("superadmin")), db: AsyncSession = Depends(get_db)):  # noqa: ANN001
    merchant = await _merchant(db, merchant_id)
    try:
        return await agent_flow_service.save_locks(db, merchant, {"locks": data.locks}, actor=_actor(admin), request=request)
    except FlowConfigError as exc:
        raise config_error(exc) from exc


@router.put("/{merchant_id}/providers")
async def save_providers(merchant_id: str, data: ProviderOverrides, request: Request, admin=Depends(require_admin("superadmin")), db: AsyncSession = Depends(get_db)):  # noqa: ANN001
    merchant = await _merchant(db, merchant_id)
    errors = []
    for entry in parse_chain(data.llm_chain):
        provider, _, model = entry.partition(":")
        if provider not in ENDPOINTS or not model:
            errors.append({"path": "llm_chain", "message": f"unknown entry {entry!r} (provider:model)"})
    for field, known in (("stt_chain", STT_PROVIDERS), ("tts_chain", TTS_PROVIDERS)):
        errors += [{"path": field, "message": f"unknown provider {name!r}"} for name in parse_chain(getattr(data, field)) if name not in known]
    if errors:
        raise HTTPException(status_code=422, detail={"errors": errors})
    merchant.provider_settings = {key: value for key, value in data.model_dump().items() if value.strip()}
    audit_service.stage(
        db, action="providers.override", actor_type="admin", actor_id=_actor(admin)["id"], target_type="merchant",
        target_id=merchant_id, merchant_id=merchant_id, request=request, meta=merchant.provider_settings,
    )
    await db.commit()
    return {"ok": True, "provider_settings": merchant.provider_settings}
