"""Extract memory items from validation and deployment evidence."""

from astra.memory.engine import MemoryItem
from astra.validation.engine import ValidationDecision


class MemoryExtractor:
    def from_validation(
        self,
        strategy_type: str,
        decision: ValidationDecision,
    ) -> list[MemoryItem]:
        items: list[MemoryItem] = []
        for reason in decision.hard_failures + decision.soft_failures:
            layer = "meta" if reason in {"PBO_TOO_HIGH", "SHARPE_INFLATION_DETECTED"} else "strategic"
            items.append(
                MemoryItem(
                    layer=layer,  # type: ignore[arg-type]
                    topic=reason.lower(),
                    claim=f"{strategy_type} produced validation failure {reason}",
                    evidence={
                        "status": decision.status,
                        "robustness_score": decision.robustness_score,
                        "fragility_score": decision.fragility_score,
                        "metrics": decision.metrics,
                    },
                    tags=[strategy_type, reason.lower()],
                    support_count=1,
                    contradiction_count=0,
                    robustness_score=max(0.0, min(1.0, 1.0 - decision.fragility_score / 100.0)),
                )
            )
        if decision.status == "PAPER_CANDIDATE":
            items.append(
                MemoryItem(
                    layer="strategic",
                    topic="robust_archetype",
                    claim=f"{strategy_type} survived validation with robustness {decision.robustness_score}",
                    evidence={"metrics": decision.metrics},
                    tags=[strategy_type, "validated"],
                    support_count=1,
                    robustness_score=min(1.0, decision.robustness_score / 100.0),
                )
            )
        return items
