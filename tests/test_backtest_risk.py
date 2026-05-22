"""Tests for risk management — Kelly criterion, position sizing."""

import numpy as np
import pandas as pd
import pytest

from astra.backtest.risk import (
    kelly_criterion,
    fixed_fraction_sizing,
    volatility_adjusted_sizing,
    compute_kelly_from_returns,
    compute_stop_loss,
    compute_take_profit,
)


class TestKellyCriterion:
    def test_positive_edge(self):
        kelly = kelly_criterion(win_rate=0.6, avg_win=1.0, avg_loss=1.0, fraction=1.0)
        assert 0 < kelly < 1.0
        assert abs(kelly - 0.2) < 0.01

    def test_no_edge(self):
        kelly = kelly_criterion(win_rate=0.5, avg_win=1.0, avg_loss=1.0, fraction=1.0)
        assert kelly == 0.0

    def test_negative_edge(self):
        kelly = kelly_criterion(win_rate=0.3, avg_win=1.0, avg_loss=1.0, fraction=1.0)
        assert kelly == 0.0

    def test_fractional_kelly(self):
        full = kelly_criterion(win_rate=0.6, avg_win=1.0, avg_loss=1.0, fraction=1.0)
        half = kelly_criterion(win_rate=0.6, avg_win=1.0, avg_loss=1.0, fraction=0.5)
        assert abs(half * 2 - full) < 0.01

    def test_edge_cases(self):
        assert kelly_criterion(0, 1, 1) == 0.0
        assert kelly_criterion(1, 1, 1) == 0.0
        assert kelly_criterion(0.5, 0, 1) == 0.0


class TestFixedFractionSizing:
    def test_basic(self):
        size = fixed_fraction_sizing(capital=100000, risk_per_trade=0.02)
        assert abs(size - 2000) < 0.01

    def test_zero_risk(self):
        size = fixed_fraction_sizing(capital=100000, risk_per_trade=0.0)
        assert size == 0.0


class TestVolatilityAdjustedSizing:
    def test_basic(self):
        shares = volatility_adjusted_sizing(
            capital=100000, price=100, atr=2.0, risk_per_trade=0.02, atr_multiple=2.0
        )
        expected = (100000 * 0.02) / (2.0 * 2.0)
        assert abs(shares - expected) < 0.1

    def test_zero_atr(self):
        shares = volatility_adjusted_sizing(capital=100000, price=100, atr=0)
        assert shares == 0.0

    def test_zero_price(self):
        shares = volatility_adjusted_sizing(capital=100000, price=0, atr=2.0)
        assert shares == 0.0


class TestComputeKellyFromReturns:
    def test_basic(self):
        returns = pd.Series([0.1, -0.05, 0.15, -0.03, 0.08])
        kelly = compute_kelly_from_returns(returns, fraction=1.0)
        assert 0 <= kelly <= 1.0

    def test_all_positive(self):
        returns = pd.Series([0.1, 0.2, 0.3])
        kelly = compute_kelly_from_returns(returns)
        assert kelly == 0.0

    def test_all_negative(self):
        returns = pd.Series([-0.1, -0.2, -0.3])
        kelly = compute_kelly_from_returns(returns)
        assert kelly == 0.0

    def test_empty(self):
        kelly = compute_kelly_from_returns(pd.Series(dtype=float))
        assert kelly == 0.0


class TestStopLossTakeProfit:
    def test_stop_loss_long(self):
        sl = compute_stop_loss(entry_price=100, atr=2.0, atr_multiple=2.0, direction="long")
        assert abs(sl - 96.0) < 0.01

    def test_stop_loss_short(self):
        sl = compute_stop_loss(entry_price=100, atr=2.0, atr_multiple=2.0, direction="short")
        assert abs(sl - 104.0) < 0.01

    def test_take_profit_long(self):
        tp = compute_take_profit(entry_price=100, atr=2.0, atr_multiple=3.0, direction="long")
        assert abs(tp - 106.0) < 0.01

    def test_take_profit_short(self):
        tp = compute_take_profit(entry_price=100, atr=2.0, atr_multiple=3.0, direction="short")
        assert abs(tp - 94.0) < 0.01
