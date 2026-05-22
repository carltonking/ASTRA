"""Broker abstraction — unified interface for multiple brokerage APIs."""

from astra.broker.base import (
    Broker,
    Account,
    Position,
    Order,
    PortfolioHistory,
)
from astra.broker.factory import create_broker, register_broker, list_brokers

# Ensure built-in brokers are registered
import astra.broker.alpaca_provider  # noqa: F401
import astra.broker.ibkr_provider  # noqa: F401
import astra.broker.tradier_provider  # noqa: F401

__all__ = [
    "Broker",
    "Account",
    "Position",
    "Order",
    "PortfolioHistory",
    "create_broker",
    "register_broker",
    "list_brokers",
]
