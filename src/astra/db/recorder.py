"""Best-effort production persistence for existing synchronous pipeline code."""

import asyncio
import json
import os
import threading
import uuid
from dataclasses import asdict, is_dataclass
from datetime import date, datetime
from typing import Any, cast

from astra.builder.generator import BuildResult
from astra.db.repositories import ResearchRepository
from astra.db.session import Database
from astra.pipeline.runner import PipelineResult
from astra.planner.spec import StrategySpec


class ProductionRecorder:
    """Persist current dataclass artifacts into Postgres without breaking local runs."""

    def __init__(self, db: Database | None = None):
        self._enabled = os.environ.get("ASTRA_ENABLE_PRODUCTION_PERSISTENCE", "0") == "1"
        self._db = db or Database()

    @property
    def enabled(self) -> bool:
        return self._enabled

    def record_build(self, spec: StrategySpec, build: BuildResult) -> None:
        if not self._enabled or not build.success:
            return
        self._spawn(self._record_build(spec, build))

    def record_pipeline(self, spec: StrategySpec, result: PipelineResult) -> None:
        if not self._enabled:
            return
        self._spawn(self._record_pipeline(spec, result))

    async def _record_build(self, spec: StrategySpec, build: BuildResult) -> None:
        repo = ResearchRepository(self._db)
        await repo.save_hypothesis(
            hypothesis_id=spec.spec_id,
            thesis=spec.market_hypothesis or spec.user_idea,
            null_hypothesis=f"No robust edge exists for {spec.strategy_type}",
            asset_universe=list(spec.symbols),
            status="BUILT",
        )
        manifest = self._load_json(build.metadata_file)
        await repo.save_strategy(
            strategy_id=spec.spec_id,
            hypothesis_id=spec.spec_id,
            parent_strategy_id=spec.parent_strategy_id,
            generation_number=spec.generation_number,
            strategy_type=spec.strategy_type,
            code_hash=build.strategy_hash,
            spec_hash=build.spec_hash,
            prompt_hash=build.prompt_hash,
            artifact_uri=build.strategy_file,
            manifest=manifest,
            status="SANDBOXED",
        )

    async def _record_pipeline(self, spec: StrategySpec, result: PipelineResult) -> None:
        repo = ResearchRepository(self._db)
        experiment_id = result.pipeline_id or str(uuid.uuid4())
        await repo.save_experiment(
            experiment_id=experiment_id,
            strategy_id=spec.spec_id,
            config_hash=result.pipeline_id or experiment_id,
            status=result.status,
        )
        metrics = result.cpcv_summary or result.backtest_metrics or {}
        robustness = float(metrics.get("dsr", 0.0)) * 50.0
        fragility = max(0.0, 100.0 - robustness)
        await repo.save_validation_run(
            validation_run_id=str(uuid.uuid4()),
            experiment_id=experiment_id,
            method="pipeline_cpcv",
            result=self._jsonable(result),
            split_spec={"method": "cpcv"},
            cost_model={"transaction_cost": spec.transaction_cost},
            robustness_score=robustness,
            fragility_score=fragility,
        )
        if result.paper_deployment_id:
            await repo.save_deployment(
                deployment_id=result.paper_deployment_id,
                strategy_id=spec.spec_id,
                broker=os.environ.get("ASTRA_BROKER", "alpaca"),
                status=result.status,
                limits={
                    "max_drawdown": spec.max_drawdown,
                    "position_size": spec.position_size,
                    "max_positions": spec.max_positions,
                    "paper_only": True,
                },
            )

    @staticmethod
    def _spawn(coro: Any) -> None:
        try:
            loop = asyncio.get_running_loop()
            loop.create_task(coro)
        except RuntimeError:
            threading.Thread(target=lambda: asyncio.run(coro), daemon=True).start()

    @staticmethod
    def _load_json(path: str) -> dict[str, Any]:
        if not path or not os.path.exists(path):
            return {}
        with open(path) as f:
            return json.load(f)

    def _jsonable(self, value: Any) -> Any:
        if is_dataclass(value):
            return self._jsonable(asdict(cast(Any, value)))
        if isinstance(value, dict):
            return {str(k): self._jsonable(v) for k, v in value.items()}
        if isinstance(value, list):
            return [self._jsonable(v) for v in value]
        if isinstance(value, (date, datetime)):
            return value.isoformat()
        return value
