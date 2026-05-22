"""Conversational strategy planner — LLM dialogue that produces a StrategySpec."""

import json
from typing import Any

from astra.llm.provider import LLMProvider
from astra.planner.spec import StrategySpec

SYSTEM_PROMPT = """You are ASTRA's strategy planner. Your job is to conduct a focused, intelligent dialogue that extracts everything needed to build a rigorous, testable trading strategy from a user's idea.

Your responsibilities:
- Ask exactly the right questions — not too many, not too few
- Never ask for information you can reasonably infer
- Push back gently when an idea has unrealistic expectations (e.g. "50% annual returns with no drawdown" — explain why that's not how markets work, suggest realistic targets)
- Flag inherently untestable ideas early (e.g. "buy when the news is good")
- Confirm your understanding before finalizing the spec
- Be direct and concise — the user is technically literate

Question sequence (follow this order, skip if already answered):
1. What market / asset class? (if not clear from idea)
2. What timeframe? (day trading, swing, position?)
3. What is the core hypothesis — why should this strategy make money?
4. Entry conditions — what has to be true to open a position?
5. Exit conditions — what triggers closing it? (profit target, stop loss, signal reversal?)
6. Risk tolerance — what annual return are you targeting and what drawdown can you stomach?
7. Data source preference — yfinance (free) or LSEG (professional)?
8. Backtest period — how far back should we test?

When you have enough information to build a complete spec, respond with:
SPEC_READY: <json>
Where <json> is a valid StrategySpec JSON format.

If the user's idea is not suitable for systematic trading (pure discretionary, requires real-time news, illegal strategies, etc.) respond with:
SPEC_REJECTED: <reason>"""


class PlannerConversation:
    def __init__(self, llm_provider: LLMProvider):
        self._llm = llm_provider
        self._messages: list[dict[str, Any]] = []
        self.spec: StrategySpec | None = None
        self.rejected: bool = False
        self.rejection_reason: str = ""

    def start(self, user_idea: str) -> str:
        self._messages.append({"role": "user", "content": user_idea})
        text = self._llm.generate(
            messages=[{"role": "user", "content": user_idea}],
            system_prompt=SYSTEM_PROMPT,
            max_tokens=4096,
        )
        self._messages.append({"role": "assistant", "content": text})
        self._check_signal(text)
        return text

    def reply(self, user_message: str) -> str:
        self._messages.append({"role": "user", "content": user_message})
        text = self._llm.generate(
            messages=self._messages[:],
            system_prompt=SYSTEM_PROMPT,
            max_tokens=4096,
        )
        self._messages.append({"role": "assistant", "content": text})
        self._check_signal(text)
        return text

    def is_complete(self) -> bool:
        return self.spec is not None or self.rejected

    def get_spec(self) -> StrategySpec | None:
        return self.spec

    def get_history(self) -> list[dict[str, Any]]:
        return list(self._messages)

    def save_session(self, path: str) -> None:
        import json as json_mod

        data: dict[str, Any] = {
            "spec": json_mod.loads(self.spec.to_json()) if self.spec else None,
            "rejected": self.rejected,
            "rejection_reason": self.rejection_reason,
            "messages": self._messages,
        }
        with open(path, "w") as f:
            json_mod.dump(data, f, indent=2, default=str)

    def _check_signal(self, text: str) -> None:
        if "SPEC_READY:" in text:
            idx = text.index("SPEC_READY:")
            json_part = text[idx + len("SPEC_READY:"):].strip()
            if json_part.startswith("```"):
                json_part = json_part.strip("`").strip()
                if json_part.startswith("json"):
                    json_part = json_part[4:].strip()
            self.spec = StrategySpec.from_json(json_part)
        elif "SPEC_REJECTED:" in text:
            self.rejected = True
            idx = text.index("SPEC_REJECTED:")
            self.rejection_reason = text[idx + len("SPEC_REJECTED:"):].strip()
