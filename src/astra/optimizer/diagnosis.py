"""Diagnosis engine — analyzes strategy performance and identifies root causes of degradation."""

from dataclasses import dataclass, field
from typing import Any

from astra.planner.spec import StrategySpec
from astra.builder.generator import BuildResult
from astra.pipeline.runner import PipelineResult
from astra.alpaca.monitor import PerformanceSnapshot

_DISCLAIMER = (
    "ASTRA research results are not profitability guarantees. "
    "Past performance does not predict future results."
)


@dataclass
class Diagnosis:
    primary_diagnosis: str = ""
    confidence: float = 0.0
    evidence: list[str] = field(default_factory=list)
    recommended_action: str = ""
    plain_english_summary: str = ""
    disclaimer: str = _DISCLAIMER


class DiagnosisEngine:
    """Deterministic diagnosis engine. No AI — pure signal analysis."""

    def diagnose(
        self,
        spec: StrategySpec,
        build_result: BuildResult,
        pipeline_results: list[PipelineResult],
        latest_snapshot: PerformanceSnapshot,
    ) -> Diagnosis:
        backtest_metrics: dict[str, Any] = {}
        if pipeline_results:
            last = pipeline_results[-1]
            if last.backtest_metrics:
                backtest_metrics = last.backtest_metrics

        bt_sharpe = float(backtest_metrics.get("mean_sharpe", 0))
        bt_dsr = float(backtest_metrics.get("dsr", 0))
        paper_sharpe = latest_snapshot.sharpe_ratio
        win_rate = latest_snapshot.win_rate
        total_trades = latest_snapshot.total_trades
        days_deployed = latest_snapshot.days_deployed

        candidates: list[tuple[str, float, list[str], str]] = []

        # INSUFFICIENT_DATA — gate check
        if days_deployed < 5:
            return Diagnosis(
                primary_diagnosis="INSUFFICIENT_DATA",
                confidence=1.0,
                evidence=[
                    f"Only {days_deployed} days of paper trading data available.",
                    "At least 5 trading days are needed for a meaningful diagnosis.",
                    "Continue paper trading to accumulate sufficient data.",
                ],
                recommended_action="EXTEND_OBSERVATION",
                plain_english_summary=(
                    f"The strategy has only been paper trading for {days_deployed} days. "
                    "That is not enough data to diagnose performance. "
                    "ASTRA will continue monitoring and re-evaluate once there are more trading days."
                ),
            )

        # PARAMETER_SENSITIVITY
        if bt_dsr < 0.5 and paper_sharpe < 0.5 * bt_sharpe and bt_sharpe > 0:
            candidates.append((
                "PARAMETER_SENSITIVITY",
                0.85,
                [
                    f"Backtest DSR is {bt_dsr:.2f} (< 0.5), indicating parameter sensitivity risk.",
                    f"Paper Sharpe ({paper_sharpe:.2f}) is less than 50% of backtest Sharpe ({bt_sharpe:.2f}).",
                    "Parameters are likely overfit to historical data windows.",
                ],
                "ADJUST_PARAMETERS",
            ))

        # TRANSACTION_COST_DRAG
        avg_trades_per_day = total_trades / max(days_deployed, 1)
        if avg_trades_per_day > 1.0 and latest_snapshot.total_return < 0.01:
            candidates.append((
                "TRANSACTION_COST_DRAG",
                0.75,
                [
                    f"Average trade frequency: {avg_trades_per_day:.1f} trades/day.",
                    "High frequency combined with near-zero or negative net return suggests costs overwhelm edge.",
                    "Consider reducing trade frequency or increasing signal thresholds.",
                ],
                "ADJUST_PARAMETERS",
            ))

        # POSITION_SIZING
        if latest_snapshot.max_drawdown > 0.10:
            candidates.append((
                "POSITION_SIZING",
                0.70,
                [
                    f"Max drawdown is {latest_snapshot.max_drawdown:.1%}, exceeding typical thresholds.",
                    "Drawdown expansion suggests position sizes are too large for current market conditions.",
                    "Consider reducing position_size parameter to preserve capital.",
                ],
                "ADJUST_PARAMETERS",
            ))

        # SIGNAL_DECAY
        if win_rate < 0.4 and total_trades > 20:
            candidates.append((
                "SIGNAL_DECAY",
                0.80,
                [
                    f"Win rate is {win_rate:.1%} with {total_trades} total trades.",
                    "Below 40% win rate on significant sample size indicates the signal may no longer be predictive.",
                    "The market hypothesis may need revisiting — the edge that existed in backtest may have decayed.",
                ],
                "REBUILD_STRATEGY",
            ))

        if not candidates:
            return Diagnosis(
                primary_diagnosis="NORMAL_DEGRADATION",
                confidence=0.5,
                evidence=[
                    f"Paper Sharpe: {paper_sharpe:.2f} vs Backtest Sharpe: {bt_sharpe:.2f}",
                    f"Days deployed: {days_deployed}, Win rate: {win_rate:.1%}",
                    "No strong signal of any specific degradation pattern.",
                ],
                recommended_action="EXTEND_OBSERVATION",
                plain_english_summary=(
                    "The strategy is experiencing normal degradation — performance is below backtest "
                    "expectations but no specific pattern dominates. More trading data is needed "
                    "before recommending changes."
                ),
            )

        candidates.sort(key=lambda c: c[1], reverse=True)
        best = candidates[0]

        return Diagnosis(
            primary_diagnosis=best[0],
            confidence=best[1],
            evidence=best[2],
            recommended_action=best[3],
            plain_english_summary=self._build_summary(best[0], best[2][0] if best[2] else ""),
        )

    @staticmethod
    def _build_summary(diagnosis: str, top_evidence: str) -> str:
        summaries = {
            "PARAMETER_SENSITIVITY": (
                "The strategy's parameters appear to be overfit to historical data. "
                "Backtest performance was strong but those results are not transferring to paper trading. "
                "ASTRA will propose adjusted parameters to improve generalization."
            ),
            "TRANSACTION_COST_DRAG": (
                "Trading costs are eating into the strategy's returns. The strategy trades frequently "
                "but each trade's average profit is too small to overcome transaction costs. "
                "ASTRA will propose reducing trade frequency or widening signal thresholds."
            ),
            "POSITION_SIZING": (
                "Drawdown is significantly worse than the backtest predicted. "
                "This suggests position sizes are too large for the current market regime. "
                "ASTRA will propose reducing position size to control risk."
            ),
            "SIGNAL_DECAY": (
                "The trading signal that worked in backtesting is no longer predictive in live markets. "
                "Below 40% win rate on over 20 trades strongly suggests the edge has decayed. "
                "ASTRA recommends rebuilding the strategy with a different hypothesis."
            ),
        }
        return summaries.get(diagnosis, top_evidence)
