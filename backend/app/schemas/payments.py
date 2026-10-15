from datetime import datetime
from typing import Literal

from pydantic import BaseModel, Field


class PayPageOut(BaseModel):
    """What the public pay page shows (no ids beyond the token)."""

    reference: str
    business: str
    description: str
    amount: str
    currency: str
    status: str
    kind: str
    provider: str
    expires_at: datetime | None = None
    paid_at: datetime | None = None
    #: The dummy page may show its "Pay" button.
    can_complete: bool
    #: Where to send the buyer after paying (empty = stay on the page).
    return_url: str = ""


class PaymentOut(BaseModel):
    id: str
    kind: str
    provider: str
    amount: str
    currency: str
    status: str
    url: str
    created_at: datetime | None = None
    paid_at: datetime | None = None
    expires_at: datetime | None = None
    hold_until: datetime | None = None


class MarkPaidOut(BaseModel):
    order_id: str
    status: str
    payment_status: str
    payment: PaymentOut


class PaymentSettingsIn(BaseModel):
    #: platform = the platform's links (dummy / Stripe); link = the owner's own link template.
    provider: Literal["platform", "link"] | None = None
    link_template: str | None = Field(default=None, max_length=500)
    methods: list[Literal["online", "at_venue"]] | None = Field(default=None, max_length=2)


class PaymentSettingsOut(BaseModel):
    provider: str
    link_template: str
    methods: list[str]
    #: What "platform" links are right now: dummy | stripe.
    platform_provider: str


class WebhookAck(BaseModel):
    received: bool = True
    status: str = ""
