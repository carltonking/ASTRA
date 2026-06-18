"""Strategy specification dataclass — the output of every planning session."""

import json
import uuid
from dataclasses import dataclass, field, asdict
from datetime import datetime, timezone
from typing import Any


_REQUIRED_FIELDS = [
    "asset_class",
    "symbols",
    "timeframe",
    "data_source",
    "strategy_type",
    "market_hypothesis",
    "entry_conditions",
    "exit_conditions",
    "target_return",
    "max_drawdown",
    "position_size",
    "max_positions",
    "backtest_start",
    "backtest_end",
]


@dataclass
class StrategySpec:
    spec_id: str = ""
    created_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
    user_idea: str = ""

    asset_class: str = ""
    symbols: list[str] = field(default_factory=list)
    timeframe: str = ""
    data_source: str = "yfinance"

    strategy_type: str = ""
    market_hypothesis: str = ""
    entry_conditions: list[str] = field(default_factory=list)
    exit_conditions: list[str] = field(default_factory=list)

    target_return: float = 0.0
    max_drawdown: float = 0.0
    position_size: float = 0.0
    max_positions: int = 0
    stop_loss: float | None = None
    take_profit: float | None = None
    transaction_cost: float = 0.001
    sizing_model: dict[str, Any] = field(default_factory=dict)
    leverage_constraints: dict[str, Any] = field(default_factory=dict)
    risk_controls: dict[str, Any] = field(default_factory=dict)
    regime_assumptions: list[str] = field(default_factory=list)
    allowed_regimes: dict[str, list[str]] = field(default_factory=dict)
    prohibited_regimes: dict[str, list[str]] = field(default_factory=dict)
    min_regime_confidence: float = 0.70
    execution_assumptions: dict[str, Any] = field(default_factory=dict)
    indicator_dependencies: list[str] = field(default_factory=list)
    parent_strategy_id: str | None = None
    mutation_source: str | None = None
    generation_number: int = 0
    prompt_ancestry: list[str] = field(default_factory=list)
    validation_scores: dict[str, float] = field(default_factory=dict)
    failure_reasons: list[str] = field(default_factory=list)

    backtest_start: str = ""
    backtest_end: str = ""

    is_complete: bool = False
    missing_fields: list[str] = field(default_factory=list)
    confidence_score: float = 0.0

    def __post_init__(self) -> None:
        if not self.spec_id:
            self.spec_id = str(uuid.uuid4())
        if not self.sizing_model:
            self.sizing_model = {
                "type": "fixed_fraction",
                "max_position_size": self.position_size,
            }
        if not self.leverage_constraints:
            self.leverage_constraints = {
                "max_gross_leverage": 1.0,
                "allow_margin": False,
                "allow_short": False,
            }
        if not self.risk_controls:
            self.risk_controls = {
                "stop_loss": self.stop_loss,
                "take_profit": self.take_profit,
                "max_positions": self.max_positions,
                "max_drawdown": self.max_drawdown,
            }
        if not self.execution_assumptions:
            self.execution_assumptions = {
                "order_type": "market_on_next_bar",
                "transaction_cost": self.transaction_cost,
                "slippage_bps": 5,
                "paper_trading_only": True,
            }
        self._refresh_completeness()

    def _refresh_completeness(self) -> None:
        missing = []
        for field_name in _REQUIRED_FIELDS:
            val = getattr(self, field_name)
            if val is None or val == "" or (isinstance(val, list) and len(val) == 0) or (isinstance(val, (int, float)) and val == 0):
                missing.append(field_name)
        self.missing_fields = missing
        self.is_complete = len(missing) == 0

    def to_json(self) -> str:
        data = asdict(self)
        data["created_at"] = self.created_at.isoformat()
        return json.dumps(data, indent=2, default=str)

    @classmethod
    def from_json(cls, json_str: str) -> "StrategySpec":
        data = json.loads(json_str)
        if "created_at" in data and isinstance(data["created_at"], str):
            data["created_at"] = datetime.fromisoformat(data["created_at"])
        spec = cls(**data)
        return spec
