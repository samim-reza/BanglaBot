from datetime import datetime

from pydantic import BaseModel, ConfigDict


class MerchantCreate(BaseModel):
    business_name: str
    owner_name: str = ""
    username: str
    password: str
    phone: str = ""
    email: str = ""
    support_phone: str = ""


class MerchantUpdate(BaseModel):
    business_name: str | None = None
    owner_name: str | None = None
    password: str | None = None
    phone: str | None = None
    support_phone: str | None = None
    active: bool | None = None


class MerchantOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    business_name: str
    owner_name: str
    username: str
    phone: str
    email: str
    support_phone: str
    custom_greeting: str
    max_call_seconds: int
    voice_tier: str
    active: bool
    created_at: datetime
