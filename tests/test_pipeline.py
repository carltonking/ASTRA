"""Tests for the ASTRA pipeline orchestration layer."""

import json
import uuid
from datetime import datetime, timezone, timedelta
from dataclasses import asdict
from unittest.mock import MagicMock, patch

import pandas as pd
import pytest

from astra.llm.provider import LLMProvider
from astra.planner.spec import StrategySpec
from astra.builder.generator import BuildResult
from astra.pipeline import (
    PipelineRunner,
    PipelineResult,
    PipelineState,
    InvalidStatusTransition,
    PipelineEventBus,
    AuroraBridge,
    LeakageVerdict,
    CPCVResult,
    ReviewVerdict,
)
from astra.pipeline.runner import DISCLAIMER as RUNNER_DISCLAIMER
from unittest.mock import patch, MagicMock


def _make_spec(**overrides) -> StrategySpec:
    params = dict(
        spec_id=str(uuid.uuid4()),
        user_idea="Test strategy",
        asset_class="equity",
        symbols=["SPY"],
        timeframe="daily",
        data_source="yfinance",
        strategy_type="trend_following",
        market_hypothesis="Moving average crossovers capture sustained trends",
        entry_conditions=["Fast MA crosses above slow MA"],
        exit_conditions=["Fast MA crosses below slow MA"],
        target_return=0.15,
        max_drawdown=0.20,
        position_size=0.10,
        max_positions=5,
        backtest_start="2018-01-01",
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
        initial_parameters={"fast_window": 20},
        parameter_bounds={"fast_window": (5, 50)},
        aurora_config_file="/tmp/config.yaml",
        build_log=["build complete"],
    )
    params.update(overrides)
    return BuildResult(**params)


# ---------------------------------------------------------------------------
# LeakageVerdict, CPCVResult, ReviewVerdict
# ---------------------------------------------------------------------------


class TestAuroraDataclasses:
    def test_leakage_verdict_defaults(self):
        v = LeakageVerdict(status="CLEAN")
        assert v.status == "CLEAN"
        assert v.details == ""

    def test_cpcv_result_fields(self):
        r = CPCVResult(mean_sharpe=0.8, dsr=0.6, overfitting_probability=0.2, n_splits=6)
        assert r.mean_sharpe == 0.8
        assert r.dsr == 0.6
        assert r.path_distribution == {}

    def test_review_verdict_approved(self):
        v = ReviewVerdict(status="APPROVED", details="All gates passed")
        assert v.status == "APPROVED"
        assert v.details == "All gates passed"


# ---------------------------------------------------------------------------
# PipelineResult
# ---------------------------------------------------------------------------


class TestPipelineResult:
    def test_serialize_deserialize_roundtrip(self):
        now = datetime(2025, 6, 1, 12, 0, 0, tzinfo=timezone.utc)
        result = PipelineResult(
            pipeline_id="pipe-123",
            spec_id="spec-456",
            cycle_number=2,
            status="DEPLOYED_PAPER",
            run_dir="/tmp/runs/pipe-123",
            leakage_verdict="CLEAN",
            review_board_status="APPROVED",
            cpcv_summary={"mean_sharpe": 0.6, "dsr": 0.4, "overfitting_probability": 0.3},
            backtest_metrics={"mean_sharpe": 0.6},
            paper_deployment_id="deploy-789",
            created_at=now,
        )
        json_str = result.to_json()
        restored = PipelineResult.from_json(json_str)
        assert restored.pipeline_id == "pipe-123"
        assert restored.spec_id == "spec-456"
        assert restored.cycle_number == 2
        assert restored.status == "DEPLOYED_PAPER"
        assert restored.created_at == now
        assert restored.cpcv_summary["mean_sharpe"] == 0.6

    def test_contains_disclaimer(self):
        result = PipelineResult(pipeline_id="p1", spec_id="s1", status="PASSED")
        assert result.disclaimer == RUNNER_DISCLAIMER

    def test_disclaimer_in_json(self):
        result = PipelineResult(pipeline_id="p1", spec_id="s1", status="PASSED")
        json_str = result.to_json()
        data = json.loads(json_str)
        assert "disclaimer" in data
        assert "profitability" in data["disclaimer"]

    def test_auto_generates_created_at(self):
        result = PipelineResult(pipeline_id="p1", spec_id="s1", status="PASSED")
        assert isinstance(result.created_at, datetime)

    def test_default_fields(self):
        result = PipelineResult(pipeline_id="p1", spec_id="s1", status="PASSED")
        assert result.cycle_number == 0
        assert result.leakage_verdict is None
        assert result.review_board_status is None
        assert result.paper_deployment_id is None
        assert result.error is None


