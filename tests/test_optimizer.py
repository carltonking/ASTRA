"""Tests for the ASTRA optimization engine."""

import json
import uuid
from dataclasses import asdict
from datetime import datetime, timezone
from unittest.mock import MagicMock, patch

import pytest

from astra.planner.spec import StrategySpec
from astra.builder.generator import BuildResult
from astra.pipeline.runner import PipelineResult, PipelineRunner
from astra.pipeline.state import PipelineState
from astra.pipeline.events import PipelineEventBus
from astra.alpaca.monitor import PerformanceSnapshot, PerformanceMonitor
from astra.optimizer import (
    OptimizationEngine,
    OptimizationResult,
    DiagnosisEngine,
    Diagnosis,
    ParameterProposer,
    ParameterProposal,
    OptimizationHistory,
)


def _make_spec(**overrides) -> StrategySpec:
    params = dict(
        spec_id=str(uuid.uuid4()),
        user_idea="Test",
        asset_class="equity",
        symbols=["SPY"],
        timeframe="daily",
        data_source="yfinance",
        strategy_type="trend_following",
        market_hypothesis="Moving average crossovers capture trends sufficiently for testing purposes",
        entry_conditions=["Test entry"],
        exit_conditions=["Test exit"],
        target_return=0.15,
        max_drawdown=0.20,
        position_size=0.10,
        max_positions=5,
        backtest_start="2020-01-01",
        backtest_end="2023-12-31",
    )
    params.update(overrides)
    return StrategySpec(**params)


def _make_build_result(spec: StrategySpec, **overrides) -> BuildResult:
    params = dict(
        success=True,
        spec_id=spec.spec_id,
        strategy_file="/tmp/strat.py",
        strategy_class_name="TrendFollowingStrategy",
        initial_parameters={"fast_window": 20, "slow_window": 50},
        parameter_bounds={"fast_window": (5, 50), "slow_window": (20, 200)},
    )
    params.update(overrides)
    return BuildResult(**params)


def _make_pipeline_result(spec: StrategySpec, **overrides) -> PipelineResult:
    params = dict(
        pipeline_id="pipe-1",
        spec_id=spec.spec_id,
        cycle_number=0,
        status="DEPLOYED_PAPER",
        cpcv_summary={"mean_sharpe": 1.5, "dsr": 0.8, "overfitting_probability": 0.2},
        backtest_metrics={"mean_sharpe": 1.5, "dsr": 0.8, "max_drawdown": 0.08},
    )
    params.update(overrides)
    return PipelineResult(**params)


