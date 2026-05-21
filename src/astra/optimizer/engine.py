"""Optimization engine — orchestrates the full optimization loop across cycles."""

import json
import uuid
from dataclasses import dataclass, field, asdict
from datetime import datetime, timezone
from typing import Any

from astra.planner.spec import StrategySpec
from astra.builder.generator import BuildResult
from astra.pipeline.runner import PipelineRunner, PipelineResult
from astra.pipeline.state import PipelineState
from astra.pipeline.events import PipelineEventBus
from astra.alpaca.monitor import PerformanceMonitor, PerformanceSnapshot
from astra.optimizer.diagnosis import DiagnosisEngine, Diagnosis
from astra.optimizer.proposer import ParameterProposer, ParameterProposal
from astra.optimizer.history import OptimizationHistory
from astra.alpaca.deployer import Deployment

_DISCLAIMER = (
    "ASTRA research results are not profitability guarantees. "
    "Past performance does not predict future results."
)


@dataclass
class OptimizationResult:
    session_id: str = ""
    status: str = ""
    total_cycles: int = 0
    final_snapshot: PerformanceSnapshot | None = None
    final_proposal: ParameterProposal | None = None
    cycle_summaries: list[dict[str, Any]] = field(default_factory=list)
    plain_english_outcome: str = ""
    disclaimer: str = _DISCLAIMER

    def to_json(self) -> str:
        data = asdict(self)
        if self.final_snapshot is not None:
            data["final_snapshot"] = asdict(self.final_snapshot)
        if self.final_proposal is not None:
            data["final_proposal"] = json.loads(self.final_proposal.to_json())
        return json.dumps(data, indent=2, default=str)