# ---------------------------------------------------------------------------
# PipelineEventBus
# ---------------------------------------------------------------------------


class TestPipelineEventBus:
    def test_emit_calls_subscribed_handler(self):
        bus = PipelineEventBus()
        received: list = []

        def handler(event: str, data: dict):
            received.append((event, data))

        bus.subscribe(handler)
        bus.emit("pipeline.started", {"cycle": 1})
        assert len(received) == 1
        assert received[0][0] == "pipeline.started"
        assert received[0][1]["cycle"] == 1

    def test_multiple_handlers_called(self):
        bus = PipelineEventBus()
        calls: list = []

        def h1(e, d):
            calls.append(("h1", e))

        def h2(e, d):
            calls.append(("h2", e))

        bus.subscribe(h1)
        bus.subscribe(h2)
        bus.emit("test_event")
        assert len(calls) == 2

    def test_get_history_records_events(self):
        bus = PipelineEventBus()
        bus.emit("event_a", {"x": 1})
        bus.emit("event_b", {"y": 2})
        history = bus.get_history()
        assert len(history) == 2
        assert history[0]["event"] == "event_a"
        assert history[0]["data"]["x"] == 1
        assert history[1]["event"] == "event_b"

    def test_emit_without_data(self):
        bus = PipelineEventBus()
        bus.emit("no_data")
        history = bus.get_history()
        assert history[0]["data"] == {}

    def test_clear_history(self):
        bus = PipelineEventBus()
        bus.emit("e1")
        bus.emit("e2")
        assert len(bus.get_history()) == 2
        bus.clear_history()
        assert len(bus.get_history()) == 0

    def test_history_is_copy(self):
        bus = PipelineEventBus()
        bus.emit("e1")
        hist = bus.get_history()
        hist.append({"event": "fake"})
        assert len(bus.get_history()) == 1


# ---------------------------------------------------------------------------
# AuroraBridge
# ---------------------------------------------------------------------------


class TestAuroraBridge:
    def test_initializes_with_data_dir(self):
        bridge = AuroraBridge(data_dir="/tmp/aurora_data")
        assert bridge.data_dir == "/tmp/aurora_data"

    def test_check_available_returns_true_with_backtest_engine(self):
        bridge = AuroraBridge()
        assert bridge.check_available() is True

    def test_download_data_works_without_aurora(self):
        bridge = AuroraBridge()
        key = bridge.download_data(symbols=["SPY"], start="2020-01-01", end="2023-12-31", source="yfinance")
        assert key == "yfinance_SPY_2020-01-01_2023-12-31"
        cached = bridge.get_cached_data(key)
        assert cached is not None
        assert "SPY" in cached

    def test_download_data_caches_results(self):
        bridge = AuroraBridge()
        key = bridge.download_data(symbols=["AAPL"], start="2020-01-01", end="2020-01-10", source="yfinance")
        cached = bridge.get_cached_data(key)
        assert cached is not None
        assert isinstance(cached["AAPL"], pd.DataFrame)
        assert not cached["AAPL"].empty

    def test_get_cached_data_returns_none_for_missing_key(self):
        bridge = AuroraBridge()
        assert bridge.get_cached_data("nonexistent") is None

    def test_builtin_engine_produces_leakage_verdict(self):
        bridge = AuroraBridge()
        verdict = bridge.run_leakage_detection()
        assert verdict.status in ("CLEAN", "SUSPECT", "COMPROMISED")

    def test_builtin_engine_produces_cpcv_result(self):
        bridge = AuroraBridge()
        result = bridge.run_cpcv_backtest()
        assert hasattr(result, "mean_sharpe")
        assert hasattr(result, "dsr")

    def test_builtin_engine_produces_review_verdict(self):
        bridge = AuroraBridge()
        verdict = bridge.run_review_board()
        assert verdict.status in ("APPROVED", "REJECTED", "NEEDS_MORE_RESEARCH")


