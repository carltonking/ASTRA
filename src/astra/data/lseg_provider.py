"""LSEG Workspace provider — wraps lseg_client functions into DataProvider ABC."""

import concurrent.futures

from typing import Any

import pandas as pd

from astra.data.provider import DataProvider
from astra.data.factory import register_provider


class LSEGProvider(DataProvider):
    def __init__(self) -> None:
        self._lseg_client: Any = None
        self._import_lseg()

    def _import_lseg(self) -> None:
        try:
            from astra.data import lseg_client

            self._lseg_client = lseg_client
        except ImportError:
            self._lseg_client = None

    def get_name(self) -> str:
        return "lseg"

    def is_available(self) -> bool:
        if self._lseg_client is None:
            return False
        return self._lseg_client.is_available() and self._lseg_client.is_session_open()

    def fetch_historical(
        self,
        symbols: list[str],
        start: str,
        end: str,
        interval: str = "1D",
    ) -> dict[str, pd.DataFrame]:
        if not self.is_available():
            return {}
        lseg = self._lseg_client
        dfs: dict[str, pd.DataFrame] = {}
        with concurrent.futures.ThreadPoolExecutor(max_workers=5) as pool:
            def _fetch(symbol: str):
                ric = lseg.RIC_MAP.get(symbol, symbol)
                try:
                    df = lseg.get_historical_data(ric, interval=interval, start=start, end=end)
                    if df is not None and not df.empty:
                        return symbol, df
                except Exception as e:
                    print(f"LSEG: failed to fetch {symbol}: {e}")
                return symbol, None
            for sym, df in pool.map(_fetch, symbols):
                if df is not None:
                    dfs[sym] = df
        return dfs


register_provider("lseg", LSEGProvider)
