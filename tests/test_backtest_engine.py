"""Tests for BacktestEngine orchestrator — data, features, signals, CPCV, review."""

import os
import tempfile

import numpy as np
import pandas as pd
import pytest

from astra.backtest.engine import BacktestEngine, import_strategy_from_file
from astra.backtest.cpcv import CPCVResult


class TestImportStrategyFromFile:
    def test_imports_valid_strategy(self):
        with tempfile.NamedTemporaryFile(suffix=".py", mode="w", delete=False) as f:
            f.write("""
import pandas as pd
class TestStrategy:
    STRATEGY_TYPE = "test"
    def generate_signals(self, data):
        return pd.Series(1, index=data.index)
    def get_parameters(self):
        return {}
    def get_parameter_bounds(self):
        return {}
""")
            path = f.name
        try:
            cls = import_strategy_from_file(path)
            assert cls.STRATEGY_TYPE == "test"
            instance = cls()
            data = pd.DataFrame({"close": [100, 101]}, index=pd.date_range("2020-01-01", periods=2))
            signals = instance.generate_signals(data)
            assert list(signals) == [1, 1]
        finally:
            os.unlink(path)

    def test_raises_on_missing_file(self):
        with pytest.raises((ImportError, FileNotFoundError)):
            import_strategy_from_file("/nonexistent/file.py")

    def test_raises_on_no_strategy_class(self):
        with tempfile.NamedTemporaryFile(suffix=".py", mode="w", delete=False) as f:
            f.write("x = 1")
            path = f.name
        try:
            with pytest.raises(ImportError, match="No strategy class found"):
                import_strategy_from_file(path)
        finally:
            os.unlink(path)


