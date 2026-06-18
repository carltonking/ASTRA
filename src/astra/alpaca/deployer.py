"""Strategy deployer — deploys strategies to paper trading and manages execution."""

import importlib.util
import inspect
import json
import os
import sys
import uuid
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any

import pandas as pd

from astra.alpaca.exceptions import DeploymentError, ShortSellingBlockedError
from astra.broker.base import Broker, Order
from astra.deployment import (
    BrokerReconnect,
    HeartbeatMonitor,
    OrderManager,
    PortfolioManager,
    RiskEngine,
    RiskLimits,
    StaleDataDetector,
    TradeAuditLog,
)
from astra.pipeline.events import PipelineEventBus
from astra.pipeline.runner import PipelineResult
from astra.builder.generator import BuildResult
from astra.planner.spec import StrategySpec
from astra.regime import RegimeEngine


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
    symbols: list[str] = field(default_factory=list)
    paper_only: bool = True
    max_drawdown: float = 0.20
    max_gross_exposure: float = 1.0
    max_net_exposure: float = 1.0
    max_position_concentration: float = 0.35
    max_correlation: float = 0.85
    intraday_var_limit: float = 0.03
    enforce_stale_data: bool = False
    suspended_reason: str | None = None

    def __post_init__(self) -> None:
        if not self.deployment_id:
            self.deployment_id = str(uuid.uuid4())


@dataclass
class CycleResult:
    deployment_id: str = ""
    cycle_number: int = 0
    signals: dict[str, int] = field(default_factory=dict)
    actions: list[str] = field(default_factory=list)
    orders: list[Order] = field(default_factory=list)
    timestamp: datetime = field(default_factory=lambda: datetime.now(timezone.utc))


