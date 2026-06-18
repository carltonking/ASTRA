"""Tests for the autonomous orchestrator loop (AutonomousLoop)."""

from astra.alpaca.deployer import CycleResult, Deployment
from astra.alpaca.monitor import DegradationReport, PerformanceSnapshot
from astra.builder.generator import BuildResult
from astra.graduation.gates import GraduationGates
from astra.graduation.tracker import GraduationTracker
from astra.optimizer.engine import OptimizationResult
from astra.optimizer.proposer import ParameterProposal
from astra.orchestrator import AutonomousLoop, AutopilotConfig
from astra.pipeline.events import PipelineEventBus
from astra.pipeline.runner import PipelineResult
from astra.pipeline.state import PipelineState
from astra.planner.spec import StrategySpec


# --------------------------------------------------------------------------
# Fakes
# --------------------------------------------------------------------------
class FakeDeployer:
    def __init__(self, suspend_at: int | None = None):
        self.cycles = 0
        self.suspend_at = suspend_at
        self.params_seen: list[dict] = []

    def deploy(self, build_result, spec, pipeline_result) -> Deployment:
        return Deployment(deployment_id="dep-test", spec_id=spec.spec_id,
                          strategy_file=build_result.strategy_file, status="ACTIVE")

    def run_cycle(self, deployment: Deployment, parameters=None) -> CycleResult:
        self.cycles += 1
        self.params_seen.append(dict(parameters or {}))
        if self.suspend_at is not None and self.cycles >= self.suspend_at:
            deployment.status = "SUSPENDED"
            deployment.suspended_reason = "TEST_SUSPEND"
        deployment.cycle_count = self.cycles
        return CycleResult(deployment_id=deployment.deployment_id, cycle_number=self.cycles)


class FakeMonitor:
    """Returns a scripted sequence of (snapshot, degradation) per tick."""

    def __init__(self, snapshots: list[PerformanceSnapshot], degradations: list[DegradationReport]):
        self._snapshots = snapshots
        self._degradations = degradations
        self._i = 0

    def snapshot(self, deployment) -> PerformanceSnapshot:
        snap = self._snapshots[min(self._i, len(self._snapshots) - 1)]
        return snap

    def compute_degradation(self, snapshot, backtest_metrics) -> DegradationReport:
        deg = self._degradations[min(self._i, len(self._degradations) - 1)]
        self._i += 1
        return deg


class FakeOptimizer:
    def __init__(self, changes: dict, status: str = "EXHAUSTED"):
        self._changes = changes
        self._status = status
        self.calls = 0

    def run_optimization_loop(self, state, monitor) -> OptimizationResult:
        self.calls += 1
        return OptimizationResult(
            session_id=state.session_id,
            status=self._status,
            total_cycles=1,
            final_proposal=ParameterProposal(action="ADJUST_PARAMETERS", parameter_changes=self._changes),
        )


# --------------------------------------------------------------------------
# Helpers
# --------------------------------------------------------------------------
def _passing_snapshot() -> PerformanceSnapshot:
    return PerformanceSnapshot(
        deployment_id="dep-test",
        annualized_return=0.12,
        sharpe_ratio=1.8,
        max_drawdown=0.05,
        total_trades=25,
        days_deployed=10,
    )


def _failing_snapshot() -> PerformanceSnapshot:
    return PerformanceSnapshot(
        deployment_id="dep-test",
        annualized_return=0.0,  # fails annual_return gate
        sharpe_ratio=0.1,
        max_drawdown=0.05,
        total_trades=25,
        days_deployed=10,
    )


def _clean_degradation() -> DegradationReport:
    return DegradationReport(overall_degradation_score=0.0, category="ACCEPTABLE", triggers_optimizer=False)


def _severe_degradation() -> DegradationReport:
    return DegradationReport(overall_degradation_score=0.8, category="SEVERE", triggers_optimizer=True)


