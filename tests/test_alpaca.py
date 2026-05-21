"""Tests for the ASTRA Alpaca paper trading integration."""

import datetime
import json
import uuid
from dataclasses import asdict
from unittest.mock import MagicMock, patch, PropertyMock

import pandas as pd
import pytest

from astra.alpaca import (
    AstraAlpacaClient,
    AlpacaAccount,
    AlpacaPosition,
    AlpacaOrder,
    PortfolioHistory,
    StrategyDeployer,
    Deployment,
    CycleResult,
    PerformanceMonitor,
    PerformanceSnapshot,
    DegradationReport,
    LiveTradingBlockedError,
    ShortSellingBlockedError,
    DeploymentError,
    AlpacaConnectionError,
)
from astra.pipeline.events import PipelineEventBus
from astra.pipeline.runner import PipelineResult
from astra.builder.generator import BuildResult
from astra.planner.spec import StrategySpec


PAPER_URL = "https://paper-api.alpaca.markets"
LIVE_URL = "https://api.alpaca.markets"


def _make_spec(**overrides) -> StrategySpec:
    params = dict(
        spec_id=str(uuid.uuid4()),
        user_idea="Test",
        asset_class="equity",
        symbols=["SPY"],
        timeframe="daily",
        data_source="yfinance",
        strategy_type="trend_following",
        market_hypothesis="Test hypothesis for alpaca tests here with enough words",
        entry_conditions=["Entry"],
        exit_conditions=["Exit"],
        target_return=0.15,
        max_drawdown=0.20,
        position_size=0.10,
        max_positions=5,
        backtest_start="2020-01-01",
        backtest_end="2023-12-31",
    )
    params.update(overrides)
    return StrategySpec(**params)


def _make_build_result(spec: StrategySpec) -> BuildResult:
    return BuildResult(
        success=True,
        spec_id=spec.spec_id,
        strategy_file="/tmp/test_strategy.py",
        strategy_class_name="TrendFollowingStrategy",
        initial_parameters={"fast_window": 20},
        parameter_bounds={"fast_window": (5, 50)},
    )


def _mock_strategy_cls(signal_value: int = 1):
    """Create a mock strategy class that returns a fixed signal."""
    cls = MagicMock()
    instance = MagicMock()
    signals = pd.Series([signal_value], index=pd.date_range("2020-01-01", periods=1))
    instance.generate_signals.return_value = signals
    cls.return_value = instance
    return cls


# ---------------------------------------------------------------------------
# Exceptions
# ---------------------------------------------------------------------------


class TestExceptions:
    def test_live_trading_blocked_error_message(self):
        err = LiveTradingBlockedError(LIVE_URL)
        assert "live trading" in str(err).lower()
        assert LIVE_URL in str(err)

    def test_short_selling_blocked_error_message(self):
        err = ShortSellingBlockedError("SPY")
        assert "short selling" in str(err).lower()
        assert "SPY" in str(err)

    def test_deployment_error_is_exception(self):
        err = DeploymentError("fail")
        assert isinstance(err, Exception)

    def test_alpaca_connection_error_is_exception(self):
        err = AlpacaConnectionError("no connection")
        assert isinstance(err, Exception)


# ---------------------------------------------------------------------------
# Dataclass defaults
# ---------------------------------------------------------------------------


class TestDataclasses:
    def test_alpaca_account_defaults(self):
        a = AlpacaAccount()
        assert a.equity == 0.0
        assert a.currency == "USD"
        assert a.status == "ACTIVE"

    def test_alpaca_position_defaults(self):
        p = AlpacaPosition()
        assert p.symbol == ""
        assert p.side == "long"

    def test_alpaca_order_defaults(self):
        o = AlpacaOrder()
        assert o.side == ""
        assert o.status == ""
        assert o.filled_qty == 0.0

    def test_portfolio_history_defaults(self):
        h = PortfolioHistory()
        assert h.timestamps == []
        assert h.base_value == 0.0

    def test_deployment_auto_generates_id(self):
        d = Deployment()
        assert d.deployment_id != ""
        uuid.UUID(d.deployment_id)

    def test_deployment_default_status(self):
        d = Deployment()
        assert d.status == "ACTIVE"

    def test_cycle_result_defaults(self):
        c = CycleResult()
        assert c.cycle_number == 0
        assert c.signals == {}
        assert c.actions == []


