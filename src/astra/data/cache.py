"""Disk cache for market data — reduces redundant API calls.

Stores DataFrames as Parquet files keyed by (source, symbol, start, end, interval).
Default TTL: 1 hour. Cache dir: .astra/cache/
"""
import hashlib
import json
import os
import time
from pathlib import Path

import pandas as pd


def _cache_dir() -> Path:
    base = Path(os.environ.get("ASTRA_DB_PATH", ".astra")).parent
    path = base / "cache"
    path.mkdir(parents=True, exist_ok=True)
    return path


def _cache_key(source: str, symbols: list[str], start: str, end: str, interval: str) -> str:
    raw = json.dumps([source, sorted(symbols), start, end, interval], sort_keys=True)
    return hashlib.sha256(raw.encode()).hexdigest()[:32]


def _meta_path(key: str) -> Path:
    return _cache_dir() / f"{key}.json"


def _data_path(key: str) -> Path:
    return _cache_dir() / f"{key}.parquet"


def get_cached(
    source: str,
    symbols: list[str],
    start: str,
    end: str,
    interval: str,
    ttl: int = 3600,
) -> dict[str, pd.DataFrame] | None:
    """Return cached data if TTL has not expired, else None."""
    key = _cache_key(source, symbols, start, end, interval)
    meta = _meta_path(key)
    data = _data_path(key)
    if not meta.exists() or not data.exists():
        return None
    try:
        with open(meta) as f:
            cached_at = json.load(f)["cached_at"]
        if time.time() - cached_at > ttl:
            return None
        result: dict[str, pd.DataFrame] = {}
        store = pd.read_parquet(data)
        for sym in symbols:
            if sym in store.columns:
                df = store[sym].dropna()
                if isinstance(df, pd.DataFrame):
                    result[sym] = df
                else:
                    series = df
                    result[sym] = series.to_frame("close")
        return result if result else None
    except Exception:
        return None


def set_cache(
    source: str,
    symbols: list[str],
    start: str,
    end: str,
    interval: str,
    data: dict[str, pd.DataFrame],
) -> None:
    """Store fetched data to disk cache."""
    key = _cache_key(source, symbols, start, end, interval)
    dirpath = _cache_dir()
    with open(dirpath / f"{key}.json", "w") as f:
        json.dump({"cached_at": time.time()}, f)
    store = {}
    for sym, df in data.items():
        store[sym] = df["close"] if "close" in df.columns else pd.Series(dtype=float)
    pd.DataFrame(store).to_parquet(dirpath / f"{key}.parquet")


def clear_cache() -> int:
    """Remove all cache files. Returns count of files removed."""
    dirpath = _cache_dir()
    count = 0
    for f in dirpath.glob("*.parquet"):
        f.unlink()
        count += 1
    for f in dirpath.glob("*.json"):
        f.unlink()
        count += 1
    return count // 2
