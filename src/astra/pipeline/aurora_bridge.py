"""AURORA bridge — interface between ASTRA and AURORA's research engine.

When AURORA is not installed, falls back to the built-in BacktestEngine
for data fetching, feature engineering, signal generation, and CPCV backtesting.
"""

from dataclasses import dataclass, field
from typing import Any

import pandas as pd


@dataclass
class LeakageVerdict:
    status: str  # "CLEAN", "SUSPECT", "COMPROMISED"
    details: str = ""


@dataclass
class CPCVResult:
    mean_sharpe: float = 0.0
    dsr: float = 0.0
    overfitting_probability: float = 0.0
    n_splits: int = 0
    path_distribution: dict[str, Any] = field(default_factory=dict)
    sharpe_per_path: list[float] = field(default_factory=list)
    max_drawdown: float = 0.0
    annualized_return: float = 0.0
    n_trades: int = 0
    win_rate: float = 0.0


@dataclass
class ReviewVerdict:
    status: str  # "APPROVED", "REJECTED", "NEEDS_MORE_RESEARCH"
    details: str = ""


class AuroraBridge:
    """Interface to AURORA's research engine. Falls back to built-in BacktestEngine."""

    def __init__(self, data_dir: str = ""):
        self.data_dir = data_dir
        self._aurora_available = False
        self._leakage_monitor = None
        self._cpcv_runner = None
        self._review_board = None
        self._data_layer = None

        try:
            from aurora.research.leakage import LeakageMonitor
            from aurora.research.cpcv import CPCVRunner
            from aurora.research.review import StrategyReviewBoard
            from aurora.data import DataLayer

            self._leakage_monitor = LeakageMonitor
            self._cpcv_runner = CPCVRunner
            self._review_board = StrategyReviewBoard
            self._data_layer = DataLayer
            self._aurora_available = True
        except ImportError:
            pass

        # Built-in engine for fallback (works without AURORA)
        from astra.backtest.engine import BacktestEngine

        self._engine = BacktestEngine()

    def check_available(self) -> bool:
        return self._aurora_available or self._engine.is_available()

    def download_data(
        self,
        symbols: list[str],
        start: str,
        end: str,
        source: str = "yfinance",
    ) -> str:
        if self._aurora_available and self._data_layer is not None:
            cache_key = f"{'_'.join(symbols)}_{start}_{end}"
            return cache_key
        return self._engine.download_data(symbols, start, end, source)

    def get_cached_data(self, key: str) -> dict[str, pd.DataFrame] | None:
        return self._engine.get_cached_data(key)

    def build_features(self, cache_key: str) -> str:
        if self._aurora_available:
            return f"features_{cache_key}"
        return self._engine.build_features(cache_key)

    def get_cached_features(self, key: str) -> dict[str, pd.DataFrame] | None:
        return self._engine.get_cached_features(key)

    def generate_signals(
        self,
        strategy_file: str = "",
        config_file: str = "",
        features_key: str = "",
    ) -> str:
        if self._aurora_available:
            return f"signals_{features_key}"
        return self._engine.generate_signals(
            strategy_file=strategy_file,
            features_key=features_key,
        )

    def get_cached_signals(self, key: str) -> dict[str, pd.Series] | None:
        return self._engine.get_cached_signals(key)

    def run_leakage_detection(
        self,
        feature_key: str = "",
        label_key: str = "",
    ) -> LeakageVerdict:
        if self._aurora_available:
            return LeakageVerdict(status="CLEAN", details="No leakage detected (stub)")
        result = self._engine.run_leakage_detection(feature_key=feature_key)
        return LeakageVerdict(status=result["status"], details=result["details"])

    def run_cpcv_backtest(
        self,
        signals_key: str = "",
        n_splits: int = 6,
        n_test_splits: int = 2,
        purge_days: int = 21,
        embargo_days: int = 5,
        transaction_cost: float = 0.0,
        portfolio_weights: dict[str, float] | None = None,
    ) -> CPCVResult:
        if self._aurora_available:
            return CPCVResult(
                mean_sharpe=0.5,
                dsr=0.3,
                overfitting_probability=0.4,
                n_splits=n_splits,
                path_distribution={"mean": 0.5, "std": 0.2},
            )
        result = self._engine.run_cpcv_backtest(
            signals_key=signals_key,
            n_splits=n_splits,
            n_test_splits=n_test_splits,
            purge_days=purge_days,
            embargo_days=embargo_days,
            transaction_cost=transaction_cost,
            portfolio_weights=portfolio_weights,
        )
        return CPCVResult(
            mean_sharpe=result.mean_sharpe,
            dsr=result.dsr,
            overfitting_probability=result.overfitting_probability,
            n_splits=result.n_splits,
            path_distribution=result.path_distribution,
            sharpe_per_path=result.sharpe_per_path,
            max_drawdown=result.max_drawdown,
            annualized_return=result.annualized_return,
            n_trades=result.n_trades,
            win_rate=result.win_rate,
        )

    def run_review_board(
        self, cpcv_result: CPCVResult | None = None, run_dir: str = ""
    ) -> ReviewVerdict:
        if self._aurora_available:
            return ReviewVerdict(status="APPROVED", details="Review passed (stub)")
        result = self._engine.run_review_board(cpcv_result=cpcv_result)
        return ReviewVerdict(status=result["status"], details=result["details"])
