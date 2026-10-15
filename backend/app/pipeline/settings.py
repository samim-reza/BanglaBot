"""Which verticals run on the skill pipeline (the rest keep their legacy flow — a per-vertical rollback)."""

from __future__ import annotations

from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict

from app.core.config import _settings_env_files


class PipelineSettings(BaseSettings):
    model_config = SettingsConfigDict(env_file=_settings_env_files(), env_file_encoding="utf-8", extra="ignore")

    #: Comma-separated vertical keys, or "all".
    pipeline_verticals: str = "all"

    def enabled(self, vertical: str) -> bool:
        wanted = {part.strip().lower() for part in self.pipeline_verticals.split(",") if part.strip()}
        return "all" in wanted or vertical in wanted


@lru_cache
def get_pipeline_settings() -> PipelineSettings:
    return PipelineSettings()


__all__ = ["PipelineSettings", "get_pipeline_settings"]
