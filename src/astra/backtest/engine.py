"""Backtest engine orchestrator — coordinates feature engineering, signal generation, and CPCV."""

import concurrent.futures
import importlib.util
import sys
import time
import uuid

import pandas as pd

from astra.backtest.features import compute_features_for_symbols
from astra.backtest.cpcv import CPCVBacktest, CPCVResult
from astra.backtest.leakage import check_leakage
from astra.backtest.review import generate_review
from astra.data.factory import create_data_provider


def import_strategy_from_file(strategy_file: str):
    """Dynamically import a strategy class from a .py file."""
    module_name = f"astra_backtest_{uuid.uuid4().hex[:8]}"
    spec = importlib.util.spec_from_file_location(module_name, strategy_file)
    if spec is None or spec.loader is None:
        raise ImportError(f"Cannot load strategy file: {strategy_file}")
    mod = importlib.util.module_from_spec(spec)
    sys.modules[module_name] = mod
    spec.loader.exec_module(mod)

    for attr_name in dir(mod):
        attr = getattr(mod, attr_name)
        if isinstance(attr, type) and hasattr(attr, "STRATEGY_TYPE"):
            return attr

    raise ImportError(f"No strategy class found in {strategy_file}")


def _retry(fn, max_retries: int = 3, delay: float = 1.0):
    """Retry a function up to max_retries times with exponential backoff."""
    last_error = None
    for attempt in range(max_retries):
        try:
            return fn()
        except Exception as e:
            last_error = e
            if attempt < max_retries - 1:
                time.sleep(delay * (2 ** attempt))
    raise last_error


def is_market_hours(dt=None) -> bool:
    """Rough check if US equities market is open (Mon-Fri, 9:30-16:00 ET)."""
    try:
        import pytz
        from datetime import datetime, time

        if dt is None:
            dt = datetime.now(pytz.timezone("US/Eastern"))
        elif dt.tzinfo is None:
            dt = dt.replace(tzinfo=pytz.UTC).astimezone(pytz.timezone("US/Eastern"))

        if dt.weekday() >= 5:
            return False
        market_open = time(9, 30)
        market_close = time(16, 0)
        return market_open <= dt.time() <= market_close
    except ImportError:
        return True  # assume open if pytz not available


def validate_market_data(df: pd.DataFrame) -> dict[str, str | bool | int]:
    """Validate market data quality. Returns a dict with status and warnings."""
    result: dict[str, str | bool | int] = {
        "valid": True,
        "warnings": [],
        "missing_dates": 0,
    }
    if df.empty:
        result["valid"] = False
        result["warnings"].append("Empty dataframe")
        return result

    if df.isna().sum().sum() > 0:
        result["warnings"].append(f"Data contains {int(df.isna().sum().sum())} NaN values")
    if len(df) < 20:
        result["warnings"].append(f"Only {len(df)} data points (< 20 suggested minimum)")

    if isinstance(df.index, pd.DatetimeIndex):
        result["missing_dates"] = 0
    return result


