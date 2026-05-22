"""Performance monitor — monitors paper deployments and computes metrics for the optimizer."""

import math
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any

from astra.broker.base import Broker
from astra.alpaca.deployer import Deployment

DISCLAIMER = (
    "ASTRA research results are not profitability guarantees. "
    "Past performance does not predict future results."
)


@dataclass
class DegradationReport:
    return_degradation: float = 0.0
    sharpe_degradation: float = 0.0
    drawdown_expansion: float = 0.0
    overall_degradation_score: float = 0.0
    category: str = "ACCEPTABLE"
    triggers_optimizer: bool = False


@dataclass
class PerformanceSnapshot:
    deployment_id: str = ""
    timestamp: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
    total_return: float = 0.0
    annualized_return: float = 0.0
    sharpe_ratio: float = 0.0
    max_drawdown: float = 0.0
    win_rate: float = 0.0
    total_trades: int = 0
    days_deployed: int = 0
    equity_curve: list[float] = field(default_factory=list)
    degradation_report: DegradationReport | None = None
    disclaimer: str = DISCLAIMER


class PerformanceMonitor:
    def __init__(self, broker: Broker):
        self._broker = broker

    def snapshot(self, deployment: Deployment) -> PerformanceSnapshot:
        account = self._broker.get_account()
        positions = self._broker.get_positions()
        history = self._broker.get_portfolio_history(period="1M", timeframe="1D")

        total_return = 0.0
        annualized_return = 0.0
        sharpe_ratio = 0.0
        max_drawdown = 0.0
        win_rate = 0.0

        equity_curve = list(history.equity) if history.equity else [account.equity]

        if len(equity_curve) > 1:
            base = history.base_value if history.base_value > 0 else equity_curve[0]
            total_return = (equity_curve[-1] - base) / base if base > 0 else 0.0

            days = len(equity_curve)
            if days > 0:
                annualized_return = total_return * (365.0 / days) if total_return != 0 else 0.0

            daily_returns = []
            for i in range(1, len(equity_curve)):
                prev = equity_curve[i - 1]
                if prev > 0:
                    daily_returns.append((equity_curve[i] - prev) / prev)

            if daily_returns:
                avg_return = sum(daily_returns) / len(daily_returns)
                variance = sum((r - avg_return) ** 2 for r in daily_returns) / len(daily_returns)
                std = math.sqrt(variance) if variance > 0 else 1e-10
                sharpe_ratio = (avg_return / std) * math.sqrt(252) if std > 0 else 0.0

            peak = equity_curve[0]
            for val in equity_curve:
                if val > peak:
                    peak = val
                dd = (peak - val) / peak if peak > 0 else 0
                if dd > max_drawdown:
                    max_drawdown = dd

        if len(equity_curve) > 1:
            up_days = sum(
                1 for i in range(1, len(equity_curve))
                if equity_curve[i] > equity_curve[i - 1]
            )
            win_rate = up_days / (len(equity_curve) - 1) if len(equity_curve) > 1 else 0.0

        total_trades = len(positions)
        days_deployed = 0
        if deployment.started_at:
            delta = datetime.now(timezone.utc) - deployment.started_at
            days_deployed = max(0, delta.days)

        return PerformanceSnapshot(
            deployment_id=deployment.deployment_id,
            total_return=round(total_return, 6),
            annualized_return=round(annualized_return, 6),
            sharpe_ratio=round(sharpe_ratio, 4),
            max_drawdown=round(max_drawdown, 6),
            win_rate=round(win_rate, 4),
            total_trades=total_trades,
            days_deployed=days_deployed,
            equity_curve=equity_curve,
        )

    @staticmethod
    def compute_degradation(
        snapshot: PerformanceSnapshot,
        backtest_metrics: dict[str, Any],
    ) -> DegradationReport:
        bt_return = float(backtest_metrics.get("mean_sharpe", 0) * 0.1)
        bt_sharpe = float(backtest_metrics.get("mean_sharpe", 0))
        bt_max_dd = float(backtest_metrics.get("max_drawdown", 0.15))

        return_degradation = bt_return - snapshot.total_return
        sharpe_degradation = bt_sharpe - snapshot.sharpe_ratio
        drawdown_expansion = snapshot.max_drawdown - bt_max_dd

        return_degradation = max(0, return_degradation)
        sharpe_degradation = max(0, sharpe_degradation)
        drawdown_expansion = max(0, drawdown_expansion)

        r_max = max(abs(bt_return), 1e-6)
        s_max = max(abs(bt_sharpe), 1e-6)
        d_max = max(abs(bt_max_dd), 1e-6)

        normalized_return = return_degradation / r_max if r_max > 0 else 0
        normalized_sharpe = sharpe_degradation / s_max if s_max > 0 else 0
        normalized_drawdown = drawdown_expansion / d_max if d_max > 0 else 0

        overall = min(
            1.0,
            normalized_return * 0.4 + normalized_sharpe * 0.35 + normalized_drawdown * 0.25,
        )

        if overall < 0.2:
            category = "ACCEPTABLE"
            triggers = False
        elif overall < 0.5:
            category = "ELEVATED"
            triggers = False
        else:
            category = "SEVERE"
            triggers = True

        return DegradationReport(
            return_degradation=round(return_degradation, 6),
            sharpe_degradation=round(sharpe_degradation, 4),
            drawdown_expansion=round(drawdown_expansion, 6),
            overall_degradation_score=round(overall, 4),
            category=category,
            triggers_optimizer=triggers,
        )
