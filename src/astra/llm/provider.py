"""Abstract LLM provider interface."""

from abc import ABC, abstractmethod
from typing import Any

from astra.llm.tools import ToolSpec, ToolResult, ToolCallResult


class LLMProvider(ABC):
    """Abstract interface for LLM providers (Anthropic, OpenAI, etc.)."""

    @abstractmethod
    def generate(
        self,
        messages: list[dict[str, Any]],
        system_prompt: str | None = None,
        max_tokens: int = 2048,
        temperature: float = 0.7,
    ) -> str:
        """Send a prompt to the LLM and return the text response.

        Args:
            messages: List of message dicts with 'role' and 'content' keys.
            system_prompt: Optional system-level instruction.
            max_tokens: Maximum tokens in the response.
            temperature: Sampling temperature (0.0 = deterministic).

        Returns:
            The LLM's response text.
        """

    # --- Tool / function calling (optional capability) ---
    # Default implementations make tool support opt-in: providers that don't
    # override these keep working as plain text generators, and existing callers
    # of generate() are unaffected.

    def supports_tools(self) -> bool:
        """Whether this provider implements the tool-calling round-trip."""
        return False

    def generate_with_tools(
        self,
        messages: list[dict[str, Any]],
        tools: list[ToolSpec],
        system_prompt: str | None = None,
        max_tokens: int = 2048,
        temperature: float = 0.7,
        tool_choice: str = "auto",
    ) -> ToolCallResult:
        """One round-trip that may return final text OR tool calls to execute."""
        raise NotImplementedError(
            f"{type(self).__name__} does not support tool calling."
        )

    def format_tool_results(self, results: list[ToolResult]) -> list[dict[str, Any]]:
        """Convert executed tool results into provider-native history messages."""
        raise NotImplementedError(
            f"{type(self).__name__} does not support tool calling."
        )
