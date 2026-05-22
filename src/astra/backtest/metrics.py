"""Performance metrics for backtesting — Sharpe, DSR, drawdown, returns."""

import math

import numpy as np
import pandas as pd
from scipy import stats


def compute_returns(
    signals: pd.Series,
    prices: pd.Series,
    transaction_cost: float = 0.0,
) -> pd.Series:
    """Compute strategy returns from signals and price series.

    Returns a Series of daily returns assuming we trade at next-day close.
    transaction_cost is a per-trade cost as a fraction of position value
    (e.g. 0.001 = 0.1% commission + slippage).
    """
    aligned = pd.concat(
        [signals.rename("signal"), prices.rename("price")], axis=1
    ).dropna()
    if len(aligned) < 2:
        return pd.Series(dtype=float)

    aligned["returns"] = aligned["price"].pct_change().shift(-1) * aligned["signal"]

    if transaction_cost > 0:
        trade_events = aligned["signal"].diff().abs() > 0
        aligned.loc[trade_events, "returns"] -= transaction_cost

    return aligned["returns"].dropna()


def compute_portfolio_returns(
    signals: dict[str, pd.Series],
    prices: dict[str, pd.Series],
    weights: dict[str, float] | None = None,
    transaction_cost: float = 0.0,
) -> pd.Series:
    """Compute equal-weighted (or custom-weighted) portfolio returns.

    Aggregates returns across symbols, weighted by portfolio allocation.
    Returns a single Series of daily portfolio returns.
    """
    if not signals or not prices:
        return pd.Series(dtype=float)

    if weights is None:
        n = len(signals)
        weights = {sym: 1.0 / n for sym in signals}

    all_returns = []
    for symbol in signals:
        if symbol not in prices:
            continue
        w = weights.get(symbol, 0.0)
        if w == 0:
            continue
        sym_returns = compute_returns(signals[symbol], prices[symbol], transaction_cost)
        all_returns.append(sym_returns * w)

    if not all_returns:
        return pd.Series(dtype=float)

    portfolio_ret = pd.concat(all_returns, axis=1)
    return portfolio_ret.sum(axis=1).dropna()


def compute_sharpe_ratio(
    returns: pd.Series,
    annual_factor: float = 252,
    risk_free_rate: float = 0.0,
) -> float:
    """Compute annualized Sharpe ratio from a return series."""
    if len(returns) < 2:
        return 0.0
    excess = returns - risk_free_rate / annual_factor
    if excess.std() < 1e-12:
        return 0.0
    return float(np.sqrt(annual_factor) * excess.mean() / excess.std())


def compute_deflated_sharpe_ratio(
    sharpe: float,
    n_observations: int,
    n_trials: int = 1,
) -> float:
    """Compute Deflated Sharpe Ratio accounting for multiple testing.

    The DSR adjusts the Sharpe ratio for the number of trials
    (parameter combinations, strategy variations) tested.
    """
    if n_observations < 2 or sharpe <= 0:
        return 0.0

    # Euler-Mascheroni constant for the standard deviation of max Sharpe
    gamma = 0.5772156649

    # Clamp n_trials to avoid ppf domain errors (ppf requires input in [0, 1])
    n_trials = max(n_trials, 3)

    # Expected maximum Sharpe under null (multiple testing adjustment)
    e_max = (1 - gamma) * stats.norm.ppf(1 - 1.0 / n_trials) + gamma * stats.norm.ppf(
        1 - 1.0 / n_trials * math.e
    )
    e_max = max(e_max, 0.0)
    var_max = (
        1
        / (n_observations - 1)
        * (1 - gamma * stats.norm.ppf(1 - 1.0 / n_trials) ** (-2))
    )
    var_max = max(var_max, 1e-6)
    var_sharpe = 1 + 0.5 * sharpe**2 / (n_observations - 1) if n_observations > 1 else 1

    dsr = (sharpe - e_max) / math.sqrt(var_max + var_sharpe)
    dsr = stats.norm.cdf(dsr)
    return float(dsr)


def compute_max_drawdown(equity_curve: pd.Series) -> float:
    """Compute maximum drawdown from an equity curve."""
    if len(equity_curve) < 2:
        return 0.0
    rolling_max = equity_curve.cummax()
    drawdown = (equity_curve - rolling_max) / rolling_max
    return float(abs(drawdown.min()))


def compute_annualized_return(equity_curve: pd.Series, periods_per_year: float = 252) -> float:
    """Compute annualized return from an equity curve."""
    if len(equity_curve) < 2:
        return 0.0
    total_return = equity_curve.iloc[-1] / equity_curve.iloc[0] - 1
    n_years = len(equity_curve) / periods_per_year
    if n_years <= 0:
        return 0.0
    return float((1 + total_return) ** (1 / n_years) - 1)


def compute_win_rate(returns: pd.Series) -> float:
    """Compute the proportion of positive returns."""
    if len(returns) == 0:
        return 0.0
    return float((returns > 0).sum() / len(returns))


def compute_profit_factor(returns: pd.Series) -> float:
    """Compute gross profit / gross loss."""
    gains = returns[returns > 0].sum()
    losses = abs(returns[returns < 0].sum())
    if losses == 0:
        return float("inf") if gains > 0 else 0.0
    return float(gains / losses)
