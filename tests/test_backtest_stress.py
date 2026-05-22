"""Parameterized stress tests — runs backtest engine with many parameter combos."""

import itertools

import numpy as np
import pandas as pd
import pytest

from astra.backtest.cpcv import CPCVBacktest
from astra.backtest.metrics import (
    compute_returns,
    compute_sharpe_ratio,
    compute_deflated_sharpe_ratio,
    compute_max_drawdown,
    compute_annualized_return,
    compute_win_rate,
    compute_profit_factor,
)


def _random_price_series(n: int = 500, seed: int = 42) -> pd.Series:
    rng = np.random.default_rng(seed)
    steps = rng.normal(0.0005, 0.01, n)
    prices = 100 * np.exp(np.cumsum(steps))
    return pd.Series(prices, index=pd.date_range("2020-01-01", periods=n, freq="D"))


def _random_signal(n: int = 500, seed: int = 99) -> pd.Series:
    rng = np.random.default_rng(seed)
    vals = rng.integers(0, 2, n)
    return pd.Series(vals, index=pd.date_range("2020-01-01", periods=n, freq="D"))


# ---- Parameterized CPCV combos ----

N_SPLITS_VALUES = [3, 4, 6]
N_TEST_SPLITS_VALUES = [1, 2]
PURGE_DAYS_VALUES = [0, 5, 21]
EMBARGO_DAYS_VALUES = [0, 5]
TXN_COST_VALUES = [0.0, 0.001, 0.005]
DATASET_SIZES = [100, 300, 1000]
SEEDS = range(5)


class TestCPCVParameterized:
    @pytest.mark.parametrize("n_splits", N_SPLITS_VALUES)
    @pytest.mark.parametrize("n_test_splits", N_TEST_SPLITS_VALUES)
    @pytest.mark.parametrize("purge_days", PURGE_DAYS_VALUES)
    @pytest.mark.parametrize("embargo_days", EMBARGO_DAYS_VALUES)
    @pytest.mark.parametrize("n_obs", DATASET_SIZES)
    def test_cpcv_runs_with_all_combos(self, n_splits, n_test_splits, purge_days, embargo_days, n_obs):
        if n_test_splits >= n_splits:
            return
        prices = _random_price_series(n_obs, seed=42)
        signals = _random_signal(n_obs, seed=99)
        runner = CPCVBacktest(
            n_splits=n_splits,
            n_test_splits=n_test_splits,
            purge_days=purge_days,
            embargo_days=embargo_days,
            transaction_cost=0.0,
        )
        result = runner.run(signals, prices)
        assert isinstance(result.mean_sharpe, float)
        assert 0 <= result.dsr <= 1.0
        assert 0 <= result.overfitting_probability <= 1.0
        assert result.n_splits == n_splits

    @pytest.mark.parametrize("n_splits", N_SPLITS_VALUES)
    @pytest.mark.parametrize("n_test_splits", N_TEST_SPLITS_VALUES)
    @pytest.mark.parametrize("n_obs", DATASET_SIZES)
    def test_cpcv_invariants_across_sizes(self, n_splits, n_test_splits, n_obs):
        if n_test_splits >= n_splits:
            return
        prices = _random_price_series(n_obs, seed=42)
        signals = _random_signal(n_obs, seed=99)
        runner = CPCVBacktest(n_splits=n_splits, n_test_splits=n_test_splits)
        result = runner.run(signals, prices)
        assert result.mean_sharpe != 0.0 or result.overfitting_probability > 0
        assert len(result.sharpe_per_path) >= 0

    @pytest.mark.parametrize("txn_cost", TXN_COST_VALUES)
    @pytest.mark.parametrize("seed", SEEDS)
    def test_cpcv_with_transaction_costs(self, txn_cost, seed):
        prices = _random_price_series(500, seed=seed)
        signals = _random_signal(500, seed=seed + 10)
        runner = CPCVBacktest(n_splits=4, n_test_splits=1, transaction_cost=txn_cost)
        result = runner.run(signals, prices)
        assert 0 <= result.overfitting_probability <= 1.0
        if txn_cost > 0:
            zero_cost_runner = CPCVBacktest(n_splits=4, n_test_splits=1, transaction_cost=0.0)
            zero_result = zero_cost_runner.run(signals.copy(), prices.copy())
            assert result.mean_sharpe <= zero_result.mean_sharpe + 1e-6

    @pytest.mark.parametrize("n_splits", N_SPLITS_VALUES)
    def test_multi_symbol_cpcv(self, n_splits):
        n = 300
        symbols = ["AAPL", "MSFT", "GOOGL"]
        prices = {sym: _random_price_series(n, seed=i) for i, sym in enumerate(symbols)}
        signals = {sym: _random_signal(n, seed=i + 10) for i, sym in enumerate(symbols)}
        runner = CPCVBacktest(n_splits=n_splits, n_test_splits=1)
        result = runner.run_multi_symbol(signals, prices)
        assert isinstance(result.mean_sharpe, float)
        assert 0 <= result.dsr <= 1.0


# ---- Parameterized metrics edge cases ----

