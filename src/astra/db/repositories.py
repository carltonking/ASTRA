"""Typed repositories for production research records."""

from typing import Any

from sqlalchemy import select

from astra.db.models import (
    DatasetRecord,
    DeploymentRecord,
    ExperimentRecord,
    HypothesisRecord,
    StrategyRecord,
    ValidationRunRecord,
)
from astra.db.session import Database


class ResearchRepository:
    def __init__(self, db: Database):
        self._db = db

    async def save_hypothesis(
        self,
        hypothesis_id: str,
        thesis: str,
        null_hypothesis: str = "",
        asset_universe: list[str] | None = None,
        status: str = "DRAFT",
    ) -> None:
        async with self._db.session() as session:
            existing = await session.get(HypothesisRecord, hypothesis_id)
            if existing is None:
                session.add(
                    HypothesisRecord(
                        hypothesis_id=hypothesis_id,
                        thesis=thesis,
                        null_hypothesis=null_hypothesis,
                        asset_universe=asset_universe or [],
                        status=status,
                    )
                )
            else:
                existing.thesis = thesis
                existing.null_hypothesis = null_hypothesis
                existing.asset_universe = asset_universe or []
                existing.status = status

    async def save_strategy(
        self,
        strategy_id: str,
        strategy_type: str,
        code_hash: str,
        spec_hash: str,
        prompt_hash: str = "",
        hypothesis_id: str | None = None,
        parent_strategy_id: str | None = None,
        generation_number: int = 0,
        artifact_uri: str = "",
        manifest: dict[str, Any] | None = None,
        status: str = "SANDBOXED",
    ) -> None:
        async with self._db.session() as session:
            existing = await session.get(StrategyRecord, strategy_id)
            payload = {
                "hypothesis_id": hypothesis_id,
                "parent_strategy_id": parent_strategy_id,
                "generation_number": generation_number,
                "strategy_type": strategy_type,
                "code_hash": code_hash,
                "spec_hash": spec_hash,
                "prompt_hash": prompt_hash,
                "artifact_uri": artifact_uri,
                "manifest": manifest or {},
                "status": status,
            }
            if existing is None:
                session.add(StrategyRecord(strategy_id=strategy_id, **payload))
            else:
                for key, value in payload.items():
                    setattr(existing, key, value)

    async def save_dataset(
        self,
        dataset_id: str,
        provider: str,
        symbols: list[str],
        start: str,
        end: str,
        checksum: str,
        quality: dict[str, Any] | None = None,
        calendar: str = "NYSE",
    ) -> None:
        async with self._db.session() as session:
            existing = await session.get(DatasetRecord, dataset_id)
            if existing is None:
                session.add(
                    DatasetRecord(
                        dataset_id=dataset_id,
                        provider=provider,
                        symbols=symbols,
                        start=start,
                        end=end,
                        calendar=calendar,
                        checksum=checksum,
                        quality=quality or {},
                    )
                )

    async def save_experiment(
        self,
        experiment_id: str,
        strategy_id: str,
        config_hash: str,
        dataset_id: str | None = None,
        seed: int = 0,
        status: str = "PENDING",
    ) -> None:
        async with self._db.session() as session:
            existing = await session.get(ExperimentRecord, experiment_id)
            if existing is None:
                session.add(
                    ExperimentRecord(
                        experiment_id=experiment_id,
                        strategy_id=strategy_id,
                        dataset_id=dataset_id,
                        seed=seed,
                        config_hash=config_hash,
                        status=status,
                    )
                )
            else:
                existing.status = status

    async def save_validation_run(
        self,
        validation_run_id: str,
        experiment_id: str,
        method: str,
        result: dict[str, Any],
        split_spec: dict[str, Any] | None = None,
        cost_model: dict[str, Any] | None = None,
        robustness_score: float = 0.0,
        fragility_score: float = 100.0,
    ) -> None:
        async with self._db.session() as session:
            session.add(
                ValidationRunRecord(
                    validation_run_id=validation_run_id,
                    experiment_id=experiment_id,
                    method=method,
                    split_spec=split_spec or {},
                    cost_model=cost_model or {},
                    result=result,
                    robustness_score=robustness_score,
                    fragility_score=fragility_score,
                )
            )

    async def save_deployment(
        self,
        deployment_id: str,
        strategy_id: str,
        broker: str,
        status: str,
        limits: dict[str, Any],
    ) -> None:
        async with self._db.session() as session:
            existing = await session.get(DeploymentRecord, deployment_id)
            if existing is None:
                session.add(
                    DeploymentRecord(
                        deployment_id=deployment_id,
                        strategy_id=strategy_id,
                        broker=broker,
                        status=status,
                        limits=limits,
                    )
                )
            else:
                existing.status = status
                existing.limits = limits

    async def list_strategies(self, limit: int = 50) -> list[StrategyRecord]:
        async with self._db.session() as session:
            rows = await session.execute(
                select(StrategyRecord).order_by(StrategyRecord.created_at.desc()).limit(limit)
            )
            return list(rows.scalars().all())
