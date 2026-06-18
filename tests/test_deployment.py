"""Tests for institutional paper deployment controls."""

from datetime import datetime, timezone
from unittest.mock import MagicMock, patch

import pandas as pd

from astra.alpaca.deployer import Deployment, StrategyDeployer
from astra.broker.base import Account, Broker, Position
from astra.deployment import (
    PortfolioManager,
    RiskEngine,
    RiskLimits,
    StaleDataDetector,
    TradeAuditLog,
)
from astra.pipeline.events import PipelineEventBus


def test_portfolio_manager_computes_exposure():
    broker = MagicMock(spec=Broker)
    broker.get_account.return_value = Account(equity=100_000, portfolio_value=100_000)
    broker.get_positions.return_value = [
        Position(symbol="SPY", qty=100, current_price=400),
        Position(symbol="QQQ", qty=50, current_price=300),
    ]

    state = PortfolioManager(broker).snapshot()

    assert state.gross_exposure == 0.55
    assert state.largest_position_weight == 0.40


def test_risk_engine_kill_switch_on_concentration():
    portfolio = MagicMock()
    portfolio.gross_exposure = 0.50
    portfolio.net_exposure = 0.50
    portfolio.largest_position_weight = 0.60
    portfolio.positions = []

    decision = RiskEngine(
        RiskLimits(max_position_concentration=0.35)
    ).evaluate(portfolio)

    assert decision.allowed is False
    assert decision.action == "SUSPEND"
    assert "POSITION_CONCENTRATION_BREACH" in decision.reasons


def test_stale_data_detector_flags_old_bars():
    bars = {
        "SPY": pd.DataFrame(
            {"close": [100.0]},
            index=pd.DatetimeIndex([datetime(2020, 1, 1, tzinfo=timezone.utc)]),
        )
    }

    report = StaleDataDetector(max_age_days=1).check(bars)

    assert report.ok is False
    assert report.stale_symbols == ["SPY"]


def test_deployer_suspends_on_heartbeat_failure():
    broker = MagicMock(spec=Broker)
    broker.get_name.return_value = "mock"
    broker.get_account.side_effect = RuntimeError("broker offline")
    bus = PipelineEventBus()
    deployer = StrategyDeployer(broker=broker, event_bus=bus)

    deployment = Deployment(deployment_id="dep-1", strategy_file="/tmp/test.py")

    result = deployer.run_cycle(deployment)

    assert deployment.status == "SUSPENDED"
    assert "BROKER_HEARTBEAT_FAILED" in (deployment.suspended_reason or "")
    assert result.actions == ["SUSPEND BROKER_HEARTBEAT_FAILED"]
    assert any(e["event"] == "deployment.suspended" for e in bus.get_history())


def test_deployer_suspends_when_stale_data_enforced(tmp_path):
    broker = MagicMock(spec=Broker)
    broker.get_name.return_value = "mock"
    broker.get_account.return_value = Account(equity=100_000, portfolio_value=100_000)
    broker.get_positions.return_value = []
    bus = PipelineEventBus()
    deployer = StrategyDeployer(broker=broker, event_bus=bus)
    old_bars = {
        "SPY": pd.DataFrame(
            {"close": [100.0]},
            index=pd.DatetimeIndex([datetime(2020, 1, 1, tzinfo=timezone.utc)]),
        )
    }
    deployment = Deployment(
        deployment_id="dep-2",
        strategy_file=str(tmp_path / "test.py"),
        symbols=["SPY"],
        enforce_stale_data=True,
    )

    with patch.object(deployer, "_import_strategy", return_value=MagicMock()):
        with patch.object(deployer, "_fetch_bars", return_value=old_bars):
            result = deployer.run_cycle(deployment)

    assert deployment.status == "SUSPENDED"
    assert "STALE_DATA" in (deployment.suspended_reason or "")
    assert result.actions == ["SUSPEND STALE_DATA"]


def test_trade_audit_log_writes_jsonl(tmp_path):
    path = tmp_path / "audit.jsonl"
    log = TradeAuditLog(str(path))

    log.record("order_submitted", "dep-1", {"symbol": "SPY"})

    assert path.exists()
    content = path.read_text()
    assert "order_submitted" in content
    assert "dep-1" in content
