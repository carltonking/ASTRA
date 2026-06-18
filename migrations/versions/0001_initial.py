"""initial schema

Revision ID: 0001_initial
Revises:
Create Date: 2026-05-23
"""

from alembic import op
import sqlalchemy as sa

revision = "0001_initial"
down_revision = None
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "events",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("event_id", sa.String(length=64), nullable=False),
        sa.Column("event_type", sa.String(length=128), nullable=False),
        sa.Column("aggregate_type", sa.String(length=64), nullable=False),
        sa.Column("aggregate_id", sa.String(length=128), nullable=False),
        sa.Column("payload", sa.JSON(), nullable=False),
        sa.Column("metadata", sa.JSON(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("event_id"),
    )
    op.create_index("ix_events_event_id", "events", ["event_id"])
    op.create_index("idx_events_aggregate", "events", ["aggregate_type", "aggregate_id", "created_at"])

    op.create_table(
        "hypotheses",
        sa.Column("hypothesis_id", sa.String(length=64), nullable=False),
        sa.Column("thesis", sa.Text(), nullable=False),
        sa.Column("null_hypothesis", sa.Text(), nullable=False),
        sa.Column("asset_universe", sa.JSON(), nullable=False),
        sa.Column("status", sa.String(length=32), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint("hypothesis_id"),
    )

    op.create_table(
        "strategies",
        sa.Column("strategy_id", sa.String(length=64), nullable=False),
        sa.Column("hypothesis_id", sa.String(length=64), nullable=True),
        sa.Column("parent_strategy_id", sa.String(length=64), nullable=True),
        sa.Column("generation_number", sa.Integer(), nullable=False),
        sa.Column("strategy_type", sa.String(length=64), nullable=False),
        sa.Column("code_hash", sa.String(length=128), nullable=False),
        sa.Column("spec_hash", sa.String(length=128), nullable=False),
        sa.Column("prompt_hash", sa.String(length=128), nullable=False),
        sa.Column("artifact_uri", sa.Text(), nullable=False),
        sa.Column("manifest", sa.JSON(), nullable=False),
        sa.Column("status", sa.String(length=32), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["hypothesis_id"], ["hypotheses.hypothesis_id"]),
        sa.PrimaryKeyConstraint("strategy_id"),
    )

    op.create_table(
        "datasets",
        sa.Column("dataset_id", sa.String(length=64), nullable=False),
        sa.Column("provider", sa.String(length=64), nullable=False),
        sa.Column("symbols", sa.JSON(), nullable=False),
        sa.Column("start", sa.String(length=32), nullable=False),
        sa.Column("end", sa.String(length=32), nullable=False),
        sa.Column("calendar", sa.String(length=64), nullable=False),
        sa.Column("checksum", sa.String(length=128), nullable=False),
        sa.Column("quality", sa.JSON(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint("dataset_id"),
        sa.UniqueConstraint("provider", "checksum", name="uq_dataset_provider_checksum"),
    )

    op.create_table(
        "experiments",
        sa.Column("experiment_id", sa.String(length=64), nullable=False),
        sa.Column("strategy_id", sa.String(length=64), nullable=False),
        sa.Column("dataset_id", sa.String(length=64), nullable=True),
        sa.Column("seed", sa.Integer(), nullable=False),
        sa.Column("config_hash", sa.String(length=128), nullable=False),
        sa.Column("status", sa.String(length=32), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["dataset_id"], ["datasets.dataset_id"]),
        sa.ForeignKeyConstraint(["strategy_id"], ["strategies.strategy_id"]),
        sa.PrimaryKeyConstraint("experiment_id"),
    )

    op.create_table(
        "validation_runs",
        sa.Column("validation_run_id", sa.String(length=64), nullable=False),
        sa.Column("experiment_id", sa.String(length=64), nullable=False),
        sa.Column("method", sa.String(length=64), nullable=False),
        sa.Column("split_spec", sa.JSON(), nullable=False),
        sa.Column("cost_model", sa.JSON(), nullable=False),
        sa.Column("result", sa.JSON(), nullable=False),
        sa.Column("robustness_score", sa.Float(), nullable=False),
        sa.Column("fragility_score", sa.Float(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["experiment_id"], ["experiments.experiment_id"]),
        sa.PrimaryKeyConstraint("validation_run_id"),
    )

    op.create_table(
        "memory_items",
        sa.Column("memory_id", sa.String(length=64), nullable=False),
        sa.Column("layer", sa.String(length=32), nullable=False),
        sa.Column("topic", sa.String(length=128), nullable=False),
        sa.Column("claim", sa.Text(), nullable=False),
        sa.Column("evidence", sa.JSON(), nullable=False),
        sa.Column("tags", sa.JSON(), nullable=False),
        sa.Column("support_count", sa.Integer(), nullable=False),
        sa.Column("contradiction_count", sa.Integer(), nullable=False),
        sa.Column("robustness_score", sa.Float(), nullable=False),
        sa.Column("relevance_score", sa.Float(), nullable=False),
        sa.Column("status", sa.String(length=32), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("last_used_at", sa.DateTime(timezone=True), nullable=True),
        sa.PrimaryKeyConstraint("memory_id"),
    )

    op.create_table(
        "paper_deployments",
        sa.Column("deployment_id", sa.String(length=64), nullable=False),
        sa.Column("strategy_id", sa.String(length=64), nullable=False),
        sa.Column("broker", sa.String(length=64), nullable=False),
        sa.Column("status", sa.String(length=32), nullable=False),
        sa.Column("limits", sa.JSON(), nullable=False),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("stopped_at", sa.DateTime(timezone=True), nullable=True),
        sa.PrimaryKeyConstraint("deployment_id"),
    )


def downgrade() -> None:
    op.drop_table("paper_deployments")
    op.drop_table("memory_items")
    op.drop_table("validation_runs")
    op.drop_table("experiments")
    op.drop_table("datasets")
    op.drop_table("strategies")
    op.drop_table("hypotheses")
    op.drop_table("events")
