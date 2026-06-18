"""Live paper-trading loop — periodically runs deployer cycles against the current market.

This is what turns a deployed strategy into *live* paper trading: it repeatedly calls
``StrategyDeployer.run_cycle`` on an interval, gated on market hours, so the strategy
actually places orders in the current market and the equity curve moves in real time.

Distinct from ``PerformanceMonitoringLoop`` (monitor_loop.py), which only evaluates
degradation vs. the backtest and triggers re-optimization — it does not place trades.
"""

import logging
import threading
from typing import Any

from astra.alpaca.deployer import StrategyDeployer, Deployment, DeploymentError

logger = logging.getLogger(__name__)


class PaperTradingLoop:
    """Drives a deployed strategy by running trade cycles on a fixed interval.

    Each tick calls ``deployer.run_cycle(deployment)`` which fetches fresh bars,
    computes signals, and submits/closes paper orders via the broker. The loop is
    market-hours aware: when the market is closed it idles instead of spinning.
    """

    def __init__(
        self,
        deployer: StrategyDeployer,
        deployment: Deployment,
        interval_seconds: int = 60,
        parameters: dict[str, Any] | None = None,
    ):
        self._deployer = deployer
        self._deployment = deployment
        self._interval = max(5, int(interval_seconds))
        self._parameters = parameters or {}
        self._stop = threading.Event()
        self._thread: threading.Thread | None = None

    def _market_open(self) -> bool:
        """Best-effort market-hours check via the Alpaca clock; defaults to True.

        If the clock can't be read (stub broker, transient error), we proceed —
        Alpaca paper accepts orders out of hours and queues them to the next open,
        so failing open is safe and keeps the loop responsive once the bell rings.
        """
        broker = getattr(self._deployer, "_broker", None)
        client = getattr(broker, "_client", None)
        trading_client = getattr(client, "_trading_client", None)
        if trading_client is None:
            return True
        try:
            return bool(trading_client.get_clock().is_open)
        except Exception as e:  # pragma: no cover - network/clock failure path
            logger.warning("Market clock check failed, assuming open: %s", e)
            return True

    def _tick(self) -> None:
        if not self._market_open():
            logger.debug("Market closed — skipping cycle for %s", self._deployment.deployment_id)
            return
        try:
            self._deployer.run_cycle(self._deployment, self._parameters)
        except DeploymentError as e:
            # run_cycle already suspends/ledgers on risk failures; log and keep looping
            logger.warning("Trade cycle failed for %s: %s", self._deployment.deployment_id, e)
        except Exception as e:  # pragma: no cover - defensive, loop must survive
            logger.exception("Unexpected error in trade cycle: %s", e)

    def run_continuous(self) -> None:
        logger.info(
            "Starting paper-trading loop for %s (interval=%ds)",
            self._deployment.deployment_id,
            self._interval,
        )
        while not self._stop.is_set():
            self._tick()
            self._stop.wait(self._interval)
        logger.info("Paper-trading loop stopped for %s", self._deployment.deployment_id)

    def start(self) -> "PaperTradingLoop":
        """Launch the loop on a daemon thread and return self."""
        if self._thread is not None:
            return self
        self._thread = threading.Thread(
            target=self.run_continuous,
            name=f"paper-trade-{self._deployment.deployment_id[:8]}",
            daemon=True,
        )
        self._thread.start()
        return self

    def stop(self) -> None:
        self._stop.set()
        if self._thread is not None:
            self._thread.join(timeout=self._interval + 5)
