"""SQLAlchemy models for traceable autonomous research."""

from datetime import datetime, timezone
from typing import Any

from sqlalchemy import DateTime, Float, ForeignKey, Index, Integer, String, Text, UniqueConstraint
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship
from sqlalchemy.types import JSON


JsonType = JSON().with_variant(JSONB, "postgresql")


def utcnow() -> datetime:
    return datetime.now(timezone.utc)


class Base(DeclarativeBase):
    pass


class EventRecord(Base):
    __tablename__ = "events"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    event_id: Mapped[str] = mapped_column(String(64), unique=True, index=True)
    event_type: Mapped[str] = mapped_column(String(128), index=True)
    aggregate_type: Mapped[str] = mapped_column(String(64), index=True)
    aggregate_id: Mapped[str] = mapped_column(String(128), index=True)
    payload: Mapped[dict[str, Any]] = mapped_column(JsonType, default=dict)
    metadata_: Mapped[dict[str, Any]] = mapped_column("metadata", JsonType, default=dict)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, index=True)


class HypothesisRecord(Base):
    __tablename__ = "hypotheses"

    hypothesis_id: Mapped[str] = mapped_column(String(64), primary_key=True)
    thesis: Mapped[str] = mapped_column(Text)
    null_hypothesis: Mapped[str] = mapped_column(Text, default="")
    asset_universe: Mapped[list[str]] = mapped_column(JsonType, default=list)
    status: Mapped[str] = mapped_column(String(32), default="DRAFT", index=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)

    strategies: Mapped[list["StrategyRecord"]] = relationship(back_populates="hypothesis")


class StrategyRecord(Base):
    __tablename__ = "strategies"

    strategy_id: Mapped[str] = mapped_column(String(64), primary_key=True)
    hypothesis_id: Mapped[str | None] = mapped_column(ForeignKey("hypotheses.hypothesis_id"), nullable=True)
    parent_strategy_id: Mapped[str | None] = mapped_column(String(64), index=True)
    generation_number: Mapped[int] = mapped_column(Integer, default=0, index=True)
    strategy_type: Mapped[str] = mapped_column(String(64), index=True)
    code_hash: Mapped[str] = mapped_column(String(128), index=True)
    spec_hash: Mapped[str] = mapped_column(String(128), index=True)
    prompt_hash: Mapped[str] = mapped_column(String(128), default="", index=True)
    artifact_uri: Mapped[str] = mapped_column(Text, default="")
    manifest: Mapped[dict[str, Any]] = mapped_column(JsonType, default=dict)
    status: Mapped[str] = mapped_column(String(32), default="SANDBOXED", index=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)

    hypothesis: Mapped[HypothesisRecord | None] = relationship(back_populates="strategies")
    experiments: Mapped[list["ExperimentRecord"]] = relationship(back_populates="strategy")


class DatasetRecord(Base):
    __tablename__ = "datasets"
    __table_args__ = (UniqueConstraint("provider", "checksum", name="uq_dataset_provider_checksum"),)

    dataset_id: Mapped[str] = mapped_column(String(64), primary_key=True)
    provider: Mapped[str] = mapped_column(String(64), index=True)
    symbols: Mapped[list[str]] = mapped_column(JsonType, default=list)
    start: Mapped[str] = mapped_column(String(32))
    end: Mapped[str] = mapped_column(String(32))
    calendar: Mapped[str] = mapped_column(String(64), default="NYSE")
    checksum: Mapped[str] = mapped_column(String(128), index=True)
    quality: Mapped[dict[str, Any]] = mapped_column(JsonType, default=dict)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)


class ExperimentRecord(Base):
    __tablename__ = "experiments"

    experiment_id: Mapped[str] = mapped_column(String(64), primary_key=True)
    strategy_id: Mapped[str] = mapped_column(ForeignKey("strategies.strategy_id"), index=True)
    dataset_id: Mapped[str | None] = mapped_column(ForeignKey("datasets.dataset_id"), nullable=True)
    seed: Mapped[int] = mapped_column(Integer, default=0)
    config_hash: Mapped[str] = mapped_column(String(128), index=True)
    status: Mapped[str] = mapped_column(String(32), default="PENDING", index=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)

    strategy: Mapped[StrategyRecord] = relationship(back_populates="experiments")
    validation_runs: Mapped[list["ValidationRunRecord"]] = relationship(back_populates="experiment")


class ValidationRunRecord(Base):
    __tablename__ = "validation_runs"

    validation_run_id: Mapped[str] = mapped_column(String(64), primary_key=True)
    experiment_id: Mapped[str] = mapped_column(ForeignKey("experiments.experiment_id"), index=True)
    method: Mapped[str] = mapped_column(String(64), index=True)
    split_spec: Mapped[dict[str, Any]] = mapped_column(JsonType, default=dict)
    cost_model: Mapped[dict[str, Any]] = mapped_column(JsonType, default=dict)
    result: Mapped[dict[str, Any]] = mapped_column(JsonType, default=dict)
    robustness_score: Mapped[float] = mapped_column(Float, default=0.0, index=True)
    fragility_score: Mapped[float] = mapped_column(Float, default=100.0, index=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)

    experiment: Mapped[ExperimentRecord] = relationship(back_populates="validation_runs")


class MemoryRecord(Base):
    __tablename__ = "memory_items"

    memory_id: Mapped[str] = mapped_column(String(64), primary_key=True)
    layer: Mapped[str] = mapped_column(String(32), index=True)
    topic: Mapped[str] = mapped_column(String(128), index=True)
    claim: Mapped[str] = mapped_column(Text)
    evidence: Mapped[dict[str, Any]] = mapped_column(JsonType, default=dict)
    tags: Mapped[list[str]] = mapped_column(JsonType, default=list)
    support_count: Mapped[int] = mapped_column(Integer, default=0)
    contradiction_count: Mapped[int] = mapped_column(Integer, default=0)
    robustness_score: Mapped[float] = mapped_column(Float, default=0.0)
    relevance_score: Mapped[float] = mapped_column(Float, default=0.0)
    status: Mapped[str] = mapped_column(String(32), default="active", index=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    last_used_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)


class DeploymentRecord(Base):
    __tablename__ = "paper_deployments"

    deployment_id: Mapped[str] = mapped_column(String(64), primary_key=True)
    strategy_id: Mapped[str] = mapped_column(String(64), index=True)
    broker: Mapped[str] = mapped_column(String(64), default="alpaca")
    status: Mapped[str] = mapped_column(String(32), default="ACTIVE", index=True)
    limits: Mapped[dict[str, Any]] = mapped_column(JsonType, default=dict)
    started_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    stopped_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)


Index("idx_events_aggregate", EventRecord.aggregate_type, EventRecord.aggregate_id, EventRecord.created_at)