# ---------------------------------------------------------------------------
# PipelineRunner
# ---------------------------------------------------------------------------


class MockAuroraBridge:
    """A mock AuroraBridge that returns deterministic results."""

    def __init__(self):
        self.check_available_calls = 0
        self.download_data_calls = []
        self.run_leakage_detection_calls = []
        self.build_features_calls = []
        self.generate_signals_calls = []
        self.run_cpcv_backtest_calls = []
        self.run_review_board_calls = []
        self.available = True
        self.leakage_verdict = "CLEAN"
        self.review_verdict = "APPROVED"
        self._data_cache: dict[str, dict[str, pd.DataFrame]] = {}

    def check_available(self) -> bool:
        self.check_available_calls += 1
        return self.available

    def download_data(self, symbols, start, end, source="yfinance"):
        self.download_data_calls.append((symbols, start, end, source))
        key = f"{source}_{'_'.join(symbols)}_{start}_{end}"
        return key

    def get_cached_data(self, key: str) -> dict[str, pd.DataFrame] | None:
        return self._data_cache.get(key)

    def run_leakage_detection(self, feature_key="", label_key=""):
        self.run_leakage_detection_calls.append((feature_key, label_key))
        return LeakageVerdict(status=self.leakage_verdict, details="mock verdict")

    def build_features(self, cache_key):
        self.build_features_calls.append(cache_key)
        return f"features_{cache_key}"

    def generate_signals(self, strategy_file="", config_file="", features_key=""):
        self.generate_signals_calls.append((strategy_file, config_file, features_key))
        return f"signals_{features_key}"

    def run_cpcv_backtest(self, signals_key="", n_splits=6, n_test_splits=2, purge_days=21, embargo_days=5, transaction_cost=0.0, portfolio_weights=None):
        self.run_cpcv_backtest_calls.append((signals_key, n_splits))
        return CPCVResult(
            mean_sharpe=0.55,
            dsr=0.42,
            overfitting_probability=0.35,
            n_splits=n_splits,
            path_distribution={"mean": 0.55, "std": 0.18},
        )

    def run_review_board(self, run_dir="", cpcv_result=None):
        self.run_review_board_calls.append((run_dir, cpcv_result))
        return ReviewVerdict(status=self.review_verdict, details="mock review")


