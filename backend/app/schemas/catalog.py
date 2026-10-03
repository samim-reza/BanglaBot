from datetime import datetime
from typing import Any

from pydantic import BaseModel, ConfigDict, Field


class CatalogItemOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    kind: str
    name: str
    data: dict[str, Any]
    active: bool
    sort_order: int
    created_at: datetime | None = None
    updated_at: datetime | None = None


class CatalogItemIn(BaseModel):
    """``name`` plus the vertical's catalog fields (validated server-side)."""

    model_config = ConfigDict(extra="allow")

    name: str | None = Field(default=None, max_length=200)
    data: dict[str, Any] = Field(default_factory=dict)
    active: bool | None = None
    sort_order: int | None = None


class CatalogImport(BaseModel):
    """CSV text: a header row of field keys or labels, then one item per row."""

    csv: str = Field(min_length=1, max_length=500_000)
    replace: bool = False


class CatalogImportResult(BaseModel):
    created: int
    skipped: int
    errors: list[str]
