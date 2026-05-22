"""Polygon.io data provider — REST API for real-time and historical market data."""

import os
import time
from datetime import datetime, timezone
from typing import Any

import pandas as pd
import requests

from astra.data.provider import DataProvider
from astra.data.factory import register_provider

BASE_URL = "https://api.polygon.io"


class PolygonProvider(DataProvider):
    def __init__(self, api_key: str | None = None):
        self._api_key = api_key or os.getenv("POLYGON_API_KEY", "")
        self._session = requests.Session()
        self._session.headers.update({"User-Agent": "ASTRA/1.0"})

    def get_name(self) -> str:
        return "polygon"

    def is_available(self) -> bool:
        return bool(self._api_key)

    def fetch_historical(
        self,
        symbols: list[str],
        start: str,
        end: str,
        interval: str = "1D",
    ) -> dict[str, pd.DataFrame]:
        timespan, multiplier = self._parse_interval(interval)
        dfs: dict[str, pd.DataFrame] = {}
        for symbol in symbols:
            df = self._fetch_single(symbol, timespan, multiplier, start, end)
            if df is not None:
                dfs[symbol] = df
            time.sleep(0.1)
        return dfs

    def _fetch_single(
        self,
        symbol: str,
        timespan: str,
        multiplier: int,
        start: str,
        end: str,
    ) -> pd.DataFrame | None:
        url = (
            f"{BASE_URL}/v2/aggs/ticker/{symbol}/range/"
            f"{multiplier}/{timespan}/{start}/{end}"
        )
        params: dict[str, Any] = {
            "adjusted": "true",
            "sort": "asc",
            "limit": 50000,
            "apiKey": self._api_key,
        }
        try:
            resp = self._session.get(url, params=params, timeout=30)
            resp.raise_for_status()
            data = resp.json()
            if data.get("status") != "OK" or "results" not in data:
                print(f"Polygon: no results for {symbol}")
                return None
            results = data["results"]
            records = []
            for r in results:
                ts = r.get("t", 0) / 1000.0
                records.append({
                    "open": r.get("o", 0.0),
                    "high": r.get("h", 0.0),
                    "low": r.get("l", 0.0),
                    "close": r.get("c", 0.0),
                    "volume": r.get("v", 0),
                    "date": datetime.fromtimestamp(ts, tz=timezone.utc),
                })
            df = pd.DataFrame(records).set_index("date")
            df.index = pd.to_datetime(df.index)
            df.index.name = "date"
            validation = self.validate_data(df)
            if not validation["valid"]:
                print(f"Polygon: {symbol} data flagged: {validation['warnings']}")
            return df
        except requests.exceptions.RequestException as e:
            print(f"Polygon: failed to fetch {symbol}: {e}")
            return None

    @staticmethod
    def _parse_interval(interval: str) -> tuple[str, int]:
        mapping: dict[str, tuple[str, int]] = {
            "1Min": ("minute", 1),
            "5Min": ("minute", 5),
            "15Min": ("minute", 15),
            "30Min": ("minute", 30),
            "1H": ("hour", 1),
            "4H": ("hour", 4),
            "1D": ("day", 1),
            "daily": ("day", 1),
            "1W": ("week", 1),
            "1M": ("month", 1),
        }
        return mapping.get(interval, ("day", 1))


register_provider("polygon", PolygonProvider)
