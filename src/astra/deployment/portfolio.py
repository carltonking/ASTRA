"""Portfolio state and exposure accounting for paper deployments."""

from dataclasses import dataclass, field

from astra.broker.base import Account, Broker, Position


@dataclass
class PortfolioState:
    account: Account
    positions: list[Position] = field(default_factory=list)
    gross_exposure: float = 0.0
    net_exposure: float = 0.0
    concentration: dict[str, float] = field(default_factory=dict)
    largest_position_weight: float = 0.0


class PortfolioManager:
    def __init__(self, broker: Broker):
        self._broker = broker

    def snapshot(self) -> PortfolioState:
        account = self._broker.get_account()
        positions = self._broker.get_positions()
        equity = self._as_float(account.equity) or self._as_float(account.portfolio_value)
        gross = 0.0
        net = 0.0
        concentration: dict[str, float] = {}

        for pos in positions:
            qty = self._as_float(pos.qty)
            market_value = abs(qty * self._as_float(pos.current_price))
            if market_value == 0 and pos.avg_entry_price:
                market_value = abs(qty * self._as_float(pos.avg_entry_price))
            signed = market_value if pos.side != "short" else -market_value
            gross += market_value
            net += signed
            concentration[pos.symbol] = market_value / equity if equity > 0 else 0.0

        largest = max(concentration.values(), default=0.0)
        return PortfolioState(
            account=account,
            positions=positions,
            gross_exposure=gross / equity if equity > 0 else 0.0,
            net_exposure=net / equity if equity > 0 else 0.0,
            concentration=concentration,
            largest_position_weight=largest,
        )

    @staticmethod
    def _as_float(value: object) -> float:
        try:
            if isinstance(value, (int, float, str)):
                return float(value)
            if hasattr(value, "__float__"):
                return float(value)  # type: ignore[arg-type]
            return 0.0
        except (TypeError, ValueError):
            return 0.0