def _make_snapshot(**overrides) -> PerformanceSnapshot:
    params = dict(
        deployment_id="dep-1",
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


# ---------------------------------------------------------------------------
# Diagnosis
# ---------------------------------------------------------------------------


class TestDiagnosis:
    def test_diagnosis_defaults(self):
        d = Diagnosis(primary_diagnosis="TEST")
        assert d.primary_diagnosis == "TEST"
        assert d.confidence == 0.0
        assert d.evidence == []
        assert d.disclaimer != ""


# ---------------------------------------------------------------------------
# DiagnosisEngine
# ---------------------------------------------------------------------------


class TestDiagnosisEngine:
    def test_insufficient_data_when_days_less_than_5(self):
        engine = DiagnosisEngine()
        spec = _make_spec()
        build = _make_build_result(spec)
        pipeline_results = [_make_pipeline_result(spec)]
        snapshot = _make_snapshot(days_deployed=2)

        diagnosis = engine.diagnose(spec, build, pipeline_results, snapshot)
        assert diagnosis.primary_diagnosis == "INSUFFICIENT_DATA"
        assert diagnosis.recommended_action == "EXTEND_OBSERVATION"
        assert diagnosis.confidence == 1.0

    def test_parameter_sensitivity_detected(self):
        engine = DiagnosisEngine()
        spec = _make_spec()
        build = _make_build_result(spec)
        pipeline_results = [
            _make_pipeline_result(
                spec,
                cpcv_summary={"mean_sharpe": 2.0, "dsr": 0.3, "overfitting_probability": 0.7},
                backtest_metrics={"mean_sharpe": 2.0, "dsr": 0.3},
            )
        ]
        snapshot = _make_snapshot(sharpe_ratio=0.5, days_deployed=20)

        diagnosis = engine.diagnose(spec, build, pipeline_results, snapshot)
        assert diagnosis.primary_diagnosis == "PARAMETER_SENSITIVITY"
        assert diagnosis.confidence == 0.85

    def test_transaction_cost_drag_detected(self):
        engine = DiagnosisEngine()
        spec = _make_spec()
        build = _make_build_result(spec)
        pipeline_results = [_make_pipeline_result(spec)]

        snapshot = _make_snapshot(
            total_return=0.001,
            total_trades=50,
            days_deployed=10,
            win_rate=0.5,
            sharpe_ratio=0.1,
        )

        diagnosis = engine.diagnose(spec, build, pipeline_results, snapshot)
        assert diagnosis.primary_diagnosis == "TRANSACTION_COST_DRAG"

    def test_position_sizing_detected(self):
        engine = DiagnosisEngine()
        spec = _make_spec()
        build = _make_build_result(spec)
        pipeline_results = [_make_pipeline_result(spec)]
        snapshot = _make_snapshot(max_drawdown=0.25, days_deployed=20)

        diagnosis = engine.diagnose(spec, build, pipeline_results, snapshot)
        assert diagnosis.primary_diagnosis == "POSITION_SIZING"

    def test_signal_decay_detected(self):
        engine = DiagnosisEngine()
        spec = _make_spec()
        build = _make_build_result(spec)
        pipeline_results = [_make_pipeline_result(spec)]
        snapshot = _make_snapshot(
            win_rate=0.35,
            total_trades=50,
            days_deployed=30,
            sharpe_ratio=-0.2,
        )

        diagnosis = engine.diagnose(spec, build, pipeline_results, snapshot)
        assert diagnosis.primary_diagnosis == "SIGNAL_DECAY"

    def test_returns_normal_degradation_when_no_pattern(self):
        engine = DiagnosisEngine()
        spec = _make_spec()
        build = _make_build_result(spec)
        pipeline_results = [_make_pipeline_result(spec)]
        snapshot = _make_snapshot(
            days_deployed=20,
            sharpe_ratio=0.8,
            win_rate=0.5,
            total_trades=10,
            max_drawdown=0.06,
            total_return=0.03,
        )

        diagnosis = engine.diagnose(spec, build, pipeline_results, snapshot)
        assert diagnosis.primary_diagnosis == "NORMAL_DEGRADATION"
        assert diagnosis.recommended_action == "EXTEND_OBSERVATION"


# ---------------------------------------------------------------------------
# ParameterProposal
# ---------------------------------------------------------------------------


class TestParameterProposal:
    def test_auto_generates_id(self):
        p = ParameterProposal()
        assert p.proposal_id != ""
        uuid.UUID(p.proposal_id)

    def test_serializes_to_json(self):
        diagnosis = Diagnosis(primary_diagnosis="TEST", confidence=0.8)
        p = ParameterProposal(
            cycle_number=1,
            action="ADJUST_PARAMETERS",
            parameter_changes={"fast_window": 30},
            reasoning={"fast_window": "Increase to reduce sensitivity"},
            summary="Test summary",
            confidence=0.7,
            diagnosis=diagnosis,
        )
        json_str = p.to_json()
        data = json.loads(json_str)
        assert data["action"] == "ADJUST_PARAMETERS"
        assert data["parameter_changes"]["fast_window"] == 30
        assert data["diagnosis"]["primary_diagnosis"] == "TEST"

    def test_default_cycle_number(self):
        p = ParameterProposal()
        assert p.cycle_number == 0


# ---------------------------------------------------------------------------
# ParameterProposer
# ---------------------------------------------------------------------------


class TestParameterProposer:
    def test_returns_extend_observation_for_insufficient_data(self):
        proposer = ParameterProposer(anthropic_api_key="test")
        spec = _make_spec()
        build = _make_build_result(spec)

        diagnosis = Diagnosis(
            primary_diagnosis="INSUFFICIENT_DATA",
            confidence=1.0,
            evidence=["Not enough data"],
            recommended_action="EXTEND_OBSERVATION",
            plain_english_summary="Need more data. Continuing observation.",
        )

        proposal = proposer.propose(
            spec=spec,
            build_result=build,
            diagnosis=diagnosis,
            current_parameters={"fast_window": 20},
            parameter_bounds={"fast_window": (5, 50)},
        )

        assert proposal.action == "EXTEND_OBSERVATION"
        assert proposal.parameter_changes == {}

    def test_returns_abandon_for_failed_diagnosis(self):
        proposer = ParameterProposer(anthropic_api_key="test")
        spec = _make_spec()
        build = _make_build_result(spec)

        diagnosis = Diagnosis(
            primary_diagnosis="SIGNAL_DECAY",
            confidence=0.9,
            evidence=["Signal has decayed"],
            recommended_action="ABANDON",
            plain_english_summary="Strategy hypothesis no longer valid. Abandoning.",
        )

        proposal = proposer.propose(
            spec=spec,
            build_result=build,
            diagnosis=diagnosis,
            current_parameters={"fast_window": 20},
            parameter_bounds={"fast_window": (5, 50)},
        )

        assert proposal.action == "ABANDON"

    def test_returns_rebuild_for_signal_decay(self):
        proposer = ParameterProposer(anthropic_api_key="test")
        spec = _make_spec()
        build = _make_build_result(spec)

        diagnosis = Diagnosis(
            primary_diagnosis="SIGNAL_DECAY",
            confidence=0.8,
            evidence=["Signal decayed"],
            recommended_action="REBUILD_STRATEGY",
            plain_english_summary="The signal is no longer predictive. Rebuild.",
        )

        proposal = proposer.propose(
            spec=spec,
            build_result=build,
            diagnosis=diagnosis,
            current_parameters={"fast_window": 20},
            parameter_bounds={"fast_window": (5, 50)},
        )

        assert proposal.action == "REBUILD_STRATEGY"

    @patch("astra.optimizer.proposer.Anthropic")
    def test_uses_claude_for_adjust_parameters(self, MockAnthropic):
        mock_client = MagicMock()
        MockAnthropic.return_value = mock_client

        content_block = MagicMock()
        content_block.text = json.dumps({
            "action": "ADJUST_PARAMETERS",
            "parameter_changes": {"fast_window": 15, "slow_window": 40},
            "reasoning": {
                "fast_window": "Reducing fast window to capture shorter trends",
                "slow_window": "Reducing slow window to match faster entry signals",
            },
            "summary": "Adjusting trend windows to improve responsiveness.",
            "confidence": 0.65,
        })
        mock_client.messages.create.return_value = MagicMock(content=[content_block])

        proposer = ParameterProposer(anthropic_api_key="test")
        spec = _make_spec()
        build = _make_build_result(spec)

        diagnosis = Diagnosis(
            primary_diagnosis="PARAMETER_SENSITIVITY",
            confidence=0.85,
            evidence=["DSR is low", "Paper Sharpe is half of backtest"],
            recommended_action="ADJUST_PARAMETERS",
            plain_english_summary="Parameters may be overfit.",
        )

        proposal = proposer.propose(
            spec=spec,
            build_result=build,
            diagnosis=diagnosis,
            current_parameters={"fast_window": 20, "slow_window": 50},
            parameter_bounds={"fast_window": (5, 50), "slow_window": (20, 200)},
        )

        assert proposal.action == "ADJUST_PARAMETERS"
        assert proposal.parameter_changes["fast_window"] == 15
        assert proposal.parameter_changes["slow_window"] == 40

    @patch("astra.optimizer.proposer.Anthropic")
    def test_claude_failure_falls_back_to_extend_observation(self, MockAnthropic):
        mock_client = MagicMock()
        MockAnthropic.return_value = mock_client
        mock_client.messages.create.side_effect = Exception("API error")

        proposer = ParameterProposer(anthropic_api_key="test")
        spec = _make_spec()
        build = _make_build_result(spec)

        diagnosis = Diagnosis(
            primary_diagnosis="PARAMETER_SENSITIVITY",
            confidence=0.85,
            evidence=["DSR is low"],
            recommended_action="ADJUST_PARAMETERS",
            plain_english_summary="Adjust parameters to improve performance.",
        )

        proposal = proposer.propose(
            spec=spec,
            build_result=build,
            diagnosis=diagnosis,
            current_parameters={"fast_window": 20},
            parameter_bounds={"fast_window": (5, 50)},
        )

        assert proposal.action == "EXTEND_OBSERVATION"


# ---------------------------------------------------------------------------
# OptimizationHistory
# ---------------------------------------------------------------------------


class TestOptimizationHistory:
    def test_auto_generates_session_id(self):
        h = OptimizationHistory()
        assert h.session_id != ""

    def test_is_cycling_detects_repeated_parameters(self):
        h = OptimizationHistory(session_id="test")

        class MockProposal:
            cycle_number = 1
            action = "ADJUST_PARAMETERS"
            parameter_changes = {"fast_window": 20}
            confidence = 0.5

        class MockResult:
            status = "DEPLOYED_PAPER"
            cpcv_summary = {"mean_sharpe": 0.5, "dsr": 0.3}

        h.record(MockProposal(), MockResult())

        class MockProposal2:
            cycle_number = 2
            action = "ADJUST_PARAMETERS"
            parameter_changes = {"fast_window": 20}
            confidence = 0.5

        class MockResult2:
            status = "DEPLOYED_PAPER"
            cpcv_summary = {"mean_sharpe": 0.6, "dsr": 0.4}

        h.record(MockProposal2(), MockResult2())

        assert h.is_cycling() is True

    def test_is_cycling_false_with_different_parameters(self):
        h = OptimizationHistory(session_id="test")

        class MockProposal:
            cycle_number = 1
            action = "ADJUST_PARAMETERS"
            parameter_changes = {"fast_window": 20}
            confidence = 0.5

        class MockResult:
            status = "DEPLOYED_PAPER"
            cpcv_summary = {"mean_sharpe": 0.5, "dsr": 0.3}

        h.record(MockProposal(), MockResult())

        class MockProposal2:
            cycle_number = 2
            action = "ADJUST_PARAMETERS"
            parameter_changes = {"fast_window": 30}
            confidence = 0.6

        h.record(MockProposal2(), MockResult())

        assert h.is_cycling() is False

    def test_has_improvement_true_when_sharpe_increases(self):
        h = OptimizationHistory(session_id="test")

        class MockResult1:
            status = "DEPLOYED_PAPER"
            cpcv_summary = {"mean_sharpe": 0.5, "dsr": 0.3}

        class MockProposal1:
            cycle_number = 0
            action = "INITIAL"
            parameter_changes = {}
            confidence = 0.0

        h.record(MockProposal1(), MockResult1())

        class MockResult2:
            status = "DEPLOYED_PAPER"
            cpcv_summary = {"mean_sharpe": 0.8, "dsr": 0.6}

        class MockProposal2:
            cycle_number = 1
            action = "ADJUST_PARAMETERS"
            parameter_changes = {"fast_window": 30}
            confidence = 0.5

        h.record(MockProposal2(), MockResult2())

        assert h.has_improvement() is True

    def test_has_improvement_false_when_sharpe_stagnates(self):
        h = OptimizationHistory(session_id="test")

        class MockResult1:
            status = "DEPLOYED_PAPER"
            cpcv_summary = {"mean_sharpe": 0.8, "dsr": 0.6}

        class MockProposal1:
            cycle_number = 0
            action = "INITIAL"
            parameter_changes = {}
            confidence = 0.0

        h.record(MockProposal1(), MockResult1())

        class MockResult2:
            status = "DEPLOYED_PAPER"
            cpcv_summary = {"mean_sharpe": 0.6, "dsr": 0.4}

        class MockProposal2:
            cycle_number = 1
            action = "ADJUST_PARAMETERS"
            parameter_changes = {"fast_window": 30}
            confidence = 0.5

        h.record(MockProposal2(), MockResult2())

        assert h.has_improvement() is False

    def test_best_cycle_returns_highest_dsr(self):
        h = OptimizationHistory(session_id="test")

        class MockProposal:
            cycle_number = 0
            action = "INITIAL"
            parameter_changes = {}
            confidence = 0.0

        class MockResult1:
            status = "DEPLOYED_PAPER"
            cpcv_summary = {"mean_sharpe": 0.5, "dsr": 0.3}

        h.record(MockProposal(), MockResult1())

        class MockResult2:
            status = "DEPLOYED_PAPER"
            cpcv_summary = {"mean_sharpe": 1.2, "dsr": 0.9}

        class MockProposal2:
            cycle_number = 1
            action = "ADJUST_PARAMETERS"
            parameter_changes = {"fast_window": 15}
            confidence = 0.7

        h.record(MockProposal2(), MockResult2())

        best = h.best_cycle()
        assert best is not None
        assert best["dsr"] == 0.9

    def test_best_cycle_returns_none_when_empty(self):
        h = OptimizationHistory(session_id="test")
        assert h.best_cycle() is None

    def test_save_and_load_roundtrip(self, tmp_path):
        h = OptimizationHistory(session_id="test-session")

        class MockProposal:
            cycle_number = 1
            action = "ADJUST_PARAMETERS"
            parameter_changes = {"fast_window": 20}
            confidence = 0.5

        class MockResult:
            status = "DEPLOYED_PAPER"
            cpcv_summary = {"mean_sharpe": 0.5, "dsr": 0.3}

        h.record(MockProposal(), MockResult())

        path = str(tmp_path / "history.json")
        h.save(path)

        loaded = OptimizationHistory.load(path)
        assert loaded.session_id == "test-session"
        assert len(loaded.records) == 1
        assert loaded.records[0]["dsr"] == 0.3


# ---------------------------------------------------------------------------
# OptimizationResult
# ---------------------------------------------------------------------------


class TestOptimizationResult:
    def test_disclaimer_populated(self):
        result = OptimizationResult()
        assert result.disclaimer != ""
        assert "profitability" in result.disclaimer

    def test_serializes_to_json(self):
        result = OptimizationResult(
            session_id="session-1",
            status="EXHAUSTED",
            total_cycles=10,
            plain_english_outcome="Did not converge.",
        )
        json_str = result.to_json()
        data = json.loads(json_str)
        assert data["status"] == "EXHAUSTED"
        assert data["total_cycles"] == 10


# ---------------------------------------------------------------------------
# OptimizationEngine
# ---------------------------------------------------------------------------


class TestOptimizationEngine:
    def test_initializes_with_params(self):
        pipeline_runner = MagicMock(spec=PipelineRunner)
        event_bus = PipelineEventBus()
        engine = OptimizationEngine(
            anthropic_api_key="test",
            pipeline_runner=pipeline_runner,
            event_bus=event_bus,
            max_cycles=5,
        )
        assert engine._max_cycles == 5

    def test_returns_error_when_no_spec(self):
        pipeline_runner = MagicMock(spec=PipelineRunner)
        event_bus = PipelineEventBus()
        engine = OptimizationEngine(
            anthropic_api_key="test",
            pipeline_runner=pipeline_runner,
            event_bus=event_bus,
        )
        state = PipelineState(session_id="test")
        monitor = MagicMock(spec=PerformanceMonitor)

        result = engine.run_optimization_loop(state, monitor)
        assert result.status == "ERROR"
        assert "no strategy spec" in result.plain_english_outcome.lower()

    def test_exhausted_at_max_cycles(self):
        pipeline_runner = MagicMock(spec=PipelineRunner)
        event_bus = PipelineEventBus()
        engine = OptimizationEngine(
            anthropic_api_key="test",
            pipeline_runner=pipeline_runner,
            event_bus=event_bus,
            max_cycles=1,
        )

        spec = _make_spec()
        build = _make_build_result(spec)
        state = PipelineState(session_id="test", spec=spec, build_result=build)
        monitor = MagicMock(spec=PerformanceMonitor)

        monitor.snapshot.return_value = _make_snapshot(days_deployed=20)
        pipeline_runner.run_optimization_cycle.return_value = _make_pipeline_result(spec)

        result = engine.run_optimization_loop(state, monitor)
        assert result.status == "EXHAUSTED"
        assert result.total_cycles == 1

    def test_abandons_on_rebuild_recommendation(self):
        pipeline_runner = MagicMock(spec=PipelineRunner)
        event_bus = PipelineEventBus()
        engine = OptimizationEngine(
            anthropic_api_key="test",
            pipeline_runner=pipeline_runner,
            event_bus=event_bus,
            max_cycles=10,
        )

        spec = _make_spec()
        build = _make_build_result(spec)
        state = PipelineState(
            session_id="test",
            spec=spec,
            build_result=build,
            pipeline_results=[
                PipelineResult(
                    pipeline_id="p1",
                    spec_id=spec.spec_id,
                    status="DEPLOYED_PAPER",
                    cpcv_summary={"mean_sharpe": 2.0, "dsr": 0.6},
                    backtest_metrics={"mean_sharpe": 2.0, "dsr": 0.6},
                )
            ],
        )
        monitor = MagicMock(spec=PerformanceMonitor)

        snapshot = _make_snapshot(
            sharpe_ratio=2.0,
            days_deployed=30,
            win_rate=0.35,
            total_trades=50,
            total_return=0.02,
            max_drawdown=0.08,
        )
        monitor.snapshot.return_value = snapshot

        result = engine.run_optimization_loop(state, monitor)
        assert result.status == "ABANDONED"

    @patch("astra.optimizer.proposer.Anthropic")
    def test_handles_pipeline_error_in_cycle(self, MockAnthropic):
        mock_client = MagicMock()
        MockAnthropic.return_value = mock_client
        content_block = MagicMock()
        content_block.text = json.dumps({
            "action": "ADJUST_PARAMETERS",
            "parameter_changes": {"fast_window": 15},
            "reasoning": {"fast_window": "Reducing to improve responsiveness"},
            "summary": "Adjusting parameters.",
            "confidence": 0.6,
        })
        mock_client.messages.create.return_value = MagicMock(content=[content_block])

        pipeline_runner = MagicMock(spec=PipelineRunner)
        event_bus = PipelineEventBus()
        engine = OptimizationEngine(
            anthropic_api_key="test",
            pipeline_runner=pipeline_runner,
            event_bus=event_bus,
            max_cycles=10,
        )

        spec = _make_spec()
        build = _make_build_result(spec)
        state = PipelineState(
            session_id="test",
            spec=spec,
            build_result=build,
            pipeline_results=[
                PipelineResult(
                    pipeline_id="p1",
                    spec_id=spec.spec_id,
                    status="DEPLOYED_PAPER",
                    cpcv_summary={"mean_sharpe": 1.5, "dsr": 0.3, "overfitting_probability": 0.7},
                    backtest_metrics={"mean_sharpe": 1.5, "dsr": 0.3},
                )
            ],
        )
        monitor = MagicMock(spec=PerformanceMonitor)

        monitor.snapshot.return_value = _make_snapshot(
            days_deployed=20,
            sharpe_ratio=0.5,
            win_rate=0.5,
            total_trades=10,
            max_drawdown=0.06,
        )

        pipeline_runner.run_optimization_cycle.return_value = PipelineResult(
            pipeline_id="p2", spec_id=spec.spec_id, status="ERROR", error="Something broke"
        )

        result = engine.run_optimization_loop(state, monitor)
        assert result.status == "ERROR"
        assert "Something broke" in result.plain_english_outcome

    def test_cycle_summaries_populated(self):
        pipeline_runner = MagicMock(spec=PipelineRunner)
        event_bus = PipelineEventBus()
        engine = OptimizationEngine(
            anthropic_api_key="test",
            pipeline_runner=pipeline_runner,
            event_bus=event_bus,
            max_cycles=1,
        )

        spec = _make_spec()
        build = _make_build_result(spec)
        state = PipelineState(session_id="test", spec=spec, build_result=build)
        monitor = MagicMock(spec=PerformanceMonitor)

        monitor.snapshot.return_value = _make_snapshot(
            days_deployed=40,
            sharpe_ratio=0.7,
            win_rate=0.5,
            total_trades=10,
            max_drawdown=0.06,
        )

        pipeline_runner.run_optimization_cycle.return_value = _make_pipeline_result(spec)

        result = engine.run_optimization_loop(state, monitor)
        assert len(result.cycle_summaries) >= 1
        assert "cycle" in result.cycle_summaries[0]
        assert "diagnosis" in result.cycle_summaries[0]
