"""Integration tests for the full pipeline — Builder → PipelineRunner → Export."""

import os
import tempfile
import uuid
from unittest.mock import MagicMock, patch

import pandas as pd
import pytest

from astra.llm.provider import LLMProvider
from astra.planner.spec import StrategySpec
from astra.builder.generator import StrategyGenerator, BuildResult
from astra.pipeline.runner import PipelineRunner
from astra.pipeline.events import PipelineEventBus
from astra.pipeline.aurora_bridge import AuroraBridge


def _make_spec(**overrides) -> StrategySpec:
    params = dict(
        spec_id=str(uuid.uuid4()),
        user_idea="Test",
        asset_class="equity",
        symbols=["SPY"],
        timeframe="daily",
        data_source="yfinance",
        strategy_type="trend_following",
        market_hypothesis="Moving average crossovers capture trends",
        entry_conditions=["Test entry"],
        exit_conditions=["Test exit"],
        target_return=0.15,
        max_drawdown=0.20,
        position_size=0.10,
        max_positions=5,
        backtest_start="2020-01-01",
        backtest_end="2023-12-31",
        transaction_cost=0.001,
    )
    params.update(overrides)
    return StrategySpec(**params)


@pytest.fixture
def mock_llm():
    provider = MagicMock(spec=LLMProvider)
    provider.generate.return_value = '{"fast_window": 20, "slow_window": 50, "signal_threshold": 0.02}'
    return provider


@pytest.fixture
def mock_aurora():
    bridge = MagicMock(spec=AuroraBridge)

    bridge.check_available.return_value = True
    bridge.download_data.return_value = "data_key_1"

    n = 500
    dates = pd.date_range("2020-01-01", periods=n, freq="D")
    rng = pd.DataFrame({
        "close": 100 + pd.Series(pd.Series(range(n)).ewm(span=50).mean() * 0.1 + 5).values,
        "open": 100 + pd.Series(pd.Series(range(n)).ewm(span=50).mean() * 0.1 + 5).values,
        "high": 100 + pd.Series(pd.Series(range(n)).ewm(span=50).mean() * 0.1 + 5 + 0.5).values,
        "low": 100 + pd.Series(pd.Series(range(n)).ewm(span=50).mean() * 0.1 + 5 - 0.5).values,
        "volume": 1000000,
    }, index=dates)

    bridge.get_cached_data.return_value = {"SPY": rng}
    bridge.build_features.return_value = "features_key_1"
    bridge.get_cached_features.return_value = {"SPY": rng}
    bridge.generate_signals.return_value = "signals_key_1"
    bridge.get_cached_signals.return_value = {"SPY": pd.Series(1, index=rng.index)}

    from astra.pipeline.aurora_bridge import LeakageVerdict, CPCVResult, ReviewVerdict
    bridge.run_leakage_detection.return_value = LeakageVerdict(status="CLEAN")
    bridge.run_cpcv_backtest.return_value = CPCVResult(
        mean_sharpe=2.0,
        dsr=1.6,
        overfitting_probability=0.05,
        n_splits=6,
        sharpe_per_path=[1.8, 2.1, 2.0],
        max_drawdown=0.08,
        annualized_return=0.15,
        n_trades=30,
        win_rate=0.60,
    )
    bridge.run_review_board.return_value = ReviewVerdict(status="APPROVED")
    return bridge


