"""Combinatorial Purged Cross-Validation (CPCV) for walk-forward backtesting."""

import itertools
from dataclasses import dataclass, field
from typing import Any

import numpy as np
import pandas as pd

from astra.backtest.metrics import (
    compute_returns,
    compute_portfolio_returns,
    compute_sharpe_ratio,
    compute_deflated_sharpe_ratio,
    compute_max_drawdown,
    compute_annualized_return,
)


@dataclass
class CPCVResult:
    mean_sharpe: float = 0.0
    dsr: float = 0.0
    overfitting_probability: float = 0.0
    n_splits: int = 0
    path_distribution: dict[str, Any] = field(default_factory=dict)
    sharpe_per_path: list[float] = field(default_factory=list)
    max_drawdown: float = 0.0
    annualized_return: float = 0.0
    n_trades: int = 0
    win_rate: float = 0.0


def cpcv_split_indices(
    n_observations: int,
    n_splits: int = 6,
    n_test_splits: int = 2,
    purge_days: int = 21,
    embargo_days: int = 5,
):
    """Generate train/test split indices for CPCV.

    Splits data into n_splits sequential groups, then creates all
    combinations of n_splits choose n_test_splits test sets.
    Each test set uses the remaining groups as training data.
    Applies purging (removes overlapping train data) and embargo
    (adds gap between train and test).
    """
    if n_splits < 2:
        raise ValueError("n_splits must be >= 2")
    if n_test_splits >= n_splits:
        raise ValueError("n_test_splits must be < n_splits")

    split_size = n_observations // n_splits
    if split_size < 1:
        return []

    splits = []
    for i in range(n_splits):
        start = i * split_size
        end = start + split_size if i < n_splits - 1 else n_observations
        splits.append((start, end))

    test_combos = list(itertools.combinations(range(n_splits), n_test_splits))
    result = []

    for test_idx_set in test_combos:
        test_indices = []
        for idx in test_idx_set:
            test_indices.append(splits[idx])

        # Training = all non-test groups
        train_splits = []
        for i in range(n_splits):
            if i not in test_idx_set:
                train_splits.append(splits[i])

        train_start = train_splits[0][0]
        train_end = max(e for _, e in train_splits)

        # Purge: remove train data that overlaps with test
        purge_before = min(s for s, _ in test_indices)
        train_end = min(train_end, purge_before - purge_days)

        # Embargo: gap between train end and test start

        if train_end > train_start:
            result.append(
                {
                    "train": (train_start, max(train_end, 0)),
                    "test": test_indices,
                    "test_splits": list(test_idx_set),
                }
            )

    return result


def run_single_backtest(
    signals: pd.Series,
    prices: pd.Series,
    transaction_cost: float = 0.0,
) -> dict[str, Any]:
    """Run a single backtest on one train/test split pair."""
    returns = compute_returns(signals, prices, transaction_cost)
    equity = (1 + returns).cumprod()
    sharpe = compute_sharpe_ratio(returns)

    return dict(
        sharpe=sharpe,
        returns=returns,
        equity=equity,
        n_trades=int((signals.diff() != 0).sum()),
    )


