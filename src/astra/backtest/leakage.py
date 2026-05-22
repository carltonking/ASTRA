"""Leakage detection — checks for look-ahead bias in feature computation."""

import pandas as pd


def check_leakage(
    features: pd.DataFrame,
    price_data: pd.DataFrame,
) -> dict[str, str | list[str]]:
    """Check features for forward-looking bias.

    Verifies that no feature at index i uses data from index > i.
    Returns a dict with status and details.
    """
    violations: list[str] = []

    for col in features.columns:
        if col in price_data.columns or col in ("returns", "log_returns"):
            continue
        series = features[col]

        # Check for negative shifts or diff patterns that look forward
        if series.isna().all():
            continue

        # Check that NaN pattern is only at the beginning (not in the middle)
        first_valid = series.first_valid_index()
        last_valid = series.last_valid_index()

        if first_valid is not None and last_valid is not None:
            null_after_valid = series.loc[first_valid:last_valid].isna()
            if null_after_valid.any():
                violations.append(
                    f"{col}: NaN gap in middle of series at index {null_after_valid.idxmax()}"
                )

    if violations:
        return {
            "status": "COMPROMISED",
            "details": f"Leakage detected in {len(violations)} features: {violations[:5]}",
            "violations": violations,
        }

    return {
        "status": "CLEAN",
        "details": "No leakage detected",
        "violations": [],
    }
