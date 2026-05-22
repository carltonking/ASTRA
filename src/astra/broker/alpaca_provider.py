"""Alpaca broker provider — wraps AstraAlpacaClient into Broker ABC."""

from typing import Any

import pandas as pd

from astra.broker.base import Broker, Account, Position, Order, PortfolioHistory
from astra.broker.factory import register_broker


class AlpacaBroker(Broker):
    def __init__(self, **kwargs: Any):
        from astra.alpaca.client import AstraAlpacaClient

        api_key = kwargs.get("api_key") or kwargs.get("key_id", "")
        api_secret = kwargs.get("api_secret") or kwargs.get("secret_key", "")
        base_url = kwargs.get("base_url", "https://paper-api.alpaca.markets")
        self._client = AstraAlpacaClient(
            api_key=api_key,
            api_secret=api_secret,
            base_url=base_url,
        )

    def get_name(self) -> str:
        return "alpaca"

    def get_account(self) -> Account:
        raw = self._client.get_account()
        return Account(
            equity=raw.equity,
            cash=raw.cash,
            buying_power=raw.buying_power,
            portfolio_value=raw.portfolio_value,
            currency=raw.currency,
            status=raw.status,
        )

    def get_positions(self) -> list[Position]:
        return [
            Position(
                symbol=p.symbol,
                qty=p.qty,
                avg_entry_price=p.avg_entry_price,
                current_price=p.current_price,
                unrealized_pl=p.unrealized_pl,
                unrealized_plpc=p.unrealized_plpc,
                side=p.side,
            )
            for p in self._client.get_positions()
        ]

    def get_orders(self, status: str = "all", limit: int = 100) -> list[Order]:
        return [
            Order(
                id=o.id,
                symbol=o.symbol,
                qty=o.qty,
                side=o.side,
                order_type=o.order_type,
                status=o.status,
                filled_avg_price=o.filled_avg_price,
                filled_qty=o.filled_qty,
                created_at=o.created_at,
            )
            for o in self._client.get_orders(status=status, limit=limit)
        ]

    def submit_order(
        self,
        symbol: str,
        qty: float,
        side: str,
        order_type: str = "market",
        time_in_force: str = "day",
    ) -> Order:
        raw = self._client.submit_order(symbol, qty, side, order_type, time_in_force)
        return Order(
            id=raw.id,
            symbol=raw.symbol,
            qty=raw.qty,
            side=raw.side,
            order_type=raw.order_type,
            status=raw.status,
            filled_avg_price=raw.filled_avg_price,
            filled_qty=raw.filled_qty,
            created_at=raw.created_at,
        )

    def close_position(self, symbol: str) -> Order:
        raw = self._client.close_position(symbol)
        return Order(
            id=raw.id,
            symbol=raw.symbol,
            qty=raw.qty,
            side=raw.side,
            order_type=raw.order_type,
            status=raw.status,
            filled_avg_price=raw.filled_avg_price,
            filled_qty=raw.filled_qty,
            created_at=raw.created_at,
        )

    def get_portfolio_history(
        self, period: str = "1M", timeframe: str = "1D"
    ) -> PortfolioHistory:
        raw = self._client.get_portfolio_history(period, timeframe)
        return PortfolioHistory(
            timestamps=raw.timestamps,
            equity=raw.equity,
            profit_loss=raw.profit_loss,
            profit_loss_pct=raw.profit_loss_pct,
            base_value=raw.base_value,
        )

    def get_bars(
        self, symbol: str, timeframe: str, start: str, end: str
    ) -> pd.DataFrame:
        return self._client.get_bars(symbol, timeframe, start, end)


register_broker("alpaca", AlpacaBroker)
