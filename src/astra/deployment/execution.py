"""Order management and paper execution simulation."""

import uuid
from dataclasses import dataclass
from datetime import datetime, timezone

from astra.broker.base import Broker, Order
from astra.deployment.audit import TradeAuditLog
from astra.deployment.risk import RiskDecision, RiskEngine


@dataclass
class SimulatedFill:
    symbol: str
    qty: float
    side: str
    fill_price: float
    slippage_bps: float
    spread_bps: float
    timestamp: datetime


class ExecutionSimulator:
    def __init__(self, slippage_bps: float = 5.0, spread_bps: float = 2.0):
        self._slippage_bps = slippage_bps
        self._spread_bps = spread_bps

    def simulate(self, symbol: str, qty: float, side: str, mid_price: float) -> SimulatedFill:
        direction = 1 if side.lower() == "buy" else -1
        cost = (self._slippage_bps + self._spread_bps / 2.0) / 10_000.0
        fill_price = mid_price * (1 + direction * cost)
        return SimulatedFill(
            symbol=symbol,
            qty=qty,
            side=side,
            fill_price=round(fill_price, 6),
            slippage_bps=self._slippage_bps,
            spread_bps=self._spread_bps,
            timestamp=datetime.now(timezone.utc),
        )


class OrderManager:
    """Paper-only order submission with risk checks and audit records."""

    def __init__(
        self,
        broker: Broker,
        risk_engine: RiskEngine,
        audit_log: TradeAuditLog,
    ):
        self._broker = broker
        self._risk = risk_engine
        self._audit = audit_log

    def submit_buy(
        self,
        deployment_id: str,
        symbol: str,
        qty: float,
        open_order_count: int,
    ) -> tuple[Order | None, RiskDecision]:
        decision = self._risk.check_order("buy", open_order_count)
        if not decision.allowed:
            self._audit.record("order_blocked", deployment_id, {"symbol": symbol, "reasons": decision.reasons})
            return None, decision
        order = self._broker.submit_order(
            symbol=symbol,
            qty=qty,
            side="buy",
            order_type="market",
            time_in_force="day",
        )
        self._audit.record("order_submitted", deployment_id, {"order": order})
        return order, decision

    def close_position(self, deployment_id: str, symbol: str) -> Order:
        order = self._broker.close_position(symbol)
        self._audit.record("position_closed", deployment_id, {"order": order})
        return order

    @staticmethod
    def simulated_order(symbol: str, qty: float, side: str, price: float) -> Order:
        return Order(
            id=f"sim-{uuid.uuid4()}",
            symbol=symbol,
            qty=qty,
            side=side,
            order_type="simulated",
            status="filled",
            filled_avg_price=price,
            filled_qty=qty,
        )