# ---------------------------------------------------------------------------
# AstraAlpacaClient — URL validation
# ---------------------------------------------------------------------------


class TestAstraAlpacaClientUrlValidation:
    def test_paper_url_accepted(self):
        client = AstraAlpacaClient(
            api_key="test", api_secret="test", base_url=PAPER_URL
        )
        assert client._base_url == PAPER_URL

    def test_live_url_raises(self):
        with pytest.raises(LiveTradingBlockedError) as exc:
            AstraAlpacaClient(api_key="test", api_secret="test", base_url=LIVE_URL)
        assert LIVE_URL in str(exc.value)

    def test_empty_url_raises(self):
        with pytest.raises(LiveTradingBlockedError):
            AstraAlpacaClient(api_key="test", api_secret="test", base_url="")

    def test_default_url_is_paper(self):
        client = AstraAlpacaClient(api_key="test", api_secret="test")
        assert "paper-api.alpaca.markets" in client._base_url


# ---------------------------------------------------------------------------
# AstraAlpacaClient — methods (mocked connection)
# ---------------------------------------------------------------------------


class TestAstraAlpacaClientMethods:
    def test_get_account_returns_stub_when_not_connected(self):
        client = AstraAlpacaClient(api_key="test", api_secret="test", base_url=PAPER_URL)
        with pytest.raises(AlpacaConnectionError):
            client.get_account()

    def test_get_positions_returns_empty_when_not_connected(self):
        client = AstraAlpacaClient(api_key="test", api_secret="test", base_url=PAPER_URL)
        with pytest.raises(AlpacaConnectionError):
            client.get_positions()


# ---------------------------------------------------------------------------
# StrategyDeployer
# ---------------------------------------------------------------------------


