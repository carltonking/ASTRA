"""Tests for AstraAssistant — the unified finance assistant with tool calling."""

from astra.llm.provider import LLMProvider
from astra.llm.tools import ToolCall, ToolResult, ToolCallResult
from astra.planner.assistant import AstraAssistant
from astra.planner.spec import StrategySpec


class ScriptedProvider(LLMProvider):
    """A provider whose generate_with_tools returns scripted ToolCallResults in order."""

    def __init__(self, results: list[ToolCallResult]):
        self._results = list(results)
        self.calls = 0

    def generate(self, messages, system_prompt=None, max_tokens=2048, temperature=0.7):
        return "plain text"

    def supports_tools(self) -> bool:
        return True

    def generate_with_tools(self, messages, tools, system_prompt=None, max_tokens=2048, temperature=0.7, tool_choice="auto"):
        self.calls += 1
        return self._results.pop(0)

    def format_tool_results(self, results):
        return [{"role": "tool", "tool_call_id": r.call_id, "content": r.content} for r in results]


class FakeContext:
    def __init__(self):
        self.build_intent = None


class FakeDispatcher:
    """Records dispatched calls; build_strategy sets build_intent on the context."""

    def __init__(self, spec_for_build: StrategySpec | None = None):
        self.ctx = FakeContext()
        self.dispatched: list[tuple[str, dict]] = []
        self._spec_for_build = spec_for_build

    def schemas(self):
        return [{"name": "quick_backtest", "description": "x", "input_schema": {"type": "object", "properties": {}}}]

    def dispatch(self, name, arguments):
        self.dispatched.append((name, arguments))
        if name == "build_strategy" and self._spec_for_build is not None:
            self.ctx.build_intent = self._spec_for_build
            return '{"status": "build_queued"}'
        return '{"sharpe": 0.8}'


def _text(t):
    return ToolCallResult(text=t, raw_assistant_message={"role": "assistant", "content": t})


def _calls(calls):
    return ToolCallResult(
        text=None,
        tool_calls=calls,
        raw_assistant_message={"role": "assistant", "content": "", "tool_calls": []},
    )


def test_plain_text_turn():
    p = ScriptedProvider([_text("Sharpe measures risk-adjusted return.")])
    a = AstraAssistant(p)
    out = a.start("what is sharpe?", FakeDispatcher())
    assert "Sharpe" in out
    assert a.is_complete() is False
    assert p.calls == 1


def test_tool_call_then_final_text():
    p = ScriptedProvider([
        _calls([ToolCall(id="c1", name="quick_backtest", arguments={"algorithm": "momentum"})]),
        _text("Momentum had a Sharpe of 0.8."),
    ])
    disp = FakeDispatcher()
    a = AstraAssistant(p)
    out = a.reply("backtest momentum", disp)
    assert "0.8" in out
    assert disp.dispatched == [("quick_backtest", {"algorithm": "momentum"})]
    assert a.is_complete() is False


def test_build_strategy_sets_spec():
    spec = StrategySpec(
        asset_class="equity", symbols=["SPY"], timeframe="daily", data_source="yfinance",
        strategy_type="momentum", market_hypothesis="trends persist",
        entry_conditions=["x"], exit_conditions=["y"], target_return=0.15, max_drawdown=0.2,
        position_size=0.1, max_positions=5, backtest_start="2020-01-01", backtest_end="2024-01-01",
    )
    assert spec.is_complete
    p = ScriptedProvider([
        _calls([ToolCall(id="b1", name="build_strategy", arguments={})]),
        _text("Building it now."),
    ])
    disp = FakeDispatcher(spec_for_build=spec)
    a = AstraAssistant(p)
    out = a.reply("build it", disp)
    assert a.is_complete() is True
    assert a.spec is spec
    assert "Building" in out


def test_malformed_args_become_error_result():
    bad = ToolCall(id="c1", name="quick_backtest", arguments={}, parse_error="invalid JSON arguments")
    p = ScriptedProvider([_calls([bad]), _text("Recovered.")])
    disp = FakeDispatcher()
    a = AstraAssistant(p)
    out = a.reply("oops", disp)
    # dispatcher must NOT have been called for a parse-error tool call
    assert disp.dispatched == []
    assert "Recovered" in out


def test_text_only_fallback_without_tool_support():
    class NoTools(LLMProvider):
        def generate(self, messages, system_prompt=None, max_tokens=2048, temperature=0.7):
            return "fallback answer"

    a = AstraAssistant(NoTools())
    out = a.start("hi", dispatcher=None)
    assert out == "fallback answer"
    assert a.is_complete() is False
