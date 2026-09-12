"""Async-friendly wrapper around the Groq API with retries and model discovery."""

from __future__ import annotations

import asyncio
import logging
import os
import time
from typing import List, Optional

import groq

log = logging.getLogger("manubot.llm")

DEFAULT_MODEL = "qwen/qwen3.8-27b"

# Fallback catalog used if the live models list can't be fetched.
KNOWN_MODELS = [
    "qwen/qwen3.8-27b",
    "qwen/qwen3.6-27b",
    "openai/gpt-oss-120b",
    "openai/gpt-oss-20b",
    "groq/compound",
    "groq/compound-mini",
    "allam-2-7b",
]


class LLMError(Exception):
    """Raised when the model can't produce a usable response."""


class GroqClient:
    def __init__(self, api_key: Optional[str] = None, max_retries: int = 3):
        self._client = groq.Groq(api_key=api_key or os.getenv("GROQ_API_KEY"))
        self.max_retries = max_retries
        self._models: Optional[List[str]] = None

    # -- discovery -------------------------------------------------------------
    def list_models(self, refresh: bool = False) -> List[str]:
        if self._models and not refresh:
            return self._models
        try:
            resp = self._client.models.list()
            ids = sorted(m.id for m in resp.data)
            if ids:
                self._models = ids
                return ids
        except Exception as exc:  # noqa: BLE001
            log.warning("model discovery failed: %s", exc)
        self._models = KNOWN_MODELS
        return self._models

    # -- sync generation (call via asyncio.to_thread) --------------------------
    def generate(
        self,
        system: str,
        messages: List[dict],
        model: Optional[str] = None,
        temperature: float = 0.9,
        max_tokens: int = 900,
    ) -> str:
        model = model or DEFAULT_MODEL
        payload = [{"role": "system", "content": system}] + list(messages)
        last_exc: Optional[Exception] = None

        for attempt in range(1, self.max_retries + 1):
            try:
                completion = self._client.chat.completions.create(
                    model=model,
                    messages=payload,
                    temperature=temperature,
                    max_tokens=max_tokens,
                )
            except (groq.RateLimitError, groq.APIConnectionError, groq.APITimeoutError) as exc:
                last_exc = exc
                wait = min(2 ** attempt, 20)
                log.warning("LLM attempt %s/%s failed (%s), retrying in %ss", attempt, self.max_retries, exc, wait)
                time.sleep(wait)
                continue
            except groq.APIStatusError as exc:
                log.error("LLM API status error: %s", exc)
                raise LLMError(f"LLM API error: {exc}") from exc

            content = completion.choices[0].message.content if completion.choices else None
            if content and content.strip():
                return content.strip()
            raise LLMError("LLM returned an empty response")

        raise LLMError(f"LLM unavailable after {self.max_retries} attempts ({last_exc})")

    async def agenerate(self, *args, **kwargs) -> str:
        """Run generation off the event loop."""
        return await asyncio.to_thread(self.generate, *args, **kwargs)