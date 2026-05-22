"""Strategy review board — evaluates backtest results against quality criteria."""


def generate_review(
    mean_sharpe: float,
    dsr: float,
    overfitting_probability: float,
    max_drawdown: float,
    annualized_return: float,
    n_trades: int,
    win_rate: float,
) -> dict[str, str | float]:
    """Evaluate strategy quality based on backtest metrics.

    Returns a dict with status, score, and detailed feedback.
    """
    score = 0.0
    reasons: list[str] = []

    # Sharpe ratio score (max 25 points)
    if mean_sharpe >= 2.0:
        score += 25
        reasons.append(f"Excellent Sharpe: {mean_sharpe:.2f}")
    elif mean_sharpe >= 1.5:
        score += 20
        reasons.append(f"Good Sharpe: {mean_sharpe:.2f}")
    elif mean_sharpe >= 1.0:
        score += 15
        reasons.append(f"Adequate Sharpe: {mean_sharpe:.2f}")
    elif mean_sharpe >= 0.5:
        score += 10
        reasons.append(f"Below-average Sharpe: {mean_sharpe:.2f}")
    else:
        reasons.append(f"Poor Sharpe: {mean_sharpe:.2f}")

    # DSR score (max 25 points)
    if dsr >= 0.95:
        score += 25
    elif dsr >= 0.90:
        score += 20
    elif dsr >= 0.75:
        score += 15
    elif dsr >= 0.50:
        score += 10
    else:
        reasons.append(f"Low DSR: {dsr:.2%}")

    # Overfitting score (max 20 points)
    if overfitting_probability <= 0.10:
        score += 20
    elif overfitting_probability <= 0.25:
        score += 15
    elif overfitting_probability <= 0.50:
        score += 10
    else:
        score += 5
        reasons.append(f"High overfitting probability: {overfitting_probability:.0%}")

    # Drawdown score (max 15 points)
    if max_drawdown <= 0.05:
        score += 15
    elif max_drawdown <= 0.10:
        score += 12
    elif max_drawdown <= 0.20:
        score += 8
    elif max_drawdown <= 0.30:
        score += 5
    else:
        reasons.append(f"High drawdown: {max_drawdown:.1%}")

    # Return score (max 10 points)
    if annualized_return >= 0.20:
        score += 10
    elif annualized_return >= 0.10:
        score += 8
    elif annualized_return >= 0.05:
        score += 5
    elif annualized_return >= 0.0:
        score += 2
    else:
        reasons.append(f"Negative return: {annualized_return:.1%}")

    # Trade count score (max 5 points)
    if n_trades >= 100:
        score += 5
    elif n_trades >= 50:
        score += 3
    elif n_trades >= 20:
        score += 2
    else:
        reasons.append(f"Low trade count: {n_trades}")

    status = "APPROVED" if score >= 60 else "REJECTED"
    if score >= 80:
        status = "APPROVED"

    detail = "; ".join(reasons) if reasons else "All metrics acceptable"
    return {"status": status, "score": score, "details": detail}
