"""Market data providers — abstraction for multiple data sources."""

from astra.data.provider import DataProvider
from astra.data.factory import create_data_provider, register_provider, list_providers

# Ensure built-in providers are registered
import astra.data.lseg_provider  # noqa: F401
import astra.data.yfinance_provider  # noqa: F401
import astra.data.polygon_provider  # noqa: F401
import astra.data.alphavantage_provider  # noqa: F401

__all__ = [
    "DataProvider",
    "create_data_provider",
    "register_provider",
    "list_providers",
]
