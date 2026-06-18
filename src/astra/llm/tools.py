"""Provider-agnostic tool/function-calling types.

These plain dataclasses are the lingua franca between the assistant (which decides
WHICH tools exist and runs the loop) and the providers (which translate to/from each
SDK's native tool-use shape). No SDK imports here on purpose.
"""

from dataclasses import dataclass, field
from typing import Any


@dataclass(frozen=True)
class ToolSpec:
    """Declaration of a tool the model may call. ``input_schema`` is JSON Schema."""

    name: str
    description: str
    input_schema: dict[str, Any]


@dataclass(frozen=True)
class ToolCall:
    """A single tool invocation requested by the model."""

    id: str
    name: str
    arguments: dict[str, Any]
    raw_arguments: str = ""
    parse_error: str = ""  # set when the model emitted unparseable JSON args


@dataclass(frozen=True)
class ToolResult:
    """The outcome of executing one ToolCall, fed back to the model."""

    call_id: str
    content: str
    is_error: bool = False


@dataclass
class ToolCallResult:
    """One provider round-trip: EITHER final text OR pending tool calls.

    ``raw_assistant_message`` is the provider's native assistant turn, stored verbatim
    so the loop can re-append it to history with valid threading for that SDK.
    """

    text: str | None = None
    tool_calls: list[ToolCall] = field(default_factory=list)
    raw_assistant_message: dict[str, Any] | None = None
    stop_reason: str = ""

    @property
    def wants_tools(self) -> bool:
        return len(self.tool_calls) > 0
