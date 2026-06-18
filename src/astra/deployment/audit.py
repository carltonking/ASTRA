"""Append-only paper-trading audit log."""

import json
import os
from dataclasses import asdict, is_dataclass
from datetime import datetime, timezone
from typing import Any, cast


class TradeAuditLog:
    """JSONL audit log for deployment decisions and broker actions."""

    def __init__(self, path: str = ""):
        self._path = path

    @property
    def path(self) -> str:
        return self._path

    def bind(self, path: str) -> None:
        self._path = path

    def record(
        self,
        event_type: str,
        deployment_id: str,
        payload: dict[str, Any] | None = None,
    ) -> None:
        if not self._path:
            return
        entry = {
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "event_type": event_type,
            "deployment_id": deployment_id,
            "payload": self._jsonable(payload or {}),
        }
        os.makedirs(os.path.dirname(self._path), exist_ok=True)
        with open(self._path, "a") as f:
            f.write(json.dumps(entry, sort_keys=True, default=str) + "\n")

    def _jsonable(self, value: Any) -> Any:
        if is_dataclass(value):
            return self._jsonable(asdict(cast(Any, value)))
        if isinstance(value, dict):
            return {str(k): self._jsonable(v) for k, v in value.items()}
        if isinstance(value, (list, tuple)):
            return [self._jsonable(v) for v in value]
        if isinstance(value, datetime):
            return value.isoformat()
        return value
