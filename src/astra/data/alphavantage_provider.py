"""Alpha Vantage data provider — free API for historical market data."""

import os
import time
from typing import Any

import pandas as pd
import requests

from astra.data.provider import DataProvider
from astra.data.factory import register_provider

BASE_URL = "https://www.alphavantage.co/query"


class AlphaVantageProvider(DataProvider):
    def __init__(self, api_key: str | None = None):
        self._api_key = api_key or os.getenv("ALPHA_VANTAGE_API_KEY", "")
        self._session = requests.Session()
        self._session.headers.update({"User-Agent": "ASTRA/1.0"})

    def get_name(self) -> str:
        return "alphavantage"

    def is_available(self) -> bool:
        return bool(self._api_key)

    def fetch_historical(
        self,
        symbols: list[str],
        start: str,
        end: str,
        interval: str = "1D",
    ) -> dict[str, pd.DataFrame]:
        function, outputsize = self._parse_interval(interval)
        dfs: dict[str, pd.DataFrame] = {}
        for symbol in symbols:
            df = self._fetch_single(symbol, function, outputsize)
            if df is not None:
                df = df.loc[start:end]
                if not df.empty:
                    validation = self.validate_data(df)
                    if not validation["valid"]:
                        print(f"AlphaVantage: {symbol} data flagged: {validation['warnings']}")
                    dfs[symbol] = df
            time.sleep(12)
        return dfs

    def _fetch_single(
        self,
        symbol: str,
        function: str,
        outputsize: str = "full",
    ) -> pd.DataFrame | None:
        params: dict[str, Any] = {
            "function": function,
            "symbol": symbol,
            "outputsize": outputsize,
            "apikey": self._api_key,
        }
        try:
            resp = self._session.get(BASE_URL, params=params, timeout=30)
            resp.raise_for_status()
            data = resp.json()
            time_series_key = next((k for k in data if "Time Series" in k), None)
            if time_series_key is None:
                msg = data.get("Note", data.get("Information", "Unknown error"))
                print(f"AlphaVantage: {symbol} — {msg}")
                return None
            records = []
            for date_str, values in data[time_series_key].items():
                records.append({
                    "open": float(values.get("1. open", 0)),
                    "high": float(values.get("2. high", 0)),
                    "low": float(values.get("3. low", 0)),
                    "close": float(values.get("4. close", 0)),
                    "volume": int(float(values.get("5. volume", 0))),
                    "date": pd.Timestamp(date_str),
                })
            df = pd.DataFrame(records).set_index("date")
            df.index = pd.to_datetime(df.index)
            df.index.name = "date"
            df = df.sort_index()
            return df
        except requests.exceptions.RequestException as e:
            print(f"AlphaVantage: failed to fetch {symbol}: {e}")
            return None

    @staticmethod
    def _parse_interval(interval: str) -> tuple[str, str]:
        mapping: dict[str, tuple[str, str]] = {
            "1Min": ("TIME_SERIES_INTRADAY", "full"),
            "5Min": ("TIME_SERIES_INTRADAY", "full"),
            "15Min": ("TIME_SERIES_INTRADAY", "full"),
            "30Min": ("TIME_SERIES_INTRADAY", "full"),
            "1H": ("TIME_SERIES_INTRADAY", "full"),
            "4H": ("TIME_SERIES_INTRADAY", "full"),
            "1D": ("TIME_SERIES_DAILY", "full"),
            "daily": ("TIME_SERIES_DAILY", "full"),
            "1W": ("TIME_SERIES_WEEKLY", "full"),
            "1M": ("TIME_SERIES_MONTHLY", "full"),
        }
        return mapping.get(interval, ("TIME_SERIES_DAILY", "full"))


register_provider("alphavantage", AlphaVantageProvider)