class TestBacktestEngine:
    def test_is_available(self):
        engine = BacktestEngine()
        assert engine.is_available()

    def test_download_data_yfinance(self):
        engine = BacktestEngine()
        key = engine.download_data(["SPY"], "2023-01-01", "2023-01-10")
        assert key is not None
        data = engine.get_cached_data(key)
        assert data is not None
        assert "SPY" in data

    def test_download_data_lseg_fallback(self):
        engine = BacktestEngine()
        key = engine.download_data(["AAPL"], "2023-01-01", "2023-01-10", source="lseg")
        data = engine.get_cached_data(key)
        assert data is not None
        assert "AAPL" in data

    def test_download_multiple_symbols(self):
        engine = BacktestEngine()
        key = engine.download_data(["SPY", "QQQ"], "2023-01-01", "2023-01-10")
        data = engine.get_cached_data(key)
        assert len(data) == 2

    def test_build_features(self):
        engine = BacktestEngine()
        data_key = engine.download_data(["SPY"], "2023-01-01", "2023-01-31")
        feat_key = engine.build_features(data_key)
        assert feat_key.startswith("features_")
        features = engine.get_cached_features(feat_key)
        assert features is not None
        assert "SPY" in features
        assert "sma_20" in features["SPY"].columns

    def test_build_features_no_data(self):
        engine = BacktestEngine()
        with pytest.raises(ValueError, match="No cached data"):
            engine.build_features("nonexistent")

    def test_generate_signals(self):
        with tempfile.NamedTemporaryFile(suffix=".py", mode="w", delete=False) as f:
            f.write("""
import pandas as pd
class TestStrat:
    STRATEGY_TYPE = "test"
    def generate_signals(self, data):
        return pd.Series(1, index=data.index)
    def get_parameters(self):
        return {}
    def get_parameter_bounds(self):
        return {}
""")
            strategy_path = f.name
        try:
            engine = BacktestEngine()
            data_key = engine.download_data(["SPY"], "2023-01-01", "2023-01-15")
            feat_key = engine.build_features(data_key)
            sig_key = engine.generate_signals(strategy_file=strategy_path, features_key=feat_key)
            signals = engine.get_cached_signals(sig_key)
            assert "SPY" in signals
            assert (signals["SPY"] == 1).all()
        finally:
            os.unlink(strategy_path)

    def test_generate_signals_error_returns_zero(self):
        with tempfile.NamedTemporaryFile(suffix=".py", mode="w", delete=False) as f:
            f.write("""
import pandas as pd
class BadStrat:
    STRATEGY_TYPE = "bad"
    def generate_signals(self, data):
        raise ValueError("oops")
    def get_parameters(self):
        return {}
    def get_parameter_bounds(self):
        return {}
""")
            strategy_path = f.name
        try:
            engine = BacktestEngine()
            data_key = engine.download_data(["SPY"], "2023-01-01", "2023-01-15")
            feat_key = engine.build_features(data_key)
            sig_key = engine.generate_signals(strategy_file=strategy_path, features_key=feat_key)
            signals = engine.get_cached_signals(sig_key)
            assert (signals["SPY"] == 0).all()
        finally:
            os.unlink(strategy_path)

    def test_run_leakage_detection_clean(self):
        engine = BacktestEngine()
        data_key = engine.download_data(["SPY"], "2023-01-01", "2023-01-31")
        feat_key = engine.build_features(data_key)
        result = engine.run_leakage_detection(feature_key=feat_key)
        assert result["status"] in ("CLEAN", "SUSPECT")

    def test_run_leakage_detection_no_features(self):
        engine = BacktestEngine()
        result = engine.run_leakage_detection(feature_key="")
        assert result["status"] == "CLEAN"

    def test_run_cpcv_backtest_single_symbol(self):
        with tempfile.NamedTemporaryFile(suffix=".py", mode="w", delete=False) as f:
            f.write("""
import pandas as pd
class TestStrat:
    STRATEGY_TYPE = "test"
    def generate_signals(self, data):
        close = data["close"]
        signal = (close > close.rolling(20).mean()).astype(int)
        return signal
    def get_parameters(self):
        return {}
    def get_parameter_bounds(self):
        return {}
""")
            strategy_path = f.name
        try:
            engine = BacktestEngine()
            data_key = engine.download_data(["SPY"], "2023-01-01", "2023-06-30")
            feat_key = engine.build_features(data_key)
            sig_key = engine.generate_signals(strategy_file=strategy_path, features_key=feat_key)
            result = engine.run_cpcv_backtest(signals_key=sig_key)
            assert isinstance(result, CPCVResult)
            assert result.n_splits == 6
        finally:
            os.unlink(strategy_path)

    def test_run_cpcv_backtest_multi_symbol(self):
        with tempfile.NamedTemporaryFile(suffix=".py", mode="w", delete=False) as f:
            f.write("""
import pandas as pd
class TestStrat:
    STRATEGY_TYPE = "test"
    def generate_signals(self, data):
        close = data["close"]
        signal = (close > close.rolling(20).mean()).astype(int)
        return signal
    def get_parameters(self):
        return {}
    def get_parameter_bounds(self):
        return {}
""")
            strategy_path = f.name
        try:
            engine = BacktestEngine()
            data_key = engine.download_data(["SPY", "QQQ"], "2023-01-01", "2023-06-30")
            feat_key = engine.build_features(data_key)
            sig_key = engine.generate_signals(strategy_file=strategy_path, features_key=feat_key)
            result = engine.run_cpcv_backtest(signals_key=sig_key)
            assert isinstance(result, CPCVResult)
            assert result.n_splits == 6
        finally:
            os.unlink(strategy_path)

    def test_run_cpcv_backtest_no_signals(self):
        engine = BacktestEngine()
        result = engine.run_cpcv_backtest(signals_key="")
        assert result.mean_sharpe == 0.0

    def test_run_cpcv_backtest_with_transaction_cost(self):
        with tempfile.NamedTemporaryFile(suffix=".py", mode="w", delete=False) as f:
            f.write("""
import pandas as pd
class TestStrat:
    STRATEGY_TYPE = "test"
    def generate_signals(self, data):
        close = data["close"]
        signal = (close > close.rolling(20).mean()).astype(int)
        return signal
    def get_parameters(self):
        return {}
    def get_parameter_bounds(self):
        return {}
""")
            strategy_path = f.name
        try:
            engine = BacktestEngine()
            data_key = engine.download_data(["SPY"], "2023-01-01", "2023-06-30")
            feat_key = engine.build_features(data_key)
            sig_key = engine.generate_signals(strategy_file=strategy_path, features_key=feat_key)
            result_no_cost = engine.run_cpcv_backtest(signals_key=sig_key, transaction_cost=0.0)
            result_with_cost = engine.run_cpcv_backtest(signals_key=sig_key, transaction_cost=0.01)
            assert result_with_cost.mean_sharpe <= result_no_cost.mean_sharpe + 1e-10
        finally:
            os.unlink(strategy_path)

    def test_run_cpcv_backtest_with_portfolio_weights(self):
        with tempfile.NamedTemporaryFile(suffix=".py", mode="w", delete=False) as f:
            f.write("""
import pandas as pd
class TestStrat:
    STRATEGY_TYPE = "test"
    def generate_signals(self, data):
        close = data["close"]
        signal = (close > close.rolling(20).mean()).astype(int)
        return signal
    def get_parameters(self):
        return {}
    def get_parameter_bounds(self):
        return {}
""")
            strategy_path = f.name
        try:
            engine = BacktestEngine()
            data_key = engine.download_data(["SPY", "QQQ"], "2023-01-01", "2023-06-30")
            feat_key = engine.build_features(data_key)
            sig_key = engine.generate_signals(strategy_file=strategy_path, features_key=feat_key)
            weights = {"SPY": 0.7, "QQQ": 0.3}
            result = engine.run_cpcv_backtest(signals_key=sig_key, portfolio_weights=weights)
            assert isinstance(result, CPCVResult)
        finally:
            os.unlink(strategy_path)

    def test_run_review_board_passed(self):
        result = CPCVResult(
            mean_sharpe=1.8,
            dsr=0.95,
            overfitting_probability=0.05,
            n_splits=6,
            max_drawdown=0.08,
            annualized_return=0.15,
            n_trades=120,
            win_rate=0.6,
        )
        engine = BacktestEngine()
        review = engine.run_review_board(cpcv_result=result)
        assert review["status"] == "APPROVED"
        assert review["score"] >= 60

    def test_run_review_board_rejected(self):
        result = CPCVResult(
            mean_sharpe=0.1,
            dsr=0.1,
            overfitting_probability=0.9,
            n_splits=6,
            max_drawdown=0.5,
            annualized_return=-0.1,
            n_trades=2,
            win_rate=0.3,
        )
        engine = BacktestEngine()
        review = engine.run_review_board(cpcv_result=result)
        assert review["status"] == "REJECTED"

    def test_run_review_board_none(self):
        engine = BacktestEngine()
        review = engine.run_review_board(cpcv_result=None)
        assert review["status"] == "REJECTED"

    def test_full_pipeline(self):
        with tempfile.NamedTemporaryFile(suffix=".py", mode="w", delete=False) as f:
            f.write("""
import pandas as pd
class TestStrat:
    STRATEGY_TYPE = "test"
    def generate_signals(self, data):
        close = data["close"]
        signal = (close > close.rolling(20).mean()).astype(int)
        return signal
    def get_parameters(self):
        return {}
    def get_parameter_bounds(self):
        return {}
""")
            strategy_path = f.name
        try:
            engine = BacktestEngine()
            data_key = engine.download_data(["SPY"], "2023-01-01", "2023-06-30")
            feat_key = engine.build_features(data_key)
            sig_key = engine.generate_signals(strategy_file=strategy_path, features_key=feat_key)
            leak_result = engine.run_leakage_detection(feature_key=feat_key)
            cpcv_result = engine.run_cpcv_backtest(signals_key=sig_key)
            review = engine.run_review_board(cpcv_result=cpcv_result)
            assert leak_result["status"] in ("CLEAN", "SUSPECT")
            assert isinstance(cpcv_result, CPCVResult)
            assert review["status"] in ("APPROVED", "REJECTED")
        finally:
            os.unlink(strategy_path)
