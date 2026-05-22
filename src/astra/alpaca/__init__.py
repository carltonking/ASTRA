"""Alpaca paper trading integration — deploy, monitor, and manage live paper positions."""

from astra.alpaca.client import (
    AstraAlpacaClient,
    AlpacaAccount,
    AlpacaPosition,
    AlpacaOrder,
    PortfolioHistory,
)
from astra.alpaca.deployer import StrategyDeployer, Deployment, CycleResult
from astra.alpaca.monitor import PerformanceMonitor, PerformanceSnapshot, DegradationReport
from astra.alpaca.monitor_loop import PerformanceMonitoringLoop, MonitoringCheckResult
from astra.alpaca.exceptions import (
    LiveTradingBlockedError,
    ShortSellingBlockedError,
    DeploymentError,
    AlpacaConnectionError,
)

__all__ = [
    "AstraAlpacaClient",
    "AlpacaAccount",
    "AlpacaPosition",
    "AlpacaOrder",
    "PortfolioHistory",
    "StrategyDeployer",
    "Deployment",
    "CycleResult",
    "PerformanceMonitor",
    "PerformanceSnapshot",
    "DegradationReport",
    "LiveTradingBlockedError",
    "ShortSellingBlockedError",
    "DeploymentError",
    "AlpacaConnectionError",
    "PerformanceMonitoringLoop",
    "MonitoringCheckResult",
]
