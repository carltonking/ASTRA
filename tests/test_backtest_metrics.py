"""Tests for backtest metrics — Sharpe, DSR, drawdown, returns, transaction costs."""

import numpy as np
import pandas as pd
import pytest

from astra.backtest.metrics import (
    compute_returns,
    compute_portfolio_returns,
    compute_sharpe_ratio,
    compute_deflated_sharpe_ratio,
    compute_max_drawdown,
    compute_annualized_return,
    compute_win_rate,
    compute_profit_factor,
)


class TestComputeReturns:
    def test_returns_basic(self):
        prices = pd.Series([100.0, 101.0, 102.0, 103.0, 104.0])
        signals = pd.Series([1, 1, 1, 1, 1])
        ret = compute_returns(signals, prices)
        expected_returns = prices.pct_change().shift(-1) * signals
        expected_returns = expected_returns.dropna()
        assert len(ret) == len(expected_returns)
        assert abs(ret.iloc[0] - 0.01) < 1e-6

    def test_returns_empty_short_series(self):
        prices = pd.Series([100.0])
        signals = pd.Series([1])
        ret = compute_returns(signals, prices)
        assert ret.empty

    def test_returns_empty_inputs(self):
        ret = compute_returns(pd.Series(dtype=float), pd.Series(dtype=float))
        assert ret.empty

    def test_returns_no_signal(self):
        prices = pd.Series([100.0, 101.0, 102.0])
        signals = pd.Series([0, 0, 0])
        ret = compute_returns(signals, prices)
        assert (ret.abs() < 1e-10).all()

    def test_transaction_cost_subtracted_on_trades(self):
        prices = pd.Series([100.0, 101.0, 102.0, 103.0, 104.0])
        signals = pd.Series([0, 1, 1, 1, 0])
        ret_no_cost = compute_returns(signals, prices, transaction_cost=0.0)
        ret_with_cost = compute_returns(signals, prices, transaction_cost=0.01)
        assert len(ret_no_cost) == len(ret_with_cost)
        assert ret_with_cost.sum() < ret_no_cost.sum()

    def test_transaction_cost_no_trades(self):
        prices = pd.Series([100.0, 101.0, 102.0])
        signals = pd.Series([1, 1, 1])
        ret_no_cost = compute_returns(signals, prices, transaction_cost=0.0)
        ret_with_cost = compute_returns(signals, prices, transaction_cost=0.01)
        pd.testing.assert_series_equal(ret_no_cost, ret_with_cost)


class TestComputePortfolioReturns:
    def test_equal_weighted(self):
        prices = {
            "A": pd.Series([100.0, 101.0, 102.0]),
            "B": pd.Series([200.0, 202.0, 204.0]),
        }
        signals = {
            "A": pd.Series([1, 1, 1]),
            "B": pd.Series([1, 1, 1]),
        }
        port_ret = compute_portfolio_returns(signals, prices)
        assert not port_ret.empty
        assert port_ret.index.is_monotonic_increasing

    def test_empty_inputs(self):
        port_ret = compute_portfolio_returns({}, {})
        assert port_ret.empty

    def test_missing_symbol_in_prices_is_excluded(self):
        signals = {"A": pd.Series([1, 1]), "B": pd.Series([1, 1])}
        prices = {"A": pd.Series([100.0, 101.0])}
        port_ret = compute_portfolio_returns(signals, prices)
        assert not port_ret.empty

    def test_custom_weights(self):
        prices = {
            "A": pd.Series([100.0, 101.0]),
            "B": pd.Series([200.0, 202.0]),
        }
        signals = {
            "A": pd.Series([1, 1]),
            "B": pd.Series([1, 1]),
        }
        weights = {"A": 0.8, "B": 0.2}
        port_ret = compute_portfolio_returns(signals, prices, weights)
        assert not port_ret.empty

    def test_transaction_cost_multi_symbol(self):
        prices = {
            "A": pd.Series([100.0, 101.0, 102.0, 103.0]),
            "B": pd.Series([200.0, 202.0, 204.0, 206.0]),
        }
        signals = {
            "A": pd.Series([0, 1, 1, 0]),
            "B": pd.Series([0, 1, 1, 0]),
        }
        port_ret_no_cost = compute_portfolio_returns(signals, prices, transaction_cost=0.0)
        port_ret_with_cost = compute_portfolio_returns(signals, prices, transaction_cost=0.01)
        assert port_ret_with_cost.sum() < port_ret_no_cost.sum()


class TestComputeSharpeRatio:
    def test_positive_sharpe(self):
        rng = np.random.default_rng(42)
        returns = pd.Series(rng.normal(0.001, 0.01, 252))
        sharpe = compute_sharpe_ratio(returns)
        assert sharpe > 0

    def test_negative_sharpe(self):
        rng = np.random.default_rng(1)
        returns = pd.Series(rng.normal(-0.001, 0.01, 252))
        sharpe = compute_sharpe_ratio(returns)
        assert sharpe < 0

    def test_zero_volatility(self):
        returns = pd.Series(np.repeat(0.01, 100))
        sharpe = compute_sharpe_ratio(returns)
        assert sharpe == 0.0

    def test_short_series(self):
        returns = pd.Series([0.01])
        sharpe = compute_sharpe_ratio(returns)
        assert sharpe == 0.0

    def test_empty_series(self):
        sharpe = compute_sharpe_ratio(pd.Series(dtype=float))
        assert sharpe == 0.0

    def test_risk_free_rate(self):
        returns = pd.Series([0.01] * 252)
        sharpe_rf = compute_sharpe_ratio(returns, risk_free_rate=0.0)
        sharpe_with_rf = compute_sharpe_ratio(returns, risk_free_rate=0.05)
        assert sharpe_with_rf < sharpe_rf or abs(sharpe_with_rf - sharpe_rf) < 1e-10


