"""Feature engineering — technical indicators computed from OHLCV data."""

import numpy as np
import pandas as pd


def _compute_rsi(series: pd.Series, period: int = 14) -> pd.Series:
    delta = series.diff()
    gain = delta.clip(lower=0)
    loss = -delta.clip(upper=0)
    avg_gain = gain.rolling(period, min_periods=period).mean()
    avg_loss = loss.rolling(period, min_periods=period).mean()
    rs = avg_gain / avg_loss.replace(0, np.nan)
    rsi = 100 - (100 / (1 + rs))
    return rsi


def _compute_atr(df: pd.DataFrame, period: int = 14) -> pd.Series:
    high, low, close = df["high"], df["low"], df["close"]
    tr1 = high - low
    tr2 = (high - close.shift()).abs()
    tr3 = (low - close.shift()).abs()
    tr = pd.concat([tr1, tr2, tr3], axis=1).max(axis=1)
    return tr.rolling(period, min_periods=period).mean()


def compute_features(df: pd.DataFrame) -> pd.DataFrame:
    """Add technical indicator columns to a price DataFrame.

    Expects columns: 'open', 'high', 'low', 'close' (and optionally 'volume').
    Returns a copy with all feature columns appended.
    """
    features = df.copy()
    price = features["close"]

    features["returns"] = price.pct_change()
    features["log_returns"] = np.log(price / price.shift(1))

    # Moving averages
    for w in [5, 10, 20, 50, 100, 200]:
        features[f"sma_{w}"] = price.rolling(w, min_periods=w).mean()
        features[f"ema_{w}"] = price.ewm(span=w, adjust=False, min_periods=w).mean()

    # RSI
    features["rsi_14"] = _compute_rsi(price, 14)

    # MACD
    ema_12 = price.ewm(span=12, adjust=False).mean()
    ema_26 = price.ewm(span=26, adjust=False).mean()
    features["macd"] = ema_12 - ema_26
    features["macd_signal"] = features["macd"].ewm(span=9, adjust=False).mean()
    features["macd_hist"] = features["macd"] - features["macd_signal"]

    # Bollinger Bands
    bb_mid = price.rolling(20, min_periods=20).mean()
    bb_std = price.rolling(20, min_periods=20).std()
    features["bb_upper"] = bb_mid + 2 * bb_std
    features["bb_lower"] = bb_mid - 2 * bb_std
    features["bb_width"] = (features["bb_upper"] - bb_mid) / bb_mid
    features["bb_position"] = (price - bb_mid) / (2 * bb_std + 1e-10)

    # ATR
    if "high" in features.columns and "low" in features.columns:
        features["atr_14"] = _compute_atr(features, 14)

    # Volume
    if "volume" in features.columns:
        vol = features["volume"]
        vol_sma = vol.rolling(20, min_periods=20).mean()
        features["volume_sma_20"] = vol_sma
        features["volume_ratio"] = vol / vol_sma.replace(0, np.nan)

    # Drop rows that are all NaN from rolling calculations
    return features


def compute_features_for_symbols(
    data: dict[str, pd.DataFrame],
) -> dict[str, pd.DataFrame]:
    """Compute features for each symbol in a data dict."""
    return {sym: compute_features(df) for sym, df in data.items()}
