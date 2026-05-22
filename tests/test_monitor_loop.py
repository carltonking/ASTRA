"""Tests for the PerformanceMonitoringLoop."""

import uuid
from unittest.mock import MagicMock

from astra.alpaca.monitor_loop import PerformanceMonitoringLoop, MonitoringCheckResult
from astra.alpaca.monitor import PerformanceSnapshot, DegradationReport, PerformanceMonitor
from astra.alpaca.deployer import Deployment
from astra.optimizer.engine import OptimizationEngine, OptimizationResult
from astra.pipeline.state import PipelineState
from astra.pipeline.events import PipelineEventBus
from astra.pipeline.runner import PipelineRunner
from astra.llm.provider import LLMProvider
from astra.planner.spec import StrategySpec
from astra.builder.generator import BuildResult


def _make_deployment(**overrides) -> Deployment:
    params = dict(
        deployment_id=str(uuid.uuid4()),
        session_id="test-session",
        spec_id=str(uuid.uuid4()),
        strategy_file="/tmp/strat.py",
    )
    params.update(overrides)
    return Deployment(**params)


def _make_snapshot(**overrides) -> PerformanceSnapshot:
    params = dict(
        deployment_id=str(uuid.uuid4()),
        total_return=0.05,
        annualized_return=0.08,
        sharpe_ratio=0.6,
        max_drawdown=0.12,
        win_rate=0.45,
        total_trades=30,
        days_deployed=20,
        equity_curve=[100000.0, 101000.0, 102000.0],
    )
    params.update(overrides)
    return PerformanceSnapshot(**params)


def _make_state(**overrides) -> PipelineState:
    params = dict(session_id="test-session")
    params.update(overrides)
    return PipelineState(**params)


class TestPerformanceMonitoringLoop:
    def test_initializes_with_deps(self):
        monitor = MagicMock(spec=PerformanceMonitor)
        engine = MagicMock(spec=OptimizationEngine)
        state = _make_state()
        loop = PerformanceMonitoringLoop(monitor, engine, state, interval_minutes=30)
        assert loop._interval == 30 * 60
        assert loop.last_check is None

    def test_check_and_optimize_monitors_only_when_no_triggers(self):
        monitor = MagicMock(spec=PerformanceMonitor)
        engine = MagicMock(spec=OptimizationEngine)
        state = _make_state()
        deployment = _make_deployment()

        snapshot = _make_snapshot()
        degradation = DegradationReport(
            return_degradation=0.01,
            sharpe_degradation=0.05,
            drawdown_expansion=0.01,
            overall_degradation_score=0.12,
            category="ACCEPTABLE",
            triggers_optimizer=False,
        )
        monitor.snapshot.return_value = snapshot
        monitor.compute_degradation.return_value = degradation

        loop = PerformanceMonitoringLoop(monitor, engine, state)
        result = loop.check_and_optimize(deployment)

        assert result.action == "MONITOR_ONLY"
        assert result.degradation is degradation
        assert result.snapshot is snapshot
        assert result.optimization_result is None
        assert loop.last_check is result
        engine.run_optimization_loop.assert_not_called()

    def test_check_and_optimize_triggers_reoptimization(self):
        monitor = MagicMock(spec=PerformanceMonitor)
        engine = MagicMock(spec=OptimizationEngine)
        state = _make_state()
        deployment = _make_deployment()

        snapshot = _make_snapshot(total_return=-0.05, sharpe_ratio=-0.3, max_drawdown=0.35)
        degradation = DegradationReport(
            return_degradation=0.3,
            sharpe_degradation=0.8,
            drawdown_expansion=0.2,
            overall_degradation_score=0.6,
            category="SEVERE",
            triggers_optimizer=True,
        )
        monitor.snapshot.return_value = snapshot
        monitor.compute_degradation.return_value = degradation

        opt_result = OptimizationResult(
            session_id="test-session",
            status="EXHAUSTED",
            total_cycles=3,
        )
        engine.run_optimization_loop.return_value = opt_result

        loop = PerformanceMonitoringLoop(monitor, engine, state)
        result = loop.check_and_optimize(deployment)

        assert result.action == "RE_OPTIMIZED"
        assert result.degradation is degradation
        assert result.optimization_result is opt_result
        assert result.snapshot is snapshot
        engine.run_optimization_loop.assert_called_once_with(
            state=state,
            monitor=monitor,
        )

    def test_check_and_optimize_marks_failed_on_error(self):
        monitor = MagicMock(spec=PerformanceMonitor)
        engine = MagicMock(spec=OptimizationEngine)
        state = _make_state()
        deployment = _make_deployment()

        snapshot = _make_snapshot()
        degradation = DegradationReport(
            overall_degradation_score=0.8,
            category="SEVERE",
            triggers_optimizer=True,
        )
        monitor.snapshot.return_value = snapshot
        monitor.compute_degradation.return_value = degradation

        opt_result = OptimizationResult(
            session_id="test-session",
            status="ABANDONED",
            total_cycles=2,
            plain_english_outcome="Signal decayed. Abandoning.",
        )
        engine.run_optimization_loop.return_value = opt_result

        loop = PerformanceMonitoringLoop(monitor, engine, state)
        result = loop.check_and_optimize(deployment)

        assert result.action == "FAILED"
        assert result.optimization_result is opt_result

    def test_check_and_optimize_uses_latest_backtest_metrics(self):
        monitor = MagicMock(spec=PerformanceMonitor)
        engine = MagicMock(spec=OptimizationEngine)
        from astra.pipeline.runner import PipelineResult

        result1 = PipelineResult(
            pipeline_id="p1",
            spec_id="s1",
            status="DEPLOYED_PAPER",
            backtest_metrics={"mean_sharpe": 1.5, "dsr": 0.8},
        )
        state = _make_state(pipeline_results=[result1])
        deployment = _make_deployment()

        snapshot = _make_snapshot()
        degradation = DegradationReport(
            overall_degradation_score=0.1,
            category="ACCEPTABLE",
            triggers_optimizer=False,
        )
        monitor.snapshot.return_value = snapshot
        monitor.compute_degradation.return_value = degradation

        loop = PerformanceMonitoringLoop(monitor, engine, state)
        loop.check_and_optimize(deployment)

        monitor.compute_degradation.assert_called_once_with(snapshot, {"mean_sharpe": 1.5, "dsr": 0.8})
