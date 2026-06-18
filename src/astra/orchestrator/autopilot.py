"""Autonomous loop — drives the full self-improving paper-trading lifecycle.

One tick:
    1. TRADE     deployer.run_cycle(deployment, current_params)   -> forward trade
    2. MEASURE   monitor.snapshot + compute_degradation           -> live metrics
    3. GRADUATE  gates.check + tracker.record_check               -> are we done?
    4. OPTIMIZE  if degraded, optimizer.run_optimization_loop      -> tweak params
                 and apply the improved parameters to the live deployment
    5. wait `interval_seconds`, repeat

Graduation requires `graduation_confirmations` *consecutive* passing gate checks
(default 3) so a single lucky day cannot graduate a strategy — this encodes the
"consistently profitable" requirement. Graduation issues a certificate and
notifies; it never auto-promotes to live trading. The deployment is paper-only.
"""

from __future__ import annotations

import logging
import os
import threading
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any

from astra.alpaca.deployer import CycleResult, Deployment, StrategyDeployer
from astra.alpaca.monitor import DegradationReport, PerformanceMonitor, PerformanceSnapshot
from astra.builder.generator import BuildResult
from astra.graduation.certificate import GraduationCertificate
from astra.graduation.gates import GateCheckResult, GraduationGates
from astra.graduation.tracker import GraduationTracker
from astra.notifications.base import NotificationLevel, Notifier
from astra.notifications.factory import create_notifiers
from astra.optimizer.engine import OptimizationEngine
from astra.pipeline.events import PipelineEventBus
from astra.pipeline.runner import PipelineResult
from astra.pipeline.state import InvalidStatusTransition, PipelineState
from astra.planner.spec import StrategySpec

logger = logging.getLogger(__name__)


@dataclass
class AutopilotConfig:
    interval_seconds: int = 3600
    max_ticks: int = 1000
    # Consecutive GRADUATED gate checks required before issuing a certificate.
    graduation_confirmations: int = 3
    optimize_on_degradation: bool = True

    @classmethod
    def from_env(cls) -> "AutopilotConfig":
        return cls(
            interval_seconds=int(os.environ.get("ASTRA_AUTOPILOT_INTERVAL_SECONDS", 3600)),
            max_ticks=int(os.environ.get("ASTRA_AUTOPILOT_MAX_TICKS", 1000)),
            graduation_confirmations=int(os.environ.get("ASTRA_GRADUATION_CONFIRMATIONS", 3)),
            optimize_on_degradation=os.environ.get("ASTRA_AUTOPILOT_OPTIMIZE", "1") == "1",
        )


@dataclass
class TickResult:
    tick: int
    action: str  # TRADE | OPTIMIZED | GRADUATED | SUSPENDED | ERROR
    snapshot: PerformanceSnapshot | None = None
    degradation: DegradationReport | None = None
    gate_result: GateCheckResult | None = None
    cycle_result: CycleResult | None = None
    consecutive_graduations: int = 0
    optimized: bool = False
    parameters: dict[str, Any] = field(default_factory=dict)
    message: str = ""


@dataclass
class LoopResult:
    session_id: str
    status: str  # GRADUATED | EXHAUSTED | STOPPED | SUSPENDED | ERROR
    ticks: int = 0
    certificate: GraduationCertificate | None = None
    last_snapshot: PerformanceSnapshot | None = None
    message: str = ""


