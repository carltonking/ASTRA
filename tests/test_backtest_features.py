"""Tests for feature engineering — technical indicators from OHLCV data."""

import numpy as np
import pandas as pd
import pytest

from astra.backtest.features import compute_features, compute_features_for_symbols


def _make_ohlcv(n=500):
    np.random.seed(42)
    close = np.cumsum(np.random.randn(n)) + 100
    df = pd.DataFrame({
        "open": close * (1 + np.random.randn(n) * 0.005),
        "high": close * (1 + np.abs(np.random.randn(n)) * 0.01),
        "low": close * (1 - np.abs(np.random.randn(n)) * 0.01),
        "close": close,
        "volume": np.random.randint(100000, 1000000, n),
    })
    return df


class TestComputeFeatures:
    def test_returns_dataframe(self):
        df = _make_ohlcv()
        result = compute_features(df)
        assert isinstance(result, pd.DataFrame)

    def test_original_columns_preserved(self):
        df = _make_ohlcv()
        result = compute_features(df)
        for col in df.columns:
            assert col in result.columns

    def test_returns_added(self):
        df = _make_ohlcv()
        result = compute_features(df)
        assert "returns" in result.columns
        assert "log_returns" in result.columns

    def test_moving_averages_added(self):
        df = _make_ohlcv()
        result = compute_features(df)
        for w in [5, 10, 20, 50, 100, 200]:
            assert f"sma_{w}" in result.columns
            assert f"ema_{w}" in result.columns

    def test_rsi_added(self):
        df = _make_ohlcv()
        result = compute_features(df)
        assert "rsi_14" in result.columns

    def test_macd_added(self):
        df = _make_ohlcv()
        result = compute_features(df)
        assert "macd" in result.columns
        assert "macd_signal" in result.columns
        assert "macd_hist" in result.columns

    def test_bollinger_bands_added(self):
        df = _make_ohlcv()
        result = compute_features(df)
        assert "bb_upper" in result.columns
        assert "bb_lower" in result.columns
        assert "bb_width" in result.columns
        assert "bb_position" in result.columns

    def test_atr_added(self):
        df = _make_ohlcv()
        result = compute_features(df)
        assert "atr_14" in result.columns

    def test_volume_features_added(self):
        df = _make_ohlcv()
        result = compute_features(df)
        assert "volume_sma_20" in result.columns
        assert "volume_ratio" in result.columns

    def test_rsi_bounds(self):
        df = _make_ohlcv()
        result = compute_features(df)
        rsi = result["rsi_14"].dropna()
        assert (rsi >= 0).all()
        assert (rsi <= 100).all()

    def test_bb_position_exists(self):
        df = _make_ohlcv()
        result = compute_features(df)
        bb_pos = result["bb_position"].dropna()
        assert len(bb_pos) > 0
        assert not bb_pos.isna().all()

    def test_first_rows_have_nans(self):
        df = _make_ohlcv()
        result = compute_features(df)
        assert result.iloc[0].isna().any()

    def test_input_not_mutated(self):
        df = _make_ohlcv()
        df_copy = df.copy()
        compute_features(df)
        pd.testing.assert_frame_equal(df, df_copy)

    def test_returns_on_small_dataframe(self):
        df = _make_ohlcv(10)
        result = compute_features(df)
        assert len(result) == 10

    def test_no_crash_with_missing_columns(self):
        df = pd.DataFrame({"close": np.cumsum(np.random.randn(100)) + 100})
        result = compute_features(df)
        assert "sma_5" in result.columns

    def test_volume_ratio(self):
        df = _make_ohlcv()
        result = compute_features(df)
        vol_ratio = result["volume_ratio"].dropna()
        assert (vol_ratio >= 0).all()


class TestComputeFeaturesForSymbols:
    def test_basic(self):
        dfs = {
            "A": _make_ohlcv(100),
            "B": _make_ohlcv(100),
        }
        result = compute_features_for_symbols(dfs)
        assert set(result.keys()) == {"A", "B"}
        for df in result.values():
            assert isinstance(df, pd.DataFrame)
            assert "sma_20" in df.columns

    def test_empty_input(self):
        result = compute_features_for_symbols({})
        assert result == {}

    def test_preserves_index(self):
        dfs = {"A": _make_ohlcv(100)}
        result = compute_features_for_symbols(dfs)
        pd.testing.assert_index_equal(result["A"].index, dfs["A"].index)
