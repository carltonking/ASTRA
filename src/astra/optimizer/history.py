"""Optimization history — tracks parameter changes across cycles to detect patterns."""

import json
import os
import uuid
from dataclasses import dataclass, field
from typing import Any

import pandas as pd

from astra.optimizer.proposer import ParameterProposal
from astra.pipeline.runner import PipelineResult


@dataclass
class OptimizationHistory:
    session_id: str = ""
    records: list[dict[str, Any]] = field(default_factory=list)

    def __post_init__(self) -> None:
        if not self.session_id:
            self.session_id = str(uuid.uuid4())

    def record(
        self,
        proposal: "ParameterProposal",
        result: "PipelineResult",
    ) -> None:
        entry = {
            "cycle": proposal.cycle_number,
            "action": proposal.action,
            "parameters": dict(proposal.parameter_changes),
            "sharpe": None,
            "dsr": None,
            "status": result.status,
        }
        if result.cpcv_summary:
            entry["sharpe"] = result.cpcv_summary.get("mean_sharpe")
            entry["dsr"] = result.cpcv_summary.get("dsr")
        self.records.append(entry)

    def has_improvement(self) -> bool:
        if len(self.records) < 2:
            return True
        latest_sharpe = self.records[-1].get("sharpe") or 0
        best_previous = max(
            (r.get("sharpe") or 0 for r in self.records[:-1]),
            default=0,
        )
        return latest_sharpe > best_previous

    def is_cycling(self) -> bool:
        if len(self.records) < 2:
            return False
        seen: set[str] = set()
        for r in self.records:
            params = r.get("parameters", {})
            key = json.dumps(params, sort_keys=True)
            if key in seen:
                return True
            seen.add(key)
        return False

    def best_cycle(self) -> dict[str, Any] | None:
        if not self.records:
            return None
        best = max(self.records, key=lambda r: r.get("dsr") or 0)
        if best.get("dsr") is None:
            return self.records[-1] if self.records else None
        return best

    def to_dataframe(self) -> pd.DataFrame:
        return pd.DataFrame(self.records)

    def save(self, path: str) -> None:
        data = {
            "session_id": self.session_id,
            "records": self.records,
        }
        os.makedirs(os.path.dirname(path) or ".", exist_ok=True)
        with open(path, "w") as f:
            json.dump(data, f, indent=2)

    @classmethod
    def load(cls, path: str) -> "OptimizationHistory":
        with open(path) as f:
            data = json.load(f)
        return cls(
            session_id=data.get("session_id", ""),
            records=data.get("records", []),
        )