class TestComputeDeflatedSharpeRatio:
    def test_high_sharpe_produces_high_dsr(self):
        dsr = compute_deflated_sharpe_ratio(sharpe=2.0, n_observations=1000, n_trials=3)
        assert 0 <= dsr <= 1.0
        assert dsr > 0.9

    def test_zero_sharpe(self):
        dsr = compute_deflated_sharpe_ratio(sharpe=0.0, n_observations=1000)
        assert dsr == 0.0

    def test_negative_sharpe(self):
        dsr = compute_deflated_sharpe_ratio(sharpe=-0.5, n_observations=1000)
        assert dsr == 0.0

    def test_few_observations(self):
        dsr = compute_deflated_sharpe_ratio(sharpe=1.0, n_observations=1)
        assert dsr == 0.0

    def test_many_trials_reduces_dsr(self):
        dsr_low = compute_deflated_sharpe_ratio(sharpe=1.0, n_observations=500, n_trials=100)
        dsr_high = compute_deflated_sharpe_ratio(sharpe=1.0, n_observations=500, n_trials=3)
        assert dsr_low <= dsr_high

    def test_dsr_clamps_low_trials(self):
        dsr = compute_deflated_sharpe_ratio(sharpe=2.0, n_observations=1000, n_trials=1)
        assert 0 <= dsr <= 1.0


class TestComputeMaxDrawdown:
    def test_no_drawdown(self):
        equity = pd.Series([100.0, 101.0, 102.0])
        dd = compute_max_drawdown(equity)
        assert dd == 0.0

    def test_simple_drawdown(self):
        equity = pd.Series([100.0, 110.0, 90.0, 95.0])
        dd = compute_max_drawdown(equity)
        assert abs(dd - (20.0 / 110.0)) < 1e-6

    def test_short_series(self):
        equity = pd.Series([100.0])
        dd = compute_max_drawdown(equity)
        assert dd == 0.0

    def test_empty_series(self):
        dd = compute_max_drawdown(pd.Series(dtype=float))
        assert dd == 0.0

    def test_complex_drawdown(self):
        equity = pd.Series([100.0, 200.0, 150.0, 180.0, 120.0, 160.0])
        dd = compute_max_drawdown(equity)
        expected_dd = (200.0 - 120.0) / 200.0
        assert abs(dd - expected_dd) < 1e-6


class TestComputeAnnualizedReturn:
    def test_positive_return(self):
        equity = pd.Series(range(100, 200))
        ann_ret = compute_annualized_return(equity, periods_per_year=252)
        assert ann_ret > 0

    def test_short_series(self):
        equity = pd.Series([100.0])
        ann_ret = compute_annualized_return(equity)
        assert ann_ret == 0.0

    def test_empty_series(self):
        ann_ret = compute_annualized_return(pd.Series(dtype=float))
        assert ann_ret == 0.0

    def test_negative_return(self):
        equity = pd.Series(range(200, 100, -1))
        ann_ret = compute_annualized_return(equity, periods_per_year=252)
        assert ann_ret < 0

    def test_no_change(self):
        equity = pd.Series([100.0] * 252)
        ann_ret = compute_annualized_return(equity, periods_per_year=252)
        assert abs(ann_ret) < 1e-10


class TestComputeWinRate:
    def test_all_positive(self):
        win_rate = compute_win_rate(pd.Series([0.01, 0.02, 0.03]))
        assert win_rate == 1.0

    def test_mixed(self):
        win_rate = compute_win_rate(pd.Series([0.01, -0.01, 0.02]))
        assert win_rate == 2.0 / 3.0

    def test_all_negative(self):
        win_rate = compute_win_rate(pd.Series([-0.01, -0.02]))
        assert win_rate == 0.0

    def test_empty(self):
        win_rate = compute_win_rate(pd.Series(dtype=float))
        assert win_rate == 0.0

    def test_zero_returns(self):
        win_rate = compute_win_rate(pd.Series([0.0, 0.0]))
        assert win_rate == 0.0


class TestComputeProfitFactor:
    def test_profitable(self):
        pf = compute_profit_factor(pd.Series([0.10, -0.05, 0.15]))
        assert pf > 1.0

    def test_all_gains(self):
        pf = compute_profit_factor(pd.Series([0.10, 0.20]))
        assert pf == float("inf")

    def test_all_losses(self):
        pf = compute_profit_factor(pd.Series([-0.10, -0.20]))
        assert pf == 0.0

    def test_empty(self):
        pf = compute_profit_factor(pd.Series(dtype=float))
        assert pf == 0.0
