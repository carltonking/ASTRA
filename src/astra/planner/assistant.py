"""AstraAssistant — one unified finance assistant chat.

Supersedes PlannerConversation for the UI: answers open-ended finance questions,
researches which of ASTRA's algorithm templates fit the user's constraints (backed by
live tools — data, backtests, memory), and builds a strategy only when the user
explicitly confirms (via the build_strategy tool, not a brittle text signal).

Backward-compatible with the backend contract: exposes start()/reply()/is_complete()/
.spec/get_history()/save_session(). Build fires when is_complete() flips True.
"""

import json
import os
import time
from typing import Any

from astra.llm.provider import LLMProvider
from astra.llm.tools import ToolSpec, ToolResult
from astra.planner.spec import StrategySpec

SYSTEM_PROMPT = """You are ASTRA, a unified quantitative-finance assistant. You operate in ONE chat that serves three roles, fluidly, based on what the user needs:

1. ANSWER finance questions clearly and accurately — markets, instruments, risk, backtesting concepts, strategy design trade-offs. Be direct; the user is technically literate. Do not give personalized investment advice or guarantee performance.

2. RECOMMEND which of ASTRA's eight algorithm templates best fits the user's goal and constraints:
   - trend_following  (moving-average crossover; rides sustained directional moves)
   - mean_reversion   (RSI extremes; fades short-term overextensions)
   - momentum         (lookback-return persistence; buys recent strength)
   - pairs            (ratio z-score on two legs; relative-value)
   - breakout         (range breakout with volume confirmation)
   - dca              (scheduled dollar-cost averaging; passive accumulation)
   - stat_arb         (hedge-ratio spread mean reversion across two legs)
   - vwap_momentum    (VWAP-anchored volume-weighted momentum)
   Back every recommendation with EVIDENCE from tools, not vibes. Use list_algorithms to ground the catalog, get_market_data for a symbol's recent behaviour, quick_backtest to compare candidate algorithms on the user's symbols, and search_memory for how similar strategies fared in past validations. Prefer one good tool call over guessing. When a user gives constraints (e.g. low drawdown, swing horizon, a specific symbol), run quick backtests on 2-3 plausible algorithms and recommend based on the numbers.

3. BUILD a strategy ONLY when the user EXPLICITLY confirms (e.g. "build it", "go ahead", "yes build that one"). To build, call the build_strategy tool with a complete, validated spec. NEVER call build_strategy speculatively or to illustrate — it triggers a real build-and-backtest pipeline. Before building, make sure you have: asset class, symbol(s), timeframe, data source (yfinance or lseg), the chosen template (one of the eight), a falsifiable market hypothesis, entry and exit conditions, target return (as a fraction, e.g. 0.15), max drawdown (fraction), position size (fraction), max positions, and a backtest window (YYYY-MM-DD). If anything is missing or unrealistic, ask first.

Behavioral rules:
- Push back on unrealistic expectations (e.g. "50% returns, no drawdown") and explain why.
- Flag inherently untestable ideas (e.g. "buy when the news is good") early.
- Keep answers concise. Use tools instead of speculating about live data or past results.
- Everything is research / paper trading only."""


class AstraAssistant:
    def __init__(self, llm_provider: LLMProvider):
        self._llm = llm_provider
        self._messages: list[dict[str, Any]] = []
        self._spec: StrategySpec | None = None
        self._max_iters = int(os.environ.get("ASTRA_ASSISTANT_MAX_TOOL_ITERS", "8"))
        self._turn_budget_s = float(os.environ.get("ASTRA_ASSISTANT_TURN_BUDGET_S", "90"))

    # --- Backend-compatible contract ---

    def start(self, user_message: str, dispatcher: Any = None) -> str:
        self._messages.append({"role": "user", "content": user_message})
        return self._respond(dispatcher)

    def reply(self, user_message: str, dispatcher: Any = None) -> str:
        self._messages.append({"role": "user", "content": user_message})
        return self._respond(dispatcher)

    def is_complete(self) -> bool:
        return self._spec is not None

    @property
    def spec(self) -> StrategySpec | None:
        return self._spec

    def get_spec(self) -> StrategySpec | None:
        return self._spec

    def get_history(self) -> list[dict[str, Any]]:
        return list(self._messages)

    def save_session(self, path: str) -> None:
        data: dict[str, Any] = {
            "spec": json.loads(self._spec.to_json()) if self._spec else None,
            "messages": self._messages,
        }
        with open(path, "w") as f:
            json.dump(data, f, indent=2, default=str)

    # --- Internals ---

    def _respond(self, dispatcher: Any) -> str:
        # Degrade gracefully if tools are unavailable (provider or dispatcher missing).
        if dispatcher is None or not self._llm.supports_tools():
            text = self._llm.generate(
                messages=self._messages[:],
                system_prompt=SYSTEM_PROMPT,
                max_tokens=4096,
            )
            self._messages.append({"role": "assistant", "content": text})
            return text
        return self._run_tool_loop(dispatcher)

    def _run_tool_loop(self, dispatcher: Any) -> str:
        tool_specs = [ToolSpec(**s) for s in dispatcher.schemas()]
        deadline = time.monotonic() + self._turn_budget_s

        for _ in range(self._max_iters):
            result = self._llm.generate_with_tools(
                messages=self._messages[:],
                tools=tool_specs,
                system_prompt=SYSTEM_PROMPT,
                max_tokens=4096,
            )
            if result.raw_assistant_message is not None:
                self._messages.append(result.raw_assistant_message)

            if not result.wants_tools:
                return result.text or self._empty_fallback()

            tool_results: list[ToolResult] = []
            for call in result.tool_calls:
                if call.parse_error:
                    content = json.dumps({"error": call.parse_error})
                else:
                    content = dispatcher.dispatch(call.name, call.arguments)
                tool_results.append(
                    ToolResult(call_id=call.id, content=content, is_error='"error"' in content)
                )
            self._messages.extend(self._llm.format_tool_results(tool_results))

            # A confirmed build_strategy call records intent on the context.
            if dispatcher.ctx.build_intent is not None and self._spec is None:
                self._spec = dispatcher.ctx.build_intent

            if time.monotonic() > deadline:
                return self._forced_fallback(dispatcher, tool_specs)

        return self._forced_fallback(dispatcher, tool_specs)

    def _forced_fallback(self, dispatcher: Any, tool_specs: list[ToolSpec]) -> str:
        """Tool budget exhausted — ask the model for a final answer with no more tools."""
        try:
            text = self._llm.generate(
                messages=self._messages[:],
                system_prompt=SYSTEM_PROMPT + "\n\nWrap up now with a final answer; do not call tools.",
                max_tokens=2048,
            )
        except Exception:
            text = ""
        text = text or "I gathered some results but ran long on this turn — could you narrow the question?"
        self._messages.append({"role": "assistant", "content": text})
        return text

    def _empty_fallback(self) -> str:
        return "Could you rephrase or add a bit more detail? I didn't produce a response."