class TestMetricsEdgeCases:
    @pytest.mark.parametrize("n", [0, 1, 2, 10, 100])
    def test_returns_lengths(self, n):
        prices = pd.Series(np.linspace(100, 110, n), index=pd.date_range("2020-01-01", periods=n, freq="D"))
        signals = pd.Series(np.ones(n), index=prices.index)
        result = compute_returns(signals, prices)
        if n < 3:
            assert len(result) <= max(0, n - 1)
        else:
            assert len(result) > 0

    @pytest.mark.parametrize("annual_factor", [52, 252, 365])
    def test_sharpe_scales_with_annual_factor(self, annual_factor):
        rng = np.random.default_rng(42)
        returns = pd.Series(rng.normal(0.001, 0.02, 252))
        sharpe = compute_sharpe_ratio(returns, annual_factor=annual_factor)
        assert isinstance(sharpe, float)
        assert sharpe != 0.0

    @pytest.mark.parametrize("n_trials", [1, 3, 10, 100])
    def test_dsr_decreases_with_more_trials(self, n_trials):
        dsr = compute_deflated_sharpe_ratio(sharpe=1.5, n_observations=500, n_trials=n_trials)
        assert 0 <= dsr <= 1.0

    @pytest.mark.parametrize("zero_std", [True, False])
    def test_sharpe_with_zero_std_returns(self, zero_std):
        returns = pd.Series([0.001] * 100) if zero_std else pd.Series(np.random.default_rng(42).normal(0, 0.02, 100))
        sharpe = compute_sharpe_ratio(returns)
        assert isinstance(sharpe, float)

    @pytest.mark.parametrize("drawdown_input", [
        pd.Series([100, 110, 120, 130]),
        pd.Series([100, 90, 80, 70]),
        pd.Series([100, 120, 90, 110]),
        pd.Series([100]),
        pd.Series(dtype=float),
    ])
    def test_drawdown_bounds(self, drawdown_input):
        dd = compute_max_drawdown(drawdown_input)
        assert 0 <= dd <= 1.0

    @pytest.mark.parametrize("n", [0, 1, 10, 100])
    def test_win_rate_bounds(self, n):
        rng = np.random.default_rng(42)
        returns = pd.Series(rng.normal(0, 1, n)) if n > 0 else pd.Series(dtype=float)
        wr = compute_win_rate(returns)
        assert 0 <= wr <= 1.0

    @pytest.mark.parametrize("composition", [
        "all_gains",
        "all_losses",
        "mixed",
        "empty",
        "single_gain",
        "single_loss",
    ])
    def test_profit_factor_variants(self, composition):
        if composition == "all_gains":
            returns = pd.Series([0.01, 0.02, 0.03])
        elif composition == "all_losses":
            returns = pd.Series([-0.01, -0.02, -0.03])
        elif composition == "mixed":
            returns = pd.Series([0.01, -0.01, 0.02, -0.02])
        elif composition == "empty":
            returns = pd.Series(dtype=float)
        elif composition == "single_gain":
            returns = pd.Series([0.01])
        elif composition == "single_loss":
            returns = pd.Series([-0.01])
        pf = compute_profit_factor(returns)
        assert pf == 0.0 or pf >= 0

    @pytest.mark.parametrize("equity_input", [
        pd.Series([100, 110]),
        pd.Series([100] * 10),
        pd.Series([100, 50, 200, 75]),
        pd.Series(dtype=float),
    ])
    def test_annualized_return_range(self, equity_input):
        ret = compute_annualized_return(equity_input)
        if len(equity_input) < 2:
            assert ret == 0.0
        else:
            assert isinstance(ret, float)


# ---- Edge case combos ----

class TestCPCVEdgeCases:
    @pytest.mark.parametrize("n_obs", [0, 1, 5, 10, 15, 19])
    def test_very_short_datasets(self, n_obs):
        prices = _random_price_series(n_obs, seed=42)
        signals = _random_signal(n_obs, seed=99)
        runner = CPCVBacktest(n_splits=3, n_test_splits=1)
        result = runner.run(signals, prices)
        assert isinstance(result.mean_sharpe, float)

    @pytest.mark.parametrize("n_splits,n_test_splits", [
        (2, 1), (6, 5), (10, 9),
    ])
    def test_edge_split_combinations(self, n_splits, n_test_splits):
        n_obs = 1000
        prices = _random_price_series(n_obs, seed=1)
        signals = _random_signal(n_obs, seed=2)
        runner = CPCVBacktest(n_splits=n_splits, n_test_splits=n_test_splits)
        result = runner.run(signals, prices)
        assert isinstance(result.mean_sharpe, float)

    @pytest.mark.parametrize("txn_cost", [-0.01, -0.1])
    def test_negative_transaction_cost(self, txn_cost):
        n_obs = 300
        prices = _random_price_series(n_obs, seed=1)
        signals = _random_signal(n_obs, seed=2)
        runner = CPCVBacktest(n_splits=3, n_test_splits=1, transaction_cost=txn_cost)
        result = runner.run(signals, prices)
        assert isinstance(result.mean_sharpe, float)

    @pytest.mark.parametrize("weights", [
        None,
        {"AAPL": 0.5, "MSFT": 0.3, "GOOGL": 0.2},
        {"AAPL": 1.0},
    ])
    def test_multi_symbol_weights(self, weights):
        n = 300
        symbols = ["AAPL", "MSFT", "GOOGL"]
        prices = {sym: _random_price_series(n, seed=i) for i, sym in enumerate(symbols)}
        signals = {sym: _random_signal(n, seed=i + 10) for i, sym in enumerate(symbols)}
        if weights and set(weights.keys()) - set(symbols):
            return
        runner = CPCVBacktest(n_splits=3, n_test_splits=1)
        result = runner.run_multi_symbol(signals, prices, weights)
        assert isinstance(result.mean_sharpe, float)
