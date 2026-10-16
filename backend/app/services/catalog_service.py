"""The account's catalog — doctors, listings, services — that the agent answers
and books from. Validated against the vertical's catalog field specs; bulk
upload takes CSV whose header row names the fields (by key or by label)."""

from __future__ import annotations

import csv
import io
from typing import Any

from fastapi import HTTPException
from sqlalchemy import delete, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.datetime_utils import utcnow
from app.models import CatalogItem, Merchant
from app.schemas.catalog import CatalogItemIn
from app.services.context_service import invalidate_catalog
from app.services.tenancy import owned
from app.services.calendar.links import check_ics_url
from app.verticals import vertical_for
from app.verticals.forms import FieldError, split_catalog

MAX_ITEMS = 500


def _vertical_kind(merchant: Merchant, kind: str | None = None) -> str:
    """The catalog kind to work on: ``kind`` when the vertical keeps it (a salon: service / staff), else the primary."""
    vertical = vertical_for(merchant)
    if not vertical.catalog_kind:
        raise HTTPException(status_code=404, detail="This account type has no catalog")
    spec = vertical.catalog_spec(kind)
    if spec is None:
        raise HTTPException(status_code=422, detail=f"Unknown catalog kind {kind!r}")
    return spec.kind


def _fields(merchant: Merchant, kind: str | None = None):  # noqa: ANN202
    spec = vertical_for(merchant).catalog_spec(kind)
    return spec.fields if spec is not None else vertical_for(merchant).catalog_fields


def _check_links(values: dict[str, Any]) -> None:
    """A catalog item's busy-calendar link is fetched by the server: refuse private / non-web addresses."""
    link = str(values.get("calendar_ics") or "").strip()
    if link:
        try:
            check_ics_url(link)
        except ValueError as exc:
            raise FieldError("calendar_ics", str(exc)) from exc


def _payload(data: CatalogItemIn) -> dict[str, Any]:
    payload = dict(data.data or {})
    payload.update(data.model_extra or {})
    if data.name is not None:
        payload["name"] = data.name
    return payload


async def list_items(db: AsyncSession, merchant: Merchant, kind: str | None = None) -> list[CatalogItem]:
    kind = _vertical_kind(merchant, kind)
    rows = await db.scalars(
        select(CatalogItem)
        .where(CatalogItem.merchant_id == merchant.id, CatalogItem.kind == kind)
        .order_by(CatalogItem.sort_order, CatalogItem.created_at)
    )
    return list(rows)


async def get_item(db: AsyncSession, merchant: Merchant, item_id: str) -> CatalogItem:
    return await owned(db, CatalogItem, item_id, merchant, detail="Catalog item not found")


async def create_item(db: AsyncSession, merchant: Merchant, data: CatalogItemIn, kind: str | None = None) -> CatalogItem:
    kind = _vertical_kind(merchant, kind)
    count = int(await db.scalar(select(func.count(CatalogItem.id)).where(CatalogItem.merchant_id == merchant.id)) or 0)
    if count >= MAX_ITEMS:
        raise HTTPException(status_code=409, detail=f"An account can have at most {MAX_ITEMS} catalog items")
    try:
        name, values = split_catalog(vertical_for(merchant), _payload(data), kind=kind)
        _check_links(values)
    except FieldError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    item = CatalogItem(
        merchant_id=merchant.id,
        kind=kind,
        name=str(name or "").strip()[:200],
        data=values,
        active=True if data.active is None else bool(data.active),
        sort_order=int(data.sort_order if data.sort_order is not None else count),
    )
    db.add(item)
    await db.commit()
    await db.refresh(item)
    invalidate_catalog(merchant.id)
    return item


async def update_item(db: AsyncSession, merchant: Merchant, item: CatalogItem, data: CatalogItemIn) -> CatalogItem:
    try:
        name, values = split_catalog(vertical_for(merchant), _payload(data), partial=True, kind=item.kind or None)
        _check_links(values)
    except FieldError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    if name:
        item.name = name[:200]
    if values or data.data:
        merged = dict(item.data or {})
        merged.update(values)
        # An explicitly cleared optional field is removed.
        for key, value in dict(data.data or {}).items():
            if value in (None, "") and key in merged:
                merged.pop(key)
        item.data = merged
    if data.active is not None:
        item.active = bool(data.active)
    if data.sort_order is not None:
        item.sort_order = int(data.sort_order)
    item.updated_at = utcnow()
    await db.commit()
    await db.refresh(item)
    invalidate_catalog(merchant.id)
    return item