class OptimizationEngine:
    def __init__(
        self,
        anthropic_api_key: str,
        pipeline_runner: PipelineRunner,
        event_bus: PipelineEventBus,
        max_cycles: int = 10,
    ):
        self._anthropic_api_key = anthropic_api_key
        self._pipeline_runner = pipeline_runner
        self._event_bus = event_bus
        self._max_cycles = max_cycles
        self._diagnosis_engine = DiagnosisEngine()
        self._parameter_proposer = ParameterProposer(anthropic_api_key)

    def run_optimization_loop(
        self,
        state: PipelineState,
        monitor: PerformanceMonitor,
    ) -> OptimizationResult:
        session_id = state.session_id
        history = OptimizationHistory(session_id=session_id)
        cycle_summaries: list[dict[str, Any]] = []

        spec = state.spec
        build_result = state.build_result

        if spec is None or build_result is None:
            return OptimizationResult(
                session_id=session_id,
                status="ERROR",
                plain_english_outcome="Cannot start optimization: no strategy spec or build result available.",
            )

        cycle = 0
        final_snapshot: PerformanceSnapshot | None = None
        final_proposal: ParameterProposal | None = None

        deployment = self._resolve_deployment(state)

        while cycle < self._max_cycles:
            cycle += 1
            self._event_bus.emit("pipeline.optimization_started", {"cycle": cycle})

            snapshot = monitor.snapshot(deployment)
            final_snapshot = snapshot

            pipeline_results = list(state.pipeline_results)

            diagnosis = self._diagnosis_engine.diagnose(
                spec=spec,
                build_result=build_result,
                pipeline_results=pipeline_results,
                latest_snapshot=snapshot,
            )

            current_params = dict(build_result.initial_parameters)
            param_bounds = dict(build_result.parameter_bounds)

            proposal = self._parameter_proposer.propose(
                spec=spec,
                build_result=build_result,
                diagnosis=diagnosis,
                current_parameters=current_params,
                parameter_bounds=param_bounds,
                cycle_history=cycle_summaries,
            )
            final_proposal = proposal

            cycle_summary = {
                "cycle": cycle,
                "diagnosis": diagnosis.primary_diagnosis,
                "action": proposal.action,
                "parameter_changes": dict(proposal.parameter_changes),
                "confidence": proposal.confidence,
                "summary": proposal.summary,
            }
            cycle_summaries.append(cycle_summary)

            if proposal.action == "ABANDON":
                self._event_bus.emit("pipeline.failed", {"reason": proposal.summary})
                return OptimizationResult(
                    session_id=session_id,
                    status="ABANDONED",
                    total_cycles=cycle,
                    final_snapshot=snapshot,
                    final_proposal=proposal,
                    cycle_summaries=cycle_summaries,
                    plain_english_outcome=proposal.summary,
                )

            if proposal.action == "EXTEND_OBSERVATION":
                self._event_bus.emit(
                    "pipeline.optimization_observation",
                    {"cycle": cycle, "message": proposal.summary},
                )
                continue

            if proposal.action == "REBUILD_STRATEGY":
                return OptimizationResult(
                    session_id=session_id,
                    status="ABANDONED",
                    total_cycles=cycle,
                    final_snapshot=snapshot,
                    final_proposal=proposal,
                    cycle_summaries=cycle_summaries,
                    plain_english_outcome=proposal.summary,
                )

            pipeline_result = self._pipeline_runner.run_optimization_cycle(
                build_result=build_result,
                spec=spec,
                updated_parameters=proposal.parameter_changes,
            )
            state.pipeline_results.append(pipeline_result)

            if pipeline_result.status == "ERROR":
                self._event_bus.emit("pipeline.failed", {"reason": pipeline_result.error})
                return OptimizationResult(
                    session_id=session_id,
                    status="ERROR",
                    total_cycles=cycle,
                    final_snapshot=snapshot,
                    final_proposal=proposal,
                    cycle_summaries=cycle_summaries,
                    plain_english_outcome=f"Pipeline error at cycle {cycle}: {pipeline_result.error}",
                )

            if pipeline_result.status in ("FAILED_BACKTEST", "FAILED_LEAKAGE"):
                self._event_bus.emit("pipeline.failed", {"reason": pipeline_result.status})
                return OptimizationResult(
                    session_id=session_id,
                    status="ERROR",
                    total_cycles=cycle,
                    final_snapshot=snapshot,
                    final_proposal=proposal,
                    cycle_summaries=cycle_summaries,
                    plain_english_outcome=(
                        f"Optimization cycle {cycle} failed: pipeline returned "
                        f"{pipeline_result.status}. {pipeline_result.error or ''}"
                    ),
                )

            if history.is_cycling():
                return OptimizationResult(
                    session_id=session_id,
                    status="ABANDONED",
                    total_cycles=cycle,
                    final_snapshot=snapshot,
                    final_proposal=proposal,
                    cycle_summaries=cycle_summaries,
                    plain_english_outcome=(
                        "Optimizer has explored these parameters before without improvement. "
                        "Consider rebuilding the strategy with a different hypothesis."
                    ),
                )

        return OptimizationResult(
            session_id=session_id,
            status="EXHAUSTED",
            total_cycles=self._max_cycles,
            final_snapshot=final_snapshot,
            final_proposal=final_proposal,
            cycle_summaries=cycle_summaries,
            plain_english_outcome=(
                f"ASTRA completed {self._max_cycles} optimization cycles but the strategy did not meet "
                "graduation criteria within the allowed cycles. Consider:\n"
                "1. Reviewing the original market hypothesis — the edge may not exist\n"
                "2. Trying a different strategy type\n"
                "3. Adjusting risk parameters (target return, max drawdown) to more realistic levels"
            ),
        )

    @staticmethod
    def _resolve_deployment(state: PipelineState) -> Deployment:
        return Deployment(
            deployment_id=state.session_id,
            session_id=state.session_id,
            spec_id=state.spec.spec_id if state.spec else "",
            strategy_file=state.build_result.strategy_file if state.build_result else "",
        )
