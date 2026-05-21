"""Graduation tracker — records gate check history and manages certificate issuance."""

import json
import os
from dataclasses import asdict
from datetime import datetime, timezone
from typing import Any

from astra.alpaca.monitor import PerformanceSnapshot
from astra.pipeline.runner import PipelineResult
from astra.graduation.gates import GateCheckResult, GraduationError
from astra.graduation.certificate import GraduationCertificate


class GraduationTracker:
    def __init__(self, session_id: str):
        self.session_id = session_id
        self.history: list[dict[str, Any]] = []
        self._certificate: GraduationCertificate | None = None

    def record_check(self, cycle_number: int, gate_result: GateCheckResult) -> None:
        if any(h["cycle_number"] == cycle_number for h in self.history):
            raise ValueError(f"Gate check for cycle {cycle_number} already recorded")

        self.history.append({
            "cycle_number": cycle_number,
            "overall_status": gate_result.overall_status,
            "gates_passed": gate_result.gates_passed,
            "gates_total": gate_result.gates_total,
            "gate_details": {
                name: {
                    "gate_name": g.gate_name,
                    "status": g.status,
                    "actual_value": g.actual_value,
                    "threshold_value": g.threshold_value,
                    "gap": g.gap,
                }
                for name, g in gate_result.gates.items()
            },
            "timestamp": datetime.now(timezone.utc).isoformat(),
        })

    def is_graduated(self) -> bool:
        return self._certificate is not None

    def get_certificate(self) -> GraduationCertificate | None:
        return self._certificate

    def issue_certificate(
        self,
        snapshot: PerformanceSnapshot,
        pipeline_result: PipelineResult,
        optimization_cycles: int,
        gate_result: GateCheckResult | None = None,
    ) -> GraduationCertificate:
        if self._certificate is not None:
            raise GraduationError("Certificate has already been issued for this session")

        if gate_result is None:
            if not self.history:
                raise GraduationError("No gate checks recorded; cannot issue certificate")
            last = self.history[-1]
            if last["overall_status"] != "GRADUATED":
                raise GraduationError(
                    f"Cannot issue certificate: last gate check was {last['overall_status']}"
                )

            from astra.graduation.gates import GateResult as GR
            gates = {}
            for name, details in last["gate_details"].items():
                gr = GR(
                    gate_name=details["gate_name"],
                    status=details["status"],
                    actual_value=details["actual_value"],
                    threshold_value=details["threshold_value"],
                    gap=details["gap"],
                )
                gates[name] = gr

            gate_result = GateCheckResult(
                overall_status=last["overall_status"],
                gates=gates,
                gates_passed=last["gates_passed"],
                gates_total=last["gates_total"],
            )

        cert = GraduationCertificate.from_gate_check(
            session_id=self.session_id,
            gate_result=gate_result,
            snapshot=snapshot,
            pipeline_result=pipeline_result,
            optimization_cycles=optimization_cycles,
        )

        self._certificate = cert
        return cert

    def progress_over_time(self) -> list[dict[str, Any]]:
        return [
            {
                "cycle": h["cycle_number"],
                "gates_passed": h["gates_passed"],
                "overall_status": h["overall_status"],
            }
            for h in self.history
        ]

    def gate_trend(self, gate_name: str) -> list[dict[str, Any]]:
        results = []
        for h in self.history:
            if gate_name in h.get("gate_details", {}):
                detail = h["gate_details"][gate_name]
                results.append({
                    "cycle": h["cycle_number"],
                    "actual_value": detail["actual_value"],
                    "threshold": detail["threshold_value"],
                    "passed": detail["status"] == "PASSED",
                })
        return results

    def save(self, store_dir: str) -> None:
        os.makedirs(store_dir, exist_ok=True)
        data: dict[str, Any] = {
            "session_id": self.session_id,
            "history": self.history,
            "certificate": None,
        }
        if self._certificate is not None:
            data["certificate"] = json.loads(self._certificate.to_json())
        path = os.path.join(store_dir, f"graduation_{self.session_id}.json")
        with open(path, "w") as f:
            json.dump(data, f, indent=2, default=str)

    @classmethod
    def load(cls, session_id: str, store_dir: str) -> "GraduationTracker":
        path = os.path.join(store_dir, f"graduation_{session_id}.json")
        if not os.path.exists(path):
            raise FileNotFoundError(f"No saved graduation state for session {session_id}")

        with open(path) as f:
            data = json.load(f)

        tracker = cls(session_id=data.get("session_id", session_id))
        tracker.history = data.get("history", [])

        cert_data = data.get("certificate")
        if cert_data is not None:
            tracker._certificate = GraduationCertificate.from_json(json.dumps(cert_data))

        return tracker