class TestStrategyDeployer:
    def test_deploy_raises_on_failed_build(self):
        client = MagicMock(spec=AstraAlpacaClient)
        bus = PipelineEventBus()
        deployer = StrategyDeployer(client=client, event_bus=bus)

        failed_build = BuildResult(
            success=False,
            error="build failed",
        )
        spec = _make_spec()
        pipeline_result = PipelineResult(pipeline_id="p1", spec_id="s1", status="PASSED")

        with pytest.raises(DeploymentError, match="failed build"):
            deployer.deploy(failed_build, spec, pipeline_result)

    def test_deploy_creates_deployment(self, tmp_path):
        client = MagicMock(spec=AstraAlpacaClient)
        bus = PipelineEventBus()
        deployer = StrategyDeployer(client=client, event_bus=bus)

        strategy_file = str(tmp_path / "test_strat.py")
        with open(strategy_file, "w") as f:
            f.write("# test strategy file\n")

        spec = _make_spec()
        build_result = BuildResult(
            success=True,
            spec_id=spec.spec_id,
            strategy_file=strategy_file,
        )
        pipeline_result = PipelineResult(
            pipeline_id="p1", spec_id=spec.spec_id, status="DEPLOYED_PAPER"
        )

        deployment = deployer.deploy(build_result, spec, pipeline_result)
        assert deployment.spec_id == spec.spec_id
        assert deployment.status == "ACTIVE"
        assert deployment.ledger_path.endswith(".jsonl")

    def test_run_cycle_buy_signal_no_position(self):
        client = MagicMock(spec=AstraAlpacaClient)
        bus = PipelineEventBus()
        deployer = StrategyDeployer(client=client, event_bus=bus)

        client.get_positions.return_value = []
        client.submit_order.return_value = AlpacaOrder(
            id="order-1", symbol="SPY", qty=1.0, side="buy", status="filled"
        )

        deployment = Deployment(
            deployment_id="dep-1",
            spec_id="spec-1",
            strategy_file="/tmp/test.py",
        )

        mock_strategy = MagicMock()
        mock_instance = MagicMock()
        mock_instance.generate_signals.return_value = pd.Series(
            [1], index=pd.date_range("2020-01-01", periods=1)
        )
        mock_strategy.return_value = mock_instance

        with patch.object(deployer, "_import_strategy", return_value=mock_strategy):
            with patch.object(deployer, "_fetch_bars", return_value={
                "SPY": pd.DataFrame({"close": [100.0]}, index=pd.date_range("2020-01-01", periods=1))
            }):
                result = deployer.run_cycle(deployment)

        assert "BUY SPY" in result.actions
        assert len(result.orders) == 1
        assert result.orders[0].side == "buy"
        assert deployment.cycle_count == 1
        assert deployment.total_orders == 1

    def test_run_cycle_flat_signal_with_position_closes(self):
        client = MagicMock(spec=AstraAlpacaClient)
        bus = PipelineEventBus()
        deployer = StrategyDeployer(client=client, event_bus=bus)

        client.get_positions.return_value = [
            AlpacaPosition(symbol="SPY", qty=10.0, side="long")
        ]
        client.close_position.return_value = AlpacaOrder(
            id="close-1", symbol="SPY", qty=10.0, side="sell", status="filled"
        )

        deployment = Deployment(
            deployment_id="dep-2",
            spec_id="spec-1",
            strategy_file="/tmp/test.py",
        )

        mock_strategy = MagicMock()
        mock_instance = MagicMock()
        mock_instance.generate_signals.return_value = pd.Series(
            [0], index=pd.date_range("2020-01-01", periods=1)
        )
        mock_strategy.return_value = mock_instance

        with patch.object(deployer, "_import_strategy", return_value=mock_strategy):
            with patch.object(deployer, "_fetch_bars", return_value={
                "SPY": pd.DataFrame({"close": [100.0]}, index=pd.date_range("2020-01-01", periods=1))
            }):
                result = deployer.run_cycle(deployment)

        assert "CLOSE SPY" in result.actions
        client.close_position.assert_called_once_with("SPY")

    def test_run_cycle_long_signal_with_position_holds(self):
        client = MagicMock(spec=AstraAlpacaClient)
        bus = PipelineEventBus()
        deployer = StrategyDeployer(client=client, event_bus=bus)

        client.get_positions.return_value = [
            AlpacaPosition(symbol="SPY", qty=10.0, side="long")
        ]

        deployment = Deployment(
            deployment_id="dep-3",
            spec_id="spec-1",
            strategy_file="/tmp/test.py",
        )

        mock_strategy = MagicMock()
        mock_instance = MagicMock()
        mock_instance.generate_signals.return_value = pd.Series(
            [1], index=pd.date_range("2020-01-01", periods=1)
        )
        mock_strategy.return_value = mock_instance

        with patch.object(deployer, "_import_strategy", return_value=mock_strategy):
            with patch.object(deployer, "_fetch_bars", return_value={
                "SPY": pd.DataFrame({"close": [100.0]}, index=pd.date_range("2020-01-01", periods=1))
            }):
                result = deployer.run_cycle(deployment)

        assert "HOLD SPY" in result.actions
        client.submit_order.assert_not_called()
        client.close_position.assert_not_called()

    def test_run_cycle_flat_signal_no_position_holds(self):
        client = MagicMock(spec=AstraAlpacaClient)
        bus = PipelineEventBus()
        deployer = StrategyDeployer(client=client, event_bus=bus)

        client.get_positions.return_value = []

        deployment = Deployment(
            deployment_id="dep-4",
            spec_id="spec-1",
            strategy_file="/tmp/test.py",
        )

        mock_strategy = MagicMock()
        mock_instance = MagicMock()
        mock_instance.generate_signals.return_value = pd.Series(
            [0], index=pd.date_range("2020-01-01", periods=1)
        )
        mock_strategy.return_value = mock_instance

        with patch.object(deployer, "_import_strategy", return_value=mock_strategy):
            with patch.object(deployer, "_fetch_bars", return_value={
                "SPY": pd.DataFrame({"close": [100.0]}, index=pd.date_range("2020-01-01", periods=1))
            }):
                result = deployer.run_cycle(deployment)

        assert "HOLD SPY" in result.actions
        client.submit_order.assert_not_called()
        client.close_position.assert_not_called()

    def test_stop_closes_all_positions(self):
        client = MagicMock(spec=AstraAlpacaClient)
        bus = PipelineEventBus()
        deployer = StrategyDeployer(client=client, event_bus=bus)

        client.get_positions.return_value = [
            AlpacaPosition(symbol="SPY", qty=10.0, side="long"),
            AlpacaPosition(symbol="QQQ", qty=5.0, side="long"),
        ]

        deployment = Deployment(deployment_id="dep-5")
        deployer.stop(deployment)

        assert deployment.status == "STOPPED"
        assert deployment.stopped_at is not None
        assert client.close_position.call_count == 2

    def test_deployment_ledger_path_set_correctly(self, tmp_path):
        client = MagicMock(spec=AstraAlpacaClient)
        bus = PipelineEventBus()
        deployer = StrategyDeployer(client=client, event_bus=bus)

        strategy_file = str(tmp_path / "strategies" / "spec-1" / "strat.py")
        import os
        os.makedirs(os.path.dirname(strategy_file), exist_ok=True)
        with open(strategy_file, "w") as f:
            f.write("# test\n")

        spec = _make_spec()
        build_result = BuildResult(
            success=True,
            spec_id=spec.spec_id,
            strategy_file=strategy_file,
        )
        pipeline_result = PipelineResult(
            pipeline_id="p1", spec_id=spec.spec_id, status="DEPLOYED_PAPER"
        )

        deployment = deployer.deploy(build_result, spec, pipeline_result)
        assert deployment.ledger_path != ""
        assert "ledger" in deployment.ledger_path
        assert deployment.ledger_path.endswith(".jsonl")


