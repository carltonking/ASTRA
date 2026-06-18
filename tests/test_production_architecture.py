"""Tests for production architecture services."""

import asyncio
from astra.db import Database
from astra.db.recorder import ProductionRecorder
from astra.db.repositories import ResearchRepository
from astra.events import AstraEvent, InMemoryEventBus
from astra.evolution import EvolutionEngine, Genome
from astra.memory import MemoryEngine, MemoryItem, MemoryQuery
from astra.memory import MemoryExtractor
from astra.regime import RegimeEngine
from astra.validation import RobustnessMetrics, ValidationEngine
from astra.builder.generator import BuildResult
from astra.pipeline.runner import PipelineResult
from astra.planner.spec import StrategySpec


def test_event_bus_persists_and_dispatches():
    asyncio.run(_event_bus_persists_and_dispatches())


async def _event_bus_persists_and_dispatches():
    db = Database("sqlite+aiosqlite:///:memory:")
    await db.create_all()
    seen: list[str] = []
    bus = InMemoryEventBus(db=db)
    bus.subscribe("StrategyBuilt", lambda event: seen.append(event.event_id))

    event = AstraEvent(
        event_type="StrategyBuilt",
        aggregate_type="strategy",
        aggregate_id="s1",
        payload={"status": "SANDBOXED"},
    )
    await bus.publish(event)

    assert seen == [event.event_id]
    assert bus.history()[0].payload["status"] == "SANDBOXED"
    await db.dispose()


def test_memory_engine_ranks_robust_evidence():
    asyncio.run(_memory_engine_ranks_robust_evidence())


async def _memory_engine_ranks_robust_evidence():
    db = Database("sqlite+aiosqlite:///:memory:")
    await db.create_all()
    engine = MemoryEngine(db)

    await engine.remember(
        MemoryItem(
            layer="strategic",
            topic="mean_reversion",
            claim="RSI mean reversion fails in high volatility downtrends",
            tags=["rsi", "high_vol"],
            support_count=10,
            contradiction_count=1,
            robustness_score=0.9,
        )
    )
    results = await engine.retrieve(
        MemoryQuery(text="RSI high volatility", tags=["rsi"], min_robustness=0.5)
    )

    assert len(results) == 1
    assert results[0].topic == "mean_reversion"
    await db.dispose()


def test_evolution_engine_preserves_elites_and_mutates_children():
    population = [
        Genome(
            strategy_id="a",
            strategy_type="momentum",
            parameters={"lookback": 20},
            validation_scores={"oos_stability": 0.9, "parameter_robustness": 0.8, "regime_adaptability": 0.7},
            complexity=2,
        ),
        Genome(
            strategy_id="b",
            strategy_type="momentum",
            parameters={"lookback": 50},
            validation_scores={"oos_stability": 0.2},
            complexity=8,
        ),
    ]

    result = EvolutionEngine(seed=1).evolve(
        population,
        parameter_bounds={"lookback": (5, 100)},
        elite_count=1,
        child_count=2,
    )

    assert result.elites[0].strategy_id == "a"
    assert len(result.children) == 2
    assert all(child.parent_ids for child in result.children)


def test_validation_engine_rejects_overfit_strategy():
    decision = ValidationEngine().decide(
        RobustnessMetrics(
            oos_sharpe=-0.1,
            dsr=0.2,
            pbo=0.8,
            parameter_plateau=0.02,
            regime_pass_rate=0.2,
            slippage_survival=0.1,
            turnover=12,
            max_drawdown=0.4,
            complexity=9,
        )
    )

    assert decision.status == "REJECT"
    assert "OOS_COLLAPSE" in decision.hard_failures
    assert "PBO_TOO_HIGH" in decision.hard_failures


def test_regime_engine_classifies_basic_uptrend():
    import pandas as pd

    data = pd.DataFrame(
        {
            "close": [100 + i * 0.5 for i in range(120)],
            "volume": [1_000_000] * 120,
        },
        index=pd.date_range("2024-01-01", periods=120),
    )
    snapshot = RegimeEngine().classify(data)

    assert snapshot.trend == "uptrend"
    assert snapshot.aggregate_confidence > 0


def test_memory_extractor_turns_rejection_into_memory():
    decision = ValidationEngine().decide(
        RobustnessMetrics(oos_sharpe=-1, dsr=0.1, pbo=0.9, slippage_survival=0.1)
    )

    memories = MemoryExtractor().from_validation("momentum", decision)

    assert memories
    assert any("OOS_COLLAPSE" in item.claim for item in memories)


def test_production_recorder_persists_build_and_pipeline(tmp_path, monkeypatch):
    async def run() -> None:
        db = Database("sqlite+aiosqlite:///:memory:")
        await db.create_all()
        monkeypatch.setenv("ASTRA_ENABLE_PRODUCTION_PERSISTENCE", "1")
        spec = StrategySpec(
            spec_id="spec-recorder",
            asset_class="equity",
            symbols=["SPY"],
            timeframe="daily",
            data_source="yfinance",
            strategy_type="momentum",
            market_hypothesis="Momentum should persist in liquid equity indices after trend confirmation",
            entry_conditions=["close above moving average"],
            exit_conditions=["close below moving average"],
            target_return=0.1,
            max_drawdown=0.2,
            position_size=0.1,
            max_positions=1,
            backtest_start="2020-01-01",
            backtest_end="2024-01-01",
        )
        build = BuildResult(
            success=True,
            spec_id=spec.spec_id,
            strategy_file=str(tmp_path / "strategy.py"),
            strategy_class_name="MomentumStrategy",
            strategy_hash="codehash",
            spec_hash="spechash",
            prompt_hash="prompthash",
        )
        recorder = ProductionRecorder(db)
        await recorder._record_build(spec, build)
        await recorder._record_pipeline(
            spec,
            PipelineResult(
                pipeline_id="pipe-1",
                spec_id=spec.spec_id,
                status="DEPLOYED_PAPER",
                cpcv_summary={"dsr": 1.2},
                paper_deployment_id="dep-1",
            ),
        )
        rows = await ResearchRepository(db).list_strategies()
        assert rows[0].strategy_id == spec.spec_id
        await db.dispose()

    asyncio.run(run())