class StrategyDeployer:
    def __init__(
        self,
        broker: Broker,
        event_bus: PipelineEventBus,
    ):
        self._broker = broker
        self._event_bus = event_bus
        self._audit_log = TradeAuditLog()
        self._portfolio = PortfolioManager(broker)
        self._heartbeat = HeartbeatMonitor(broker)
        self._reconnect = BrokerReconnect()
        self._stale_detector = StaleDataDetector()
        self._regime_engine = RegimeEngine()
        self._risk_engine = RiskEngine()
        self._order_manager = OrderManager(broker, self._risk_engine, self._audit_log)

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
            symbols=list(spec.symbols),
            max_drawdown=spec.max_drawdown or 0.20,
            max_gross_exposure=float(spec.leverage_constraints.get("max_gross_leverage", 1.0)),
            max_net_exposure=float(spec.leverage_constraints.get("max_gross_leverage", 1.0)),
            max_position_concentration=min(1.0, max(spec.position_size * 3, spec.position_size)),
            paper_only=True,
        )

        ledger_dir = os.path.join(
            os.path.dirname(build_result.strategy_file), "ledger"
        )
        os.makedirs(ledger_dir, exist_ok=True)
        deployment.ledger_path = os.path.join(
            ledger_dir, f"{deployment.deployment_id}_ledger.jsonl"
        )
        self._audit_log.bind(deployment.ledger_path)
        self._reset_risk_engine(deployment)
        self._audit_log.record(
            "deployment_created",
            deployment.deployment_id,
            {
                "spec_id": spec.spec_id,
                "symbols": deployment.symbols,
                "paper_only": deployment.paper_only,
                "risk_limits": self._risk_payload(deployment),
            },
        )

        self._event_bus.emit(
            "pipeline.paper_deployed",
            {
                "deployment_id": deployment.deployment_id,
                "strategy_file": build_result.strategy_file,
                "spec_id": spec.spec_id,
                "symbols": deployment.symbols,
                "paper_only": deployment.paper_only,
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
        self._audit_log.bind(deployment.ledger_path)
        self._reset_risk_engine(deployment)

        result = CycleResult(
            deployment_id=deployment.deployment_id,
            cycle_number=cycle_number,
        )

        try:
            if deployment.status == "SUSPENDED":
                result.actions.append("SUSPENDED")
                self._append_to_ledger(deployment.ledger_path, result)
                return result

            heartbeat = self._heartbeat.check()
            self._event_bus.emit(
                "deployment.heartbeat",
                {
                    "deployment_id": deployment.deployment_id,
                    "ok": heartbeat.ok,
                    "broker": heartbeat.broker_name,
                    "latency_ms": heartbeat.latency_ms,
                    "error": heartbeat.error,
                },
            )
            if not heartbeat.ok:
                self._suspend(deployment, f"BROKER_HEARTBEAT_FAILED: {heartbeat.error}")
                result.actions.append("SUSPEND BROKER_HEARTBEAT_FAILED")
                self._append_to_ledger(deployment.ledger_path, result)
                return result

            strategy_cls = self._import_strategy(deployment.strategy_file)
            strategy = strategy_cls(**params)

            symbols = self._resolve_symbols(deployment)
            positions = {p.symbol: p for p in self._reconnect.call(self._broker.get_positions)}
            bars = self._fetch_bars(symbols)
            stale = self._stale_detector.check(bars)
            self._event_bus.emit(
                "deployment.data_checked",
                {
                    "deployment_id": deployment.deployment_id,
                    "ok": stale.ok,
                    "stale_symbols": stale.stale_symbols,
                    "latest_timestamps": stale.latest_timestamps,
                },
            )
            if deployment.enforce_stale_data and not stale.ok:
                self._suspend(deployment, f"STALE_DATA: {','.join(stale.stale_symbols)}")
                result.actions.append("SUSPEND STALE_DATA")
                self._append_to_ledger(deployment.ledger_path, result)
                return result

            portfolio = self._portfolio.snapshot()
            risk = self._risk_engine.evaluate(portfolio)
            self._event_bus.emit(
                "deployment.risk_checked",
                {
                    "deployment_id": deployment.deployment_id,
                    "allowed": risk.allowed,
                    "action": risk.action,
                    "reasons": risk.reasons,
                    "metrics": risk.metrics,
                },
            )
            self._audit_log.record(
                "risk_checked",
                deployment.deployment_id,
                {"allowed": risk.allowed, "reasons": risk.reasons, "metrics": risk.metrics},
            )
            if not risk.allowed:
                self._suspend(deployment, ",".join(risk.reasons))
                result.actions.append(f"SUSPEND {','.join(risk.reasons)}")
                self._append_to_ledger(deployment.ledger_path, result)
                return result

            for symbol in symbols:
                regime_action = self._regime_action(strategy, bars.get(symbol))
                if regime_action == "SUSPEND":
                    self._suspend(deployment, f"REGIME_PROHIBITED:{symbol}")
                    result.actions.append(f"SUSPEND REGIME {symbol}")
                    self._append_to_ledger(deployment.ledger_path, result)
                    return result
                if regime_action == "NO_NEW_ENTRIES" and symbol not in positions:
                    result.actions.append(f"NO_NEW_ENTRIES {symbol}")
                    continue

                signal = self._compute_signal(strategy, bars, symbol)
                result.signals[symbol] = signal
                has_position = symbol in positions

                if signal == 1 and not has_position:
                    order, order_risk = self._order_manager.submit_buy(
                        deployment_id=deployment.deployment_id,
                        symbol=symbol,
                        qty=1.0,
                        open_order_count=len(result.orders),
                    )
                    if order is None:
                        result.actions.append(f"BLOCK BUY {symbol}")
                        self._event_bus.emit(
                            "deployment.order_blocked",
                            {
                                "deployment_id": deployment.deployment_id,
                                "symbol": symbol,
                                "reasons": order_risk.reasons,
                            },
                        )
                        continue
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
                    order = self._order_manager.close_position(
                        deployment_id=deployment.deployment_id,
                        symbol=symbol,
                    )
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
            self._audit_log.record(
                "cycle_complete",
                deployment.deployment_id,
                {
                    "cycle": cycle_number,
                    "signals": result.signals,
                    "actions": result.actions,
                    "orders": result.orders,
                },
            )
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
        positions = self._broker.get_positions()
        for pos in positions:
            try:
                self._broker.close_position(pos.symbol)
            except Exception:
                pass

        deployment.status = "STOPPED"
        deployment.stopped_at = datetime.now(timezone.utc)
        self._audit_log.bind(deployment.ledger_path)
        self._audit_log.record(
            "deployment_stopped",
            deployment.deployment_id,
            {"positions_closed": len(positions)},
        )

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

        # Generated files import the abstract BaseStrategy (which also carries a
        # STRATEGY_TYPE attr) alongside the concrete subclass. Skip abstract
        # bases and prefer a class defined in this module, otherwise the loader
        # returns BaseStrategy and instantiation fails on abstract methods.
        candidates = [
            getattr(mod, attr_name)
            for attr_name in dir(mod)
            if isinstance(getattr(mod, attr_name), type)
            and hasattr(getattr(mod, attr_name), "STRATEGY_TYPE")
            and not inspect.isabstract(getattr(mod, attr_name))
        ]
        for cls in candidates:
            if cls.__module__ == module_name:
                return cls
        if candidates:
            return candidates[0]

        raise DeploymentError(f"No strategy class found in {strategy_file}")

    @staticmethod
    def _resolve_symbols(deployment: Deployment) -> list[str]:
        return list(deployment.symbols) if deployment.symbols else ["SPY"]

    def _fetch_bars(self, symbols: list[str]) -> dict[str, pd.DataFrame]:
        bars: dict[str, pd.DataFrame] = {}
        for symbol in symbols:
            df = self._reconnect.call(
                self._broker.get_bars,
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

    def _regime_action(self, strategy: Any, df: pd.DataFrame | None) -> str:
        if df is None or df.empty:
            return "ACTIVE"
        snapshot = self._regime_engine.classify(df)
        allowed = getattr(strategy, "ALLOWED_REGIMES", {}) or {}
        prohibited = getattr(strategy, "PROHIBITED_REGIMES", {}) or {}
        min_conf = float(getattr(strategy, "MIN_REGIME_CONFIDENCE", 0.0) or 0.0)
        action = self._regime_engine.deployment_action(
            snapshot=snapshot,
            allowed_regimes=allowed,
            prohibited_regimes=prohibited,
            min_confidence=min_conf,
        )
        self._event_bus.emit(
            "deployment.regime_checked",
            {
                "action": action,
                "trend": snapshot.trend,
                "volatility": snapshot.volatility,
                "liquidity": snapshot.liquidity,
                "risk_mode": snapshot.risk_mode,
                "confidence": snapshot.aggregate_confidence,
            },
        )
        return action

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

    def _reset_risk_engine(self, deployment: Deployment) -> None:
        self._risk_engine = RiskEngine(
            RiskLimits(
                max_drawdown=deployment.max_drawdown,
                max_gross_exposure=deployment.max_gross_exposure,
                max_net_exposure=deployment.max_net_exposure,
                max_position_concentration=deployment.max_position_concentration,
                max_correlation=deployment.max_correlation,
                intraday_var_limit=deployment.intraday_var_limit,
                allow_short=False,
                paper_trading_only=True,
            )
        )
        self._order_manager = OrderManager(self._broker, self._risk_engine, self._audit_log)

    @staticmethod
    def _risk_payload(deployment: Deployment) -> dict[str, Any]:
        return {
            "max_drawdown": deployment.max_drawdown,
            "max_gross_exposure": deployment.max_gross_exposure,
            "max_net_exposure": deployment.max_net_exposure,
            "max_position_concentration": deployment.max_position_concentration,
            "max_correlation": deployment.max_correlation,
            "intraday_var_limit": deployment.intraday_var_limit,
            "paper_only": deployment.paper_only,
        }

    def _suspend(self, deployment: Deployment, reason: str) -> None:
        deployment.status = "SUSPENDED"
        deployment.suspended_reason = reason
        self._audit_log.record(
            "deployment_suspended",
            deployment.deployment_id,
            {"reason": reason},
        )
        self._event_bus.emit(
            "deployment.suspended",
            {
                "deployment_id": deployment.deployment_id,
                "reason": reason,
            },
        )