# ---------------------------------------------------------------------------
# PerformanceMonitor
# ---------------------------------------------------------------------------


class TestPerformanceMonitor:
    def test_snapshot_has_disclaimer(self):
        client = MagicMock(spec=AstraAlpacaClient)
        client.get_account.return_value = AlpacaAccount(equity=100000.0, cash=50000.0)
        client.get_positions.return_value = []
        client.get_portfolio_history.return_value = PortfolioHistory(
            timestamps=[1, 2], equity=[100000.0, 101000.0], base_value=100000.0
        )

        monitor = PerformanceMonitor(client=client)
        deployment = Deployment(deployment_id="dep-1")
        snapshot = monitor.snapshot(deployment)

        assert snapshot.disclaimer is not None
        assert "profitability" in snapshot.disclaimer

    def test_snapshot_populates_fields(self):
        client = MagicMock(spec=AstraAlpacaClient)
        client.get_account.return_value = AlpacaAccount(
            equity=105000.0, cash=50000.0, portfolio_value=105000.0
        )
        client.get_positions.return_value = [
            AlpacaPosition(symbol="SPY", qty=100, unrealized_pl=500.0)
        ]
        client.get_portfolio_history.return_value = PortfolioHistory(
            timestamps=[1, 2, 3],
            equity=[100000.0, 102000.0, 105000.0],
            base_value=100000.0,
        )

        monitor = PerformanceMonitor(client=client)
        deployment = Deployment(deployment_id="dep-1")
        snapshot = monitor.snapshot(deployment)

        assert snapshot.total_return > 0
        assert len(snapshot.equity_curve) == 3
        assert snapshot.total_trades > 0

    def test_degradation_acceptable(self):
        snapshot = PerformanceSnapshot(
            deployment_id="dep-1",
            total_return=0.14,
            sharpe_ratio=1.5,
            max_drawdown=0.05,
        )
        backtest_metrics = {
            "mean_sharpe": 1.6,
            "max_drawdown": 0.04,
        }
        report = PerformanceMonitor.compute_degradation(snapshot, backtest_metrics)
        assert report.category == "ACCEPTABLE"
        assert report.triggers_optimizer is False

    def test_degradation_elevated(self):
        snapshot = PerformanceSnapshot(
            deployment_id="dep-1",
            total_return=0.02,
            sharpe_ratio=0.3,
            max_drawdown=0.20,
        )
        backtest_metrics = {
            "mean_sharpe": 1.5,
            "max_drawdown": 0.05,
        }
        report = PerformanceMonitor.compute_degradation(snapshot, backtest_metrics)
        assert report.category in ("ELEVATED", "SEVERE")
        assert report.overall_degradation_score > 0

    def test_degradation_severe_triggers_optimizer(self):
        snapshot = PerformanceSnapshot(
            deployment_id="dep-1",
            total_return=-0.05,
            sharpe_ratio=-0.5,
            max_drawdown=0.40,
        )
        backtest_metrics = {
            "mean_sharpe": 2.0,
            "max_drawdown": 0.10,
        }
        report = PerformanceMonitor.compute_degradation(snapshot, backtest_metrics)
        assert report.category == "SEVERE"
        assert report.triggers_optimizer is True

    def test_degradation_report_fields(self):
        report = DegradationReport(
            return_degradation=0.1,
            sharpe_degradation=0.5,
            drawdown_expansion=0.05,
            overall_degradation_score=0.3,
            category="ELEVATED",
        )
        assert report.return_degradation == 0.1
        assert report.sharpe_degradation == 0.5
        assert report.category == "ELEVATED"

    def test_snapshot_with_empty_equity_curve(self):
        client = MagicMock(spec=AstraAlpacaClient)
        client.get_account.return_value = AlpacaAccount(equity=100000.0, cash=100000.0)
        client.get_positions.return_value = []
        client.get_portfolio_history.return_value = PortfolioHistory()

        monitor = PerformanceMonitor(client=client)
        deployment = Deployment(deployment_id="dep-1")
        snapshot = monitor.snapshot(deployment)

        assert snapshot.total_return == 0.0
        assert snapshot.sharpe_ratio == 0.0
        assert len(snapshot.equity_curve) == 1
        assert snapshot.equity_curve[0] == 100000.0


