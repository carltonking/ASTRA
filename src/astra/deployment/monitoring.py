"""Broker heartbeat, reconnect, and stale-data checks."""

import time
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any, Callable, cast

import pandas as pd

from astra.broker.base import Broker


@dataclass
class HeartbeatStatus:
    ok: bool
    broker_name: str = ""
    checked_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
    latency_ms: float = 0.0
    error: str | None = None


class HeartbeatMonitor:
    def __init__(self, broker: Broker):
        self._broker = broker

    def check(self) -> HeartbeatStatus:
        started = time.monotonic()
        try:
            self._broker.get_account()
            latency = (time.monotonic() - started) * 1000
            return HeartbeatStatus(
                ok=True,
                broker_name=self._broker.get_name(),
                latency_ms=round(latency, 3),
            )
        except Exception as e:
            latency = (time.monotonic() - started) * 1000
            return HeartbeatStatus(
                ok=False,
                broker_name=self._safe_name(),
                latency_ms=round(latency, 3),
                error=str(e),
            )

    def _safe_name(self) -> str:
        try:
            return self._broker.get_name()
        except Exception:
            return "unknown"


class BrokerReconnect:
    """Retry broker calls with bounded backoff.

    Broker ABC has no explicit reconnect method, so reconnect means re-issuing
    broker health calls and surfacing failure deterministically.
    """

    def __init__(self, retries: int = 3, backoff_seconds: float = 0.25):
        self._retries = retries
        self._backoff_seconds = backoff_seconds

    def call(self, fn: Callable[..., Any], *args: Any, **kwargs: Any) -> Any:
        last_error: Exception | None = None
        for attempt in range(self._retries):
            try:
                return fn(*args, **kwargs)
            except Exception as e:
                last_error = e
                if attempt < self._retries - 1:
                    time.sleep(self._backoff_seconds * (2 ** attempt))
        if last_error is not None:
            raise last_error
        raise RuntimeError("broker reconnect failed without error")


@dataclass
class StaleDataReport:
    stale_symbols: list[str] = field(default_factory=list)
    latest_timestamps: dict[str, str] = field(default_factory=dict)

    @property
    def ok(self) -> bool:
        return not self.stale_symbols


class StaleDataDetector:
    def __init__(self, max_age_days: int = 7):
        self._max_age_days = max_age_days

    def check(self, bars: dict[str, pd.DataFrame]) -> StaleDataReport:
        now = datetime.now(timezone.utc)
        stale: list[str] = []
        latest: dict[str, str] = {}
        for symbol, df in bars.items():
            if df.empty or not isinstance(df.index, pd.DatetimeIndex):
                stale.append(symbol)
                continue
            ts = pd.Timestamp(cast(Any, df.index.max()))
            if ts.tzinfo is None:
                ts = ts.tz_localize(timezone.utc)
            else:
                ts = ts.tz_convert(timezone.utc)
            latest[symbol] = ts.isoformat()
            if (now - ts.to_pydatetime()).days > self._max_age_days:
                stale.append(symbol)
        return StaleDataReport(stale_symbols=stale, latest_timestamps=latest)
