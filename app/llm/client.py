import asyncio
import json
import os
import random
import time
from dataclasses import dataclass
from typing import Any

from openai import AsyncOpenAI, APIConnectionError, APITimeoutError, APIStatusError, RateLimitError


@dataclass
class ModelResponse:
    text: str
    input_tokens: int | None
    output_tokens: int | None
    duration_ms: int
    model: str


class LLMClient:
    """OpenAI-compatible client with explicit timeout and bounded retries."""

    def __init__(self) -> None:
        self.model = os.getenv("LLM_MODEL", "openrouter/free")
        self.base_url = os.getenv("LLM_BASE_URL", "https://openrouter.ai/api/v1")
        self.api_key = os.getenv("LLM_API_KEY", "")
        self.timeout = float(os.getenv("LLM_TIMEOUT_SECONDS", "30"))
        self.max_retries = int(os.getenv("LLM_MAX_RETRIES", "2"))
        self.client = AsyncOpenAI(
            base_url=self.base_url,
            api_key=self.api_key or "missing-key",
            timeout=self.timeout,
            max_retries=0,  # retries are explicit and observable below
        )

    async def complete(self, system_prompt: str, user_text: str) -> ModelResponse:
        last_error: Exception | None = None
        for attempt in range(self.max_retries + 1):
            started = time.perf_counter()
            try:
                response = await self.client.chat.completions.create(
                    model=self.model,
                    temperature=0.0,
                    messages=[
                        {"role": "system", "content": system_prompt},
                        {"role": "user", "content": json.dumps({"text": user_text})},
                    ],
                )
                usage = getattr(response, "usage", None)
                return ModelResponse(
                    text=response.choices[0].message.content or "",
                    input_tokens=getattr(usage, "prompt_tokens", None),
                    output_tokens=getattr(usage, "completion_tokens", None),
                    duration_ms=round((time.perf_counter() - started) * 1000),
                    model=self.model,
                )
            except (APITimeoutError, APIConnectionError, RateLimitError, APIStatusError) as exc:
                last_error = exc
                if not self._retryable(exc) or attempt >= self.max_retries:
                    raise
                delay = self._retry_after(exc)
                if delay is None:
                    delay = min(4.0, 2**attempt) + random.uniform(0, 0.25)
                await asyncio.sleep(delay)
        raise last_error or RuntimeError("LLM request failed")

    @staticmethod
    def _retryable(exc: Exception) -> bool:
        if isinstance(exc, (APITimeoutError, APIConnectionError, RateLimitError)):
            return True
        if isinstance(exc, APIStatusError):
            return exc.status_code == 429 or exc.status_code >= 500
        return False

    @staticmethod
    def _retry_after(exc: Exception) -> float | None:
        response = getattr(exc, "response", None)
        headers: Any = getattr(response, "headers", {}) if response else {}
        value = headers.get("retry-after") if headers else None
        try:
            return float(value) if value is not None else None
        except (TypeError, ValueError):
            return None