def _make_loop(deployer, monitor, *, optimizer=None, confirmations=3):
    spec = StrategySpec(spec_id="sess-1", symbols=["SPY"], data_source="yfinance",
                        strategy_type="trend_following")
    build = BuildResult(success=True, spec_id="sess-1", strategy_file="/tmp/strat.py",
                        initial_parameters={"fast_window": 20, "slow_window": 50},
                        parameter_bounds={"fast_window": (5, 50), "slow_window": (20, 200)})
    state = PipelineState(session_id="sess-1", spec=spec, build_result=build)
    state.transition_to("BUILDING")
    state.transition_to("RUNNING")
    # A backtest result supplies the DSR for the graduation gate.
    state.pipeline_results.append(PipelineResult(
        spec_id="sess-1", status="DEPLOYED_PAPER",
        cpcv_summary={"dsr": 0.97, "mean_sharpe": 1.5},
        backtest_metrics={"mean_sharpe": 1.5, "max_drawdown": 0.08},
    ))
    return AutonomousLoop(
        deployer=deployer, monitor=monitor, gates=GraduationGates(),
        tracker=GraduationTracker(session_id="sess-1"), state=state,
        build_result=build, spec=spec, event_bus=PipelineEventBus(),
        optimization_engine=optimizer, notifiers=[],
        config=AutopilotConfig(interval_seconds=0, max_ticks=20,
                               graduation_confirmations=confirmations),
    )


# --------------------------------------------------------------------------
# Tests
# --------------------------------------------------------------------------
def test_graduates_after_consecutive_passes():
    monitor = FakeMonitor([_passing_snapshot()], [_clean_degradation()])
    deployer = FakeDeployer()
    loop = _make_loop(deployer, monitor, confirmations=3)

    result = loop.run_forever()

    assert result.status == "GRADUATED"
    assert result.ticks == 3  # graduates exactly at the 3rd consecutive pass
    assert result.certificate is not None
    assert loop._state.status == "GRADUATED"
    assert loop._state.graduation_result["status"] == "GRADUATED"


def test_single_pass_does_not_graduate():
    monitor = FakeMonitor([_passing_snapshot()], [_clean_degradation()])
    deployer = FakeDeployer()
    loop = _make_loop(deployer, monitor, confirmations=3)

    t1 = loop.tick()
    assert t1.action == "TRADE"
    assert t1.consecutive_graduations == 1
    assert loop._tracker.get_certificate() is None


def test_consistency_resets_on_failure():
    # pass, pass, FAIL, pass, pass, pass -> graduate only at tick 6
    snaps = [_passing_snapshot(), _passing_snapshot(), _failing_snapshot(),
             _passing_snapshot(), _passing_snapshot(), _passing_snapshot()]
    degs = [_clean_degradation()] * 6
    monitor = FakeMonitor(snaps, degs)
    loop = _make_loop(FakeDeployer(), monitor, confirmations=3)

    result = loop.run_forever()
    assert result.status == "GRADUATED"
    assert result.ticks == 6


def test_optimization_triggered_and_params_applied():
    monitor = FakeMonitor([_failing_snapshot()], [_severe_degradation()])
    optimizer = FakeOptimizer(changes={"fast_window": 10})
    loop = _make_loop(FakeDeployer(), monitor, optimizer=optimizer, confirmations=3)

    tick = loop.tick()
    assert tick.action == "OPTIMIZED"
    assert tick.optimized is True
    assert optimizer.calls == 1
    assert loop.current_parameters["fast_window"] == 10


def test_optimization_params_clamped_to_bounds():
    monitor = FakeMonitor([_failing_snapshot()], [_severe_degradation()])
    optimizer = FakeOptimizer(changes={"fast_window": 9999})  # above bound 50
    loop = _make_loop(FakeDeployer(), monitor, optimizer=optimizer)

    loop.tick()
    assert loop.current_parameters["fast_window"] == 50


def test_no_optimizer_means_no_optimization():
    monitor = FakeMonitor([_failing_snapshot()], [_severe_degradation()])
    loop = _make_loop(FakeDeployer(), monitor, optimizer=None)

    tick = loop.tick()
    assert tick.action == "TRADE"
    assert tick.optimized is False


def test_suspension_stops_loop():
    monitor = FakeMonitor([_passing_snapshot()], [_clean_degradation()])
    deployer = FakeDeployer(suspend_at=1)
    loop = _make_loop(deployer, monitor)

    result = loop.run_forever()
    assert result.status == "SUSPENDED"
    assert "suspended" in result.message.lower()


def test_optimized_params_flow_into_next_trade_cycle():
    # Degraded once -> optimize -> next cycle should trade with new params.
    snaps = [_failing_snapshot()]
    degs = [_severe_degradation(), _clean_degradation()]
    monitor = FakeMonitor(snaps, degs)
    optimizer = FakeOptimizer(changes={"fast_window": 12})
    deployer = FakeDeployer()
    loop = _make_loop(deployer, monitor, optimizer=optimizer, confirmations=99)

    loop.tick()  # degraded -> optimize -> fast_window=12
    loop.tick()  # trades again
    assert deployer.params_seen[1]["fast_window"] == 12
