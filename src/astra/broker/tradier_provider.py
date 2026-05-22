"""Tradier broker provider — wraps Tradier REST API."""

import os
from datetime import datetime
from typing import Any

import pandas as pd
import requests

from astra.broker.base import Broker, Account, Position, Order, PortfolioHistory
from astra.broker.factory import register_broker

BASE_URL = "https://api.tradier.com/v1"


class TradierBroker(Broker):
    def __init__(self, **kwargs: Any):
        self._token = kwargs.get("token") or os.getenv("TRADIER_TOKEN", "")
        self._account_id = kwargs.get("account_id") or os.getenv("TRADIER_ACCOUNT_ID", "")
        self._sandbox = kwargs.get("sandbox", True)
        self._session = requests.Session()
        self._session.headers.update({
            "Authorization": f"Bearer {self._token}",
            "Accept": "application/json",
        })
        if self._sandbox:
            self._base = "https://sandbox.tradier.com/v1"
        else:
            self._base = "https://api.tradier.com/v1"

    def get_name(self) -> str:
        return "tradier"

    def is_available(self) -> bool:
        return bool(self._token)

    def _get(self, path: str, params: dict | None = None) -> dict:
        resp = self._session.get(f"{self._base}{path}", params=params, timeout=15)
        resp.raise_for_status()
        return resp.json()

    def _post(self, path: str, data: dict) -> dict:
        resp = self._session.post(f"{self._base}{path}", data=data, timeout=15)
        resp.raise_for_status()
        return resp.json()

    def get_account(self) -> Account:
        try:
            data = self._get(f"/accounts/{self._account_id}/balances") if self._account_id else self._get("/accounts")
            if "accounts" in data and data["accounts"]:
                accounts = data["accounts"].get("account", [])
                if isinstance(accounts, dict):
                    accounts = [accounts]
                if accounts:
                    bal = accounts[0].get("balances", {})
                    return Account(
                        equity=float(bal.get("total_equity", 0)),
                        cash=float(bal.get("cash", 0)),
                        buying_power=float(bal.get("buying_power", 0)),
                        portfolio_value=float(bal.get("total_equity", 0)),
                    )
        except Exception as e:
            print(f"Tradier: get_account failed: {e}")
        return Account()

    def get_positions(self) -> list[Position]:
        try:
            data = self._get(f"/accounts/{self._account_id}/positions") if self._account_id else self._get("/accounts")
            positions = []
            if "positions" in data and data["positions"]:
                raw = data["positions"].get("position", [])
                if isinstance(raw, dict):
                    raw = [raw]
                for p in raw:
                    pos_data = p.get("position", p)
                    positions.append(
                        Position(
                            symbol=pos_data.get("symbol", ""),
                            qty=float(pos_data.get("quantity", 0)),
                            avg_entry_price=float(pos_data.get("cost_basis", 0) or 0),
                            current_price=float(pos_data.get("current_price", 0) or 0),
                            unrealized_pl=float(pos_data.get("unrealized_gain_loss", 0) or 0),
                            side="long" if float(pos_data.get("quantity", 0)) > 0 else "short",
                        )
                    )
            return positions
        except Exception as e:
            print(f"Tradier: get_positions failed: {e}")
            return []

    def get_orders(self, status: str = "all", limit: int = 100) -> list[Order]:
        try:
            params = {"includeTags": "false"}
            if status == "open":
                params["status"] = "open"
            data = self._get(f"/accounts/{self._account_id}/orders", params=params) if self._account_id else {"orders": {}}
            orders = []
            if "orders" in data and data["orders"]:
                raw = data["orders"].get("order", [])
                if isinstance(raw, dict):
                    raw = [raw]
                for o in raw[:limit]:
                    orders.append(
                        Order(
                            id=str(o.get("id", "")),
                            symbol=o.get("symbol", ""),
                            qty=float(o.get("quantity", 0)),
                            side=o.get("side", "").lower(),
                            order_type=o.get("type", "").lower(),
                            status=o.get("status", ""),
                            filled_avg_price=float(o.get("average_fill_price", 0) or 0),
                            filled_qty=float(o.get("filled_quantity", 0) or 0),
                        )
                    )
            return orders
        except Exception as e:
            print(f"Tradier: get_orders failed: {e}")
            return []

    def submit_order(
        self,
        symbol: str,
        qty: float,
        side: str,
        order_type: str = "market",
        time_in_force: str = "day",
    ) -> Order:
        try:
            data = {
                "symbol": symbol,
                "quantity": qty,
                "side": side.capitalize(),
                "type": order_type.lower(),
                "duration": time_in_force.lower(),
            }
            resp_data = self._post(f"/accounts/{self._account_id}/orders", data=data)
            order_data = resp_data.get("order", resp_data)
            return Order(
                id=str(order_data.get("id", "")),
                symbol=symbol,
                qty=qty,
                side=side,
                order_type=order_type,
                status=order_data.get("status", "pending"),
            )
        except Exception as e:
            print(f"Tradier: submit_order failed: {e}")
            return Order(symbol=symbol, qty=qty, side=side, status="failed")

    def close_position(self, symbol: str) -> Order:
        positions = self.get_positions()
        for pos in positions:
            if pos.symbol == symbol:
                side = "sell" if pos.qty > 0 else "buy"
                return self.submit_order(symbol, abs(pos.qty), side)
        return Order(status="no_position")

    def get_portfolio_history(
        self, period: str = "1M", timeframe: str = "1D"
    ) -> PortfolioHistory:
        try:
            data = self._get(f"/accounts/{self._account_id}/history") if self._account_id else {}
            ph = PortfolioHistory(base_value=100000.0)
            if "history" in data and data["history"]:
                raw = data["history"].get("event", [])
                if isinstance(raw, dict):
                    raw = [raw]
                equity_curve = []
                timestamps = []
                for ev in raw:
                    if "equity" in ev:
                        equity_curve.append(float(ev["equity"]))
                        ts = datetime.fromisoformat(ev.get("date", "")).timestamp()
                        timestamps.append(int(ts))
                ph.equity = equity_curve
                ph.timestamps = timestamps
                if equity_curve:
                    ph.base_value = equity_curve[0]
            return ph
        except Exception as e:
            print(f"Tradier: portfolio history failed: {e}")
            return PortfolioHistory(base_value=100000.0)

    def get_bars(
        self, symbol: str, timeframe: str, start: str, end: str
    ) -> pd.DataFrame:
        try:
            tf_map = {
                "1min": "1min",
                "5min": "5min",
                "15min": "15min",
                "30min": "30min",
                "1H": "1hour",
                "daily": "daily",
                "1D": "daily",
                "1W": "weekly",
                "1M": "monthly",
            }
            tf = tf_map.get(timeframe, "daily")
            params = {
                "symbol": symbol,
                "interval": tf,
                "start": start,
                "end": end,
            }
            data = self._get("/markets/history", params=params)
            if "history" in data and data["history"]:
                raw = data["history"].get("day", [])
                if isinstance(raw, dict):
                    raw = [raw]
                records = []
                for r in raw:
                    records.append({
                        "open": float(r.get("open", 0)),
                        "high": float(r.get("high", 0)),
                        "low": float(r.get("low", 0)),
                        "close": float(r.get("close", 0)),
                        "volume": int(r.get("volume", 0)),
                        "date": pd.Timestamp(r.get("date", "")),
                    })
                df = pd.DataFrame(records).set_index("date")
                df.index = pd.to_datetime(df.index)
                df.index.name = "date"
                df = df.sort_index()
                return df
        except Exception as e:
            print(f"Tradier: get_bars failed for {symbol}: {e}")
        return pd.DataFrame()


register_broker("tradier", TradierBroker)
