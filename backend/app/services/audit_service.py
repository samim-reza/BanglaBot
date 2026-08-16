"""Append-only audit trail shared by all routes."""

from sqlalchemy.ext.asyncio import AsyncSession

from app.models import AuditLog


def record(
    db: AsyncSession,
    *,
    actor_role: str,
    actor_id: str = "",
    actor_name: str = "",
    action: str,
    detail: str = "",
    merchant_id: str | None = None,
) -> None:
    """Add an audit row to the session; the caller commits."""
    db.add(
        AuditLog(
            actor_role=actor_role,
            actor_id=actor_id,
            actor_name=actor_name,
            action=action,
            detail=detail,
            merchant_id=merchant_id,
        )
    )
