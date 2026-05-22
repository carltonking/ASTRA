"""Broker ABC — abstract interface for brokerage APIs."""

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from datetime import datetime, timezone

import pandas as pd


@dataclass
class Account:
    equity: float = 0.0
    cash: float = 0.0
    buying_power: float = 0.0
    portfolio_value: float = 0.0
    currency: str = "USD"
    status: str = "ACTIVE"


@dataclass
class Position:
    symbol: str = ""
    qty: float = 0.0
    avg_entry_price: float = 0.0
    current_price: float = 0.0
    unrealized_pl: float = 0.0
    unrealized_plpc: float = 0.0
    side: str = "long"


@dataclass
class Order:
    id: str = ""
    symbol: str = ""
    qty: float = 0.0
    side: str = ""
    order_type: str = "market"
    status: str = ""
    filled_avg_price: float = 0.0
    filled_qty: float = 0.0
    created_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))


@dataclass
class PortfolioHistory:
    timestamps: list[int] = field(default_factory=list)
    equity: list[float] = field(default_factory=list)
    profit_loss: list[float] = field(default_factory=list)
    profit_loss_pct: list[float] = field(default_factory=list)
    base_value: float = 0.0


class Broker(ABC):
    @abstractmethod
    def get_name(self) -> str:
        ...

    @abstractmethod
    def get_account(self) -> Account:
        ...

    @abstractmethod
    def get_positions(self) -> list[Position]:
        ...

    @abstractmethod
    def get_orders(self, status: str = "all", limit: int = 100) -> list[Order]:
        ...

    @abstractmethod
    def submit_order(
        self,
        symbol: str,
        qty: float,
        side: str,
        order_type: str = "market",
        time_in_force: str = "day",
    ) -> Order:
        ...

    @abstractmethod
    def close_position(self, symbol: str) -> Order:
        ...

    @abstractmethod
    def get_portfolio_history(
        self, period: str = "1M", timeframe: str = "1D"
    ) -> PortfolioHistory:
        ...

    @abstractmethod
    def get_bars(
        self, symbol: str, timeframe: str, start: str, end: str
    ) -> "pd.DataFrame":
        ...
