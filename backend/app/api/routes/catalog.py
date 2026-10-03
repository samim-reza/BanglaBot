"""The account's catalog: doctors / listings / services the agent answers and books from."""

from __future__ import annotations

from fastapi import APIRouter, Depends, Response
from fastapi.responses import PlainTextResponse
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_current_merchant
from app.db.session import get_db
from app.models import Merchant
from app.schemas.catalog import CatalogImport, CatalogImportResult, CatalogItemIn, CatalogItemOut
from app.services import catalog_service

router = APIRouter(prefix="/api/catalog", tags=["catalog"])


@router.get("", response_model=list[CatalogItemOut])
async def list_items(merchant: Merchant = Depends(get_current_merchant), db: AsyncSession = Depends(get_db)):
    return await catalog_service.list_items(db, merchant)


@router.post("", response_model=CatalogItemOut, status_code=201)
async def create_item(data: CatalogItemIn, merchant: Merchant = Depends(get_current_merchant), db: AsyncSession = Depends(get_db)):
    return await catalog_service.create_item(db, merchant, data)


@router.get("/template.csv", response_class=PlainTextResponse)
async def template(merchant: Merchant = Depends(get_current_merchant)):
    return PlainTextResponse(
        catalog_service.csv_template(merchant),
        media_type="text/csv",
        headers={"Content-Disposition": 'attachment; filename="catalog-template.csv"'},
    )


@router.post("/import", response_model=CatalogImportResult)
async def import_csv(data: CatalogImport, merchant: Merchant = Depends(get_current_merchant), db: AsyncSession = Depends(get_db)):
    return await catalog_service.import_csv(db, merchant, data.csv, replace=data.replace)


@router.patch("/{item_id}", response_model=CatalogItemOut)
async def update_item(
    item_id: str, data: CatalogItemIn, merchant: Merchant = Depends(get_current_merchant), db: AsyncSession = Depends(get_db)
):
    item = await catalog_service.get_item(db, merchant, item_id)
    return await catalog_service.update_item(db, merchant, item, data)


@router.delete("/{item_id}", status_code=204)
async def delete_item(item_id: str, merchant: Merchant = Depends(get_current_merchant), db: AsyncSession = Depends(get_db)):
    item = await catalog_service.get_item(db, merchant, item_id)
    await catalog_service.delete_item(db, item)
    return Response(status_code=204)
