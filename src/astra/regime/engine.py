"""Deterministic market regime classifier."""

from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import cast

import numpy as np
import pandas as pd


@dataclass
class RegimeSnapshot:
    timestamp: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
    trend: str = "unknown"
    volatility: str = "unknown"
    liquidity: str = "unknown"
    correlation: str = "unknown"
    macro_stress: str = "unknown"
    risk_mode: str = "unknown"
    structural_break: str = "none"
    confidence_by_label: dict[str, float] = field(default_factory=dict)
    aggregate_confidence: float = 0.0
    features: dict[str, float] = field(default_factory=dict)


class RegimeEngine:
    """Classify regimes from point-in-time OHLCV data.

    Labels are deterministic and use only rolling historical observations.
    """

    def classify(
        self,
        data: pd.DataFrame,
        peer_returns: pd.DataFrame | None = None,
    ) -> RegimeSnapshot:
        if data.empty or "close" not in data.columns:
            return RegimeSnapshot()

        close = cast(pd.Series, data["close"]).astype(float)
        returns = close.pct_change().dropna()
        volume = cast(pd.Series, data["volume"]).astype(float) if "volume" in data.columns else pd.Series(dtype=float)

        features = self._features(close, returns, volume)
        trend, trend_conf = self._trend(features)
        vol, vol_conf = self._volatility(features)
        liquidity, liq_conf = self._liquidity(features)
        corr, corr_conf = self._correlation(peer_returns)
        stress, stress_conf = self._macro_stress(features, vol, corr)
        risk_mode, risk_conf = self._risk_mode(trend, vol, stress)
        break_label, break_conf = self._structural_break(returns)
        conf = {
            "trend": trend_conf,
            "volatility": vol_conf,
            "liquidity": liq_conf,
            "correlation": corr_conf,
            "macro_stress": stress_conf,
            "risk_mode": risk_conf,
            "structural_break": break_conf,
        }
        return RegimeSnapshot(
            trend=trend,
            volatility=vol,
            liquidity=liquidity,
            correlation=corr,
            macro_stress=stress,
            risk_mode=risk_mode,
            structural_break=break_label,
            confidence_by_label=conf,
            aggregate_confidence=round(float(np.mean(list(conf.values()))), 4),
            features=features,
        )

    @staticmethod
    def deployment_action(
        snapshot: RegimeSnapshot,
        allowed_regimes: dict[str, list[str]],
        prohibited_regimes: dict[str, list[str]],
        min_confidence: float,
    ) -> str:
        labels = {
            "trend": snapshot.trend,
            "volatility": snapshot.volatility,
            "liquidity": snapshot.liquidity,
            "correlation": snapshot.correlation,
            "macro_stress": snapshot.macro_stress,
            "risk_mode": snapshot.risk_mode,
            "structural_break": snapshot.structural_break,
        }
        for key, blocked in prohibited_regimes.items():
            if labels.get(key) in blocked:
                return "SUSPEND"
        if snapshot.aggregate_confidence < min_confidence:
            return "REDUCE_EXPOSURE"
        for key, allowed in allowed_regimes.items():
            if allowed and labels.get(key) not in allowed:
                return "NO_NEW_ENTRIES"
        return "ACTIVE"

    @staticmethod
    def _features(close: pd.Series, returns: pd.Series, volume: pd.Series) -> dict[str, float]:
        ma20_series = cast(pd.Series, close.rolling(20).mean())
        ma60_series = cast(pd.Series, close.rolling(60).mean())
        ma20 = ma20_series.iloc[-1] if len(close) >= 20 else close.iloc[-1]
        ma60 = ma60_series.iloc[-1] if len(close) >= 60 else ma20
        ret20 = close.pct_change(20).iloc[-1] if len(close) > 20 else 0.0
        ret60 = close.pct_change(60).iloc[-1] if len(close) > 60 else ret20
        ret_std20 = cast(pd.Series, returns.rolling(20).std())
        ret_std60 = cast(pd.Series, returns.rolling(60).std())
        ret_std_rank = cast(pd.Series, returns.rolling(252).std().rank(pct=True))
        vol20 = ret_std20.iloc[-1] * np.sqrt(252) if len(returns) >= 20 else 0.0
        vol60 = ret_std60.iloc[-1] * np.sqrt(252) if len(returns) >= 60 else vol20
        vol_pct = ret_std_rank.iloc[-1] if len(returns) >= 30 else 0.5
        dd = (close.iloc[-1] / close.cummax().iloc[-1] - 1.0) if close.cummax().iloc[-1] else 0.0
        vol_ratio = 1.0
        volume_mean60 = cast(pd.Series, volume.rolling(60).mean()) if len(volume) else pd.Series(dtype=float)
        if len(volume) >= 60 and volume_mean60.iloc[-1] > 0:
            vol_ratio = volume.iloc[-1] / volume_mean60.iloc[-1]
        return {
            "ma20": float(ma20),
            "ma60": float(ma60),
            "ret20": float(ret20) if np.isfinite(ret20) else 0.0,
            "ret60": float(ret60) if np.isfinite(ret60) else 0.0,
            "realized_vol20": float(vol20) if np.isfinite(vol20) else 0.0,
            "realized_vol60": float(vol60) if np.isfinite(vol60) else 0.0,
            "vol_percentile": float(vol_pct) if np.isfinite(vol_pct) else 0.5,
            "drawdown": float(abs(dd)) if np.isfinite(dd) else 0.0,
            "volume_ratio": float(vol_ratio) if np.isfinite(vol_ratio) else 1.0,
        }

    @staticmethod
    def _trend(features: dict[str, float]) -> tuple[str, float]:
        score = 0
        score += 1 if features["ret20"] > 0 else -1
        score += 1 if features["ret60"] > 0 else -1
        score += 1 if features["ma20"] > features["ma60"] else -1
        if score >= 2:
            return "uptrend", min(1.0, 0.55 + abs(features["ret60"]) * 2)
        if score <= -2:
            return "downtrend", min(1.0, 0.55 + abs(features["ret60"]) * 2)
        return "range", 0.60

    @staticmethod
    def _volatility(features: dict[str, float]) -> tuple[str, float]:
        pct = features["vol_percentile"]
        if pct >= 0.95:
            return "crisis", 0.90
        if pct >= 0.75:
            return "high", 0.80
        if pct <= 0.25:
            return "low", 0.75
        return "normal", 0.70

    @staticmethod
    def _liquidity(features: dict[str, float]) -> tuple[str, float]:
        ratio = features["volume_ratio"]
        if ratio < 0.25:
            return "stressed", 0.80
        if ratio < 0.60:
            return "thin", 0.70
        return "normal", 0.75

    @staticmethod
    def _correlation(peer_returns: pd.DataFrame | None) -> tuple[str, float]:
        if peer_returns is None or peer_returns.shape[1] < 2 or len(peer_returns) < 20:
            return "unknown", 0.35
        corr = peer_returns.tail(60).corr().abs()
        avg = (corr.values.sum() - len(corr)) / max(1, len(corr) * (len(corr) - 1))
        if avg > 0.75:
            return "correlation_spike", 0.85
        if avg > 0.50:
            return "clustered", 0.75
        return "diversified", 0.70

    @staticmethod
    def _macro_stress(features: dict[str, float], volatility: str, correlation: str) -> tuple[str, float]:
        stress = 0.0
        stress += features["drawdown"] * 2
        stress += 0.4 if volatility in {"high", "crisis"} else 0.0
        stress += 0.2 if correlation == "correlation_spike" else 0.0
        if stress > 0.75:
            return "stressed", 0.80
        if stress > 0.35:
            return "elevated", 0.70
        return "calm", 0.65

    @staticmethod
    def _risk_mode(trend: str, volatility: str, stress: str) -> tuple[str, float]:
        if trend == "uptrend" and volatility in {"low", "normal"} and stress == "calm":
            return "risk_on", 0.75
        if trend == "downtrend" or volatility == "crisis" or stress == "stressed":
            return "risk_off", 0.80
        return "neutral", 0.65

    @staticmethod
    def _structural_break(returns: pd.Series) -> tuple[str, float]:
        if len(returns) < 80:
            return "none", 0.50
        recent = returns.tail(20)
        prior = returns.tail(80).head(60)
        mean_shift = abs(recent.mean() - prior.mean())
        vol_shift = abs(recent.std() - prior.std())
        threshold = max(prior.std(), 1e-6) * 2.0
        if mean_shift > threshold or vol_shift > threshold:
            return "suspected", 0.75
        return "none", 0.70
