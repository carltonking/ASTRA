"""Deployment risk engine and kill-switch policy."""

import math
from dataclasses import dataclass, field
from typing import Any

from astra.deployment.portfolio import PortfolioState


@dataclass
class RiskLimits:
    max_drawdown: float = 0.20
    max_gross_exposure: float = 1.0
    max_net_exposure: float = 1.0
    max_position_concentration: float = 0.35
    max_correlation: float = 0.85
    intraday_var_limit: float = 0.03
    max_orders_per_cycle: int = 20
    allow_short: bool = False
    paper_trading_only: bool = True


@dataclass
class RiskDecision:
    allowed: bool
    action: str = "ALLOW"
    reasons: list[str] = field(default_factory=list)
    exposure_multiplier: float = 1.0
    metrics: dict[str, Any] = field(default_factory=dict)


class RiskEngine:
    """Hard safety checks for paper deployment cycles."""

    def __init__(self, limits: RiskLimits | None = None):
        self._limits = limits or RiskLimits()

    @property
    def limits(self) -> RiskLimits:
        return self._limits

    def evaluate(
        self,
        portfolio: PortfolioState,
        equity_curve: list[float] | None = None,
        correlation: float | None = None,
        intraday_returns: list[float] | None = None,
    ) -> RiskDecision:
        reasons: list[str] = []
        metrics: dict[str, Any] = {
            "gross_exposure": portfolio.gross_exposure,
            "net_exposure": portfolio.net_exposure,
            "largest_position_weight": portfolio.largest_position_weight,
        }

        drawdown = self._max_drawdown(equity_curve or [])
        metrics["max_drawdown"] = drawdown
        if drawdown > self._limits.max_drawdown:
            reasons.append("MAX_DRAWDOWN_BREACH")

        if portfolio.gross_exposure > self._limits.max_gross_exposure:
            reasons.append("MAX_GROSS_EXPOSURE_BREACH")
        if abs(portfolio.net_exposure) > self._limits.max_net_exposure:
            reasons.append("MAX_NET_EXPOSURE_BREACH")
        if portfolio.largest_position_weight > self._limits.max_position_concentration:
            reasons.append("POSITION_CONCENTRATION_BREACH")

        if correlation is not None:
            metrics["correlation"] = correlation
            if correlation > self._limits.max_correlation:
                reasons.append("CORRELATION_LIMIT_BREACH")

        intraday_var = self._historical_var(intraday_returns or [])
        metrics["intraday_var"] = intraday_var
        if intraday_var > self._limits.intraday_var_limit:
            reasons.append("INTRADAY_VAR_BREACH")

        short_positions = [p.symbol for p in portfolio.positions if p.side == "short" or p.qty < 0]
        if short_positions and not self._limits.allow_short:
            metrics["short_positions"] = short_positions
            reasons.append("SHORT_EXPOSURE_BLOCKED")

        if reasons:
            return RiskDecision(
                allowed=False,
                action="SUSPEND",
                reasons=reasons,
                exposure_multiplier=0.0,
                metrics=metrics,
            )
        return RiskDecision(allowed=True, metrics=metrics)

    def check_order(
        self,
        side: str,
        open_order_count: int,
    ) -> RiskDecision:
        reasons: list[str] = []
        if side.lower() == "sell" and not self._limits.allow_short:
            reasons.append("SELL_ORDER_REQUIRES_EXISTING_POSITION")
        if open_order_count >= self._limits.max_orders_per_cycle:
            reasons.append("MAX_ORDERS_PER_CYCLE_BREACH")
        if reasons:
            return RiskDecision(
                allowed=False,
                action="BLOCK_ORDER",
                reasons=reasons,
                exposure_multiplier=0.0,
            )
        return RiskDecision(allowed=True)

    @staticmethod
    def _max_drawdown(equity_curve: list[float]) -> float:
        if len(equity_curve) < 2:
            return 0.0
        peak = equity_curve[0]
        max_dd = 0.0
        for value in equity_curve:
            peak = max(peak, value)
            if peak > 0:
                max_dd = max(max_dd, (peak - value) / peak)
        return max_dd

    @staticmethod
    def _historical_var(returns: list[float], percentile: float = 0.05) -> float:
        if not returns:
            return 0.0
        losses = sorted([-r for r in returns if math.isfinite(r)])
        if not losses:
            return 0.0
        idx = min(len(losses) - 1, max(0, int((1.0 - percentile) * len(losses)) - 1))
        return max(0.0, losses[idx])
