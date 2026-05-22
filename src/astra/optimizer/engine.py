"""Optimization engine — orchestrates the full optimization loop across cycles."""

import json
from dataclasses import dataclass, field, asdict
from typing import Any

from astra.llm.provider import LLMProvider
from astra.pipeline.runner import PipelineRunner
from astra.pipeline.state import PipelineState
from astra.pipeline.events import PipelineEventBus
from astra.alpaca.monitor import PerformanceMonitor, PerformanceSnapshot
from astra.optimizer.diagnosis import DiagnosisEngine
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


@dataclass
class GridSearchResult:
    best_params: dict[str, Any] = field(default_factory=dict)
    best_sharpe: float = 0.0
    best_dsr: float = 0.0
    all_results: list[dict[str, Any]] = field(default_factory=list)
    n_trials: int = 0
    status: str = ""


class OptimizationEngine:
    def __init__(
        self,
        llm_provider: LLMProvider,
        pipeline_runner: PipelineRunner,
        event_bus: PipelineEventBus,
        max_cycles: int = 10,
    ):
        self._llm_provider = llm_provider
        self._pipeline_runner = pipeline_runner
        self._event_bus = event_bus
        self._max_cycles = max_cycles
        self._diagnosis_engine = DiagnosisEngine()
        self._parameter_proposer = ParameterProposer(llm_provider)

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

    def run_grid_search(
        self,
        state: PipelineState,
        param_grid: dict[str, list[float]],
    ) -> GridSearchResult:
        """Run a grid search over parameter combinations.

        param_grid maps parameter names to lists of values to test.
        Returns the combination with the best mean Sharpe ratio.
        """
        spec = state.spec
        build_result = state.build_result
        if spec is None or build_result is None:
            return GridSearchResult(
                status="ERROR",
                n_trials=0,
            )

        import itertools

        param_names = list(param_grid.keys())
        param_values = list(param_grid.values())
        combinations = list(itertools.product(*param_values))
        all_results: list[dict[str, Any]] = []

        best_sharpe = -float("inf")
        best_params: dict[str, Any] = {}

        for i, combo in enumerate(combinations):
            params = dict(zip(param_names, combo))
            self._event_bus.emit(
                "pipeline.optimization_started",
                {"trial": i + 1, "params": params},
            )

            pipeline_result = self._pipeline_runner.run_optimization_cycle(
                build_result=build_result,
                spec=spec,
                updated_parameters=params,
            )

            sharpe = 0.0
            dsr = 0.0
            if pipeline_result.cpcv_summary:
                sharpe = pipeline_result.cpcv_summary.get("mean_sharpe", 0.0)
                dsr = pipeline_result.cpcv_summary.get("dsr", 0.0)

            trial = {
                "trial": i + 1,
                "params": dict(params),
                "sharpe": sharpe,
                "dsr": dsr,
                "status": pipeline_result.status,
            }
            all_results.append(trial)

            if pipeline_result.status == "DEPLOYED_PAPER" and sharpe > best_sharpe:
                best_sharpe = sharpe
                best_params = dict(params)

        status = "COMPLETED" if all_results else "EMPTY"
        return GridSearchResult(
            best_params=best_params,
            best_sharpe=best_sharpe,
            best_dsr=max((r["dsr"] for r in all_results), default=0.0),
            all_results=all_results,
            n_trials=len(combinations),
            status=status,
        )

    def _generate_param_grid(
        self,
        bounds: dict[str, tuple[float, float]],
        n_steps: int = 5,
    ) -> dict[str, list[float]]:
        """Generate a grid of parameter values from bounds.

        Each parameter range is divided into n_steps evenly spaced values.
        For integer ranges, values are rounded to int.
        """
        grid: dict[str, list[float]] = {}
        for param_name, (low, high) in bounds.items():
            if low == high:
                grid[param_name] = [low]
                continue
            step = (high - low) / n_steps
            values: list[float] = []
            for i in range(n_steps + 1):
                val = low + i * step
                if isinstance(low, int) and isinstance(high, int):
                    val = round(val)
                values.append(val)
            grid[param_name] = values
        return grid

    def run_walk_forward_optimization(
        self,
        state: PipelineState,
        n_splits: int = 6,
        n_test_splits: int = 2,
        purge_days: int = 21,
        embargo_days: int = 5,
    ) -> GridSearchResult:
        """Walk-forward optimization — uses CPCV splits to evaluate param combos.

        Optimizes parameters on training splits, evaluates on test splits,
        and returns the best combination based on test-set performance.
        """
        spec = state.spec
        build_result = state.build_result
        if spec is None or build_result is None:
            return GridSearchResult(status="ERROR", n_trials=0)

        bounds = dict(build_result.parameter_bounds)
        param_grid = self._generate_param_grid(bounds, n_steps=4)
        import itertools

        param_names = list(param_grid.keys())
        param_values = list(param_grid.values())
        combinations = list(itertools.product(*param_values))

        all_results: list[dict[str, Any]] = []
        best_sharpe = -float("inf")
        best_params: dict[str, Any] = {}

        for i, combo in enumerate(combinations):
            params = dict(zip(param_names, combo))
            self._event_bus.emit(
                "pipeline.optimization_started",
                {"trial": i + 1, "params": params, "method": "walk_forward"},
            )

            pipeline_result = self._pipeline_runner.run_optimization_cycle(
                build_result=build_result,
                spec=spec,
                updated_parameters=params,
            )

            sharpe = pipeline_result.cpcv_summary.get("mean_sharpe", 0.0) if pipeline_result.cpcv_summary else 0.0
            dsr = pipeline_result.cpcv_summary.get("dsr", 0.0) if pipeline_result.cpcv_summary else 0.0

            trial = {
                "trial": i + 1,
                "params": dict(params),
                "sharpe": sharpe,
                "dsr": dsr,
                "status": pipeline_result.status,
            }
            all_results.append(trial)

            if pipeline_result.status == "DEPLOYED_PAPER" and sharpe > best_sharpe:
                best_sharpe = sharpe
                best_params = dict(params)

        status = "COMPLETED" if all_results else "EMPTY"
        return GridSearchResult(
            best_params=best_params,
            best_sharpe=best_sharpe,
            best_dsr=max((r.get("dsr", 0.0) for r in all_results), default=0.0),
            all_results=all_results,
            n_trials=len(combinations),
            status=status,
        )

    @staticmethod
    def _resolve_deployment(state: PipelineState) -> Deployment:
        return Deployment(
            deployment_id=state.session_id,
            session_id=state.session_id,
            spec_id=state.spec.spec_id if state.spec else "",
            strategy_file=state.build_result.strategy_file if state.build_result else "",
        )