class TestPipelineRunner:
    def _make_runner(self, **kwargs) -> PipelineRunner:
        defaults = dict(
            llm_provider=MagicMock(spec=LLMProvider),
            alpaca_paper_key="test",
            alpaca_paper_secret="test",
            alpaca_base_url="https://paper-api.alpaca.markets",
            build_dir="/tmp/astra",
        )
        defaults.update(kwargs)
        return PipelineRunner(**defaults)

    def test_initializes_with_required_params(self):
        runner = self._make_runner()
        assert runner._max_optimization_cycles == 10

    def test_initializes_with_custom_max_cycles(self):
        runner = self._make_runner(max_optimization_cycles=5)
        assert runner._max_optimization_cycles == 5

    def test_run_returns_passed_when_aurora_available(self):
        mock_bridge = MockAuroraBridge()
        runner = self._make_runner(aurora_bridge=mock_bridge)
        spec = _make_spec()
        build_result = _make_build_result(spec)
        result = runner.run(build_result, spec)

        assert result.status == "DEPLOYED_PAPER"
        assert result.leakage_verdict == "CLEAN"
        assert result.review_board_status == "APPROVED"
        assert result.paper_deployment_id is not None
        assert result.error is None

    def test_run_succeeds_with_builtin_engine(self):
        """Pipeline runner now succeeds even without AURORA (uses BacktestEngine)."""
        mock_bridge = MockAuroraBridge()
        mock_bridge.available = False
        runner = self._make_runner(aurora_bridge=mock_bridge)
        spec = _make_spec()
        build_result = _make_build_result(spec)
        result = runner.run(build_result, spec)

        assert result.status == "DEPLOYED_PAPER"

    def test_run_fails_on_leakage_compromised(self):
        mock_bridge = MockAuroraBridge()
        mock_bridge.leakage_verdict = "COMPROMISED"
        runner = self._make_runner(aurora_bridge=mock_bridge)
        spec = _make_spec()
        build_result = _make_build_result(spec)
        result = runner.run(build_result, spec)

        assert result.status == "FAILED_LEAKAGE"
        assert "COMPROMISED" in result.leakage_verdict.upper() or "blocked" in (result.error or "").lower()

    def test_run_fails_on_review_rejected(self):
        mock_bridge = MockAuroraBridge()
        mock_bridge.review_verdict = "REJECTED"
        runner = self._make_runner(aurora_bridge=mock_bridge)
        spec = _make_spec()
        build_result = _make_build_result(spec)
        result = runner.run(build_result, spec)

        assert result.status == "FAILED_BACKTEST"
        assert "REJECTED" in (result.review_board_status or "")

    def test_run_populates_cpcv_summary(self):
        mock_bridge = MockAuroraBridge()
        runner = self._make_runner(aurora_bridge=mock_bridge)
        spec = _make_spec()
        build_result = _make_build_result(spec)
        result = runner.run(build_result, spec)

        assert result.cpcv_summary is not None
        assert "mean_sharpe" in result.cpcv_summary
        assert "dsr" in result.cpcv_summary
        assert "overfitting_probability" in result.cpcv_summary

    @patch("astra.pipeline.runner.StrategyGenerator")
    def test_run_optimization_cycle_increments_cycle(self, MockGen):
        mock_bridge = MockAuroraBridge()

        mock_gen_instance = MagicMock()
        MockGen.return_value = mock_gen_instance
        mock_gen_instance.generate.return_value = _make_build_result(
            _make_spec(), success=True
        )

        runner = self._make_runner(aurora_bridge=mock_bridge)
        spec = _make_spec()
        build_result = _make_build_result(spec)
        result = runner.run_optimization_cycle(
            build_result, spec, {"fast_window": 30}
        )

        assert result.cycle_number >= 1

    @patch("astra.pipeline.runner.StrategyGenerator")
    def test_optimization_cycle_rebuild_failure(self, MockGen):
        mock_bridge = MockAuroraBridge()

        mock_gen_instance = MagicMock()
        MockGen.return_value = mock_gen_instance
        mock_gen_instance.generate.return_value = _make_build_result(
            _make_spec(), success=False, error="Build failed"
        )

        runner = self._make_runner(aurora_bridge=mock_bridge)
        spec = _make_spec()
        build_result = _make_build_result(spec)
        result = runner.run_optimization_cycle(
            build_result, spec, {"fast_window": 30}
        )

        assert result.status == "ERROR"
        assert "Build failed" in (result.error or "")

    def test_runner_creates_event_bus_by_default(self):
        runner = self._make_runner()
        assert runner._event_bus is not None

    def test_runner_accepts_external_event_bus(self):
        bus = PipelineEventBus()
        runner = self._make_runner(event_bus=bus)
        assert runner._event_bus is bus


# ---------------------------------------------------------------------------
# PipelineState
# ---------------------------------------------------------------------------


