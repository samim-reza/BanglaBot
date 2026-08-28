from fastapi import APIRouter

from app.core.config import get_settings
from app.core.redis import redis_health

router = APIRouter(tags=["public"])


@router.get("/health")
async def health():
    settings = get_settings()
    return {"status": "ok", "service": settings.app_name, "redis": await redis_health()}