class TestFullPipelineIntegration:
    def test_builder_produces_valid_strategy(self, mock_llm, tmp_path):
        spec = _make_spec()
        gen = StrategyGenerator(llm_provider=mock_llm, build_dir=str(tmp_path))
        result = gen.generate(spec)
        assert result.success, f"Build failed: {result.error}"
        assert result.strategy_file is not None
        assert os.path.exists(result.strategy_file)
        assert "TrendFollowingStrategy" in result.strategy_class_name
        assert "fast_window" in result.initial_parameters
        assert "slow_window" in result.parameter_bounds

    def test_builder_llm_failure_falls_back_to_defaults(self, mock_llm, tmp_path):
        mock_llm.generate.side_effect = Exception("API error")
        spec = _make_spec()
        gen = StrategyGenerator(llm_provider=mock_llm, build_dir=str(tmp_path))
        result = gen.generate(spec)
        assert result.success
        assert result.initial_parameters["fast_window"] == 20

    @patch.dict(os.environ, {"APCA_API_KEY_ID": "test_key", "APCA_API_SECRET_KEY": "test_secret"})
    def test_pipeline_runner_executes_successfully(self, mock_aurora, mock_llm, tmp_path):
        spec = _make_spec()
        result = BuildResult(
            success=True,
            spec_id=spec.spec_id,
            strategy_file=os.path.join(str(tmp_path), "strat.py"),
            strategy_class_name="TrendFollowingStrategy",
            initial_parameters={"fast_window": 20, "slow_window": 50},
            parameter_bounds={"fast_window": (5, 50), "slow_window": (20, 200)},
            build_log=["Build completed"],
        )

        with open(result.strategy_file, "w") as f:
            f.write('"""Test."""\nimport pandas\ndef generate_signals(data):\n    return pd.Series(1, index=data.index)\n')

        event_bus = PipelineEventBus()
        events_log = []
        event_bus.subscribe(lambda e, d: events_log.append(e))

        runner = PipelineRunner(
            llm_provider=mock_llm,
            alpaca_paper_key="test_key",
            alpaca_paper_secret="test_secret",
            alpaca_base_url="https://paper-api.alpaca.markets",
            build_dir=str(tmp_path),
            aurora_bridge=mock_aurora,
            event_bus=event_bus,
        )

        pipeline_result = runner.run(result, spec)
        assert pipeline_result.status == "DEPLOYED_PAPER"
        assert pipeline_result.leakage_verdict == "CLEAN"
        assert pipeline_result.review_board_status == "APPROVED"
        assert pipeline_result.paper_deployment_id is not None

        assert pipeline_result.cpcv_summary is not None
        assert pipeline_result.cpcv_summary["mean_sharpe"] == 2.0
        assert pipeline_result.cpcv_summary["annualized_return"] == 0.15
        assert pipeline_result.cpcv_summary["win_rate"] == 0.60
        assert pipeline_result.cpcv_summary["n_trades"] == 30

        assert pipeline_result.backtest_metrics is not None
        assert pipeline_result.backtest_metrics["mean_sharpe"] == 2.0
        assert pipeline_result.backtest_metrics["max_drawdown"] == 0.08

        assert "pipeline.started" in events_log
        assert "pipeline.backtest_complete" in events_log
        assert "pipeline.paper_deployed" in events_log

    def test_pipeline_fails_on_leakage(self, mock_aurora, mock_llm, tmp_path):
        from astra.pipeline.aurora_bridge import LeakageVerdict
        mock_aurora.run_leakage_detection.return_value = LeakageVerdict(status="COMPROMISED", details="Look-ahead bias detected")

        spec = _make_spec()
        result = BuildResult(
            success=True,
            spec_id=spec.spec_id,
            strategy_file=os.path.join(str(tmp_path), "strat.py"),
            strategy_class_name="TrendFollowingStrategy",
            initial_parameters={"fast_window": 20},
            parameter_bounds={"fast_window": (5, 50)},
            build_log=[],
        )

        with open(result.strategy_file, "w") as f:
            f.write('"""Test."""\nimport pandas\ndef generate_signals(data):\n    return pd.Series(1, index=data.index)\n')

        runner = PipelineRunner(
            llm_provider=mock_llm,
            alpaca_paper_key="test",
            alpaca_paper_secret="test",
            alpaca_base_url="https://paper-api.alpaca.markets",
            build_dir=str(tmp_path),
            aurora_bridge=mock_aurora,
        )

        pipeline_result = runner.run(result, spec)
        assert pipeline_result.status == "FAILED_LEAKAGE"
        assert "Look-ahead bias" in (pipeline_result.error or "")

    def test_optimization_cycle_updates_cycle_number(self, mock_aurora, mock_llm, tmp_path):
        spec = _make_spec()
        result = BuildResult(
            success=True,
            spec_id=spec.spec_id,
            strategy_file=os.path.join(str(tmp_path), "strat.py"),
            strategy_class_name="TrendFollowingStrategy",
            initial_parameters={"fast_window": 20},
            parameter_bounds={"fast_window": (5, 50)},
            build_log=[],
        )

        with open(result.strategy_file, "w") as f:
            f.write('"""Test."""\nimport pandas\ndef generate_signals(data):\n    return pd.Series(1, index=data.index)\n')

        runner = PipelineRunner(
            llm_provider=mock_llm,
            alpaca_paper_key="test",
            alpaca_paper_secret="test",
            alpaca_base_url="https://paper-api.alpaca.markets",
            build_dir=str(tmp_path),
            aurora_bridge=mock_aurora,
        )

        pipeline_result = runner.run_optimization_cycle(
            build_result=result,
            spec=spec,
            updated_parameters={"fast_window": 15},
        )
        assert pipeline_result.cycle_number == 1
        assert pipeline_result.status == "DEPLOYED_PAPER"

    def test_export_package_from_pipeline_result(self, mock_aurora, mock_llm, tmp_path):
        from astra.graduation import (
            GraduationCertificate, GraduationGates, GateCheckResult, GateResult,
        )
        from astra.alpaca.monitor import PerformanceSnapshot, DegradationReport
        from astra.export.packager import StrategyPackager

        spec = _make_spec()
        result = BuildResult(
            success=True,
            spec_id=spec.spec_id,
            strategy_file=os.path.join(str(tmp_path), "strat.py"),
            strategy_class_name="TrendFollowingStrategy",
            initial_parameters={"fast_window": 20, "slow_window": 50},
            parameter_bounds={"fast_window": (5, 50), "slow_window": (20, 200)},
            build_log=["Build completed"],
        )

        with open(result.strategy_file, "w") as f:
            f.write('"""Test."""\nfrom abc import ABC, abstractmethod\nimport pandas as pd\n\nclass BaseStrategy(ABC):\n    STRATEGY_TYPE="trend_following"\n    @abstractmethod\n    def generate_signals(self, data):\n        ...\n\nclass TrendFollowingStrategy(BaseStrategy):\n    STRATEGY_TYPE="trend_following"\n    def __init__(self, fast_window=20, slow_window=50):\n        self.fast_window = fast_window\n        self.slow_window = slow_window\n    def generate_signals(self, data):\n        fast = data["close"].rolling(self.fast_window).mean()\n        slow = data["close"].rolling(self.slow_window).mean()\n        return (fast > slow).astype(int)\n    def get_parameters(self):\n        return {"fast_window": self.fast_window, "slow_window": self.slow_window}\n    def get_parameter_bounds(self):\n        return {"fast_window": (5, 50), "slow_window": (20, 200)}\n')

        runner = PipelineRunner(
            llm_provider=mock_llm,
            alpaca_paper_key="test",
            alpaca_paper_secret="test",
            alpaca_base_url="https://paper-api.alpaca.markets",
            build_dir=str(tmp_path),
            aurora_bridge=mock_aurora,
        )
        pipeline_result = runner.run(result, spec)

        snapshot = PerformanceSnapshot(
            deployment_id=pipeline_result.paper_deployment_id or "unknown",
            total_return=0.05,
            annualized_return=0.08,
            sharpe_ratio=0.6,
            max_drawdown=0.12,
            win_rate=0.55,
            total_trades=30,
            days_deployed=20,
            degradation_report=DegradationReport(category="ACCEPTABLE"),
        )

        gates = GraduationGates()
        gate_result = gates.check(snapshot, pipeline_result)
        tracker = __import__("astra.graduation.tracker", fromlist=["GraduationTracker"]).GraduationTracker(session_id="test")
        tracker.record_check(0, gate_result)
        cert = tracker.issue_certificate(
            snapshot=snapshot,
            pipeline_result=pipeline_result,
            optimization_cycles=3,
            gate_result=gate_result,
        )

        export_dir = str(tmp_path / "exports")
        packager = StrategyPackager(export_dir=export_dir)
        pkg = packager.package(
            build_result=result,
            spec=spec,
            certificate=cert,
            pipeline_result=pipeline_result,
            snapshot=snapshot,
        )

        assert pkg.export_id is not None
        assert os.path.exists(pkg.strategy_file)
        with open(pkg.strategy_file) as f:
            content = f.read()
        assert "GRADUATION CERTIFICATE" in content
        assert "STRATEGY_METADATA" in content
        assert "disclaimer" in content.lower()