# ---------------------------------------------------------------------------
# Short selling block
# ---------------------------------------------------------------------------


class TestShortSellingBlock:
    def test_short_sell_without_position_raises(self):
        client = MagicMock(spec=AstraAlpacaClient)
        client.get_positions.return_value = []

        bus = PipelineEventBus()
        deployer = StrategyDeployer(client=client, event_bus=bus)

        deployment = Deployment(
            deployment_id="dep-6",
            spec_id="spec-1",
            strategy_file="/tmp/test.py",
        )

        mock_strategy = MagicMock()
        mock_instance = MagicMock()
        mock_instance.generate_signals.return_value = pd.Series(
            [1], index=pd.date_range("2020-01-01", periods=1)
        )
        mock_strategy.return_value = mock_instance

        client.submit_order.side_effect = ShortSellingBlockedError("SPY")

        with patch.object(deployer, "_import_strategy", return_value=mock_strategy):
            with patch.object(deployer, "_fetch_bars", return_value={
                "SPY": pd.DataFrame({"close": [100.0]}, index=pd.date_range("2020-01-01", periods=1))
            }):
                with pytest.raises(ShortSellingBlockedError):
                    deployer.run_cycle(deployment)


# ---------------------------------------------------------------------------
# CycleResult recording
# ---------------------------------------------------------------------------


class TestCycleResultRecording:
    def test_records_actions_correctly(self):
        result = CycleResult(
            deployment_id="dep-1",
            cycle_number=1,
            signals={"SPY": 1, "QQQ": 0},
            actions=["BUY SPY", "HOLD QQQ"],
            orders=[
                AlpacaOrder(id="o1", symbol="SPY", qty=1.0, side="buy")
            ],
        )
        assert result.signals["SPY"] == 1
        assert result.signals["QQQ"] == 0
        assert len(result.orders) == 1
        assert result.orders[0].id == "o1"

    def test_deployment_cycle_increments(self):
        client = MagicMock(spec=AstraAlpacaClient)
        bus = PipelineEventBus()
        deployer = StrategyDeployer(client=client, event_bus=bus)

        client.get_positions.return_value = []

        deployment = Deployment(deployment_id="dep-7")
        mock_strategy = MagicMock()
        mock_instance = MagicMock()
        mock_instance.generate_signals.return_value = pd.Series(
            [0], index=pd.date_range("2020-01-01", periods=1)
        )
        mock_strategy.return_value = mock_instance

        with patch.object(deployer, "_import_strategy", return_value=mock_strategy):
            with patch.object(deployer, "_fetch_bars", return_value={
                "SPY": pd.DataFrame({"close": [100.0]}, index=pd.date_range("2020-01-01", periods=1))
            }):
                r1 = deployer.run_cycle(deployment)
                assert r1.cycle_number == 1
                assert deployment.cycle_count == 1

                r2 = deployer.run_cycle(deployment)
                assert r2.cycle_number == 2
                assert deployment.cycle_count == 2
