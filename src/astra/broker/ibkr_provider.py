"""IBKR broker provider — wraps Interactive Brokers API via ib_insync."""

import os
from typing import Any

import pandas as pd

from astra.broker.base import Broker, Account, Position, Order, PortfolioHistory
from astra.broker.factory import register_broker


class IBKRBroker(Broker):
    def __init__(self, **kwargs: Any):
        self._host = kwargs.get("host") or os.getenv("IBKR_HOST", "127.0.0.1")
        self._port = int(kwargs.get("port") or os.getenv("IBKR_PORT", "7497"))
        self._client_id = int(kwargs.get("client_id") or os.getenv("IBKR_CLIENT_ID", "1"))
        self._account_id = kwargs.get("account_id") or os.getenv("IBKR_ACCOUNT_ID", "")
        self._ib = None

    def get_name(self) -> str:
        return "ibkr"

    def _ensure_connected(self):
        if self._ib is not None and self._ib.isConnected():
            return
        try:
            from ib_insync import IB
            self._ib = IB()
            self._ib.connect(self._host, self._port, clientId=self._client_id)
        except ImportError:
            raise RuntimeError(
                "ib_insync not installed. Install with: pip install ib_insync"
            )

    def is_available(self) -> bool:
        try:
            self._ensure_connected()
            return self._ib is not None and self._ib.isConnected()
        except Exception:
            return False

    def get_account(self) -> Account:
        self._ensure_connected()
        raw = self._ib.accountSummary()
        summary = {item.tag: item.value for item in raw}
        return Account(
            equity=float(summary.get("NetLiquidation", 0)),
            cash=float(summary.get("TotalCashValue", 0)),
            buying_power=float(summary.get("BuyingPower", 0)),
            portfolio_value=float(summary.get("NetLiquidation", 0)),
            currency=summary.get("Currency", "USD"),
        )

    def get_positions(self) -> list[Position]:
        self._ensure_connected()
        raw = self._ib.positions()
        return [
            Position(
                symbol=p.contract.symbol,
                qty=float(p.position),
                avg_entry_price=float(p.avgCost),
                current_price=float(p.marketPrice),
                unrealized_pl=float(p.unrealizedPNL),
                unrealized_plpc=0.0,
                side="long" if p.position > 0 else "short",
            )
            for p in raw
        ]

    def get_orders(self, status: str = "all", limit: int = 100) -> list[Order]:
        self._ensure_connected()
        raw = self._ib.openOrders()
        orders = []
        for o in raw[:limit]:
            orders.append(
                Order(
                    id=str(o.orderId),
                    symbol=o.contract.symbol,
                    qty=float(o.order.totalQuantity),
                    side="buy" if o.order.action == "BUY" else "sell",
                    order_type=o.order.orderType.lower(),
                    status=o.orderStatus.status,
                    filled_avg_price=float(o.orderStatus.avgFillPrice or 0),
                    filled_qty=float(o.orderStatus.filled or 0),
                )
            )
        return orders

    def submit_order(
        self,
        symbol: str,
        qty: float,
        side: str,
        order_type: str = "market",
        time_in_force: str = "day",
    ) -> Order:
        self._ensure_connected()
        from ib_insync import Stock, MarketOrder

        contract = Stock(symbol, "SMART", "USD")
        ib_side = "BUY" if side == "buy" else "SELL"
        if order_type == "market":
            ib_order = MarketOrder(ib_side, qty)
        else:
            raise ValueError(f"IBKR: unsupported order type: {order_type}")
        trade = self._ib.placeOrder(contract, ib_order)
        return Order(
            id=str(trade.order.orderId),
            symbol=symbol,
            qty=qty,
            side=side,
            order_type=order_type,
            status=trade.orderStatus.status,
            filled_qty=float(trade.orderStatus.filled or 0),
        )

    def close_position(self, symbol: str) -> Order:
        self._ensure_connected()
        for pos in self._ib.positions():
            if pos.contract.symbol == symbol:
                side = "sell" if pos.position > 0 else "buy"
                return self.submit_order(symbol, abs(float(pos.position)), side)
        return Order(status="no_position")

    def get_portfolio_history(
        self, period: str = "1M", timeframe: str = "1D"
    ) -> PortfolioHistory:
        self._ensure_connected()
        try:
            from ib_insync import Stock
            import pandas as pd
            raw = self._ib.reqHistoricalData(
                contract=Stock("SPY", "SMART", "USD"),
                endDateTime="",
                durationStr=self._to_duration(period),
                barSizeSetting=self._to_bar_size(timeframe),
                whatToShow="TRADES",
                useRTH=True,
            )
            if raw:
                df = pd.DataFrame(raw)
                return PortfolioHistory(
                    timestamps=[int(t.timestamp()) for t in df["date"]],
                    equity=list(df["close"]),
                    profit_loss=list(df["close"] - df["open"]),
                    profit_loss_pct=list((df["close"] - df["open"]) / df["open"] * 100),
                    base_value=float(df["close"].iloc[0]),
                )
        except Exception as e:
            print(f"IBKR: portfolio history failed: {e}")
        return PortfolioHistory(base_value=100000.0)

    def get_bars(
        self, symbol: str, timeframe: str, start: str, end: str
    ) -> pd.DataFrame:
        self._ensure_connected()
        from ib_insync import Stock
        contract = Stock(symbol, "SMART", "USD")
        raw = self._ib.reqHistoricalData(
            contract=contract,
            endDateTime=end,
            durationStr=self._to_duration_from_dates(start, end),
            barSizeSetting=self._to_bar_size(timeframe),
            whatToShow="TRADES",
            useRTH=True,
        )
        if raw:
            import pandas as pd
            df = pd.DataFrame(raw)
            df = df.rename(columns={
                "open": "open",
                "high": "high",
                "low": "low",
                "close": "close",
                "volume": "volume",
            })
            df = df[["date", "open", "high", "low", "close", "volume"]]
            df = df.set_index("date")
            df.index = pd.to_datetime(df.index)
            df.index.name = "date"
            return df
        return pd.DataFrame()

    @staticmethod
    def _to_duration(period: str) -> str:
        mapping = {"1W": "7 D", "1M": "30 D", "3M": "90 D", "6M": "180 D", "1Y": "1 Y"}
        return mapping.get(period, "30 D")

    @staticmethod
    def _to_duration_from_dates(start: str, end: str) -> str:
        from datetime import datetime
        s = datetime.fromisoformat(start) if isinstance(start, str) else start
        e = datetime.fromisoformat(end) if isinstance(end, str) else end
        days = (e - s).days
        return f"{days} D"

    @staticmethod
    def _to_bar_size(timeframe: str) -> str:
        mapping = {
            "1min": "1 min",
            "5min": "5 mins",
            "15min": "15 mins",
            "30min": "30 mins",
            "1H": "1 hour",
            "4H": "4 hours",
            "1D": "1 day",
            "daily": "1 day",
            "1W": "1 week",
        }
        return mapping.get(timeframe, "1 day")


register_broker("ibkr", IBKRBroker)
