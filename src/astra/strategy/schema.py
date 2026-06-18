"""Pydantic schemas for generated strategy contracts."""

from datetime import datetime, timezone
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator


class SizingModel(BaseModel):
    model_config = ConfigDict(extra="forbid")

    type: Literal["fixed_fraction", "volatility_target", "kelly_fractional"] = "fixed_fraction"
    max_position_size: float = Field(default=0.10, ge=0.0, le=1.0)
    target_volatility: float | None = Field(default=None, gt=0.0, le=1.0)


class LeverageConstraints(BaseModel):
    model_config = ConfigDict(extra="forbid")

    max_gross_leverage: float = Field(default=1.0, ge=0.0, le=1.0)
    allow_margin: bool = False
    allow_short: bool = False


class RiskControls(BaseModel):
    model_config = ConfigDict(extra="forbid")

    max_drawdown: float = Field(default=0.20, ge=0.0, le=1.0)
    max_positions: int = Field(default=1, ge=1)
    stop_loss: float | None = Field(default=None, ge=0.0, le=1.0)
    take_profit: float | None = Field(default=None, ge=0.0, le=5.0)


class RegimeContract(BaseModel):
    model_config = ConfigDict(extra="forbid")

    assumptions: list[str] = Field(default_factory=list)
    allowed_regimes: dict[str, list[str]] = Field(default_factory=dict)
    prohibited_regimes: dict[str, list[str]] = Field(default_factory=dict)
    min_confidence: float = Field(default=0.70, ge=0.0, le=1.0)
    uncertain_action: Literal["suspend", "reduce", "hold_no_new_entries"] = "reduce"


class ExecutionAssumptions(BaseModel):
    model_config = ConfigDict(extra="forbid")

    order_type: Literal["market_on_next_bar", "close_to_close", "vwap_next_bar"] = "market_on_next_bar"
    transaction_cost: float = Field(default=0.001, ge=0.0, le=0.05)
    slippage_bps: float = Field(default=5.0, ge=0.0, le=500.0)
    max_participation_rate: float = Field(default=0.05, ge=0.0, le=1.0)
    paper_trading_only: bool = True


class StrategyLineage(BaseModel):
    model_config = ConfigDict(extra="forbid")

    strategy_id: str
    parent_strategy_id: str | None = None
    mutation_source: str | None = None
    generation_number: int = Field(default=0, ge=0)
    prompt_ancestry: list[str] = Field(default_factory=list)
    prompt_hash: str = ""
    validation_scores: dict[str, float] = Field(default_factory=dict)
    failure_reasons: list[str] = Field(default_factory=list)


class StrategySpecSchema(BaseModel):
    model_config = ConfigDict(extra="forbid")

    spec_id: str
    user_idea: str = ""
    asset_class: str
    symbols: list[str]
    timeframe: str
    data_source: str = "yfinance"
    strategy_type: str
    market_hypothesis: str
    entry_conditions: list[str]
    exit_conditions: list[str]
    target_return: float = Field(ge=0.0, le=5.0)
    max_drawdown: float = Field(ge=0.0, le=1.0)
    sizing_model: SizingModel
    leverage_constraints: LeverageConstraints
    risk_controls: RiskControls
    regime_contract: RegimeContract
    execution_assumptions: ExecutionAssumptions
    indicator_dependencies: list[str] = Field(default_factory=list)
    backtest_start: str
    backtest_end: str
    lineage: StrategyLineage

    @field_validator("symbols", "entry_conditions", "exit_conditions")
    @classmethod
    def _non_empty_list(cls, value: list[str]) -> list[str]:
        if not value:
            raise ValueError("must not be empty")
        return value


class StrategyMetadata(BaseModel):
    model_config = ConfigDict(extra="forbid")

    strategy_id: str
    spec_id: str
    strategy_type: str
    strategy_class_name: str
    generated_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    code_hash: str
    spec_hash: str
    parameters: dict[str, Any]
    parameter_bounds: dict[str, tuple[float, float]]
    entry_logic: list[str]
    exit_logic: list[str]
    sizing_model: SizingModel
    leverage_constraints: LeverageConstraints
    risk_controls: RiskControls
    regime_contract: RegimeContract
    execution_assumptions: ExecutionAssumptions
    indicator_dependencies: list[str]
    lineage: StrategyLineage
