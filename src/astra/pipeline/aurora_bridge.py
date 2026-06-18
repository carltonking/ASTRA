"""AURORA bridge — interface between ASTRA and AURORA's research-validation engine.

When AURORA (`aurora-trading-research`) is installed, the validation steps —
leakage detection, CPCV backtesting, and the review board — are delegated to
AURORA's institutional implementations. When it is not installed, the bridge
falls back to ASTRA's built-in BacktestEngine so the pipeline still runs.

Data fetching, feature engineering, and signal generation always use ASTRA's
engine (its in-memory caches are what the rest of the pipeline consumes); AURORA
is layered on top purely for validation. The adapters below pull the cached
signals/features back out of the engine and feed them to AURORA.

Activate AURORA locally with:  uv sync --extra aurora
"""

from __future__ import annotations

import json
import shutil
import tempfile
from dataclasses import dataclass, field
from datetime import UTC, datetime
from pathlib import Path
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


# AURORA review-board status -> ASTRA ReviewVerdict status.
_AURORA_REVIEW_STATUS_MAP = {
    "APPROVED_FOR_PAPER_SIMULATION": "APPROVED",
    "NEEDS_MORE_RESEARCH": "NEEDS_MORE_RESEARCH",
    "REJECTED": "REJECTED",
}

# Safety flags AURORA's review board requires in the manifest. ASTRA's pipeline
# is research-only and never places orders, so these are all satisfied.
_RESEARCH_ONLY_SAFETY_FLAGS = {
    "research_only": True,
    "placed_orders": False,
    "used_broker": False,
    "wrote_ledger": False,
    "external_llm_calls": False,
}


