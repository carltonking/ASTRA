"""Multi-layer research memory with deterministic scoring."""

import math
import uuid
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any, Literal

from sqlalchemy import select

from astra.db.models import MemoryRecord
from astra.db.session import Database


MemoryLayer = Literal["tactical", "strategic", "meta"]


@dataclass
class MemoryItem:
    layer: MemoryLayer
    topic: str
    claim: str
    evidence: dict[str, Any] = field(default_factory=dict)
    tags: list[str] = field(default_factory=list)
    support_count: int = 0
    contradiction_count: int = 0
    robustness_score: float = 0.0
    memory_id: str = field(default_factory=lambda: str(uuid.uuid4()))


@dataclass
class MemoryQuery:
    text: str = ""
    layer: MemoryLayer | None = None
    tags: list[str] = field(default_factory=list)
    min_robustness: float = 0.0
    limit: int = 10


class MemoryEngine:
    def __init__(self, db: Database):
        self._db = db

    async def remember(self, item: MemoryItem) -> str:
        score = self._confidence(item.support_count, item.contradiction_count) * item.robustness_score
        async with self._db.session() as session:
            session.add(
                MemoryRecord(
                    memory_id=item.memory_id,
                    layer=item.layer,
                    topic=item.topic,
                    claim=item.claim,
                    evidence=item.evidence,
                    tags=item.tags,
                    support_count=item.support_count,
                    contradiction_count=item.contradiction_count,
                    robustness_score=item.robustness_score,
                    relevance_score=score,
                )
            )
        return item.memory_id

    async def retrieve(self, query: MemoryQuery) -> list[MemoryRecord]:
        async with self._db.session() as session:
            stmt = select(MemoryRecord).where(MemoryRecord.status == "active")
            if query.layer is not None:
                stmt = stmt.where(MemoryRecord.layer == query.layer)
            if query.min_robustness:
                stmt = stmt.where(MemoryRecord.robustness_score >= query.min_robustness)
            records = list((await session.execute(stmt)).scalars().all())

            ranked = sorted(
                records,
                key=lambda rec: self._rank(rec, query),
                reverse=True,
            )
            for rec in ranked[: query.limit]:
                rec.last_used_at = datetime.now(timezone.utc)
            return ranked[: query.limit]

    async def reinforce(
        self,
        memory_id: str,
        supported: bool,
        robustness_delta: float = 0.0,
    ) -> None:
        async with self._db.session() as session:
            rec = await session.get(MemoryRecord, memory_id)
            if rec is None:
                return
            if supported:
                rec.support_count += 1
            else:
                rec.contradiction_count += 1
            rec.robustness_score = max(0.0, min(1.0, rec.robustness_score + robustness_delta))
            rec.relevance_score = self._confidence(rec.support_count, rec.contradiction_count) * rec.robustness_score
            if rec.contradiction_count > rec.support_count * 2 and rec.support_count >= 3:
                rec.status = "disputed"

    async def prune(self, min_relevance: float = 0.05) -> int:
        pruned = 0
        async with self._db.session() as session:
            rows = list((await session.execute(select(MemoryRecord))).scalars().all())
            for rec in rows:
                if rec.relevance_score < min_relevance and rec.support_count + rec.contradiction_count >= 5:
                    rec.status = "deprecated"
                    pruned += 1
        return pruned

    @staticmethod
    def _confidence(support: int, contradiction: int) -> float:
        return (support + 1) / (support + contradiction + 2)

    def _rank(self, rec: MemoryRecord, query: MemoryQuery) -> float:
        semantic = self._token_overlap(query.text, f"{rec.topic} {rec.claim}")
        tag_match = len(set(query.tags) & set(rec.tags)) / max(1, len(set(query.tags)))
        evidence = math.log1p(rec.support_count) * self._confidence(rec.support_count, rec.contradiction_count)
        return (
            0.35 * semantic
            + 0.20 * tag_match
            + 0.25 * rec.robustness_score
            + 0.15 * evidence
            + 0.05 * rec.relevance_score
        )

    @staticmethod
    def _token_overlap(a: str, b: str) -> float:
        left = {t.lower() for t in a.split() if len(t) > 2}
        right = {t.lower() for t in b.split() if len(t) > 2}
        if not left or not right:
            return 0.0
        return len(left & right) / len(left | right)
