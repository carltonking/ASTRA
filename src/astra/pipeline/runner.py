"""Pipeline orchestration — runs the full ASTRA loop for a built strategy."""

import json
import os
import uuid
from dataclasses import dataclass, field, asdict
from datetime import datetime, timezone
from typing import Any

from astra.planner.spec import StrategySpec
from astra.builder.generator import BuildResult, StrategyGenerator
from astra.pipeline.aurora_bridge import AuroraBridge, LeakageVerdict, CPCVResult, ReviewVerdict
from astra.pipeline.events import PipelineEventBus

DISCLAIMER = (
    "ASTRA research results are not profitability guarantees. "
    "Past performance does not predict future results."
)


@dataclass
class PipelineResult:
    pipeline_id: str = ""
    spec_id: str = ""
    cycle_number: int = 0
    status: str = ""
    run_dir: str = ""
    leakage_verdict: str | None = None
    review_board_status: str | None = None
    cpcv_summary: dict[str, Any] | None = None
    backtest_metrics: dict[str, Any] | None = None
    paper_deployment_id: str | None = None
    error: str | None = None
    created_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
    disclaimer: str = DISCLAIMER

    def to_json(self) -> str:
        data = asdict(self)
        data["created_at"] = self.created_at.isoformat()
        return json.dumps(data, indent=2, default=str)

    @classmethod
    def from_json(cls, json_str: str) -> "PipelineResult":
        data = json.loads(json_str)
        if "created_at" in data and isinstance(data["created_at"], str):
            data["created_at"] = datetime.fromisoformat(data["created_at"])
        return cls(**data)


