"""Pipeline state — tracks ASTRA session state across optimization cycles."""

import json
import os
import uuid
from dataclasses import dataclass, field, asdict
from datetime import datetime, timezone
from typing import Any

from astra.planner.spec import StrategySpec
from astra.builder.generator import BuildResult
from astra.pipeline.runner import PipelineResult

VALID_TRANSITIONS: dict[str, list[str]] = {
    "PLANNING": ["BUILDING", "ABANDONED"],
    "BUILDING": ["RUNNING", "ABANDONED"],
    "RUNNING": ["OPTIMIZING", "PAPER_TRADING", "FAILED", "ABANDONED"],
    "OPTIMIZING": ["RUNNING", "PAPER_TRADING", "GRADUATED", "FAILED", "ABANDONED"],
    "PAPER_TRADING": ["OPTIMIZING", "GRADUATED", "FAILED", "ABANDONED"],
    "GRADUATED": [],
    "FAILED": ["ABANDONED"],
    "ABANDONED": [],
}

DISCLAIMER = (
    "ASTRA research results are not profitability guarantees. "
    "Past performance does not predict future results."
)


class InvalidStatusTransition(Exception):
    ...


@dataclass
class PipelineState:
    session_id: str = ""
    spec: StrategySpec | None = None
    build_result: BuildResult | None = None
    pipeline_results: list[PipelineResult] = field(default_factory=list)
    current_cycle: int = 0
    status: str = "PLANNING"
    paper_deployment_id: str | None = None
    graduation_result: dict[str, Any] | None = None
    created_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
    updated_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
    disclaimer: str = DISCLAIMER

    def __post_init__(self) -> None:
        if not self.session_id:
            self.session_id = str(uuid.uuid4())

    def transition_to(self, new_status: str) -> None:
        allowed = VALID_TRANSITIONS.get(self.status, [])
        if new_status not in allowed:
            raise InvalidStatusTransition(
                f"Cannot transition from {self.status} to {new_status}. "
                f"Allowed transitions: {allowed}"
            )
        self.status = new_status
        self.updated_at = datetime.now(timezone.utc)

    def save(self, path: str) -> None:
        data = asdict(self)
        data["created_at"] = self.created_at.isoformat()
        data["updated_at"] = self.updated_at.isoformat()
        if self.spec is not None:
            data["spec"] = json.loads(self.spec.to_json())
        if self.build_result is not None:
            data["build_result"] = asdict(self.build_result)
        data["pipeline_results"] = [json.loads(r.to_json()) for r in self.pipeline_results]
        os.makedirs(os.path.dirname(path) or ".", exist_ok=True)
        with open(path, "w") as f:
            json.dump(data, f, indent=2, default=str)

    @classmethod
    def load(cls, path: str) -> "PipelineState":
        with open(path) as f:
            data = json.load(f)

        if "created_at" in data and isinstance(data["created_at"], str):
            data["created_at"] = datetime.fromisoformat(data["created_at"])
        if "updated_at" in data and isinstance(data["updated_at"], str):
            data["updated_at"] = datetime.fromisoformat(data["updated_at"])

        spec_data = data.pop("spec", None)
        build_data = data.pop("build_result", None)
        results_data = data.pop("pipeline_results", [])

        state = cls(**data)

        if spec_data:
            state.spec = StrategySpec.from_json(json.dumps(spec_data))
        if build_data:
            state.build_result = BuildResult(**build_data)
        for r in results_data:
            state.pipeline_results.append(PipelineResult.from_json(json.dumps(r)))

        return state

    def latest_result(self) -> PipelineResult | None:
        if not self.pipeline_results:
            return None
        return self.pipeline_results[-1]

    def has_graduated(self) -> bool:
        return self.graduation_result is not None

    def cycle_history_summary(self) -> list[dict[str, Any]]:
        summaries: list[dict[str, Any]] = []
        for r in self.pipeline_results:
            entry: dict[str, Any] = {
                "cycle": r.cycle_number,
                "status": r.status,
                "sharpe": None,
                "dsr": None,
                "drawdown": None,
                "deployed": r.paper_deployment_id is not None,
            }
            if r.cpcv_summary:
                entry["sharpe"] = r.cpcv_summary.get("mean_sharpe")
                entry["dsr"] = r.cpcv_summary.get("dsr")
            summaries.append(entry)
        return summaries