class CPCVBacktest:
    """Combinatorial Purged Cross-Validation backtest runner."""

    def __init__(
        self,
        n_splits: int = 6,
        n_test_splits: int = 2,
        purge_days: int = 21,
        embargo_days: int = 5,
        transaction_cost: float = 0.0,
    ):
        self.n_splits = n_splits
        self.n_test_splits = n_test_splits
        self.purge_days = purge_days
        self.embargo_days = embargo_days
        self.transaction_cost = transaction_cost

    def run(
        self,
        signals: pd.Series,
        prices: pd.Series,
    ) -> CPCVResult:
        """Run CPCV backtest on signals and price data."""
        aligned = pd.concat(
            [signals.rename("signal"), prices.rename("price")], axis=1
        ).dropna()
        if len(aligned) < 20:
            return CPCVResult(n_splits=self.n_splits)

        split_indices = cpcv_split_indices(
            n_observations=len(aligned),
            n_splits=self.n_splits,
            n_test_splits=self.n_test_splits,
            purge_days=self.purge_days,
            embargo_days=self.embargo_days,
        )

        path_sharpes = []
        path_results = []

        for split in split_indices:
            train_start, train_end = split["train"]
            train_signal = aligned["signal"].iloc[train_start:train_end]
            train_price = aligned["price"].iloc[train_start:train_end]

            if len(train_signal) >= 10:
                result = run_single_backtest(train_signal, train_price, self.transaction_cost)
                path_sharpes.append(result["sharpe"])
                path_results.append(result)

            for test_range in split["test"]:
                test_start, test_end = test_range
                test_signal = aligned["signal"].iloc[test_start:test_end]
                test_price = aligned["price"].iloc[test_start:test_end]

                if len(test_signal) >= 2:
                    result = run_single_backtest(test_signal, test_price, self.transaction_cost)
                    path_sharpes.append(result["sharpe"])
                    path_results.append(result)

        if not path_sharpes:
            return CPCVResult(
                mean_sharpe=0.0,
                dsr=0.0,
                overfitting_probability=1.0,
                n_splits=self.n_splits,
                path_distribution={"mean": 0, "std": 0, "min": 0, "max": 0},
            )

        mean_sharpe = float(np.mean(path_sharpes))
        std_sharpe = float(np.std(path_sharpes)) if len(path_sharpes) > 1 else 0.0
        n_obs = len(aligned)
        n_trials = len(split_indices) * 2 if split_indices else 1
        dsr = compute_deflated_sharpe_ratio(
            sharpe=mean_sharpe,
            n_observations=n_obs,
            n_trials=max(n_trials, 1),
        )

        # Overfitting probability: proportion of paths with negative Sharpe
        neg_count = sum(1 for s in path_sharpes if s < 0)
        overfit_prob = neg_count / len(path_sharpes) if path_sharpes else 1.0

        # Aggregate metrics — mean path equity avoids O(n log n) groupby sort
        mean_equity = sum(r["equity"] for r in path_results) / len(path_results)
        all_returns_flat = pd.concat([r["returns"] for r in path_results])

        max_dd = compute_max_drawdown(mean_equity)
        ann_ret = compute_annualized_return(mean_equity)
        n_trades = sum(r["n_trades"] for r in path_results)
        win_rate = (
            float((all_returns_flat > 0).mean()) if len(all_returns_flat) > 0 else 0.0
        )

        return CPCVResult(
            mean_sharpe=mean_sharpe,
            dsr=dsr,
            overfitting_probability=overfit_prob,
            n_splits=self.n_splits,
            path_distribution={
                "mean": mean_sharpe,
                "std": std_sharpe,
                "min": float(np.min(path_sharpes)) if path_sharpes else 0,
                "max": float(np.max(path_sharpes)) if path_sharpes else 0,
            },
            sharpe_per_path=path_sharpes,
            max_drawdown=max_dd,
            annualized_return=ann_ret,
            n_trades=n_trades,
            win_rate=win_rate,
        )

    def run_multi_symbol(
        self,
        signals: dict[str, pd.Series],
        prices: dict[str, pd.Series],
        weights: dict[str, float] | None = None,
    ) -> CPCVResult:
        """Run CPCV on a multi-symbol portfolio (equal-weighted by default).

        Aggregates signals and prices into a single portfolio return series,
        then runs standard CPCV on the combined series.
        """
        portfolio_returns = compute_portfolio_returns(
            signals, prices, weights, self.transaction_cost
        )
        if portfolio_returns.empty:
            return CPCVResult(
                mean_sharpe=0.0,
                dsr=0.0,
                overfitting_probability=1.0,
                n_splits=self.n_splits,
            )

        synthetic_equity = (1 + portfolio_returns).cumprod()
        synthetic_price = synthetic_equity
        synthetic_signal = pd.Series(1, index=synthetic_equity.index)

        return self.run(synthetic_signal, synthetic_price)
