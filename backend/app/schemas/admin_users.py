"""Request bodies for admin sign-in (with 2FA) and admin-user management."""

from pydantic import BaseModel, Field

from app.schemas.admin import AdminLoginRequest


class AdminLoginIn(AdminLoginRequest):
    #: The authenticator code, once two-factor sign-in is on.
    code: str = Field(default="", max_length=12)


class AdminUserCreate(BaseModel):
    username: str = Field(min_length=3, max_length=80, pattern=r"^[A-Za-z0-9_.@-]+$")
    password: str = Field(min_length=1, max_length=200)
    role: str = Field(default="support", max_length=16)


class AdminUserUpdate(BaseModel):
    role: str | None = Field(default=None, max_length=16)
    active: bool | None = None
    password: str | None = Field(default=None, min_length=1, max_length=200)
    #: Turn the admin's two-factor sign-in off (lost phone); they set it up again.
    reset_totp: bool = False


class PasswordChangeIn(BaseModel):
    current_password: str = Field(min_length=1, max_length=200)
    new_password: str = Field(min_length=1, max_length=200)


class TotpCodeIn(BaseModel):
    code: str = Field(min_length=6, max_length=12)
