"""Risk management — position sizing, Kelly criterion, volatility adjustment,
Value at Risk (VaR), Conditional VaR (CVaR), and correlation-aware sizing."""

import numpy as np
import pandas as pd


def kelly_criterion(
    win_rate: float,
    avg_win: float,
    avg_loss: float,
    fraction: float = 0.25,
) -> float:
    """Compute Kelly-optimal position size as a fraction of capital.

    Uses the standard Kelly formula: f* = (p * b - q) / b
    where p = win_rate, q = 1-p, b = avg_win/|avg_loss|.

    fraction parameter applies a fractional Kelly (default 25%)
    for more conservative sizing.
    """
    if avg_loss == 0:
        return 0.0
    if win_rate <= 0 or win_rate >= 1:
        return 0.0

    b = abs(avg_win / avg_loss) if avg_loss != 0 else 0
    q = 1.0 - win_rate
    kelly = (win_rate * b - q) / b if b > 0 else 0.0
    kelly = max(0.0, min(kelly, 1.0))
    return kelly * fraction


def fixed_fraction_sizing(
    capital: float,
    risk_per_trade: float = 0.02,
) -> float:
    """Fixed fraction position sizing — risk a fixed % of capital per trade."""
    return capital * risk_per_trade


def volatility_adjusted_sizing(
    capital: float,
    price: float,
    atr: float,
    risk_per_trade: float = 0.02,
    atr_multiple: float = 2.0,
) -> float:
    """Volatility-adjusted position sizing using ATR.

    Position size = (capital * risk_per_trade) / (atr * atr_multiple)
    Returns the number of shares/units.
    """
    if atr <= 0 or price <= 0:
        return 0.0
    dollar_risk = capital * risk_per_trade
    stop_distance = atr * atr_multiple
    shares = dollar_risk / stop_distance
    return max(0.0, shares)


def compute_kelly_from_returns(returns: pd.Series, fraction: float = 0.25) -> float:
    """Compute Kelly fraction from a series of trade returns."""
    wins = returns[returns > 0]
    losses = returns[returns < 0]
    if len(wins) == 0 or len(losses) == 0:
        return 0.0
    win_rate = len(wins) / len(returns)
    avg_win = wins.mean()
    avg_loss = abs(losses.mean())
    return kelly_criterion(win_rate, avg_win, avg_loss, fraction)


def compute_max_position_size(
    capital: float,
    price: float,
    max_fraction: float = 0.25,
) -> float:
    """Maximum position size as a fraction of capital."""
    return (capital * max_fraction) / price if price > 0 else 0.0


def compute_stop_loss(
    entry_price: float,
    atr: float,
    atr_multiple: float = 2.0,
    direction: str = "long",
) -> float:
    """Compute stop-loss price based on ATR."""
    if direction == "long":
        return entry_price - atr * atr_multiple
    return entry_price + atr * atr_multiple


def compute_take_profit(
    entry_price: float,
    atr: float,
    atr_multiple: float = 3.0,
    direction: str = "long",
) -> float:
    """Compute take-profit price based on ATR."""
    if direction == "long":
        return entry_price + atr * atr_multiple
    return entry_price - atr * atr_multiple


def compute_var_historical(
    returns: pd.Series,
    confidence_level: float = 0.95,
) -> float:
    """Historical Value at Risk — the worst return at the given confidence level.

    Returns a positive number representing the loss amount.
    E.g., VaR 95% = 0.02 means 95% of returns are better than -2%.
    """
    if len(returns) < 10:
        return 0.0
    return float(abs(np.percentile(returns, (1 - confidence_level) * 100)))


def compute_var_parametric(
    returns: pd.Series,
    confidence_level: float = 0.95,
) -> float:
    """Parametric (variance-covariance) Value at Risk.

    Assumes normally distributed returns.
    """
    from scipy import stats

    if len(returns) < 10 or returns.std() == 0:
        return 0.0
    z = float(abs(stats.norm.ppf(1 - confidence_level)))
    return float(z * returns.std())


def compute_cvar(
    returns: pd.Series,
    confidence_level: float = 0.95,
) -> float:
    """Conditional VaR (Expected Shortfall) — average loss beyond VaR threshold.

    Returns a positive number representing the expected loss amount
    in the worst (1-confidence_level) percentile of outcomes.
    """
    if len(returns) < 10:
        return 0.0
    threshold = np.percentile(returns, (1 - confidence_level) * 100)
    tail = returns[returns <= threshold]
    if len(tail) == 0:
        return 0.0
    return float(abs(tail.mean()))


def compute_correlation_matrix(
    returns_dict: dict[str, pd.Series],
) -> pd.DataFrame:
    """Compute pairwise correlation matrix from a dict of return series.

    Aligns all series on their common index before computing correlations.
    Returns a DataFrame with ticker names as index and columns.
    """
    frame = pd.DataFrame(returns_dict)
    return frame.corr().fillna(0)


def correlation_adjusted_sizing(
    capital: float,
    position_value: float,
    correlation_matrix: pd.DataFrame,
    ticker: str,
    max_correlation: float = 0.7,
    base_allocation: float = 0.25,
) -> float:
    """Reduce position size when a ticker is highly correlated with existing positions.

    For each existing position with correlation > max_correlation to the new ticker,
    the allocation is reduced proportionally. Returns the adjusted dollar amount.
    """
    if ticker not in correlation_matrix.index:
        return capital * base_allocation

    corr_row = correlation_matrix.loc[ticker]
    high_corr_count = int((corr_row.abs() > max_correlation).sum() - 1)
    if high_corr_count <= 0:
        return capital * base_allocation

    reduction = 1.0 / (1.0 + high_corr_count)
    return min(position_value, capital * base_allocation * reduction)
