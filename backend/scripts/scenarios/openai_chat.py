"""A tiny OpenAI chat client for the simulated caller and the judge (not the agent under test)."""

from __future__ import annotations

import asyncio
import json
from typing import Any

import httpx

from app.core.config import get_settings

URL = "https://api.openai.com/v1/chat/completions"
MODEL = "gpt-5.4-mini"


class OpenAIChat:
    def __init__(self, *, model: str = MODEL, timeout: float = 60.0) -> None:
        key = get_settings().openai_api_key
        if not key:
            raise RuntimeError("OPENAI_API_KEY is not set (.env)")
        self.model = model
        self._client = httpx.AsyncClient(timeout=timeout, headers={"Authorization": f"Bearer {key}"})
        self.prompt_tokens = 0
        self.completion_tokens = 0

    async def complete(self, messages: list[dict[str, str]], *, effort: str = "none", max_tokens: int = 400, json_mode: bool = False) -> str:
        body: dict[str, Any] = {"model": self.model, "messages": messages, "max_completion_tokens": max_tokens, "reasoning_effort": effort}
        if json_mode:
            body["response_format"] = {"type": "json_object"}
        for attempt in range(4):
            response = await self._client.post(URL, json=body)
            if (response.status_code == 429 or response.status_code >= 500) and attempt < 3:
                await asyncio.sleep(2 * (attempt + 1))
                continue
            response.raise_for_status()
            data = response.json()
            usage = data.get("usage") or {}
            self.prompt_tokens += int(usage.get("prompt_tokens") or 0)
            self.completion_tokens += int(usage.get("completion_tokens") or 0)
            return str(data["choices"][0]["message"].get("content") or "").strip()
        raise RuntimeError("OpenAI kept failing")

    async def complete_json(self, messages: list[dict[str, str]], *, effort: str = "low", max_tokens: int = 1200) -> dict[str, Any]:
        text = await self.complete(messages, effort=effort, max_tokens=max_tokens, json_mode=True)
        try:
            return json.loads(text)
        except ValueError:
            return {"pass": False, "issues": [f"judge returned non-JSON: {text[:200]}"]}

    async def aclose(self) -> None:
        await self._client.aclose()
