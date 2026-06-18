"""Production research APIs backed by event sourcing and SQLAlchemy."""

import os
from typing import Any

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field

from astra.db import Database
from astra.events import AstraEvent, InMemoryEventBus, RedisEventBus
from astra.evolution import EvolutionEngine, Genome
from astra.memory import MemoryEngine, MemoryItem, MemoryQuery
from astra.validation import RobustnessMetrics, ValidationEngine, ValidationPolicy


router = APIRouter(prefix="/api/v1", tags=["research"])


def _db() -> Database:
    return Database()


def _bus() -> InMemoryEventBus:
    if os.environ.get("ASTRA_ENABLE_REDIS_EVENTS", "0") == "1":
        return RedisEventBus(db=_db())
    return InMemoryEventBus(db=_db())


class EventRequest(BaseModel):
    event_type: str
    aggregate_type: str
    aggregate_id: str
    payload: dict[str, Any] = Field(default_factory=dict)
    metadata: dict[str, Any] = Field(default_factory=dict)


class MemoryRequest(BaseModel):
    layer: str
    topic: str
    claim: str
    evidence: dict[str, Any] = Field(default_factory=dict)
    tags: list[str] = Field(default_factory=list)
    support_count: int = 0
    contradiction_count: int = 0
    robustness_score: float = 0.0


class MemorySearchRequest(BaseModel):
    text: str = ""
    layer: str | None = None
    tags: list[str] = Field(default_factory=list)
    min_robustness: float = 0.0
    limit: int = 10


class EvolutionRequest(BaseModel):
    population: list[dict[str, Any]]
    parameter_bounds: dict[str, tuple[float, float]]
    elite_count: int = 2
    child_count: int = 4
    seed: int = 0


class ValidationRequest(BaseModel):
    metrics: dict[str, float]
    policy: dict[str, float] = Field(default_factory=dict)


@router.post("/events")
async def publish_event(req: EventRequest) -> dict[str, str]:
    event = AstraEvent(
        event_type=req.event_type,
        aggregate_type=req.aggregate_type,
        aggregate_id=req.aggregate_id,
        payload=req.payload,
        metadata=req.metadata,
    )
    try:
        await _bus().publish(event)
    except Exception as e:
        raise HTTPException(status_code=503, detail=f"Event publication failed: {e}") from e
    return {"event_id": event.event_id, "status": "published"}


@router.post("/memory")
async def remember(req: MemoryRequest) -> dict[str, str]:
    if req.layer not in {"tactical", "strategic", "meta"}:
        raise HTTPException(status_code=422, detail="Invalid memory layer")
    engine = MemoryEngine(_db())
    memory_id = await engine.remember(
        MemoryItem(
            layer=req.layer,  # type: ignore[arg-type]
            topic=req.topic,
            claim=req.claim,
            evidence=req.evidence,
            tags=req.tags,
            support_count=req.support_count,
            contradiction_count=req.contradiction_count,
            robustness_score=req.robustness_score,
        )
    )
    return {"memory_id": memory_id, "status": "stored"}


@router.post("/memory/search")
async def search_memory(req: MemorySearchRequest) -> dict[str, Any]:
    if req.layer is not None and req.layer not in {"tactical", "strategic", "meta"}:
        raise HTTPException(status_code=422, detail="Invalid memory layer")
    rows = await MemoryEngine(_db()).retrieve(
        MemoryQuery(
            text=req.text,
            layer=req.layer,  # type: ignore[arg-type]
            tags=req.tags,
            min_robustness=req.min_robustness,
            limit=req.limit,
        )
    )
    return {
        "items": [
            {
                "memory_id": row.memory_id,
                "layer": row.layer,
                "topic": row.topic,
                "claim": row.claim,
                "tags": row.tags,
                "support_count": row.support_count,
                "contradiction_count": row.contradiction_count,
                "robustness_score": row.robustness_score,
                "relevance_score": row.relevance_score,
                "status": row.status,
            }
            for row in rows
        ]
    }


@router.post("/evolution/evolve")
async def evolve(req: EvolutionRequest) -> dict[str, Any]:
    population = [
        Genome(
            strategy_id=str(item["strategy_id"]),
            strategy_type=str(item.get("strategy_type", "")),
            parameters={k: float(v) for k, v in item.get("parameters", {}).items()},
            indicators=list(item.get("indicators", [])),
            allowed_regimes=dict(item.get("allowed_regimes", {})),
            generation=int(item.get("generation", 0)),
            validation_scores={k: float(v) for k, v in item.get("validation_scores", {}).items()},
            complexity=float(item.get("complexity", 1.0)),
            turnover=float(item.get("turnover", 0.0)),
            max_drawdown=float(item.get("max_drawdown", 0.0)),
        )
        for item in req.population
    ]
    result = EvolutionEngine(seed=req.seed).evolve(
        population=population,
        parameter_bounds=req.parameter_bounds,
        elite_count=req.elite_count,
        child_count=req.child_count,
    )
    return {
        "elites": [g.__dict__ for g in result.elites],
        "children": [g.__dict__ for g in result.children],
        "rejected": [g.__dict__ for g in result.rejected],
    }


@router.post("/validation/decide")
async def validate(req: ValidationRequest) -> dict[str, Any]:
    policy = ValidationPolicy(**req.policy)
    metrics = RobustnessMetrics(**req.metrics)
    decision = ValidationEngine(policy).decide(metrics)
    return decision.__dict__


@router.post("/db/init")
async def init_database() -> dict[str, str]:
    try:
        await _db().create_all()
    except Exception as e:
        raise HTTPException(status_code=503, detail=f"Database initialization failed: {e}") from e
    return {"status": "initialized"}
