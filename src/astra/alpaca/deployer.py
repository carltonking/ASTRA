"""Strategy deployer — deploys strategies to Alpaca paper trading and manages execution."""

import importlib.util
import json
import os
import sys
import uuid
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any

import pandas as pd

from astra.alpaca.client import AstraAlpacaClient, AlpacaOrder
from astra.alpaca.exceptions import DeploymentError, ShortSellingBlockedError
from astra.pipeline.events import PipelineEventBus
from astra.pipeline.runner import PipelineResult
from astra.builder.generator import BuildResult
from astra.planner.spec import StrategySpec


@dataclass
class Deployment:
    deployment_id: str = ""
    session_id: str = ""
    spec_id: str = ""
    strategy_file: str = ""
    status: str = "ACTIVE"
    started_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
    stopped_at: datetime | None = None
    cycle_count: int = 0
    total_orders: int = 0
    ledger_path: str = ""

    def __post_init__(self) -> None:
        if not self.deployment_id:
            self.deployment_id = str(uuid.uuid4())


@dataclass
class CycleResult:
    deployment_id: str = ""
    cycle_number: int = 0
    signals: dict[str, int] = field(default_factory=dict)
    actions: list[str] = field(default_factory=list)
    orders: list[AlpacaOrder] = field(default_factory=list)
    timestamp: datetime = field(default_factory=lambda: datetime.now(timezone.utc))


class StrategyDeployer:
    def __init__(
        self,
        client: AstraAlpacaClient,
        event_bus: PipelineEventBus,
    ):
        self._client = client
        self._event_bus = event_bus

    def deploy(
        self,
        build_result: BuildResult,
        spec: StrategySpec,
        pipeline_result: PipelineResult,
    ) -> Deployment:
        if not build_result.success:
            raise DeploymentError("Cannot deploy a failed build")

        deployment = Deployment(
            session_id=spec.spec_id,
            spec_id=spec.spec_id,
            strategy_file=build_result.strategy_file,
        )

        ledger_dir = os.path.join(
            os.path.dirname(build_result.strategy_file), "ledger"
        )
        os.makedirs(ledger_dir, exist_ok=True)
        deployment.ledger_path = os.path.join(
            ledger_dir, f"{deployment.deployment_id}_ledger.jsonl"
        )

        self._event_bus.emit(
            "pipeline.paper_deployed",
            {
                "deployment_id": deployment.deployment_id,
                "strategy_file": build_result.strategy_file,
                "spec_id": spec.spec_id,
            },
        )

        return deployment

    def run_cycle(
        self,
        deployment: Deployment,
        parameters: dict[str, Any] | None = None,
    ) -> CycleResult:
        params = parameters or {}
        cycle_number = deployment.cycle_count + 1

        result = CycleResult(
            deployment_id=deployment.deployment_id,
            cycle_number=cycle_number,
        )

        try:
            strategy_cls = self._import_strategy(deployment.strategy_file)
            strategy = strategy_cls(**params)

            symbols = self._resolve_symbols(deployment)
            positions = {p.symbol: p for p in self._client.get_positions()}
            bars = self._fetch_bars(symbols)

            for symbol in symbols:
                signal = self._compute_signal(strategy, bars, symbol)
                result.signals[symbol] = signal
                has_position = symbol in positions

                if signal == 1 and not has_position:
                    order = self._client.submit_order(
                        symbol=symbol,
                        qty=1.0,
                        side="buy",
                        order_type="market",
                        time_in_force="day",
                    )
                    result.orders.append(order)
                    result.actions.append(f"BUY {symbol}")
                    self._event_bus.emit(
                        "pipeline.cycle_action",
                        {
                            "deployment_id": deployment.deployment_id,
                            "action": "BUY",
                            "symbol": symbol,
                            "order_id": order.id,
                        },
                    )

                elif signal == 0 and has_position:
                    order = self._client.close_position(symbol)
                    result.orders.append(order)
                    result.actions.append(f"CLOSE {symbol}")
                    self._event_bus.emit(
                        "pipeline.cycle_action",
                        {
                            "deployment_id": deployment.deployment_id,
                            "action": "CLOSE",
                            "symbol": symbol,
                            "order_id": order.id,
                        },
                    )

                else:
                    result.actions.append(f"HOLD {symbol}")

            deployment.cycle_count = cycle_number
            deployment.total_orders += len(result.orders)

            self._append_to_ledger(deployment.ledger_path, result)
            self._event_bus.emit(
                "pipeline.cycle_complete",
                {
                    "deployment_id": deployment.deployment_id,
                    "cycle": cycle_number,
                    "actions": result.actions,
                    "orders": len(result.orders),
                },
            )

        except DeploymentError:
            raise
        except ShortSellingBlockedError:
            raise
        except Exception as e:
            raise DeploymentError(f"Cycle {cycle_number} failed: {e}") from e

        return result

    def stop(self, deployment: Deployment) -> None:
        positions = self._client.get_positions()
        for pos in positions:
            try:
                self._client.close_position(pos.symbol)
            except Exception:
                pass

        deployment.status = "STOPPED"
        deployment.stopped_at = datetime.now(timezone.utc)

        self._event_bus.emit(
            "pipeline.deployment_stopped",
            {
                "deployment_id": deployment.deployment_id,
                "positions_closed": len(positions),
            },
        )

    @staticmethod
    def _import_strategy(strategy_file: str) -> type:
        module_name = f"astra_deployed_{uuid.uuid4().hex[:8]}"
        spec = importlib.util.spec_from_file_location(module_name, strategy_file)
        if spec is None or spec.loader is None:
            raise DeploymentError(f"Cannot load strategy file: {strategy_file}")
        mod = importlib.util.module_from_spec(spec)
        sys.modules[module_name] = mod
        spec.loader.exec_module(mod)

        for attr_name in dir(mod):
            attr = getattr(mod, attr_name)
            if isinstance(attr, type) and hasattr(attr, "STRATEGY_TYPE"):
                return attr

        raise DeploymentError(f"No strategy class found in {strategy_file}")

    @staticmethod
    def _resolve_symbols(deployment: Deployment) -> list[str]:
        return ["SPY"]

    def _fetch_bars(self, symbols: list[str]) -> dict[str, pd.DataFrame]:
        bars: dict[str, pd.DataFrame] = {}
        for symbol in symbols:
            df = self._client.get_bars(
                symbol=symbol,
                timeframe="1D",
                start="2020-01-01",
                end=datetime.now(timezone.utc).strftime("%Y-%m-%d"),
            )
            bars[symbol] = df
        return bars

    @staticmethod
    def _compute_signal(
        strategy: Any, bars: dict[str, pd.DataFrame], symbol: str
    ) -> int:
        df = bars.get(symbol)
        if df is None or df.empty:
            return 0
        try:
            signals = strategy.generate_signals(df)
            if len(signals) > 0:
                return int(signals.iloc[-1])
            return 0
        except Exception:
            return 0

    @staticmethod
    def _append_to_ledger(ledger_path: str, result: CycleResult) -> None:
        if not ledger_path:
            return
        entry = {
            "cycle_number": result.cycle_number,
            "timestamp": result.timestamp.isoformat(),
            "signals": result.signals,
            "actions": result.actions,
            "order_count": len(result.orders),
        }
        os.makedirs(os.path.dirname(ledger_path), exist_ok=True)
        with open(ledger_path, "a") as f:
            f.write(json.dumps(entry) + "\n")
