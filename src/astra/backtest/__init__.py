"""ASTRA backtesting engine — replaces AURORA dependency with in-process computation."""

from astra.backtest.metrics import (
    compute_returns,
    compute_sharpe_ratio,
    compute_deflated_sharpe_ratio,
    compute_max_drawdown,
    compute_annualized_return,
    compute_win_rate,
    compute_profit_factor,
)
from astra.backtest.features import compute_features
from astra.backtest.cpcv import CPCVBacktest, cpcv_split_indices
from astra.backtest.engine import BacktestEngine

__all__ = [
    "compute_returns",
    "compute_sharpe_ratio",
    "compute_deflated_sharpe_ratio",
    "compute_max_drawdown",
    "compute_annualized_return",
    "compute_win_rate",
    "compute_profit_factor",
    "compute_features",
    "CPCVBacktest",
    "cpcv_split_indices",
    "BacktestEngine",
]
