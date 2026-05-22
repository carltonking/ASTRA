"""In-memory session store with disk persistence."""

import json
import os
from typing import Any

from astra.pipeline.state import PipelineState
from astra.graduation.tracker import GraduationTracker
from astra.optimizer.history import OptimizationHistory


class SessionStore:
    def __init__(self) -> None:
        self._sessions: dict[str, dict[str, Any]] = {}

    def create(self, session_id: str) -> None:
        if session_id in self._sessions:
            raise KeyError(f"Session {session_id} already exists")
        self._sessions[session_id] = {
            "session_id": session_id,
            "state": PipelineState(session_id=session_id),
            "conversation": None,
            "deployment": None,
            "graduation_tracker": GraduationTracker(session_id=session_id),
            "optimization_history": OptimizationHistory(session_id=session_id),
            "export_package": None,
        }

    def get(self, session_id: str) -> dict[str, Any] | None:
        return self._sessions.get(session_id)

    def update(self, session_id: str, key: str, value: Any) -> None:
        if session_id not in self._sessions:
            raise KeyError(f"Session {session_id} not found")
        self._sessions[session_id][key] = value

    def list_sessions(self) -> list[dict[str, Any]]:
        results = []
        for sid, data in self._sessions.items():
            state = data.get("state")
            if state is None:
                continue
            results.append({
                "session_id": sid,
                "status": state.status,
                "created_at": state.created_at.isoformat() if hasattr(state, "created_at") else "",
                "strategy_type": state.spec.strategy_type if state.spec else None,
                "symbols": state.spec.symbols if state.spec else None,
            })
        return results

    def save_all(self, store_dir: str) -> None:
        os.makedirs(store_dir, exist_ok=True)
        for sid, data in self._sessions.items():
            path = os.path.join(store_dir, f"session_{sid}.json")
            serializable = _make_serializable(data)
            with open(path, "w") as f:
                json.dump(serializable, f, indent=2, default=str)

    def load_all(self, store_dir: str) -> None:
        if not os.path.isdir(store_dir):
            return
        for fname in os.listdir(store_dir):
            if not fname.startswith("session_") or not fname.endswith(".json"):
                continue
            path = os.path.join(store_dir, fname)
            with open(path) as f:
                data = json.load(f)
            sid = data.get("session_id", "")
            if sid:
                self._sessions[sid] = data


def _make_serializable(data: dict[str, Any]) -> dict[str, Any]:
    result = {}
    for key, val in data.items():
        if hasattr(val, "to_json"):
            result[key] = json.loads(val.to_json())
        elif hasattr(val, "__dict__") and not isinstance(val, type):
            result[key] = _object_to_dict(val)
        else:
            result[key] = val
    return result


def _object_to_dict(obj: Any) -> dict[str, Any]:
    if hasattr(obj, "__dataclass_fields__"):
        from dataclasses import asdict
        return asdict(obj)
    return dict(obj.__dict__)
