"""Tests for CPCV (Combinatorial Purged Cross-Validation) backtesting."""

import numpy as np
import pandas as pd
import pytest

from astra.backtest.cpcv import (
    CPCVResult,
    cpcv_split_indices,
    run_single_backtest,
    CPCVBacktest,
)


class TestCPCVSplitIndices:
    def test_basic_split(self):
        indices = cpcv_split_indices(n_observations=1000, n_splits=6, n_test_splits=2)
        assert len(indices) > 0
        for split in indices:
            assert "train" in split
            assert "test" in split
            train_start, train_end = split["train"]
            assert train_start < train_end

    def test_minimum_splits(self):
        with pytest.raises(ValueError, match="n_splits must be >= 2"):
            cpcv_split_indices(n_observations=100, n_splits=1)

    def test_test_splits_less_than_total(self):
        with pytest.raises(ValueError, match="n_test_splits must be < n_splits"):
            cpcv_split_indices(n_observations=100, n_splits=3, n_test_splits=3)

    def test_returns_empty_for_short_data(self):
        indices = cpcv_split_indices(n_observations=3, n_splits=6)
        assert len(indices) == 0

    def test_purge_and_embargo_applied(self):
        indices = cpcv_split_indices(
            n_observations=1000, n_splits=6, n_test_splits=2, purge_days=50, embargo_days=10
        )
        assert len(indices) > 0
        for split in indices:
            train_end = split["train"][1]
            test_start = min(s for s, _ in split["test"])
            assert train_end < test_start

    def test_all_test_splits_covered(self):
        n_splits = 6
        n_test = 2
        indices = cpcv_split_indices(n_observations=600, n_splits=n_splits, n_test_splits=n_test)
        expected_combos = 15
        assert len(indices) <= expected_combos

    def test_each_split_has_multiple_test_segments(self):
        indices = cpcv_split_indices(n_observations=600, n_splits=4, n_test_splits=2)
        for split in indices:
            assert len(split["test"]) == 2


class TestRunSingleBacktest:
    def test_returns_expected_keys(self):
        prices = pd.Series(np.cumsum(np.random.randn(100)) + 100)
        signals = pd.Series(np.random.choice([0, 1], 100))
        result = run_single_backtest(signals, prices)
        assert "sharpe" in result
        assert "returns" in result
        assert "equity" in result
        assert "n_trades" in result

    def test_transaction_cost_affects_returns(self):
        prices = pd.Series(np.cumsum(np.random.randn(100)) + 100)
        signals = pd.Series([0, 1, 1, 1, 0] * 20)
        result_no_cost = run_single_backtest(signals, prices, transaction_cost=0.0)
        result_with_cost = run_single_backtest(signals, prices, transaction_cost=0.01)
        assert result_with_cost["sharpe"] <= result_no_cost["sharpe"]

    def test_constant_signal_zero_trades(self):
        rng = np.random.default_rng(42)
        prices = pd.Series(np.cumsum(rng.normal(0, 1, 100)) + 100)
        signals = pd.Series([1] * 100)
        result = run_single_backtest(signals, prices)
        assert result["n_trades"] == 0 or result["n_trades"] == 1  # first diff is NaN


