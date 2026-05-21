"""Simple event bus for real-time pipeline updates via websocket."""

from typing import Any, Callable


class PipelineEventBus:
    def __init__(self) -> None:
        self._handlers: list[Callable] = []
        self._history: list[dict[str, Any]] = []

    def subscribe(self, handler: Callable[[str, dict[str, Any]], None]) -> None:
        self._handlers.append(handler)

    def emit(self, event: str, data: dict[str, Any] | None = None) -> None:
        record: dict[str, Any] = {"event": event, "data": data or {}}
        self._history.append(record)
        for handler in self._handlers:
            handler(event, data or {})

    def get_history(self) -> list[dict[str, Any]]:
        return list(self._history)

    def clear_history(self) -> None:
        self._history.clear()
