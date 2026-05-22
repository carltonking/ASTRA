"""Graduation certificate — immutable record that a strategy has passed all gates."""

import json
import uuid
from dataclasses import dataclass, field, asdict
from datetime import datetime, timezone
from typing import Any

from astra.alpaca.monitor import PerformanceSnapshot
from astra.pipeline.runner import PipelineResult
from astra.graduation.gates import GateCheckResult, GateResult, GraduationError


_LIMITATIONS = (
    "Past performance does not guarantee future results",
    "This strategy was validated only in specific market conditions",
    "Paper trading does not account for slippage, fees, or liquidity constraints",
    "Live trading may produce substantially different results",
    "This certificate does not constitute financial advice",
)


@dataclass
class GraduationCertificate:
    certificate_id: str = ""
    session_id: str = ""
    strategy_type: str = ""
    spec_id: str = ""
    symbols: list[str] = field(default_factory=list)
    issued_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
    gate_results: dict[str, GateResult] = field(default_factory=dict)
    performance_snapshot: PerformanceSnapshot | None = None
    pipeline_result_summary: dict[str, Any] = field(default_factory=dict)
    optimization_cycles: int = 0
    limitations: list[str] = field(default_factory=list)

    def __post_init__(self) -> None:
        if not self.certificate_id:
            self.certificate_id = str(uuid.uuid4())
        if not self.limitations:
            self.limitations = list(_LIMITATIONS)

    @classmethod
    def from_gate_check(
        cls,
        session_id: str,
        gate_result: GateCheckResult,
        snapshot: PerformanceSnapshot,
        pipeline_result: PipelineResult,
        optimization_cycles: int,
    ) -> "GraduationCertificate":
        if gate_result.overall_status != "GRADUATED":
            raise GraduationError(
                f"Cannot issue certificate: overall status is '{gate_result.overall_status}', "
                f"expected 'GRADUATED' ({gate_result.gates_passed}/6 gates passed)"
            )

        ppr = pipeline_result
        pipeline_summary = {
            "pipeline_id": ppr.pipeline_id,
            "status": ppr.status,
            "cycle_number": ppr.cycle_number,
            "leakage_verdict": ppr.leakage_verdict,
            "review_board_status": ppr.review_board_status,
        }
        if ppr.cpcv_summary:
            pipeline_summary["cpcv_summary"] = dict(ppr.cpcv_summary)
        if ppr.backtest_metrics:
            pipeline_summary["backtest_metrics"] = dict(ppr.backtest_metrics)

        return cls(
            session_id=session_id,
            strategy_type="",
            spec_id="",
            symbols=[],
            gate_results=dict(gate_result.gates),
            performance_snapshot=snapshot,
            pipeline_result_summary=pipeline_summary,
            optimization_cycles=optimization_cycles,
        )

    def to_json(self) -> str:
        data = asdict(self)
        data["issued_at"] = self.issued_at.isoformat()
        data["gate_results"] = {
            k: asdict(v) for k, v in self.gate_results.items()
        }
        if self.performance_snapshot is not None:
            data["performance_snapshot"] = asdict(self.performance_snapshot)
        return json.dumps(data, indent=2, default=str)

    @classmethod
    def from_json(cls, json_str: str) -> "GraduationCertificate":
        data = json.loads(json_str)
        if "issued_at" in data and isinstance(data["issued_at"], str):
            data["issued_at"] = datetime.fromisoformat(data["issued_at"])
        if "gate_results" in data and isinstance(data["gate_results"], dict):
            data["gate_results"] = {
                k: GateResult(**v) for k, v in data["gate_results"].items()
            }
        if "performance_snapshot" in data and data["performance_snapshot"] is not None:
            ps = data.pop("performance_snapshot")
            from astra.alpaca.monitor import PerformanceSnapshot
            data["performance_snapshot"] = PerformanceSnapshot(**ps)
        return cls(**data)

    def to_text_block(self) -> str:
        lines = [
            "# ============================================================",
            "# GRADUATION CERTIFICATE",
            f"# Certificate ID: {self.certificate_id}",
            f"# Session ID: {self.session_id}",
            f"# Spec ID: {self.spec_id}",
            f"# Issued: {self.issued_at.isoformat()}",
            f"# Strategy Type: {self.strategy_type}",
            f"# Optimization Cycles: {self.optimization_cycles}",
        ]
        for gr in self.gate_results.values():
            lines.append(
                f"#   Gate [{gr.status}] {gr.gate_name}: actual={gr.actual_value}, "
                f"threshold={gr.threshold_value}, gap={gr.gap}"
            )
        lines.append("# ------------------------------------------------------------")
        lines.append("# Limitations:")
        for i, lim in enumerate(self.limitations, 1):
            lines.append(f"#   {i}. {lim}")
        lines.append("# ------------------------------------------------------------")
        lines.append("# ASTRA research results are not profitability guarantees.")
        lines.append("# Past performance does not predict future results.")
        lines.append("# ============================================================")
        return "\n".join(lines)
