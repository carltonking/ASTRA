"""Strategy specification dataclass — the output of every planning session."""

import json
import uuid
from dataclasses import dataclass, field, asdict
from datetime import datetime, timezone


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

    backtest_start: str = ""
    backtest_end: str = ""

    is_complete: bool = False
    missing_fields: list[str] = field(default_factory=list)
    confidence_score: float = 0.0

    def __post_init__(self) -> None:
        if not self.spec_id:
            self.spec_id = str(uuid.uuid4())
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