class TestCPCVBacktest:
    def _make_test_data(self, n=500):
        np.random.seed(42)
        prices = pd.Series(np.cumsum(np.random.randn(n)) + 100)
        signals = pd.Series(np.random.choice([0, 1], n))
        return signals, prices

    def test_run_returns_cpcv_result(self):
        signals, prices = self._make_test_data()
        cpcv = CPCVBacktest(n_splits=6, n_test_splits=2)
        result = cpcv.run(signals, prices)
        assert isinstance(result, CPCVResult)
        assert result.n_splits == 6

    def test_run_returns_metrics(self):
        signals, prices = self._make_test_data()
        cpcv = CPCVBacktest()
        result = cpcv.run(signals, prices)
        assert isinstance(result.mean_sharpe, float)
        assert isinstance(result.dsr, float)
        assert 0 <= result.overfitting_probability <= 1.0
        assert isinstance(result.max_drawdown, float)
        assert isinstance(result.annualized_return, float)
        assert isinstance(result.n_trades, int)
        assert isinstance(result.win_rate, float)

    def test_run_sharpe_per_path(self):
        signals, prices = self._make_test_data()
        cpcv = CPCVBacktest()
        result = cpcv.run(signals, prices)
        assert len(result.sharpe_per_path) > 0

    def test_run_path_distribution(self):
        signals, prices = self._make_test_data()
        cpcv = CPCVBacktest()
        result = cpcv.run(signals, prices)
        dist = result.path_distribution
        assert "mean" in dist
        assert "std" in dist
        assert "min" in dist
        assert "max" in dist

    def test_run_short_data_returns_empty(self):
        signals = pd.Series([1, 0, 1])
        prices = pd.Series([100.0, 101.0, 102.0])
        cpcv = CPCVBacktest()
        result = cpcv.run(signals, prices)
        assert result.mean_sharpe == 0.0
        assert result.dsr == 0.0

    def test_run_empty_data(self):
        cpcv = CPCVBacktest()
        result = cpcv.run(pd.Series(dtype=float), pd.Series(dtype=float))
        assert result.mean_sharpe == 0.0

    def test_transaction_cost(self):
        signals, prices = self._make_test_data()
        cpcv_no_cost = CPCVBacktest(transaction_cost=0.0)
        cpcv_with_cost = CPCVBacktest(transaction_cost=0.01)
        result_no_cost = cpcv_no_cost.run(signals, prices)
        result_with_cost = cpcv_with_cost.run(signals, prices)
        assert result_with_cost.mean_sharpe <= result_no_cost.mean_sharpe + 1e-10

    def test_multi_symbol_run(self):
        n = 500
        np.random.seed(42)
        signals = {
            "A": pd.Series(np.random.choice([0, 1], n)),
            "B": pd.Series(np.random.choice([0, 1], n)),
        }
        prices = {
            "A": pd.Series(np.cumsum(np.random.randn(n)) + 100),
            "B": pd.Series(np.cumsum(np.random.randn(n)) + 200),
        }
        cpcv = CPCVBacktest()
        result = cpcv.run_multi_symbol(signals, prices)
        assert isinstance(result, CPCVResult)
        assert result.n_splits == 6

    def test_multi_symbol_empty_signals(self):
        cpcv = CPCVBacktest()
        result = cpcv.run_multi_symbol({}, {})
        assert result.mean_sharpe == 0.0
        assert result.overfitting_probability == 1.0

    def test_multi_symbol_with_weights(self):
        n = 500
        np.random.seed(42)
        signals = {
            "A": pd.Series(np.random.choice([0, 1], n)),
            "B": pd.Series(np.random.choice([0, 1], n)),
        }
        prices = {
            "A": pd.Series(np.cumsum(np.random.randn(n)) + 100),
            "B": pd.Series(np.cumsum(np.random.randn(n)) + 200),
        }
        cpcv = CPCVBacktest()
        weights = {"A": 0.8, "B": 0.2}
        result = cpcv.run_multi_symbol(signals, prices, weights)
        assert isinstance(result, CPCVResult)

    def test_multi_symbol_transaction_cost(self):
        n = 500
        np.random.seed(42)
        signals = {
            "A": pd.Series(np.random.choice([0, 1], n)),
            "B": pd.Series(np.random.choice([0, 1], n)),
        }
        prices = {
            "A": pd.Series(np.cumsum(np.random.randn(n)) + 100),
            "B": pd.Series(np.cumsum(np.random.randn(n)) + 200),
        }
        cpcv_no_cost = CPCVBacktest(transaction_cost=0.0)
        cpcv_with_cost = CPCVBacktest(transaction_cost=0.01)
        result_no_cost = cpcv_no_cost.run_multi_symbol(signals, prices)
        result_with_cost = cpcv_with_cost.run_multi_symbol(signals, prices)
        assert result_with_cost.mean_sharpe <= result_no_cost.mean_sharpe + 1e-10


class TestCPCVResult:
    def test_defaults(self):
        r = CPCVResult()
        assert r.mean_sharpe == 0.0
        assert r.dsr == 0.0
        assert r.overfitting_probability == 0.0
        assert r.n_splits == 0
        assert r.path_distribution == {}
        assert r.sharpe_per_path == []
        assert r.max_drawdown == 0.0

    def test_custom_values(self):
        r = CPCVResult(
            mean_sharpe=1.5,
            dsr=0.95,
            overfitting_probability=0.05,
            n_splits=6,
            path_distribution={"mean": 1.5, "std": 0.5},
            sharpe_per_path=[1.2, 1.8],
            max_drawdown=0.15,
            annualized_return=0.12,
            n_trades=50,
            win_rate=0.6,
        )
        assert r.mean_sharpe == 1.5
        assert r.dsr == 0.95
        assert r.n_trades == 50
        assert r.win_rate == 0.6
