"""Anthropic Claude LLM provider."""

import json
from typing import Any

from anthropic import Anthropic

from astra.llm.provider import LLMProvider
from astra.llm.errors import LLMConfigurationError
from astra.llm.tools import ToolSpec, ToolCall, ToolResult, ToolCallResult


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
        for block in response.content:
            if getattr(block, "type", None) == "text":
                return block.text
        return ""

    # --- Tool calling ---

    def supports_tools(self) -> bool:
        return True

    def generate_with_tools(
        self,
        messages: list[dict[str, Any]],
        tools: list[ToolSpec],
        system_prompt: str | None = None,
        max_tokens: int = 2048,
        temperature: float = 0.7,
        tool_choice: str = "auto",
    ) -> ToolCallResult:
        kwargs: dict[str, Any] = dict(
            model=self._model,
            max_tokens=max_tokens,
            messages=messages,
            tools=[
                {"name": t.name, "description": t.description, "input_schema": t.input_schema}
                for t in tools
            ],
            tool_choice={"type": tool_choice} if tool_choice in ("auto", "any") else {"type": "auto"},
        )
        if system_prompt is not None:
            kwargs["system"] = system_prompt

        response = self._client.messages.create(**kwargs)

        text_parts: list[str] = []
        tool_calls: list[ToolCall] = []
        for block in response.content:
            btype = getattr(block, "type", None)
            if btype == "text":
                text_parts.append(block.text)
            elif btype == "tool_use":
                tool_calls.append(
                    ToolCall(
                        id=block.id,
                        name=block.name,
                        arguments=dict(block.input or {}),
                        raw_arguments=json.dumps(block.input or {}),
                    )
                )

        # Store native content blocks verbatim for valid re-threading.
        raw_assistant = {"role": "assistant", "content": response.content}
        return ToolCallResult(
            text="".join(text_parts) if text_parts else None,
            tool_calls=tool_calls,
            raw_assistant_message=raw_assistant,
            stop_reason=getattr(response, "stop_reason", "") or "",
        )

    def format_tool_results(self, results: list[ToolResult]) -> list[dict[str, Any]]:
        # Anthropic bundles all tool results into ONE user message.
        return [
            {
                "role": "user",
                "content": [
                    {
                        "type": "tool_result",
                        "tool_use_id": r.call_id,
                        "content": r.content,
                        "is_error": r.is_error,
                    }
                    for r in results
                ],
            }
        ]