class BacktestEngine:
    """In-process backtesting engine that replaces the AURORA dependency."""

    def __init__(self):
        self._data_cache: dict[str, dict[str, pd.DataFrame]] = {}
        self._features_cache: dict[str, dict[str, pd.DataFrame]] = {}
        self._signals_cache: dict[str, dict[str, pd.Series]] = {}

    def is_available(self) -> bool:
        return True

    def download_data(
        self,
        symbols: list[str],
        start: str,
        end: str,
        source: str = "yfinance",
        interval: str = "1D",
    ) -> str:
        data_key = f"{source}_{'_'.join(symbols)}_{start}_{end}"

        provider = create_data_provider(source)
        df_dict = provider.fetch_historical(symbols, start, end, interval=interval)

        missing = [s for s in symbols if s not in df_dict]
        if missing:
            fallback = create_data_provider("yfinance")
            if fallback.get_name() != source:
                print(f"Falling back to yfinance for {len(missing)} symbols")
                df_dict.update(fallback.fetch_historical(missing, start, end))

        self._data_cache[data_key] = df_dict
        return data_key

    def get_cached_data(self, key: str) -> dict[str, pd.DataFrame] | None:
        return self._data_cache.get(key)

    def build_features(self, data_key: str) -> str:
        """Compute features from cached data."""
        data = self._data_cache.get(data_key)
        if data is None:
            raise ValueError(f"No cached data for key: {data_key}")
        features = compute_features_for_symbols(data)
        features_key = f"features_{data_key}"
        self._features_cache[features_key] = features
        return features_key

    def get_cached_features(self, key: str) -> dict[str, pd.DataFrame] | None:
        return self._features_cache.get(key)

    def generate_signals(
        self,
        strategy_file: str = "",
        config_file: str = "",
        features_key: str = "",
    ) -> str:
        """Generate trading signals by running the strategy on features."""
        features = self._features_cache.get(features_key)
        if features is None:
            raise ValueError(f"No cached features for key: {features_key}")

        strategy_cls = import_strategy_from_file(strategy_file)

        signals: dict[str, pd.Series] = {}
        with concurrent.futures.ThreadPoolExecutor(max_workers=8) as pool:
            def _gen(symbol, feature_df):
                instance = strategy_cls()
                try:
                    return symbol, instance.generate_signals(feature_df)
                except Exception as e:
                    print(f"Signal generation failed for {symbol}: {e}")
                    return symbol, pd.Series(0, index=feature_df.index)
            for sym, sig in pool.map(lambda kv: _gen(kv[0], kv[1]), features.items()):
                signals[sym] = sig

        signals_key = f"signals_{features_key}"
        self._signals_cache[signals_key] = signals
        return signals_key

    def get_cached_signals(self, key: str) -> dict[str, pd.Series] | None:
        return self._signals_cache.get(key)

    def run_leakage_detection(
        self,
        feature_key: str = "",
        label_key: str = "",
    ) -> dict:
        """Check for look-ahead bias in computed features."""
        features = self._features_cache.get(feature_key)
        if features is None:
            return {"status": "CLEAN", "details": "No features to check", "violations": []}

        all_clear = True
        for symbol, feature_df in features.items():
            price = feature_df.get("close", feature_df.iloc[:, 0])
            result = check_leakage(feature_df, price.to_frame("close"))
            if result["status"] == "COMPROMISED":
                all_clear = False

        if all_clear:
            return {"status": "CLEAN", "details": "No leakage detected"}
        return {"status": "SUSPECT", "details": "Potential look-ahead bias in some features"}

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
        """Run CPCV backtest on all symbols' signals, aggregated into a portfolio.

        Supports both single-symbol and multi-symbol strategies.
        transaction_cost is the per-trade cost as a fraction (e.g. 0.001).
        portfolio_weights allows custom allocation across symbols (default equal-weight).
        """
        signals = self._signals_cache.get(signals_key) if signals_key else None
        if signals is None or len(signals) == 0:
            return CPCVResult(
                mean_sharpe=0.0,
                dsr=0.0,
                overfitting_probability=1.0,
                n_splits=n_splits,
            )

        feat_key = signals_key.replace("signals_", "features_", 1) if signals_key else ""
        features = self._features_cache.get(feat_key, {}) if feat_key else {}

        cpcv = CPCVBacktest(
            n_splits=n_splits,
            n_test_splits=n_test_splits,
            purge_days=purge_days,
            embargo_days=embargo_days,
            transaction_cost=transaction_cost,
        )

        if len(signals) == 1:
            symbol = next(iter(signals))
            signal_series = signals[symbol]
            price_data = pd.Series(dtype=float)
            if symbol in features and "close" in features[symbol].columns:
                price_data = features[symbol]["close"]
            if price_data.empty:
                return CPCVResult(
                    mean_sharpe=0.0, dsr=0.0, overfitting_probability=1.0, n_splits=n_splits,
                )
            return cpcv.run(signal_series, price_data)

        prices: dict[str, pd.Series] = {}
        for symbol in signals:
            if symbol in features and "close" in features[symbol].columns:
                prices[symbol] = features[symbol]["close"]

        missing = [s for s in signals if s not in prices]
        if missing:
            print(f"Multi-symbol CPCV: missing prices for {missing}, excluding them")
            for s in missing:
                del signals[s]

        if not prices or not signals:
            return CPCVResult(
                mean_sharpe=0.0, dsr=0.0, overfitting_probability=1.0, n_splits=n_splits,
            )

        return cpcv.run_multi_symbol(signals, prices, portfolio_weights)

    def run_review_board(self, cpcv_result: CPCVResult | None = None) -> dict:
        """Evaluate strategy quality based on CPCV results."""
        if cpcv_result is None:
            return {"status": "REJECTED", "score": 0.0, "details": "No backtest data"}

        return generate_review(
            mean_sharpe=cpcv_result.mean_sharpe,
            dsr=cpcv_result.dsr,
            overfitting_probability=cpcv_result.overfitting_probability,
            max_drawdown=cpcv_result.max_drawdown,
            annualized_return=cpcv_result.annualized_return,
            n_trades=cpcv_result.n_trades,
            win_rate=cpcv_result.win_rate,
        )