class PipelineRunner:
    def __init__(
        self,
        anthropic_api_key: str,
        alpaca_paper_key: str,
        alpaca_paper_secret: str,
        alpaca_base_url: str,
        build_dir: str,
        max_optimization_cycles: int = 10,
        aurora_bridge: AuroraBridge | None = None,
        event_bus: PipelineEventBus | None = None,
    ):
        self._anthropic_api_key = anthropic_api_key
        self._alpaca_paper_key = alpaca_paper_key
        self._alpaca_paper_secret = alpaca_paper_secret
        self._alpaca_base_url = alpaca_base_url
        self._build_dir = build_dir
        self._max_optimization_cycles = max_optimization_cycles

        if aurora_bridge is not None:
            self._aurora = aurora_bridge
        else:
            data_dir = os.path.join(build_dir, ".aurora_data")
            self._aurora = AuroraBridge(data_dir=data_dir)

        self._event_bus = event_bus or PipelineEventBus()

    def run(self, build_result: BuildResult, spec: StrategySpec) -> PipelineResult:
        pipeline_id = str(uuid.uuid4())
        result = PipelineResult(
            pipeline_id=pipeline_id,
            spec_id=spec.spec_id,
            cycle_number=0,
            status="PASSED",
            run_dir=os.path.join(self._build_dir, spec.spec_id, "runs", pipeline_id),
        )

        self._event_bus.emit("pipeline.started", {"pipeline_id": pipeline_id, "spec_id": spec.spec_id})

        try:
            if not self._aurora.check_available():
                return self._fail(
                    result, "AURORA engine is not available (not installed or import failed)"
                )

            self._event_bus.emit("pipeline.data_downloaded", {"symbols": spec.symbols})
            data_key = self._aurora.download_data(
                symbols=spec.symbols,
                start=spec.backtest_start,
                end=spec.backtest_end,
                source=spec.data_source,
            )

            leak = self._aurora.run_leakage_detection(feature_key=data_key, label_key="signals")
            result.leakage_verdict = leak.status
            self._event_bus.emit("pipeline.leakage_checked", {"verdict": leak.status, "details": leak.details})

            if leak.status == "COMPROMISED":
                return self._fail(
                    result, f"Leakage detection blocked: {leak.details}", "FAILED_LEAKAGE"
                )

            self._event_bus.emit("pipeline.features_built", {})
            features_key = self._aurora.build_features(cache_key=data_key)

            self._event_bus.emit("pipeline.signals_generated", {})
            signals_key = self._aurora.generate_signals(
                strategy_file=build_result.strategy_file,
                config_file=build_result.aurora_config_file,
                features_key=features_key,
            )

            self._event_bus.emit("pipeline.backtest_complete", {})
            cpcv = self._aurora.run_cpcv_backtest(signals_key=signals_key)
            result.cpcv_summary = {
                "mean_sharpe": cpcv.mean_sharpe,
                "dsr": cpcv.dsr,
                "overfitting_probability": cpcv.overfitting_probability,
                "n_splits": cpcv.n_splits,
            }
            result.backtest_metrics = {
                "mean_sharpe": cpcv.mean_sharpe,
                "dsr": cpcv.dsr,
                "overfitting_probability": cpcv.overfitting_probability,
            }

            self._event_bus.emit("pipeline.review_complete", {"cpcv_summary": result.cpcv_summary})
            review = self._aurora.run_review_board(run_dir=result.run_dir)
            result.review_board_status = review.status

            if review.status != "APPROVED":
                return self._fail(
                    result, f"Review board {review.status}: {review.details}", "FAILED_BACKTEST"
                )

            deployment_id = self._deploy_to_paper(spec, build_result)
            result.paper_deployment_id = deployment_id
            result.status = "DEPLOYED_PAPER"
            self._event_bus.emit("pipeline.paper_deployed", {"deployment_id": deployment_id})

        except Exception as e:
            return self._fail(result, str(e), "ERROR")

        return result

    def run_optimization_cycle(
        self,
        build_result: BuildResult,
        spec: StrategySpec,
        updated_parameters: dict[str, Any],
    ) -> PipelineResult:
        cycle_number = build_result.build_log.count("Optimization cycle")
        cycle_number += 1

        self._event_bus.emit(
            "pipeline.optimization_started",
            {"cycle": cycle_number, "parameters": updated_parameters},
        )

        generator = StrategyGenerator(
            anthropic_api_key=self._anthropic_api_key,
            build_dir=self._build_dir,
        )

        updated_spec = StrategySpec(
            spec_id=spec.spec_id,
            user_idea=spec.user_idea,
            asset_class=spec.asset_class,
            symbols=list(spec.symbols),
            timeframe=spec.timeframe,
            data_source=spec.data_source,
            strategy_type=spec.strategy_type,
            market_hypothesis=spec.market_hypothesis,
            entry_conditions=list(spec.entry_conditions),
            exit_conditions=list(spec.exit_conditions),
            target_return=spec.target_return,
            max_drawdown=spec.max_drawdown,
            position_size=spec.position_size,
            max_positions=spec.max_positions,
            stop_loss=spec.stop_loss,
            take_profit=spec.take_profit,
            backtest_start=spec.backtest_start,
            backtest_end=spec.backtest_end,
        )

        new_build = generator.generate(updated_spec)
        if not new_build.success:
            result = PipelineResult(
                pipeline_id=str(uuid.uuid4()),
                spec_id=spec.spec_id,
                cycle_number=cycle_number,
                status="ERROR",
                error=f"Rebuild failed: {new_build.error}",
            )
            self._event_bus.emit("pipeline.failed", {"reason": result.error})
            return result

        result = self.run(new_build, updated_spec)
        result.cycle_number = cycle_number
        return result

    def _deploy_to_paper(self, spec: StrategySpec, build_result: BuildResult) -> str:
        deployment_id = str(uuid.uuid4())
        return deployment_id

    def _fail(
        self,
        result: PipelineResult,
        message: str,
        status: str = "ERROR",
    ) -> PipelineResult:
        result.status = status
        result.error = message
        self._event_bus.emit("pipeline.failed", {"reason": message, "status": status})
        return result
