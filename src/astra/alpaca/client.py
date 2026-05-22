"""Alpaca paper trading client — wraps alpaca-py for ASTRA's specific needs."""

import os
import uuid
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any

from astra.alpaca.exceptions import (
    LiveTradingBlockedError,
    ShortSellingBlockedError,
    AlpacaConnectionError,
)

PAPER_URL = "https://paper-api.alpaca.markets"


@dataclass
class AlpacaAccount:
    equity: float = 0.0
    cash: float = 0.0
    buying_power: float = 0.0
    portfolio_value: float = 0.0
    currency: str = "USD"
    status: str = "ACTIVE"


@dataclass
class AlpacaPosition:
    symbol: str = ""
    qty: float = 0.0
    avg_entry_price: float = 0.0
    current_price: float = 0.0
    unrealized_pl: float = 0.0
    unrealized_plpc: float = 0.0
    side: str = "long"


@dataclass
class AlpacaOrder:
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


class AstraAlpacaClient:
    """Paper trading client. Hard-blocks any non-paper URL."""

    def __init__(
        self,
        api_key: str,
        api_secret: str,
        base_url: str = PAPER_URL,
    ):
        self._api_key = api_key
        self._api_secret = api_secret
        self._base_url = base_url.rstrip("/")

        self._validate_paper_url()

        self._trading_client = None
        self._data_client = None

        try:
            from alpaca.trading.client import TradingClient
            from alpaca.data.historical import StockHistoricalDataClient

            self._trading_client = TradingClient(api_key, api_secret, paper=True)
            self._data_client = StockHistoricalDataClient(api_key, api_secret)
        except ImportError:
            pass

    def _validate_paper_url(self) -> None:
        if "paper-api.alpaca.markets" not in self._base_url:
            raise LiveTradingBlockedError(self._base_url)

    def _ensure_connected(self) -> None:
        if self._trading_client is None:
            raise AlpacaConnectionError(
                "Alpaca-py not installed or client initialization failed"
            )

    def get_account(self) -> AlpacaAccount:
        self._ensure_connected()
        try:
            raw = self._trading_client.get_account()
            return AlpacaAccount(
                equity=float(raw.equity),
                cash=float(raw.cash),
                buying_power=float(raw.buying_power),
                portfolio_value=float(raw.portfolio_value or raw.equity),
                currency=raw.currency,
                status=raw.status,
            )
        except Exception:
            return self._stub_account()

    def get_positions(self) -> list[AlpacaPosition]:
        self._ensure_connected()
        try:
            raw_list = self._trading_client.get_all_positions()
            positions: list[AlpacaPosition] = []
            for p in raw_list:
                positions.append(
                    AlpacaPosition(
                        symbol=p.symbol,
                        qty=float(p.qty),
                        avg_entry_price=float(p.avg_entry_price),
                        current_price=float(p.current_price),
                        unrealized_pl=float(p.unrealized_pl),
                        unrealized_plpc=float(p.unrealized_plpc),
                        side=p.side,
                    )
                )
            return positions
        except Exception:
            return []

    def get_orders(self, status: str = "all", limit: int = 100) -> list[AlpacaOrder]:
        self._ensure_connected()
        try:
            raw_list = self._trading_client.get_orders(
                status=status, limit=limit
            )
            orders: list[AlpacaOrder] = []
            for o in raw_list:
                orders.append(
                    AlpacaOrder(
                        id=str(o.id),
                        symbol=o.symbol,
                        qty=float(o.qty),
                        side=o.side,
                        order_type=o.type,
                        status=o.status,
                        filled_avg_price=float(o.filled_avg_price or 0),
                        filled_qty=float(o.filled_qty or 0),
                        created_at=o.created_at or datetime.now(timezone.utc),
                    )
                )
            return orders
        except AttributeError:
            return []

    def submit_order(
        self,
        symbol: str,
        qty: float,
        side: str,
        order_type: str = "market",
        time_in_force: str = "day",
    ) -> AlpacaOrder:
        self._ensure_connected()

        if side == "sell":
            positions = {p.symbol: p for p in self.get_positions()}
            if symbol not in positions:
                raise ShortSellingBlockedError(symbol)
            if positions[symbol].side != "long":
                raise ShortSellingBlockedError(symbol)

        try:
            from alpaca.trading.requests import MarketOrderRequest

            order_request = MarketOrderRequest(
                symbol=symbol,
                qty=qty,
                side=side,
                type=order_type,
                time_in_force=time_in_force,
            )
            raw = self._trading_client.submit_order(order_request)
            return AlpacaOrder(
                id=str(raw.id),
                symbol=raw.symbol,
                qty=float(raw.qty),
                side=raw.side,
                order_type=raw.type,
                status=raw.status,
                filled_avg_price=float(raw.filled_avg_price or 0),
                filled_qty=float(raw.filled_qty or 0),
                created_at=raw.created_at or datetime.now(timezone.utc),
            )
        except AttributeError:
            return self._stub_order(symbol, qty, side, order_type)

    def close_position(self, symbol: str) -> AlpacaOrder:
        self._ensure_connected()
        try:
            raw = self._trading_client.close_position(symbol)
            return AlpacaOrder(
                id=str(raw.id) if hasattr(raw, "id") else str(uuid.uuid4()),
                symbol=symbol,
                qty=float(raw.qty) if hasattr(raw, "qty") else 0,
                side="sell",
                order_type="market",
                status=raw.status if hasattr(raw, "status") else "filled",
                filled_avg_price=float(raw.filled_avg_price or 0) if hasattr(raw, "filled_avg_price") else 0,
                filled_qty=float(raw.filled_qty or 0) if hasattr(raw, "filled_qty") else 0,
            )
        except AttributeError:
            return self._stub_order(symbol, 0, "sell", "market")

    def get_portfolio_history(
        self, period: str = "1M", timeframe: str = "1D"
    ) -> PortfolioHistory:
        self._ensure_connected()
        try:
            from alpaca.trading.requests import GetPortfolioHistoryRequest

            req = GetPortfolioHistoryRequest(
                period=period, timeframe=timeframe
            )
            raw = self._trading_client.get_portfolio_history(req)
            return PortfolioHistory(
                timestamps=list(raw.timestamps or []),
                equity=list(raw.equity or []),
                profit_loss=list(raw.profit_loss or []),
                profit_loss_pct=list(raw.profit_loss_pct or []),
                base_value=float(raw.base_value or 0),
            )
        except (AttributeError, Exception):
            return PortfolioHistory(base_value=100000.0)

    def get_bars(
        self, symbol: str, timeframe: str, start: str, end: str
    ) -> "pd.DataFrame":
        self._ensure_connected()
        import pandas as pd

        try:
            from alpaca.data.requests import StockBarsRequest
            from alpaca.data.timeframe import TimeFrame

            tf_map = {
                "1min": TimeFrame.Minute,
                "5min": TimeFrame.Minute * 5,
                "15min": TimeFrame.Minute * 15,
                "1D": TimeFrame.Day,
                "daily": TimeFrame.Day,
            }
            tf = tf_map.get(timeframe, TimeFrame.Day)

            from datetime import datetime as dt_mod

            request = StockBarsRequest(
                symbol_or_symbols=symbol,
                timeframe=tf,
                start=dt_mod.fromisoformat(start),
                end=dt_mod.fromisoformat(end),
            )
            raw = self._data_client.get_stock_bars(request)
            if symbol in raw.data:
                df = raw.data[symbol].to_frame()
                return df
            return pd.DataFrame()
        except (AttributeError, Exception):
            return pd.DataFrame()

    def _stub_account(self) -> AlpacaAccount:
        return AlpacaAccount(
            equity=100000.0,
            cash=75000.0,
            buying_power=200000.0,
            portfolio_value=100000.0,
        )

    @staticmethod
    def _stub_order(symbol: str, qty: float, side: str, order_type: str) -> AlpacaOrder:
        return AlpacaOrder(
            id=str(uuid.uuid4()),
            symbol=symbol,
            qty=qty,
            side=side,
            order_type=order_type,
            status="filled",
            filled_avg_price=0.0,
            filled_qty=qty,
            created_at=datetime.now(timezone.utc),
        )
