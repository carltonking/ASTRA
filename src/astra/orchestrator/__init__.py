"""ASTRA autonomous orchestrator — the continuous forward-trade + self-tweak loop.

This is the missing top-level wiring that ties together the deployer (paper
trading), the performance monitor, the optimizer, and the graduation gates into
a single self-improving loop:

    trade a cycle -> measure -> check graduation -> optimize if degraded -> repeat

It paper-trades only. Graduation never auto-promotes to live; it issues a
certificate and notifies that the strategy is ready to be exported and run live
by a human.
"""

from astra.orchestrator.autopilot import (
    AutonomousLoop,
    AutopilotConfig,
    LoopResult,
    TickResult,
    ThreadedAutopilot,
)

__all__ = [
    "AutonomousLoop",
    "AutopilotConfig",
    "LoopResult",
    "TickResult",
    "ThreadedAutopilot",
]
