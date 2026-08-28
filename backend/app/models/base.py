"""Re-export so ``app.models.base`` keeps working as an import path."""

from app.db.base import Base, new_id

__all__ = ["Base", "new_id"]
