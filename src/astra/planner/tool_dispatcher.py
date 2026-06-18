"""Per-request tool context + dispatcher for the unified finance assistant.

The dispatcher binds request-scoped context (session, backtest engine, WS emitter)
into the stateless tool functions, streams tool-activity events to the UI, and never
lets a tool exception escape — failures come back as error results the model can read.

No backend imports here: ``emit`` and ``db_factory`` are injected by the endpoint, so
the planner package stays decoupled from the FastAPI layer.
"""

import json
from dataclasses import dataclass, field
from typing import Any, Callable

from astra.backtest.engine import BacktestEngine
from astra.db import Database
from astra.planner.spec import StrategySpec
from astra.planner.tools import TOOL_REGISTRY, TOOL_SCHEMAS

# Human-readable activity labels streamed to the UI per tool.
_ACTIVITY_LABELS = {
    "list_algorithms": "listing algorithms…",
    "get_market_data": "fetching market data…",
    "quick_backtest": "running quick backtest…",
    "search_memory": "searching research memory…",
    "build_strategy": "preparing build…",
}


@dataclass
class ToolContext:
    """Request-scoped state handed to every tool call."""

    session_id: str
    engine: BacktestEngine
    emit: Callable[[str, dict[str, Any]], None] = lambda ev, data: None
    db_factory: Callable[[], Any] = Database
    build_intent: StrategySpec | None = None
    cache: dict[str, Any] = field(default_factory=dict)


class ToolDispatcher:
    """Exposes tool schemas and executes tool calls against a ToolContext."""

    def __init__(self, ctx: ToolContext):
        self.ctx = ctx

    def schemas(self) -> list[dict[str, Any]]:
        return TOOL_SCHEMAS

    def dispatch(self, name: str, arguments: dict[str, Any]) -> str:
        """Execute a tool; always returns a JSON string (errors included)."""
        fn = TOOL_REGISTRY.get(name)
        if fn is None:
            return json.dumps({"error": f"unknown tool '{name}'"})

        label = _ACTIVITY_LABELS.get(name, "working…")
        self._safe_emit("chat.tool_start", {"tool": name, "label": label})
        try:
            result = fn(self.ctx, **arguments)
        except TypeError as e:
            result = {"error": f"invalid arguments for {name}: {e}"}
        except Exception as e:
            result = {"error": f"{type(e).__name__}: {e}"}
        self._safe_emit("chat.tool_end", {"tool": name, "ok": "error" not in result})

        try:
            return json.dumps(result, default=str)
        except (TypeError, ValueError):
            return json.dumps({"error": "tool result not serializable"})

    def _safe_emit(self, event: str, data: dict[str, Any]) -> None:
        try:
            self.ctx.emit(event, data)
        except Exception:
            pass  # UI streaming is best-effort; never break a tool on emit failure
