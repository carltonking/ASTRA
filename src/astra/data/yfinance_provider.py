"""yfinance data provider — free Yahoo Finance data via yfinance library."""

import concurrent.futures
import time

import pandas as pd

from astra.data.provider import DataProvider
from astra.data.factory import register_provider


def _retry(fn, max_retries: int = 3, delay: float = 1.0):
    last_error = None
    for attempt in range(max_retries):
        try:
            return fn()
        except Exception as e:
            last_error = e
            if attempt < max_retries - 1:
                time.sleep(delay * (2**attempt))
    raise last_error


class YFinanceProvider(DataProvider):
    def get_name(self) -> str:
        return "yfinance"

    def is_available(self) -> bool:
        try:
            import yfinance  # noqa: F401
            return True
        except ImportError:
            return False

    def fetch_historical(
        self,
        symbols: list[str],
        start: str,
        end: str,
        interval: str = "1D",
    ) -> dict[str, pd.DataFrame]:
        import yfinance as yf

        dfs: dict[str, pd.DataFrame] = {}
        with concurrent.futures.ThreadPoolExecutor(max_workers=5) as pool:
            def _fetch(symbol: str):
                try:
                    def _inner():
                        ticker = yf.Ticker(symbol)
                        df = ticker.history(start=start, end=end, interval=interval)
                        if not df.empty:
                            df.columns = [c.lower() for c in df.columns]
                        return df
                    df = _retry(_inner, max_retries=3, delay=1.0)
                    if not df.empty:
                        validation = self.validate_data(df)
                        if not validation["valid"]:
                            print(f"yfinance: {symbol} data flagged: {validation['warnings']}")
                        return symbol, df
                    print(f"yfinance: {symbol} returned empty data")
                except Exception as e:
                    print(f"yfinance: failed to fetch {symbol}: {e}")
                return symbol, None
            for sym, df in pool.map(_fetch, symbols):
                if df is not None:
                    dfs[sym] = df
        return dfs


register_provider("yfinance", YFinanceProvider)
