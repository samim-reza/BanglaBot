"""The test-phase provider: a link to our own pay page, ``{FRONTEND_ORIGIN}/pay/{token}``.

The token is signed (``typ="pay"``, 24 h) and carries the payment reference,
amount and currency, so the page can show what is owed without a session and
nobody can change the amount. "Paying" is a button on that page
(``POST /api/public/pay/{token}/complete``): no money moves.
"""

from __future__ import annotations

from collections.abc import Mapping
from datetime import datetime, timedelta, timezone
from decimal import Decimal
from typing import Any

from fastapi import HTTPException

from app.core.security import TYP_PAY, sign_token, verify_token
from app.services.payments.base import STATUS_PAID, PaymentError, PaymentEvent, PaymentLink, currency_code, money

PROVIDER = "dummy"
PAY_TOKEN_TTL_SECONDS = 24 * 3600


def sign_pay_token(*, reference: str, amount: Decimal, currency: str, ttl_seconds: int = PAY_TOKEN_TTL_SECONDS) -> str:
    """Short claims on purpose: the URL travels in an SMS."""
    return sign_token({"r": str(reference), "a": str(money(amount)), "c": currency_code(currency)}, ttl_seconds=ttl_seconds, typ=TYP_PAY)


def read_pay_token(token: str) -> dict[str, Any]:
    """``{"reference", "amount", "currency", "exp"}`` of a valid pay token; ``PaymentError`` otherwise."""
    try:
        claims = verify_token(str(token or "")[:1024], typ=TYP_PAY)
    except HTTPException as exc:
        raise PaymentError("This payment link is invalid or has expired") from exc
    reference = str(claims.get("r") or "")
    if not reference:
        raise PaymentError("This payment link is invalid or has expired")
    return {"reference": reference, "amount": money(claims.get("a") or 0), "currency": currency_code(claims.get("c")), "exp": claims.get("exp")}


class DummyProvider:
    name = PROVIDER

    def __init__(self, *, base_url: str | None = None, ttl_seconds: int = PAY_TOKEN_TTL_SECONDS) -> None:
        self._base_url = base_url
        self.ttl_seconds = int(ttl_seconds)

    def base_url(self) -> str:
        if self._base_url is not None:
            return self._base_url.rstrip("/")
        from app.services.payments.config import frontend_base

        return frontend_base()

    async def create_link(
        self,
        *,
        reference: str,
        amount: Decimal,
        currency: str,
        description: str,
        metadata: dict[str, Any],
        success_url: str | None = None,
    ) -> PaymentLink:
        token = sign_pay_token(reference=reference, amount=amount, currency=currency, ttl_seconds=self.ttl_seconds)
        expires = datetime.now(timezone.utc) + timedelta(seconds=self.ttl_seconds)
        return PaymentLink(url=f"{self.base_url()}/pay/{token}", provider=PROVIDER, provider_ref=f"dummy_{reference}", expires_at=expires)

    async def handle_webhook(self, request_body: bytes, headers: Mapping[str, str]) -> PaymentEvent | None:
        """No webhooks: the pay page's button completes the payment."""
        return None

    @staticmethod
    def complete_event(claims: dict[str, Any]) -> PaymentEvent:
        """The "paid" event the pay page's button stands for."""
        reference = str(claims["reference"])
        return PaymentEvent(
            provider=PROVIDER,
            status=STATUS_PAID,
            reference=reference,
            provider_ref=f"dummy_{reference}",
            amount=claims["amount"],
            currency=claims["currency"],
            event_type="dummy.completed",
        )


__all__ = ["PAY_TOKEN_TTL_SECONDS", "PROVIDER", "DummyProvider", "read_pay_token", "sign_pay_token"]