class AutonomousLoop:
    """Self-improving paper-trading loop. All collaborators are injected so the
    loop is fully testable without a live broker or LLM."""

    def __init__(
        self,
        *,
        deployer: StrategyDeployer,
        monitor: PerformanceMonitor,
        gates: GraduationGates,
        tracker: GraduationTracker,
        state: PipelineState,
        build_result: BuildResult,
        spec: StrategySpec,
        event_bus: PipelineEventBus,
        optimization_engine: OptimizationEngine | None = None,
        notifiers: list[Notifier] | None = None,
        config: AutopilotConfig | None = None,
    ):
        self._deployer = deployer
        self._monitor = monitor
        self._optimizer = optimization_engine
        self._gates = gates
        self._tracker = tracker
        self._state = state
        self._build_result = build_result
        self._spec = spec
        self._event_bus = event_bus
        self._notifiers = notifiers if notifiers is not None else create_notifiers()
        self._config = config or AutopilotConfig()

        self._current_params: dict[str, Any] = dict(build_result.initial_parameters)
        self._bounds: dict[str, Any] = dict(build_result.parameter_bounds)
        self._deployment: Deployment | None = None
        self._tick_no = 0
        self._consecutive_graduations = 0
        self._optimization_cycles = 0
        self._last_tick: TickResult | None = None

    # ------------------------------------------------------------------
    @property
    def deployment(self) -> Deployment | None:
        return self._deployment

    @property
    def current_parameters(self) -> dict[str, Any]:
        return dict(self._current_params)

    @property
    def progress(self) -> dict[str, Any]:
        """Live snapshot of loop progress for status polling / UI."""
        t = self._last_tick
        return {
            "tick": self._tick_no,
            "consecutive_graduations": self._consecutive_graduations,
            "graduation_confirmations": self._config.graduation_confirmations,
            "graduated": self._tracker.is_graduated(),
            "optimization_cycles": self._optimization_cycles,
            "last_action": t.action if t else None,
            "gates_passed": (t.gate_result.gates_passed if t and t.gate_result else None),
            "gates_total": (t.gate_result.gates_total if t and t.gate_result else 6),
            "sharpe": (t.snapshot.sharpe_ratio if t and t.snapshot else None),
            "total_return": (t.snapshot.total_return if t and t.snapshot else None),
            "degradation": (t.degradation.category if t and t.degradation else None),
            "message": t.message if t else "",
        }

    def _record(self, result: TickResult) -> TickResult:
        self._last_tick = result
        return result

    def start_deployment(self) -> Deployment:
        pipeline_result = self._state.latest_result() or PipelineResult(
            spec_id=self._spec.spec_id, status="DEPLOYED_PAPER"
        )
        self._deployment = self._deployer.deploy(
            build_result=self._build_result,
            spec=self._spec,
            pipeline_result=pipeline_result,
        )
        self._state.paper_deployment_id = self._deployment.deployment_id
        self._safe_transition("PAPER_TRADING")
        return self._deployment

    # ------------------------------------------------------------------
    def tick(self) -> TickResult:
        if self._deployment is None:
            self.start_deployment()
        assert self._deployment is not None
        self._tick_no += 1

        # 1. TRADE
        try:
            cycle = self._deployer.run_cycle(self._deployment, self._current_params)
        except Exception as e:
            msg = f"Trade cycle failed: {e}"
            logger.exception(msg)
            self._event_bus.emit("autopilot.error", {"tick": self._tick_no, "error": str(e)})
            return self._record(TickResult(tick=self._tick_no, action="ERROR", message=msg,
                                           parameters=dict(self._current_params)))

        if self._deployment.status == "SUSPENDED":
            msg = f"Deployment suspended: {self._deployment.suspended_reason}"
            self._notify("Autopilot suspended", msg, NotificationLevel.ERROR)
            self._event_bus.emit("autopilot.suspended",
                                 {"tick": self._tick_no, "reason": self._deployment.suspended_reason})
            return self._record(TickResult(tick=self._tick_no, action="SUSPENDED", cycle_result=cycle,
                                           message=msg, parameters=dict(self._current_params)))

        # 2. MEASURE
        snapshot = self._monitor.snapshot(self._deployment)
        degradation = self._monitor.compute_degradation(snapshot, self._latest_backtest_metrics())
        snapshot.degradation_report = degradation

        # 3. GRADUATION CHECK
        pipeline_result = self._state.latest_result() or PipelineResult(spec_id=self._spec.spec_id)
        gate_result = self._gates.check(snapshot, pipeline_result)
        try:
            self._tracker.record_check(self._tick_no, gate_result)
        except ValueError:
            # Cycle already recorded (e.g. tracker shared across a restart) —
            # the gate result still drives graduation below; skip the dup record.
            pass

        if gate_result.overall_status == "GRADUATED":
            self._consecutive_graduations += 1
        else:
            self._consecutive_graduations = 0

        self._event_bus.emit("autopilot.tick", {
            "tick": self._tick_no,
            "gates_passed": gate_result.gates_passed,
            "consecutive_graduations": self._consecutive_graduations,
            "degradation": degradation.category,
            "sharpe": snapshot.sharpe_ratio,
            "total_return": snapshot.total_return,
        })

        # 4. GRADUATE? (require consistency across consecutive checks)
        if self._consecutive_graduations >= self._config.graduation_confirmations:
            return self._graduate(snapshot, pipeline_result, gate_result, cycle, degradation)

        # 5. OPTIMIZE on severe degradation
        optimized = False
        action = "TRADE"
        message = (
            f"{gate_result.gates_passed}/6 gates passed, "
            f"{self._consecutive_graduations}/{self._config.graduation_confirmations} consecutive; "
            f"degradation={degradation.category}"
        )
        if self._config.optimize_on_degradation and degradation.triggers_optimizer and self._optimizer is not None:
            optimized = self._optimize()
            action = "OPTIMIZED" if optimized else "TRADE"
            if optimized:
                message += f" | re-optimized -> params {self._current_params}"

        return self._record(TickResult(
            tick=self._tick_no,
            action=action,
            snapshot=snapshot,
            degradation=degradation,
            gate_result=gate_result,
            cycle_result=cycle,
            consecutive_graduations=self._consecutive_graduations,
            optimized=optimized,
            parameters=dict(self._current_params),
            message=message,
        ))

    # ------------------------------------------------------------------
    def run_forever(self, stop_event: threading.Event | None = None) -> LoopResult:
        if self._deployment is None:
            self.start_deployment()

        last_snapshot: PerformanceSnapshot | None = None
        status = "EXHAUSTED"
        message = f"Completed {self._config.max_ticks} ticks without graduation."

        logger.info("Autopilot starting (interval=%ds, max_ticks=%d, confirmations=%d)",
                    self._config.interval_seconds, self._config.max_ticks,
                    self._config.graduation_confirmations)

        while self._tick_no < self._config.max_ticks:
            if stop_event is not None and stop_event.is_set():
                status, message = "STOPPED", "Autopilot stopped by request."
                break

            result = self.tick()
            last_snapshot = result.snapshot or last_snapshot

            if result.action == "GRADUATED":
                status, message = "GRADUATED", result.message
                break
            if result.action == "SUSPENDED":
                status, message = "SUSPENDED", result.message
                break
            if result.action == "ERROR":
                status, message = "ERROR", result.message
                break

            if stop_event is not None:
                if stop_event.wait(self._config.interval_seconds):
                    status, message = "STOPPED", "Autopilot stopped by request."
                    break
            elif self._config.interval_seconds > 0:
                threading.Event().wait(self._config.interval_seconds)

        self._event_bus.emit("autopilot.stopped", {"status": status, "ticks": self._tick_no})
        return LoopResult(
            session_id=self._state.session_id,
            status=status,
            ticks=self._tick_no,
            certificate=self._tracker.get_certificate(),
            last_snapshot=last_snapshot,
            message=message,
        )

    # ------------------------------------------------------------------
    def _graduate(self, snapshot, pipeline_result, gate_result, cycle, degradation) -> TickResult:
        self._safe_transition("GRADUATED")
        certificate = None
        try:
            certificate = self._tracker.issue_certificate(
                snapshot=snapshot,
                pipeline_result=pipeline_result,
                optimization_cycles=self._optimization_cycles,
                gate_result=gate_result,
            )
        except Exception as e:
            logger.warning("Certificate issuance failed: %s", e)

        self._state.graduation_result = {
            "status": "GRADUATED",
            "gates_passed": gate_result.gates_passed,
            "issued_at": datetime.now(timezone.utc).isoformat(),
        }
        msg = (
            f"Strategy GRADUATED after {self._tick_no} ticks "
            f"({self._consecutive_graduations} consecutive passing checks). "
            "Ready to export and run live (manual step — autopilot does not trade live)."
        )
        self._notify("Strategy graduated", msg, NotificationLevel.SUCCESS)
        self._event_bus.emit("autopilot.graduated", {
            "tick": self._tick_no,
            "certificate_id": getattr(certificate, "certificate_id", None),
        })
        return self._record(TickResult(
            tick=self._tick_no,
            action="GRADUATED",
            snapshot=snapshot,
            degradation=degradation,
            gate_result=gate_result,
            cycle_result=cycle,
            consecutive_graduations=self._consecutive_graduations,
            parameters=dict(self._current_params),
            message=msg,
        ))

    def _optimize(self) -> bool:
        try:
            opt_result = self._optimizer.run_optimization_loop(state=self._state, monitor=self._monitor)
        except Exception as e:
            logger.warning("Optimization loop failed: %s", e)
            return False

        self._optimization_cycles += opt_result.total_cycles
        proposal = opt_result.final_proposal
        if opt_result.status in ("ABANDONED", "ERROR") or proposal is None:
            return False

        changes = getattr(proposal, "parameter_changes", None) or {}
        if not changes:
            return False
        self._apply_parameters(changes)
        self._event_bus.emit("autopilot.optimized", {
            "tick": self._tick_no,
            "status": opt_result.status,
            "cycles": opt_result.total_cycles,
            "parameters": dict(self._current_params),
        })
        return True

    def _apply_parameters(self, changes: dict[str, Any]) -> None:
        for name, value in changes.items():
            if name not in self._current_params:
                continue
            bounds = self._bounds.get(name)
            if bounds and len(bounds) == 2:
                low, high = bounds
                try:
                    value = max(low, min(high, value))
                except TypeError:
                    pass
            self._current_params[name] = value

    def _latest_backtest_metrics(self) -> dict[str, Any]:
        latest = self._state.latest_result()
        if latest is not None and latest.backtest_metrics:
            return dict(latest.backtest_metrics)
        return {}

    def _safe_transition(self, status: str) -> None:
        try:
            self._state.transition_to(status)
        except InvalidStatusTransition:
            pass

    def _notify(self, subject: str, message: str, level: NotificationLevel) -> None:
        for notifier in self._notifiers:
            try:
                notifier.send(subject=subject, message=message, level=level)
            except Exception:
                pass


