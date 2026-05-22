"""Parameter proposer — uses LLM to propose specific parameter adjustments."""

import json
import uuid
from dataclasses import dataclass, field, asdict
from datetime import datetime, timezone
from typing import Any

from astra.llm.provider import LLMProvider
from astra.planner.spec import StrategySpec
from astra.builder.generator import BuildResult
from astra.optimizer.diagnosis import Diagnosis

_SYSTEM_PROMPT = """You are ASTRA's parameter optimization engine. You receive a trading strategy diagnosis and current parameters, and you propose specific adjustments to improve performance.

Rules you must follow:
- Only propose parameters that exist in current_parameters
- All proposed values must be within parameter_bounds
- Never propose more than 3 parameter changes per cycle — changing too many parameters at once makes it impossible to know what worked
- Explain the reasoning for each change in plain English
- If diagnosis is REGIME_SHIFT or SIGNAL_DECAY, recommend REBUILD_STRATEGY instead of parameter adjustment
- If this is cycle 3+ and Sharpe has not improved, recommend ABANDON with honest explanation
- Do not claim the changes will definitely improve performance

Respond ONLY with JSON:
{
  "action": "ADJUST_PARAMETERS" | "REBUILD_STRATEGY" | "EXTEND_OBSERVATION" | "ABANDON",
  "parameter_changes": {
    "param_name": new_value
  },
  "reasoning": {
    "param_name": "plain English explanation of why this change"
  },
  "summary": "2-3 sentence plain English summary for the user",
  "confidence": 0.0-1.0
}"""


@dataclass
class ParameterProposal:
    proposal_id: str = ""
    cycle_number: int = 0
    action: str = ""
    parameter_changes: dict[str, Any] = field(default_factory=dict)
    reasoning: dict[str, str] = field(default_factory=dict)
    summary: str = ""
    confidence: float = 0.0
    diagnosis: Diagnosis | None = None
    created_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))

    def __post_init__(self) -> None:
        if not self.proposal_id:
            self.proposal_id = str(uuid.uuid4())

    def to_json(self) -> str:
        data = asdict(self)
        data["created_at"] = self.created_at.isoformat()
        if self.diagnosis is not None:
            data["diagnosis"] = asdict(self.diagnosis)
        return json.dumps(data, indent=2, default=str)


class ParameterProposer:
    def __init__(self, llm_provider: LLMProvider):
        self._llm = llm_provider

    def propose(
        self,
        spec: StrategySpec,
        build_result: BuildResult,
        diagnosis: Diagnosis,
        current_parameters: dict[str, Any],
        parameter_bounds: dict[str, tuple[float, float]],
        cycle_history: list[dict[str, Any]] | None = None,
    ) -> ParameterProposal:
        if diagnosis.recommended_action == "EXTEND_OBSERVATION":
            return ParameterProposal(
                cycle_number=len(cycle_history or []) + 1,
                action="EXTEND_OBSERVATION",
                parameter_changes={},
                reasoning={},
                summary=diagnosis.plain_english_summary,
                confidence=0.9,
                diagnosis=diagnosis,
            )

        if diagnosis.recommended_action == "REBUILD_STRATEGY":
            return ParameterProposal(
                cycle_number=len(cycle_history or []) + 1,
                action="REBUILD_STRATEGY",
                parameter_changes={},
                reasoning={},
                summary=diagnosis.plain_english_summary,
                confidence=0.85,
                diagnosis=diagnosis,
            )

        if diagnosis.recommended_action == "ABANDON":
            return ParameterProposal(
                cycle_number=len(cycle_history or []) + 1,
                action="ABANDON",
                parameter_changes={},
                reasoning={},
                summary=diagnosis.plain_english_summary,
                confidence=0.95,
                diagnosis=diagnosis,
            )

        prompt = self._build_prompt(
            spec, diagnosis, current_parameters, parameter_bounds, cycle_history or []
        )

        try:
            text = self._llm.generate(
                messages=[{"role": "user", "content": prompt}],
                system_prompt=_SYSTEM_PROMPT,
                max_tokens=2048,
            ).strip()

            if text.startswith("```"):
                text = text.strip("`").strip()
                if text.startswith("json"):
                    text = text[4:].strip()

            data = json.loads(text)
            return ParameterProposal(
                cycle_number=len(cycle_history or []) + 1,
                action=data.get("action", "ADJUST_PARAMETERS"),
                parameter_changes=data.get("parameter_changes", {}),
                reasoning=data.get("reasoning", {}),
                summary=data.get("summary", ""),
                confidence=float(data.get("confidence", 0.5)),
                diagnosis=diagnosis,
            )
        except Exception as e:
            return ParameterProposal(
                cycle_number=len(cycle_history or []) + 1,
                action="EXTEND_OBSERVATION",
                parameter_changes={},
                reasoning={},
                summary=f"Parameter proposal failed: {e}. Continuing observation.",
                confidence=0.3,
                diagnosis=diagnosis,
            )

    @staticmethod
    def _build_prompt(
        spec: StrategySpec,
        diagnosis: Diagnosis,
        current_parameters: dict[str, Any],
        parameter_bounds: dict[str, tuple[float, float]],
        cycle_history: list[dict[str, Any]],
    ) -> str:
        lines = [
            "## Strategy",
            f"Type: {spec.strategy_type}",
            f"Market hypothesis: {spec.market_hypothesis}",
            f"Timeframe: {spec.timeframe}",
            "",
            "## Diagnosis",
            f"Primary: {diagnosis.primary_diagnosis}",
            f"Confidence: {diagnosis.confidence}",
            f"Recommended action: {diagnosis.recommended_action}",
            "",
            "## Evidence",
        ]
        for e in diagnosis.evidence:
            lines.append(f"- {e}")

        lines.extend([
            "",
            "## Current Parameters",
        ])
        for k, v in current_parameters.items():
            bounds = parameter_bounds.get(k, (0, 0))
            lines.append(f"- {k}: {v} (allowed range: {bounds[0]} to {bounds[1]})")

        lines.extend([
            "",
            "## Cycle History",
        ])
        if cycle_history:
            for c in cycle_history:
                lines.append(f"- Cycle {c.get('cycle', '?')}: Sharpe={c.get('sharpe', 'N/A')}, "
                           f"Params={c.get('parameters', {})}")
        else:
            lines.append("- No prior cycles.")

        return "\n".join(lines)
