"""Anthropic Claude LLM provider."""

from typing import Any

from anthropic import Anthropic

from astra.llm.provider import LLMProvider
from astra.llm.errors import LLMConfigurationError


_DEFAULT_MODEL = "claude-sonnet-4-20250514"


class AnthropicProvider(LLMProvider):
    """LLM provider backed by Anthropic's Claude API."""

    def __init__(
        self,
        api_key: str,
        model: str = _DEFAULT_MODEL,
    ):
        if not api_key:
            raise LLMConfigurationError(
                "Anthropic API key is required. Set ANTHROPIC_API_KEY environment variable."
            )
        self._client = Anthropic(api_key=api_key)
        self._model = model

    def generate(
        self,
        messages: list[dict[str, Any]],
        system_prompt: str | None = None,
        max_tokens: int = 2048,
        temperature: float = 0.7,
    ) -> str:
        kwargs: dict[str, Any] = dict(
            model=self._model,
            max_tokens=max_tokens,
            messages=messages,
        )
        if system_prompt is not None:
            kwargs["system"] = system_prompt

        response = self._client.messages.create(**kwargs)
        return response.content[0].text
