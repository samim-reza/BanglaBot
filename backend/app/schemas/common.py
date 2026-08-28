from typing import Any

from pydantic import BaseModel, Field


class Page(BaseModel):
    items: list[Any]
    total: int
    page: int
    page_size: int


class PageQuery(BaseModel):
    page: int = Field(default=1, ge=1)
    page_size: int = Field(default=20, ge=1, le=200)
