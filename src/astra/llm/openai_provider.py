"""OpenAI LLM provider."""

import json
from typing import Any

from openai import OpenAI

from astra.llm.provider import LLMProvider
from astra.llm.errors import LLMConfigurationError
from astra.llm.tools import ToolSpec, ToolCall, ToolResult, ToolCallResult


_DEFAULT_MODEL = "gpt-4o"


class OpenAIProvider(LLMProvider):
    """LLM provider backed by OpenAI's API."""

    def __init__(
        self,
        api_key: str,
        model: str = _DEFAULT_MODEL,
        base_url: str | None = None,
    ):
        if not api_key:
            raise LLMConfigurationError(
                "OpenAI API key is required. Set OPENAI_API_KEY environment variable."
            )
        # base_url lets this provider target any OpenAI-compatible endpoint
        # (e.g. Google Gemini, Groq, OpenRouter), not just api.openai.com.
        client_kwargs: dict[str, Any] = {"api_key": api_key}
        if base_url:
            client_kwargs["base_url"] = base_url
        self._client = OpenAI(**client_kwargs)
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

    # --- Tool calling (works for OpenAI + Gemini/Groq/OpenRouter via base_url) ---

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
        openai_messages: list[dict[str, Any]] = list(messages)
        if system_prompt is not None:
            openai_messages.insert(0, {"role": "system", "content": system_prompt})

        # NOTE: never set response_format alongside tools — Gemini's OpenAI-compat
        # endpoint rejects that combination.
        response = self._client.chat.completions.create(
            model=self._model,
            messages=openai_messages,
            tools=[
                {
                    "type": "function",
                    "function": {
                        "name": t.name,
                        "description": t.description,
                        "parameters": t.input_schema,
                    },
                }
                for t in tools
            ],
            tool_choice=tool_choice,
            max_tokens=max_tokens,
            temperature=temperature,
        )

        msg = response.choices[0].message
        tool_calls: list[ToolCall] = []
        native_tool_calls: list[dict[str, Any]] = []
        for tc in (msg.tool_calls or []):
            raw_args = tc.function.arguments or "{}"
            parsed: dict[str, Any] = {}
            parse_error = ""
            try:
                parsed = json.loads(raw_args) if raw_args.strip() else {}
            except json.JSONDecodeError as e:
                parse_error = f"invalid JSON arguments: {e}"
            tool_calls.append(
                ToolCall(
                    id=tc.id,
                    name=tc.function.name,
                    arguments=parsed,
                    raw_arguments=raw_args,
                    parse_error=parse_error,
                )
            )
            native_tool_calls.append(
                {
                    "id": tc.id,
                    "type": "function",
                    "function": {"name": tc.function.name, "arguments": raw_args},
                }
            )

        raw_assistant: dict[str, Any] = {"role": "assistant", "content": msg.content or ""}
        if native_tool_calls:
            raw_assistant["tool_calls"] = native_tool_calls

        return ToolCallResult(
            text=msg.content if not tool_calls else None,
            tool_calls=tool_calls,
            raw_assistant_message=raw_assistant,
            stop_reason=response.choices[0].finish_reason or "",
        )

    def format_tool_results(self, results: list[ToolResult]) -> list[dict[str, Any]]:
        # OpenAI/Gemini require ONE message per tool call id.
        return [
            {"role": "tool", "tool_call_id": r.call_id, "content": r.content}
            for r in results
        ]