class TestPipelineState:
    def test_auto_generates_session_id(self):
        state = PipelineState()
        assert state.session_id != ""
        uuid.UUID(state.session_id)

    def test_initial_status_is_planning(self):
        state = PipelineState()
        assert state.status == "PLANNING"

    def test_valid_transition(self):
        state = PipelineState(status="PLANNING")
        state.transition_to("BUILDING")
        assert state.status == "BUILDING"

    def test_save_and_load_roundtrip(self, tmp_path):
        spec = _make_spec()
        build_result = _make_build_result(spec)
        result = PipelineResult(
            pipeline_id="p1", spec_id=spec.spec_id, status="DEPLOYED_PAPER"
        )

        state = PipelineState(
            session_id="session-test-123",
            spec=spec,
            build_result=build_result,
            pipeline_results=[result],
            current_cycle=2,
            status="PAPER_TRADING",
        )
        path = str(tmp_path / "state.json")
        state.save(path)

        loaded = PipelineState.load(path)
        assert loaded.session_id == "session-test-123"
        assert loaded.status == "PAPER_TRADING"
        assert loaded.current_cycle == 2
        assert loaded.spec is not None
        assert loaded.spec.spec_id == spec.spec_id
        assert loaded.build_result is not None
        assert loaded.build_result.spec_id == spec.spec_id
        assert len(loaded.pipeline_results) == 1
        assert loaded.pipeline_results[0].pipeline_id == "p1"

    def test_latest_result_returns_none_when_empty(self):
        state = PipelineState()
        assert state.latest_result() is None

    def test_latest_result_returns_last(self):
        r1 = PipelineResult(pipeline_id="p1", spec_id="s1", status="PASSED")
        r2 = PipelineResult(pipeline_id="p2", spec_id="s1", status="DEPLOYED_PAPER")
        state = PipelineState(pipeline_results=[r1, r2])
        assert state.latest_result().pipeline_id == "p2"

    def test_has_graduated_false_by_default(self):
        state = PipelineState()
        assert state.has_graduated() is False

    def test_has_graduated_true_when_set(self):
        state = PipelineState(graduation_result={"sharpe": 1.2, "status": "GRADUATED"})
        assert state.has_graduated() is True

    def test_cycle_history_summary_structure(self):
        r1 = PipelineResult(
            pipeline_id="p1",
            spec_id="s1",
            cycle_number=0,
            status="PASSED",
            cpcv_summary={"mean_sharpe": 0.5, "dsr": 0.3},
        )
        r2 = PipelineResult(
            pipeline_id="p2",
            spec_id="s1",
            cycle_number=1,
            status="DEPLOYED_PAPER",
            cpcv_summary={"mean_sharpe": 0.7, "dsr": 0.5},
            paper_deployment_id="deploy-1",
        )
        state = PipelineState(pipeline_results=[r1, r2])
        history = state.cycle_history_summary()

        assert len(history) == 2
        assert history[0]["cycle"] == 0
        assert history[0]["status"] == "PASSED"
        assert history[0]["sharpe"] == 0.5
        assert history[0]["deployed"] is False
        assert history[1]["cycle"] == 1
        assert history[1]["sharpe"] == 0.7
        assert history[1]["dsr"] == 0.5
        assert history[1]["deployed"] is True

    def test_disclaimer_in_state(self):
        state = PipelineState()
        assert "profitability" in state.disclaimer

    # Status transition validation

    def test_invalid_transition_raises(self):
        state = PipelineState(status="GRADUATED")
        with pytest.raises(InvalidStatusTransition) as exc:
            state.transition_to("RUNNING")
        assert "Cannot transition" in str(exc.value)

    def test_invalid_transition_from_abandoned(self):
        state = PipelineState(status="ABANDONED")
        with pytest.raises(InvalidStatusTransition):
            state.transition_to("RUNNING")

    def test_valid_transition_planning_to_building(self):
        state = PipelineState(status="PLANNING")
        state.transition_to("BUILDING")
        assert state.status == "BUILDING"

    def test_valid_transition_building_to_running(self):
        state = PipelineState(status="BUILDING")
        state.transition_to("RUNNING")
        assert state.status == "RUNNING"

    def test_valid_transition_running_to_optimizing(self):
        state = PipelineState(status="RUNNING")
        state.transition_to("OPTIMIZING")
        assert state.status == "OPTIMIZING"

    def test_valid_transition_optimizing_to_graduated(self):
        state = PipelineState(status="OPTIMIZING")
        state.transition_to("GRADUATED")
        assert state.status == "GRADUATED"

    def test_valid_transition_paper_trading_to_graduated(self):
        state = PipelineState(status="PAPER_TRADING")
        state.transition_to("GRADUATED")
        assert state.status == "GRADUATED"

    def test_updated_at_changes_on_transition(self):
        state = PipelineState(status="PLANNING")
        old = state.updated_at
        state.transition_to("BUILDING")
        assert state.updated_at > old

    def test_empty_cycle_history_summary(self):
        state = PipelineState()
        assert state.cycle_history_summary() == []
