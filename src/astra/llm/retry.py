"""Retry wrapper for LLM providers."""

import time
from typing import Any

from astra.llm.provider import LLMProvider
from astra.llm.tools import ToolSpec, ToolResult, ToolCallResult


class RetryingProvider(LLMProvider):
    """Wraps an LLM provider with exponential backoff retry logic."""

    def __init__(
        self,
        inner: LLMProvider,
        max_retries: int = 3,
        base_delay: float = 1.0,
        backoff: float = 2.0,
    ):
        self._inner = inner
        self._max_retries = max_retries
        self._base_delay = base_delay
        self._backoff = backoff

    def generate(
        self,
        messages: list[dict[str, Any]],
        system_prompt: str | None = None,
        max_tokens: int = 2048,
        temperature: float = 0.7,
    ) -> str:
        last_exception: Exception | None = None
        for attempt in range(self._max_retries):
            try:
                return self._inner.generate(
                    messages=messages,
                    system_prompt=system_prompt,
                    max_tokens=max_tokens,
                    temperature=temperature,
                )
            except Exception as e:
                last_exception = e
                if attempt < self._max_retries - 1:
                    delay = self._base_delay * (self._backoff ** attempt)
                    time.sleep(delay)
        raise last_exception  # type: ignore[misc]

    # --- Tool calling passthrough (retries the round-trip like generate) ---

    def supports_tools(self) -> bool:
        return self._inner.supports_tools()

    def generate_with_tools(
        self,
        messages: list[dict[str, Any]],
        tools: list[ToolSpec],
        system_prompt: str | None = None,
        max_tokens: int = 2048,
        temperature: float = 0.7,
        tool_choice: str = "auto",
    ) -> ToolCallResult:
        last_exception: Exception | None = None
        for attempt in range(self._max_retries):
            try:
                return self._inner.generate_with_tools(
                    messages=messages,
                    tools=tools,
                    system_prompt=system_prompt,
                    max_tokens=max_tokens,
                    temperature=temperature,
                    tool_choice=tool_choice,
                )
            except Exception as e:
                last_exception = e
                if attempt < self._max_retries - 1:
                    delay = self._base_delay * (self._backoff ** attempt)
                    time.sleep(delay)
        raise last_exception  # type: ignore[misc]

    def format_tool_results(self, results: list[ToolResult]) -> list[dict[str, Any]]:
        return self._inner.format_tool_results(results)
