from pydantic import BaseModel, Field

from app.schemas.merchant import MerchantOut


class LoginRequest(BaseModel):
    username: str = Field(min_length=1, max_length=80)
    password: str = Field(min_length=1, max_length=200)


class MerchantLoginResponse(BaseModel):
    token: str
    merchant: MerchantOut


class ChangePasswordRequest(BaseModel):
    current_password: str = Field(min_length=1, max_length=200)
    new_password: str = Field(min_length=6, max_length=200)


class FlowPreview(BaseModel):
    steps: list[str]
    #: direction ("inbound" / "outbound") → steps
    sections: dict[str, list[str]] = {}
