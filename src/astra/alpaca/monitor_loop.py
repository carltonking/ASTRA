"""Performance monitoring loop — periodically checks paper performance and triggers re-optimization."""

import time
import logging
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any

from astra.alpaca.monitor import PerformanceMonitor, PerformanceSnapshot, DegradationReport
from astra.alpaca.deployer import Deployment
from astra.notifications.base import Notifier, NotificationLevel
from astra.notifications.factory import create_notifiers
from astra.optimizer.engine import OptimizationEngine, OptimizationResult
from astra.pipeline.state import PipelineState

logger = logging.getLogger(__name__)


@dataclass
class MonitoringCheckResult:
    timestamp: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
    action: str = "NONE"
    degradation: DegradationReport | None = None
    optimization_result: OptimizationResult | None = None
    snapshot: PerformanceSnapshot | None = None
    message: str = ""


class PerformanceMonitoringLoop:
    def __init__(
        self,
        monitor: PerformanceMonitor,
        optimization_engine: OptimizationEngine,
        state: PipelineState,
        interval_minutes: int = 60,
        notifiers: list[Notifier] | None = None,
    ):
        self._monitor = monitor
        self._optimization_engine = optimization_engine
        self._state = state
        self._interval = interval_minutes * 60
        self._last_check: MonitoringCheckResult | None = None
        self._notifiers = notifiers if notifiers is not None else create_notifiers()

    def check_and_optimize(self, deployment: Deployment) -> MonitoringCheckResult:
        snapshot = self._monitor.snapshot(deployment)
        self._last_check = None

        backtest_metrics: dict[str, Any] = {}
        if self._state.pipeline_results:
            last = self._state.pipeline_results[-1]
            if last.backtest_metrics:
                backtest_metrics = last.backtest_metrics

        degradation = self._monitor.compute_degradation(snapshot, backtest_metrics)
        msg = f"Degradation: {degradation.category} (score={degradation.overall_degradation_score:.2f}, triggers={degradation.triggers_optimizer})"
        logger.info("Monitoring check: %s", msg)

        if not degradation.triggers_optimizer:
            result = MonitoringCheckResult(
                action="MONITOR_ONLY",
                degradation=degradation,
                snapshot=snapshot,
                message=msg,
            )
            self._last_check = result
            return result

        logger.warning("Degradation threshold exceeded — starting optimization loop")
        opt_result = self._optimization_engine.run_optimization_loop(
            state=self._state,
            monitor=self._monitor,
        )
        msg += f" | Optimization: {opt_result.status} ({opt_result.total_cycles} cycles)"
        logger.info("Optimization result: %s", opt_result.status)

        result = MonitoringCheckResult(
            action="RE_OPTIMIZED" if opt_result.status not in ("ABANDONED", "ERROR") else "FAILED",
            degradation=degradation,
            optimization_result=opt_result,
            snapshot=snapshot,
            message=msg,
        )
        self._last_check = result
        self._notify(result)
        return result

    def _notify(self, result: MonitoringCheckResult) -> None:
        if not self._notifiers:
            return
        level = NotificationLevel.SUCCESS if result.action == "RE_OPTIMIZED" else NotificationLevel.INFO
        if result.action == "FAILED":
            level = NotificationLevel.ERROR
        for notifier in self._notifiers:
            notifier.send(
                subject=f"ASTRA Monitoring: {result.action}",
                message=result.message,
                level=level,
            )

    def run_continuous(
        self,
        deployment: Deployment,
        stop_event=None,
    ) -> None:
        logger.info(
            "Starting continuous monitoring loop (interval=%ds)",
            self._interval,
        )
        while True:
            if stop_event is not None and stop_event.is_set():
                logger.info("Monitoring loop stopped via event")
                break

            self.check_and_optimize(deployment)

            if stop_event is not None:
                stop_event.wait(self._interval)
            else:
                time.sleep(self._interval)

    @property
    def last_check(self) -> MonitoringCheckResult | None:
        return self._last_check