async def delete_item(db: AsyncSession, item: CatalogItem) -> None:
    merchant_id = item.merchant_id
    await db.delete(item)
    await db.commit()
    invalidate_catalog(merchant_id)


def _header_map(merchant: Merchant, header: list[str], kind: str | None = None) -> dict[int, str]:
    """CSV column index → field key (headers may be keys or labels)."""
    specs = _fields(merchant, kind)
    lookup: dict[str, str] = {}
    for spec in specs:
        lookup[spec.key.lower()] = spec.key
        for label in spec.label.values():
            lookup[label.strip().lower()] = spec.key
    mapping: dict[int, str] = {}
    for index, raw in enumerate(header):
        key = lookup.get(str(raw or "").strip().lower())
        if key:
            mapping[index] = key
    return mapping


async def import_csv(db: AsyncSession, merchant: Merchant, text: str, *, replace: bool = False, kind: str | None = None) -> dict[str, Any]:
    kind = _vertical_kind(merchant, kind)
    vertical = vertical_for(merchant)
    try:
        rows = list(csv.reader(io.StringIO(text.strip())))
    except csv.Error as exc:
        raise HTTPException(status_code=422, detail="The CSV couldn't be read — check its quotes and line breaks") from exc
    if not rows:
        raise HTTPException(status_code=422, detail="The CSV is empty")
    mapping = _header_map(merchant, rows[0], kind)
    if "name" not in mapping.values():
        raise HTTPException(status_code=422, detail="The CSV header must include a 'name' column")
    skipped = 0
    errors: list[str] = []
    parsed: list[tuple[int, Any, dict[str, Any]]] = []
    for line_no, row in enumerate(rows[1:], start=2):
        if not any(cell.strip() for cell in row):
            continue
        payload: dict[str, Any] = {}
        for index, key in mapping.items():
            if index < len(row) and row[index].strip():
                payload[key] = row[index].strip()
        try:
            name, values = split_catalog(vertical, payload, kind=kind)
            _check_links(values)
        except FieldError as exc:
            skipped += 1
            errors.append(f"line {line_no}: {exc}")
            continue
        parsed.append((line_no, name, values))
    if replace:
        if not parsed:
            # Validate first: a file with no usable rows must not wipe the catalog.
            raise HTTPException(status_code=422, detail="No valid rows — the catalog was left as it was")
        await db.execute(delete(CatalogItem).where(CatalogItem.merchant_id == merchant.id, CatalogItem.kind == kind))
    existing = int(await db.scalar(select(func.count(CatalogItem.id)).where(CatalogItem.merchant_id == merchant.id)) or 0)
    created = 0
    for line_no, name, values in parsed:
        if existing + created >= MAX_ITEMS:
            skipped += 1
            errors.append(f"line {line_no}: catalog limit of {MAX_ITEMS} reached")
            continue
        db.add(CatalogItem(merchant_id=merchant.id, kind=kind, name=str(name)[:200], data=values, active=True, sort_order=existing + created))
        created += 1
    await db.commit()
    invalidate_catalog(merchant.id)
    return {"created": created, "skipped": skipped, "errors": errors[:50]}


def csv_template(merchant: Merchant, kind: str | None = None) -> str:
    specs = _fields(merchant, kind)
    buffer = io.StringIO()
    writer = csv.writer(buffer)
    writer.writerow([spec.key for spec in specs])
    example = []
    for spec in specs:
        placeholder = spec.placeholder or ""
        if spec.type == "days":
            example.append("mon,wed,sat" if spec.key else "")
        elif spec.default is not None and not isinstance(spec.default, list):
            example.append(str(spec.default))
        elif "…" in placeholder:
            # An elided hint ("https://calendar.google.com/…/basic.ics"), not a value: importing
            # the example row as-is must not configure a bogus busy calendar.
            example.append("")
        elif not placeholder and spec.required and spec.type in ("money", "number"):
            example.append("10")  # the example row imports as downloaded
        else:
            example.append(placeholder)
    writer.writerow(example)
    return buffer.getvalue()


__all__ = ["create_item", "csv_template", "delete_item", "get_item", "import_csv", "list_items", "update_item"]