class AuroraBridge:
    """Interface to AURORA's research engine. Falls back to built-in BacktestEngine."""

    def __init__(self, data_dir: str = ""):
        self.data_dir = data_dir
        self._aurora_available = False

        # AURORA validation entry points (populated when the package is present).
        self._aurora_run_cpcv = None
        self._aurora_cpcv_config = None
        self._aurora_leakage_monitor = None
        self._aurora_review_run = None
        self._aurora_review_config = None

        try:
            from aurora.validation.cpcv import CPCVConfig, run_cpcv_validation
            from aurora.validation.leakage_monitor import LeakageMonitor
            from aurora.review.board import ReviewBoardConfig, review_research_run

            self._aurora_run_cpcv = run_cpcv_validation
            self._aurora_cpcv_config = CPCVConfig
            self._aurora_leakage_monitor = LeakageMonitor
            self._aurora_review_run = review_research_run
            self._aurora_review_config = ReviewBoardConfig
            self._aurora_available = True
        except ImportError:
            pass

        # Built-in engine: always used for data/features/signals, and as the
        # validation fallback when AURORA is unavailable.
        from astra.backtest.engine import BacktestEngine

        self._engine = BacktestEngine()

    def check_available(self) -> bool:
        return self._aurora_available or self._engine.is_available()

    def using_aurora(self) -> bool:
        """True when validation is being delegated to AURORA."""
        return self._aurora_available

    # ------------------------------------------------------------------
    # Data / features / signals — always delegated to ASTRA's engine.
    # ------------------------------------------------------------------
    def download_data(
        self,
        symbols: list[str],
        start: str,
        end: str,
        source: str = "yfinance",
    ) -> str:
        return self._engine.download_data(symbols, start, end, source)

    def get_cached_data(self, key: str) -> dict[str, pd.DataFrame] | None:
        return self._engine.get_cached_data(key)

    def build_features(self, cache_key: str) -> str:
        return self._engine.build_features(cache_key)

    def get_cached_features(self, key: str) -> dict[str, pd.DataFrame] | None:
        return self._engine.get_cached_features(key)

    def generate_signals(
        self,
        strategy_file: str = "",
        config_file: str = "",
        features_key: str = "",
    ) -> str:
        return self._engine.generate_signals(
            strategy_file=strategy_file,
            features_key=features_key,
        )

    def get_cached_signals(self, key: str) -> dict[str, pd.Series] | None:
        return self._engine.get_cached_signals(key)

    # ------------------------------------------------------------------
    # Validation — delegated to AURORA when available.
    # ------------------------------------------------------------------
    def run_leakage_detection(
        self,
        feature_key: str = "",
        label_key: str = "",
        horizon_days: int = 5,
    ) -> LeakageVerdict:
        if not self._aurora_available:
            result = self._engine.run_leakage_detection(feature_key=feature_key)
            return LeakageVerdict(status=result["status"], details=result["details"])

        features = self._engine.get_cached_features(feature_key) or {}
        if not features:
            return LeakageVerdict(status="CLEAN", details="No features to check")

        # Run AURORA's leakage monitor per symbol; worst verdict wins.
        severity = {"CLEAN": 0, "SUSPECT": 1, "COMPROMISED": 2}
        worst = "CLEAN"
        notes: list[str] = []
        run_dir = tempfile.mkdtemp(prefix="astra_aurora_leakage_")
        try:
            for symbol, feature_df in features.items():
                label = self._forward_return_label(feature_df, horizon_days)
                if label is None:
                    continue
                feat = feature_df.drop(columns=["close"], errors="ignore")
                monitor = self._aurora_leakage_monitor(
                    run_dir=run_dir,
                    feature_df=feat,
                    label_series=label,
                    horizon_days=horizon_days,
                    block_on_compromised=False,
                )
                report = monitor.run()
                verdict = str(report.get("verdict", "CLEAN")).upper()
                if severity.get(verdict, 0) > severity.get(worst, 0):
                    worst = verdict
                notes.append(f"{symbol}:{verdict}")
        finally:
            shutil.rmtree(run_dir, ignore_errors=True)

        return LeakageVerdict(status=worst, details="; ".join(notes) or "AURORA leakage scan")

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
        if not self._aurora_available:
            result = self._engine.run_cpcv_backtest(
                signals_key=signals_key,
                n_splits=n_splits,
                n_test_splits=n_test_splits,
                purge_days=purge_days,
                embargo_days=embargo_days,
                transaction_cost=transaction_cost,
                portfolio_weights=portfolio_weights,
            )
            return self._engine_cpcv_to_bridge(result)

        signals = self._engine.get_cached_signals(signals_key) or {}
        # signals_key is f"signals_{features_key}"; invert by stripping the prefix.
        feat_key = (
            signals_key[len("signals_"):]
            if signals_key.startswith("signals_")
            else signals_key
        )
        features = self._engine.get_cached_features(feat_key) or {}

        df = self._build_aurora_cpcv_frame(signals, features)
        if df is None or df.empty:
            return CPCVResult(overfitting_probability=1.0, n_splits=n_splits)

        config = self._aurora_cpcv_config(
            n_splits=n_splits,
            n_test_splits=n_test_splits,
            purge_days=purge_days,
            embargo_days=embargo_days,
            signal_col="signal",
            price_col="close",
            timestamp_col="timestamp",
            # ASTRA transaction_cost is a fraction; AURORA models cost as slippage bps.
            slippage_bps=transaction_cost * 10_000.0,
            commission_per_trade=0.0,
        )
        result = self._aurora_run_cpcv(df, config, observed_sharpe=0.0)
        return self._aurora_cpcv_to_bridge(result)

    def run_review_board(
        self, cpcv_result: CPCVResult | None = None, run_dir: str = ""
    ) -> ReviewVerdict:
        if not self._aurora_available:
            result = self._engine.run_review_board(cpcv_result=cpcv_result)
            return ReviewVerdict(status=result["status"], details=result["details"])

        if cpcv_result is None:
            return ReviewVerdict(status="REJECTED", details="No backtest data")

        work_dir = Path(tempfile.mkdtemp(prefix="astra_aurora_review_"))
        try:
            self._write_review_artifacts(work_dir, cpcv_result)
            config = self._aurora_review_config(
                run_dir=str(work_dir),
                require_diagnostics=False,
                require_manifest_safety_flags=True,
            )
            result = self._aurora_review_run(config)
            status = _AURORA_REVIEW_STATUS_MAP.get(result.status, "NEEDS_MORE_RESEARCH")
            critical = [f.message for f in result.findings if f.severity == "CRITICAL"]
            details = "; ".join(critical) if critical else f"AURORA review: {result.status}"
            return ReviewVerdict(status=status, details=details)
        finally:
            shutil.rmtree(work_dir, ignore_errors=True)

    # ------------------------------------------------------------------
    # Adapters / helpers.
    # ------------------------------------------------------------------
    @staticmethod
    def _forward_return_label(feature_df: pd.DataFrame, horizon_days: int) -> pd.Series | None:
        """Forward return over `horizon_days` — the label AURORA tests features against."""
        if "close" not in feature_df.columns:
            return None
        close = feature_df["close"]
        return close.pct_change(horizon_days).shift(-horizon_days).rename("label")

    @staticmethod
    def _build_aurora_cpcv_frame(
        signals: dict[str, pd.Series],
        features: dict[str, pd.DataFrame],
    ) -> pd.DataFrame | None:
        """Build a (timestamp, signal, close) frame for AURORA's single-series CPCV.

        Single symbol: used directly. Multi symbol: collapsed into an equal-weight
        portfolio — mean signal over an index of normalized prices.
        """
        usable = {
            s: sig for s, sig in signals.items()
            if s in features and "close" in features[s].columns
        }
        if not usable:
            return None

        if len(usable) == 1:
            symbol = next(iter(usable))
            close = features[symbol]["close"]
            frame = pd.concat([usable[symbol].rename("signal"), close.rename("close")], axis=1)
        else:
            sig_df = pd.DataFrame({s: usable[s] for s in usable})
            close_df = pd.DataFrame({s: features[s]["close"] for s in usable})
            close_df = close_df.reindex(sig_df.index)
            normalized = close_df / close_df.bfill().iloc[0]
            frame = pd.DataFrame(
                {
                    "signal": sig_df.mean(axis=1),
                    "close": normalized.mean(axis=1),
                }
            )

        frame = frame.dropna()
        if frame.empty:
            return None
        frame.index.name = "timestamp"
        return frame.reset_index()

    @staticmethod
    def _aurora_cpcv_to_bridge(result: Any) -> CPCVResult:
        """Map AURORA's CPCVResult (summary dict + paths) into ASTRA's CPCVResult."""
        summary = result.summary or {}
        paths = result.paths or []
        sharpes = [p.sharpe_ratio for p in paths]
        n = len(paths)
        return CPCVResult(
            mean_sharpe=float(summary.get("mean_path_sharpe", 0.0)),
            dsr=float(summary.get("deflated_sharpe_ratio", 0.0)),
            overfitting_probability=float(summary.get("backtest_overfitting_probability", 0.0)),
            n_splits=int(summary.get("n_paths_tested", n)),
            path_distribution={
                "mean": float(summary.get("mean_path_sharpe", 0.0)),
                "std": float(summary.get("sharpe_std", 0.0)),
                "worst": float(summary.get("worst_path_sharpe", 0.0)),
                "best": float(summary.get("best_path_sharpe", 0.0)),
            },
            sharpe_per_path=sharpes,
            max_drawdown=min((p.max_drawdown for p in paths), default=0.0),
            annualized_return=(sum(p.total_return for p in paths) / n) if n else 0.0,
            n_trades=sum(p.trade_count for p in paths),
            win_rate=(sum(p.win_rate for p in paths) / n) if n else 0.0,
        )

    @staticmethod
    def _engine_cpcv_to_bridge(result: Any) -> CPCVResult:
        """Map ASTRA engine's native CPCVResult into the bridge's CPCVResult."""
        return CPCVResult(
            mean_sharpe=result.mean_sharpe,
            dsr=result.dsr,
            overfitting_probability=result.overfitting_probability,
            n_splits=result.n_splits,
            path_distribution=getattr(result, "path_distribution", {}) or {},
            sharpe_per_path=getattr(result, "sharpe_per_path", []) or [],
            max_drawdown=getattr(result, "max_drawdown", 0.0),
            annualized_return=getattr(result, "annualized_return", 0.0),
            n_trades=getattr(result, "n_trades", 0),
            win_rate=getattr(result, "win_rate", 0.0),
        )

    @staticmethod
    def _write_review_artifacts(run_dir: Path, cpcv_result: CPCVResult) -> None:
        """Write the minimal manifest/backtest/cpcv artifacts AURORA's board reads."""
        manifest = {
            "run_id": run_dir.name,
            "strategy_id": "astra_pipeline",
            "created_at": datetime.now(UTC).isoformat(),
            "safety_flags": dict(_RESEARCH_ONLY_SAFETY_FLAGS),
            "artifacts": {
                "backtest": "backtest.json",
                "cpcv": "cpcv_report.json",
            },
        }
        backtest = {
            "metrics": {
                "trade_count": int(cpcv_result.n_trades),
                # AURORA expects max_drawdown as a negative fraction.
                "max_drawdown": -abs(float(cpcv_result.max_drawdown)),
                "sharpe_ratio": float(cpcv_result.mean_sharpe),
                "win_rate": float(cpcv_result.win_rate),
                "annualized_return": float(cpcv_result.annualized_return),
            }
        }
        cpcv_report = {
            "summary": {
                "n_paths_tested": int(cpcv_result.n_splits),
                "mean_path_sharpe": float(cpcv_result.mean_sharpe),
                "deflated_sharpe_ratio": float(cpcv_result.dsr),
                "backtest_overfitting_probability": float(cpcv_result.overfitting_probability),
            }
        }
        (run_dir / "manifest.json").write_text(json.dumps(manifest, indent=2), encoding="utf-8")
        (run_dir / "backtest.json").write_text(json.dumps(backtest, indent=2), encoding="utf-8")
        (run_dir / "cpcv_report.json").write_text(
            json.dumps(cpcv_report, indent=2), encoding="utf-8"
        )
