"""Governance-oriented validation scoring."""

from dataclasses import dataclass, field
from typing import Any

import numpy as np
import pandas as pd


@dataclass(frozen=True)
class ValidationPolicy:
    min_oos_sharpe: float = 0.0
    min_dsr: float = 0.95
    max_pbo: float = 0.20
    max_fragility: float = 40.0
    min_robustness: float = 70.0
    max_turnover: float = 5.0
    max_drawdown: float = 0.20
    min_parameter_plateau: float = 0.15


@dataclass
class RobustnessMetrics:
    oos_sharpe: float = 0.0
    dsr: float = 0.0
    pbo: float = 1.0
    parameter_plateau: float = 0.0
    regime_pass_rate: float = 0.0
    slippage_survival: float = 0.0
    turnover: float = 0.0
    max_drawdown: float = 1.0
    complexity: float = 1.0
    confidence_interval_width: float = 1.0


@dataclass
class ValidationDecision:
    status: str
    robustness_score: float
    fragility_score: float
    hard_failures: list[str] = field(default_factory=list)
    soft_failures: list[str] = field(default_factory=list)
    metrics: dict[str, Any] = field(default_factory=dict)


class ValidationEngine:
    def __init__(self, policy: ValidationPolicy | None = None):
        self._policy = policy or ValidationPolicy()

    def decide(self, metrics: RobustnessMetrics) -> ValidationDecision:
        hard: list[str] = []
        soft: list[str] = []
        if metrics.oos_sharpe <= self._policy.min_oos_sharpe:
            hard.append("OOS_COLLAPSE")
        if metrics.dsr < self._policy.min_dsr:
            hard.append("SHARPE_INFLATION_DETECTED")
        if metrics.pbo > self._policy.max_pbo:
            hard.append("PBO_TOO_HIGH")
        if metrics.slippage_survival < 0.70:
            hard.append("SLIPPAGE_EDGE_DECAY")
        if metrics.max_drawdown > self._policy.max_drawdown:
            hard.append("MAX_DRAWDOWN_BREACH")
        if metrics.parameter_plateau < self._policy.min_parameter_plateau:
            soft.append("PARAMETER_SURFACE_NARROW")
        if metrics.regime_pass_rate < 0.60:
            soft.append("REGIME_ROBUSTNESS_WEAK")
        if metrics.turnover > self._policy.max_turnover:
            soft.append("TURNOVER_UNREALISTIC")
        if metrics.confidence_interval_width > 0.75:
            soft.append("CONFIDENCE_INTERVAL_WEAK")

        robustness = self.robustness_score(metrics)
        fragility = self.fragility_score(metrics)
        if fragility > self._policy.max_fragility:
            hard.append("FRAGILITY_TOO_HIGH")
        if robustness < self._policy.min_robustness:
            soft.append("ROBUSTNESS_TOO_LOW")

        status = "REJECT" if hard else "PAPER_CANDIDATE" if robustness >= self._policy.min_robustness else "MUTATE"
        return ValidationDecision(
            status=status,
            robustness_score=round(robustness, 4),
            fragility_score=round(fragility, 4),
            hard_failures=hard,
            soft_failures=soft,
            metrics=metrics.__dict__,
        )

    @staticmethod
    def parameter_stability(surface: dict[str, float], selected_key: str) -> float:
        if not surface or selected_key not in surface:
            return 0.0
        selected = surface[selected_key]
        values = np.array(list(surface.values()), dtype=float)
        if len(values) == 0:
            return 0.0
        median = float(np.nanmedian(values))
        if selected <= 0:
            return 0.0
        return max(0.0, min(1.0, median / selected))

    @staticmethod
    def monte_carlo_resample(
        returns: pd.Series,
        trials: int = 500,
        seed: int = 0,
    ) -> dict[str, float]:
        clean = returns.dropna().astype(float).to_numpy()
        if len(clean) == 0:
            return {"prob_loss": 1.0, "p05_return": 0.0, "p95_drawdown": 1.0}
        rng = np.random.default_rng(seed)
        totals: list[float] = []
        drawdowns: list[float] = []
        for _ in range(trials):
            sample = rng.choice(clean, size=len(clean), replace=True)
            equity = np.cumprod(1.0 + sample)
            peak = np.maximum.accumulate(equity)
            dd = np.max((peak - equity) / np.maximum(peak, 1e-12))
            totals.append(float(equity[-1] - 1.0))
            drawdowns.append(float(dd))
        return {
            "prob_loss": float(np.mean(np.array(totals) < 0.0)),
            "p05_return": float(np.quantile(totals, 0.05)),
            "p95_drawdown": float(np.quantile(drawdowns, 0.95)),
        }

    @staticmethod
    def regime_pass_rate(regime_metrics: dict[str, dict[str, float]]) -> float:
        if not regime_metrics:
            return 0.0
        passed = 0
        total = 0
        for metrics in regime_metrics.values():
            total += 1
            if metrics.get("oos_sharpe", 0.0) > 0 and metrics.get("max_drawdown", 1.0) < 0.25:
                passed += 1
        return passed / total if total else 0.0

    @staticmethod
    def slippage_survival(base_return: float, stressed_return: float) -> float:
        if base_return <= 0:
            return 0.0
        return max(0.0, min(1.0, stressed_return / base_return))

    @staticmethod
    def robustness_score(metrics: RobustnessMetrics) -> float:
        score = (
            20 * min(1.0, max(0.0, metrics.oos_sharpe / 2.0))
            + 18 * min(1.0, metrics.dsr)
            + 15 * max(0.0, 1.0 - metrics.pbo)
            + 12 * metrics.parameter_plateau
            + 12 * metrics.regime_pass_rate
            + 10 * metrics.slippage_survival
            + 7 * max(0.0, 1.0 - metrics.turnover / 10.0)
            + 6 * max(0.0, 1.0 - metrics.complexity / 10.0)
        )
        return max(0.0, min(100.0, score))

    @staticmethod
    def fragility_score(metrics: RobustnessMetrics) -> float:
        score = (
            18 * (1.0 if metrics.oos_sharpe <= 0 else 0.0)
            + 14 * max(0.0, 1.0 - metrics.parameter_plateau)
            + 12 * min(1.0, metrics.pbo)
            + 10 * max(0.0, 1.0 - metrics.slippage_survival)
            + 10 * max(0.0, 1.0 - metrics.regime_pass_rate)
            + 8 * min(1.0, metrics.turnover / 10.0)
            + 8 * min(1.0, metrics.max_drawdown)
            + 7 * min(1.0, metrics.complexity / 10.0)
            + 7 * min(1.0, metrics.confidence_interval_width)
        )
        return max(0.0, min(100.0, score))
