"""Finance knobs from the ``.env`` files (the finance engine owns them, like the provider layer)."""

from __future__ import annotations

from decimal import Decimal, InvalidOperation
from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict

from app.core.config import _settings_env_files


class FinanceSettings(BaseSettings):
    model_config = SettingsConfigDict(env_file=_settings_env_files(), env_file_encoding="utf-8", extra="ignore")

    #: Ledger lines (usage_events) older than this are deleted; daily rollups are kept.
    finance_event_retention_days: int = 400
    #: Daily spend caps per provider in USD, e.g. "openai=5,deepgram=3,azure=2" (empty = none).
    #: The admin console's caps (platform_settings "finance.caps") override these per provider.
    provider_daily_caps_usd: str = ""
    #: How often the finance jobs run (SMS metering, cap refresh, retention).
    finance_job_interval_seconds: int = 300


def parse_caps(raw: str | None) -> dict[str, Decimal]:
    """``"openai=5, deepgram=3.5"`` → ``{"openai": Decimal("5"), "deepgram": Decimal("3.5")}`` (junk skipped)."""
    caps: dict[str, Decimal] = {}
    for part in str(raw or "").split(","):
        name, _, value = part.partition("=")
        name = name.strip().lower()
        if not name or not value.strip():
            continue
        try:
            amount = Decimal(value.strip())
        except InvalidOperation:
            continue
        if amount.is_finite() and amount >= 0:
            caps[name] = amount
    return caps


@lru_cache
def get_finance_settings() -> FinanceSettings:
    return FinanceSettings()


__all__ = ["FinanceSettings", "get_finance_settings", "parse_caps"]
