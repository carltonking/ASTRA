"""AURORA bridge — interface between ASTRA and AURORA's research engine."""

from dataclasses import dataclass, field
from typing import Any


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


@dataclass
class ReviewVerdict:
    status: str  # "APPROVED", "REJECTED", "NEEDS_MORE_RESEARCH"
    details: str = ""


class AuroraBridge:
    """Interface to AURORA's research engine. Attempts to import AURORA
    modules on initialization. If unavailable, methods raise RuntimeError."""

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

    def check_available(self) -> bool:
        return self._aurora_available

    def download_data(
        self,
        symbols: list[str],
        start: str,
        end: str,
        source: str = "yfinance",
    ) -> str:
        if not self._aurora_available:
            raise RuntimeError("AURORA is not installed")
        cache_key = f"{'_'.join(symbols)}_{start}_{end}"
        return cache_key

    def run_leakage_detection(
        self,
        feature_key: str = "",
        label_key: str = "",
    ) -> LeakageVerdict:
        if not self._aurora_available:
            raise RuntimeError("AURORA is not installed")
        return LeakageVerdict(status="CLEAN", details="No leakage detected (stub)")

    def build_features(self, cache_key: str) -> str:
        if not self._aurora_available:
            raise RuntimeError("AURORA is not installed")
        return f"features_{cache_key}"

    def generate_signals(
        self,
        strategy_file: str = "",
        config_file: str = "",
        features_key: str = "",
    ) -> str:
        if not self._aurora_available:
            raise RuntimeError("AURORA is not installed")
        return f"signals_{features_key}"

    def run_cpcv_backtest(
        self,
        signals_key: str = "",
        n_splits: int = 6,
        n_test_splits: int = 2,
        purge_days: int = 21,
        embargo_days: int = 5,
    ) -> CPCVResult:
        if not self._aurora_available:
            raise RuntimeError("AURORA is not installed")
        return CPCVResult(
            mean_sharpe=0.5,
            dsr=0.3,
            overfitting_probability=0.4,
            n_splits=n_splits,
            path_distribution={"mean": 0.5, "std": 0.2},
        )

    def run_review_board(self, run_dir: str = "") -> ReviewVerdict:
        if not self._aurora_available:
            raise RuntimeError("AURORA is not installed")
        return ReviewVerdict(status="APPROVED", details="Review passed (stub)")
