"""Self-serve purchase payloads: a selection (tier + interval + add-ons), the signup form,
email verification, owner plan changes and the admin's signup decisions."""

from __future__ import annotations

import re
from typing import Literal

from pydantic import BaseModel, Field, field_validator

from app.core.addons import MAX_QUANTITY

_EMAIL = re.compile(r"^[^@\s]{1,64}@[A-Za-z0-9-]+(\.[A-Za-z0-9-]+)+$")
_PHONE = re.compile(r"^\+?[0-9][0-9\s().-]{5,30}$")
_USERNAME = re.compile(r"^[A-Za-z0-9._@+-]{3,80}$")


class SelectionIn(BaseModel):
    tier: str = Field(min_length=1, max_length=24)
    interval: Literal["month", "year"] = "month"
    #: {add-on key: quantity}; 0 = not selected.
    addons: dict[str, int] = Field(default_factory=dict)

    @field_validator("tier")
    @classmethod
    def _tier(cls, value: str) -> str:
        return value.strip().lower()

    @field_validator("addons")
    @classmethod
    def _addons(cls, value: dict[str, int]) -> dict[str, int]:
        if len(value) > 30:
            raise ValueError("too many add-ons")
        cleaned: dict[str, int] = {}
        for key, qty in value.items():
            name = str(key).strip().lower()
            if not name or len(name) > 32:
                raise ValueError("unknown add-on")
            if int(qty) < 0 or int(qty) > MAX_QUANTITY:
                raise ValueError(f"quantities are between 0 and {MAX_QUANTITY}")
            cleaned[name] = int(qty)
        return cleaned


class QuoteIn(SelectionIn):
    vertical: str = Field(default="", max_length=32)


class SignupIn(SelectionIn):
    business_name: str = Field(min_length=2, max_length=160)
    owner_name: str = Field(min_length=1, max_length=120)
    email: str = Field(min_length=5, max_length=160)
    phone: str = Field(default="", max_length=32)
    #: Checked against the password policy (readable 422).
    password: str = Field(min_length=1, max_length=200)
    region: str = Field(default="INTL", max_length=8)
    vertical: str = Field(min_length=1, max_length=32)
    #: Sign-in name; empty = the email.
    username: str = Field(default="", max_length=80)
    #: Honeypot: real visitors never fill this hidden field.
    website: str = Field(default="", max_length=200)

    @field_validator("business_name", "owner_name")
    @classmethod
    def _text(cls, value: str) -> str:
        cleaned = " ".join(value.split())
        if not cleaned:
            raise ValueError("required")
        return cleaned

    @field_validator("email")
    @classmethod
    def _email(cls, value: str) -> str:
        email = value.strip().lower()
        if not _EMAIL.match(email):
            raise ValueError("enter a valid email address")
        return email

    @field_validator("phone")
    @classmethod
    def _phone(cls, value: str) -> str:
        phone = value.strip()
        if phone and not _PHONE.match(phone):
            raise ValueError("enter a valid phone number")
        return phone

    @field_validator("username")
    @classmethod
    def _username(cls, value: str) -> str:
        name = value.strip()
        if name and not _USERNAME.match(name):
            raise ValueError("use 3-80 letters, digits or . _ @ + -")
        return name

    @field_validator("region", "vertical")
    @classmethod
    def _key(cls, value: str) -> str:
        return value.strip()


class VerifyEmailIn(BaseModel):
    token: str = Field(min_length=16, max_length=200)


class PlanChangeIn(SelectionIn):
    pass


class SignupDecisionIn(BaseModel):
    note: str = Field(default="", max_length=500)
    #: Approve: also activate the subscription as paid offline (manual payment).
    mark_paid: bool = False


__all__ = ["PlanChangeIn", "QuoteIn", "SelectionIn", "SignupDecisionIn", "SignupIn", "VerifyEmailIn"]
