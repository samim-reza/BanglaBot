from datetime import datetime
from decimal import Decimal

from pydantic import BaseModel, ConfigDict, Field


class RateOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    cost_key: str
    label_bn: str
    unit: str
    rate_bdt: Decimal
    effective_from: datetime
    created_by: str


class RateUpdate(BaseModel):
    cost_key: str
    rate_bdt: Decimal = Field(ge=0)
