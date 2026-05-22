"""Data provider abstraction — ABC for all market data sources."""

from abc import ABC, abstractmethod

import pandas as pd


class DataProvider(ABC):
    """Abstract base class for market data providers."""

    @abstractmethod
    def get_name(self) -> str:
        ...

    @abstractmethod
    def is_available(self) -> bool:
        ...

    @abstractmethod
    def fetch_historical(
        self,
        symbols: list[str],
        start: str,
        end: str,
        interval: str = "1D",
    ) -> dict[str, pd.DataFrame]:
        ...

    def validate_data(self, df: pd.DataFrame) -> dict[str, str | bool | int]:
        result: dict[str, str | bool | int] = {
            "valid": True,
            "warnings": [],
            "missing_dates": 0,
        }
        if df.empty:
            result["valid"] = False
            result["warnings"].append("Empty dataframe")
            return result
        if df.isna().sum().sum() > 0:
            result["warnings"].append(
                f"Data contains {int(df.isna().sum().sum())} NaN values"
            )
        if len(df) < 20:
            result["warnings"].append(
                f"Only {len(df)} data points (< 20 suggested minimum)"
            )
        return result