class ThreadedAutopilot:
    """Runs an AutonomousLoop in a background daemon thread. Used by the UI/API
    to start, stop, and poll the loop without blocking the request handler."""

    def __init__(self, loop: AutonomousLoop):
        self._loop = loop
        self._thread: threading.Thread | None = None
        self._stop_event = threading.Event()
        self._result: LoopResult | None = None

    def start(self) -> None:
        if self._thread is not None and self._thread.is_alive():
            return
        self._stop_event.clear()

        def _run() -> None:
            self._result = self._loop.run_forever(stop_event=self._stop_event)

        self._thread = threading.Thread(target=_run, daemon=True, name="astra-autopilot")
        self._thread.start()

    def stop(self, timeout: float | None = 5.0) -> LoopResult | None:
        self._stop_event.set()
        if self._thread is not None:
            self._thread.join(timeout=timeout)
        return self._result

    def is_running(self) -> bool:
        return self._thread is not None and self._thread.is_alive()

    def status(self) -> dict[str, Any]:
        deployment = self._loop.deployment
        return {
            "running": self.is_running(),
            "deployment_id": deployment.deployment_id if deployment else None,
            "deployment_status": deployment.status if deployment else None,
            "parameters": self._loop.current_parameters,
            "progress": self._loop.progress,
            "result": None if self._result is None else {
                "status": self._result.status,
                "ticks": self._result.ticks,
                "message": self._result.message,
            },
        }
