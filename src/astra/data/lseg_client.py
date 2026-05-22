"""LSEG Workspace data client — provides historical and real-time market data."""

import os

from dotenv import load_dotenv

load_dotenv()

try:
    import lseg.data as ld  # type: ignore
    _lseg_available = True
except ImportError:
    ld = None  # type: ignore
    _lseg_available = False

_session_open = False


def is_available() -> bool:
    return _lseg_available


def is_session_open() -> bool:
    return _session_open


def open_session() -> None:
    global _session_open
    if not _lseg_available:
        print("WARNING: lseg-data package not installed. Install with: pip install lseg-data")
        _session_open = False
        return
    assert ld is not None
    try:
        app_key = os.getenv("LSEG_APP_KEY")
        if not app_key:
            print("WARNING: LSEG_APP_KEY not set in .env")
            _session_open = False
            return
        ld.open_session(app_key=app_key)
        _session_open = True
        print("LSEG session opened")
    except Exception as e:
        print(f"WARNING: LSEG session failed to open: {e}")
        print("LSEG Workspace may not be running. Install and run the LSEG Workspace desktop app.")
        _session_open = False


def close_session() -> None:
    global _session_open
    if not _lseg_available or not _session_open:
        _session_open = False
        return
    assert ld is not None
    try:
        ld.close_session()
        print("LSEG session closed")
    except Exception as e:
        print(f"WARNING: LSEG session close failed: {e}")
    finally:
        _session_open = False


def get_historical_data(
    symbol: str,
    interval: str = "1D",
    start: str = "2020-01-01",
    end: str | None = None,
):
    """Fetch OHLCV historical data for a given RIC symbol.

    interval options: 1Min, 5Min, 15Min, 30Min, 1H, 4H, 1D, 1W, 1M
    """
    if not _lseg_available:
        print("WARNING: lseg-data not available, cannot fetch historical data")
        return None
    if not _session_open:
        print("WARNING: LSEG session not open, call open_session() first")
        return None
    assert ld is not None
    try:
        fields = ["OPEN_PRC", "HIGH_1", "LOW_1", "TRDPRC_1", "ACVOL_UNS"]
        df = ld.get_history(
            universe=symbol,
            fields=fields,
            interval=interval,
            start=start,
            end=end,
        )
        return df
    except Exception as e:
        print(f"ERROR: LSEG get_historical_data failed for {symbol} ({interval}): {e}")
        return None


def get_realtime_snapshot(symbol: str):
    """Get latest price snapshot for a symbol."""
    if not _lseg_available:
        return None
    assert ld is not None
    try:
        data = ld.get_data(
            universe=symbol,
            fields=["BID", "ASK", "TRDPRC_1", "ACVOL_UNS", "PCTCHNG"],
        )
        return data
    except Exception as e:
        print(f"ERROR: LSEG get_realtime_snapshot failed for {symbol}: {e}")
        return None


def search_symbol(query: str):
    """Search for a RIC code by company name or ticker."""
    if not _lseg_available:
        return None
    assert ld is not None
    try:
        result = ld.search(query=query, filter="AssetType eq 'CommonStock'")
        return result
    except Exception as e:
        print(f"ERROR: LSEG search_symbol failed for '{query}': {e}")
        return None


RIC_MAP = {
    "AAPL": "AAPL.O",
    "TSLA": "TSLA.O",
    "MSFT": "MSFT.O",
    "GOOGL": "GOOG.O",
    "AMZN": "AMZN.O",
    "NVDA": "NVDA.O",
    "SPY": "SPY",
    "QQQ": "QQQ.O",
    "BTC": "BTC=",
    "ETH": "ETH=",
    "EUR/USD": "EUR=",
    "GLD": "GLD",
}
