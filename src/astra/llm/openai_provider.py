"""OpenAI LLM provider."""

from typing import Any

from openai import OpenAI

from astra.llm.provider import LLMProvider
from astra.llm.errors import LLMConfigurationError


_DEFAULT_MODEL = "gpt-4o"


class OpenAIProvider(LLMProvider):
    """LLM provider backed by OpenAI's API."""

    def __init__(
        self,
        api_key: str,
        model: str = _DEFAULT_MODEL,
    ):
        if not api_key:
            raise LLMConfigurationError(
                "OpenAI API key is required. Set OPENAI_API_KEY environment variable."
            )
        self._client = OpenAI(api_key=api_key)
        self._model = model

    def generate(
        self,
        messages: list[dict[str, Any]],
        system_prompt: str | None = None,
        max_tokens: int = 2048,
        temperature: float = 0.7,
    ) -> str:
        openai_messages: list[dict[str, Any]] = list(messages)
        if system_prompt is not None:
            openai_messages.insert(0, {"role": "system", "content": system_prompt})

        response = self._client.chat.completions.create(
            model=self._model,
            messages=openai_messages,
            max_tokens=max_tokens,
            temperature=temperature,
        )
        return response.choices[0].message.content or ""
