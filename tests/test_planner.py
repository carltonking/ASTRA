"""Tests for the ASTRA conversational strategy planner."""

import json
import uuid
from datetime import datetime, timezone, timedelta
from unittest.mock import MagicMock, patch

import pytest

from astra.planner import StrategySpec, PlannerConversation, SpecValidator, ValidationResult


# ---------------------------------------------------------------------------
# StrategySpec serialization / deserialization
# ---------------------------------------------------------------------------


class TestStrategySpec:
    def test_serialize_deserialize_roundtrip(self):
        spec = StrategySpec(
            spec_id=str(uuid.uuid4()),
            created_at=datetime(2025, 1, 15, 12, 0, 0, tzinfo=timezone.utc),
            user_idea="Mean reversion on SPY",
            asset_class="equity",
            symbols=["SPY"],
            timeframe="daily",
            data_source="yfinance",
            strategy_type="mean_reversion",
            market_hypothesis="SPY exhibits mean reversion at 2-standard-deviation extremes over 5-day windows",
            entry_conditions=["RSI(14) < 30"],
            exit_conditions=["RSI(14) > 70"],
            target_return=0.12,
            max_drawdown=0.15,
            position_size=0.05,
            max_positions=4,
            backtest_start="2018-01-01",
            backtest_end="2023-12-31",
        )
        json_str = spec.to_json()
        restored = StrategySpec.from_json(json_str)
        assert restored.spec_id == spec.spec_id
        assert restored.created_at == spec.created_at
        assert restored.user_idea == spec.user_idea
        assert restored.asset_class == spec.asset_class
        assert restored.symbols == spec.symbols
        assert restored.target_return == spec.target_return

    def test_is_complete_false_when_fields_missing(self):
        spec = StrategySpec()
        assert spec.is_complete is False
        assert len(spec.missing_fields) > 0
        assert "asset_class" in spec.missing_fields

    def test_is_complete_true_when_all_fields_present(self):
        spec = StrategySpec(
            asset_class="equity",
            symbols=["SPY"],
            timeframe="daily",
            data_source="yfinance",
            strategy_type="momentum",
            market_hypothesis="Stocks with strong relative momentum over 6 months continue to outperform",
            entry_conditions=["Close > 200-day SMA", "Volume > 1.5x average"],
            exit_conditions=["Close < 50-day SMA"],
            target_return=0.15,
            max_drawdown=0.20,
            position_size=0.10,
            max_positions=10,
            backtest_start="2015-01-01",
            backtest_end="2023-12-31",
        )
        assert spec.is_complete is True
        assert spec.missing_fields == []

    def test_auto_generates_uuid(self):
        spec = StrategySpec()
        assert spec.spec_id != ""
        uuid.UUID(spec.spec_id)

    def test_created_at_defaults_to_utc(self):
        before = datetime.now(timezone.utc) - timedelta(seconds=1)
        spec = StrategySpec()
        after = datetime.now(timezone.utc) + timedelta(seconds=1)
        assert before <= spec.created_at <= after


# ---------------------------------------------------------------------------
# PlannerConversation with mocked Anthropic API
# ---------------------------------------------------------------------------


def _make_mock_response(text: str):
    """Build a mock Anthropic messages response with the given text."""
    content_block = MagicMock()
    content_block.text = text
    response = MagicMock()
    response.content = [content_block]
    return response


class TestPlannerConversation:
    def test_initializes_with_api_key(self):
        conv = PlannerConversation(anthropic_api_key="test-key-123")
        assert conv.is_complete() is False
        assert conv.get_spec() is None
        assert conv.rejected is False

    @patch("astra.planner.conversation.Anthropic")
    def test_start_returns_claude_response(self, MockAnthropic):
        mock_client = MagicMock()
        MockAnthropic.return_value = mock_client
        mock_client.messages.create.return_value = _make_mock_response(
            "Great idea! Let me ask about your timeframe. Are you thinking day trading, swing trading, or long-term position trading?"
        )

        conv = PlannerConversation(anthropic_api_key="test-key")
        reply = conv.start("I want to trade momentum on QQQ")

        assert "timeframe" in reply.lower()
        assert conv.is_complete() is False
        assert conv.get_spec() is None
        assert len(conv.get_history()) == 2

    @patch("astra.planner.conversation.Anthropic")
    def test_detects_spec_ready_signal(self, MockAnthropic):
        mock_client = MagicMock()
        MockAnthropic.return_value = mock_client

        spec_json = json.dumps({
            "asset_class": "equity",
            "symbols": ["QQQ"],
            "timeframe": "daily",
            "data_source": "yfinance",
            "strategy_type": "momentum",
            "market_hypothesis": "QQQ exhibits strong momentum persistence over 3-6 month periods driven by tech sector concentration",
            "entry_conditions": ["Close > 200-day SMA", "50-day SMA > 200-day SMA"],
            "exit_conditions": ["Close < 50-day SMA"],
            "target_return": 0.15,
            "max_drawdown": 0.20,
            "position_size": 0.10,
            "max_positions": 5,
            "backtest_start": "2015-01-01",
            "backtest_end": "2023-12-31",
        })
        mock_client.messages.create.return_value = _make_mock_response(
            f"I have enough information. Here is the complete spec.\n\nSPEC_READY:\n{spec_json}"
        )

        conv = PlannerConversation(anthropic_api_key="test-key")
        reply = conv.start("I want to trade momentum on QQQ")

        assert conv.is_complete() is True
        assert conv.get_spec() is not None
        assert conv.get_spec().strategy_type == "momentum"
        assert conv.get_spec().symbols == ["QQQ"]

    @patch("astra.planner.conversation.Anthropic")
    def test_detects_spec_rejected_signal(self, MockAnthropic):
        mock_client = MagicMock()
        MockAnthropic.return_value = mock_client
        mock_client.messages.create.return_value = _make_mock_response(
            "SPEC_REJECTED: Your idea relies on interpreting real-time news headlines, which is not suitable for systematic backtesting as it cannot be expressed as deterministic rules."
        )

        conv = PlannerConversation(anthropic_api_key="test-key")
        reply = conv.start("Buy when the news is good and sell when it's bad")

        assert conv.is_complete() is True
        assert conv.get_spec() is None
        assert conv.rejected is True
        assert "not suitable" in conv.rejection_reason

    @patch("astra.planner.conversation.Anthropic")
    def test_detects_spec_ready_with_code_block(self, MockAnthropic):
        mock_client = MagicMock()
        MockAnthropic.return_value = mock_client

        spec_json = json.dumps({
            "asset_class": "crypto",
            "symbols": ["BTC/USD"],
            "timeframe": "hourly",
            "data_source": "yfinance",
            "strategy_type": "trend_following",
            "market_hypothesis": "Bitcoin exhibits strong trending behavior on hourly timescales with low autocorrelation of returns",
            "entry_conditions": ["Close > 50-period EMA", "MACD line > signal line"],
            "exit_conditions": ["Close < 50-period EMA"],
            "target_return": 0.30,
            "max_drawdown": 0.35,
            "position_size": 0.02,
            "max_positions": 3,
            "backtest_start": "2020-01-01",
            "backtest_end": "2023-12-31",
        })
        mock_client.messages.create.return_value = _make_mock_response(
            f"Here you go:\n\nSPEC_READY:\n```json\n{spec_json}\n```"
        )

        conv = PlannerConversation(anthropic_api_key="test-key")
        reply = conv.start("Trade bitcoin trends")

        assert conv.is_complete() is True
        assert conv.get_spec() is not None
        assert conv.get_spec().strategy_type == "trend_following"
        assert conv.get_spec().symbols == ["BTC/USD"]

    @patch("astra.planner.conversation.Anthropic")
    def test_reply_maintains_history(self, MockAnthropic):
        mock_client = MagicMock()
        MockAnthropic.return_value = mock_client

        mock_client.messages.create.side_effect = [
            _make_mock_response("What timeframe are you thinking?"),
            _make_mock_response("Great, daily is good. What is your core hypothesis?"),
        ]

        conv = PlannerConversation(anthropic_api_key="test-key")
        conv.start("Momentum on SPY")
        conv.reply("Daily timeframe")

        history = conv.get_history()
        assert len(history) == 4
        assert history[0]["role"] == "user"
        assert history[1]["role"] == "assistant"
        assert history[2]["role"] == "user"
        assert history[3]["role"] == "assistant"

    @patch("astra.planner.conversation.Anthropic")
    def test_save_session_writes_json(self, MockAnthropic, tmp_path):
        mock_client = MagicMock()
        MockAnthropic.return_value = mock_client

        spec_json = json.dumps({
            "asset_class": "equity",
            "symbols": ["SPY"],
            "timeframe": "daily",
            "data_source": "yfinance",
            "strategy_type": "trend_following",
            "market_hypothesis": "SPY trends persist across multiple timeframes due to institutional flow",
            "entry_conditions": ["Close > 200-day SMA"],
            "exit_conditions": ["Close < 50-day SMA"],
            "target_return": 0.12,
            "max_drawdown": 0.18,
            "position_size": 0.10,
            "max_positions": 5,
            "backtest_start": "2018-01-01",
            "backtest_end": "2023-12-31",
        })
        mock_client.messages.create.return_value = _make_mock_response(
            f"SPEC_READY:\n{spec_json}"
        )

        conv = PlannerConversation(anthropic_api_key="test-key")
        conv.start("Trend following on SPY")

        session_path = tmp_path / "session.json"
        conv.save_session(str(session_path))

        assert session_path.exists()
        with open(session_path) as f:
            data = json.load(f)
        assert data["spec"]["strategy_type"] == "trend_following"
        assert data["rejected"] is False


# ---------------------------------------------------------------------------
# SpecValidator
# ---------------------------------------------------------------------------


class TestSpecValidator:
    def test_passes_valid_spec(self):
        spec = StrategySpec(
            asset_class="equity",
            symbols=["SPY", "QQQ"],
            timeframe="daily",
            data_source="yfinance",
            strategy_type="momentum",
            market_hypothesis="Cross-sectional momentum across US large-cap equities generates persistent excess returns over 6-12 month holding periods",
            entry_conditions=["Close > 200-day SMA", "6-month return > top quartile"],
            exit_conditions=["Close < 50-day SMA"],
            target_return=0.15,
            max_drawdown=0.20,
            position_size=0.05,
            max_positions=10,
            backtest_start="2010-01-01",
            backtest_end="2023-12-31",
        )
        result = SpecValidator.validate(spec)
        assert result.is_valid is True
        assert len(result.errors) == 0

    def test_position_sizing_error(self):
        spec = StrategySpec(
            asset_class="equity",
            symbols=["SPY"],
            timeframe="daily",
            data_source="yfinance",
            strategy_type="momentum",
            market_hypothesis="Test hypothesis for position sizing error validation purposes only",
            entry_conditions=["Test entry"],
            exit_conditions=["Test exit"],
            target_return=0.10,
            max_drawdown=0.20,
            position_size=0.30,
            max_positions=10,
            backtest_start="2020-01-01",
            backtest_end="2023-12-31",
        )
        result = SpecValidator.validate(spec)
        assert result.is_valid is False
        assert any("exceeds 100%" in e for e in result.errors)

    def test_warns_on_unrealistic_return(self):
        spec = StrategySpec(
            asset_class="equity",
            symbols=["SPY"],
            timeframe="daily",
            data_source="yfinance",
            strategy_type="momentum",
            market_hypothesis="Test hypothesis for unrealistic return warning validation purposes to check validator",
            entry_conditions=["Test entry"],
            exit_conditions=["Test exit"],
            target_return=0.60,
            max_drawdown=0.20,
            position_size=0.05,
            max_positions=4,
            backtest_start="2020-01-01",
            backtest_end="2023-12-31",
        )
        result = SpecValidator.validate(spec)
        assert result.is_valid is True
        assert any("50%" in w for w in result.warnings)

    def test_warns_on_short_backtest(self):
        spec = StrategySpec(
            asset_class="equity",
            symbols=["SPY"],
            timeframe="daily",
            data_source="yfinance",
            strategy_type="momentum",
            market_hypothesis="This is a test hypothesis for short backtest warning validation purposes",
            entry_conditions=["Test entry"],
            exit_conditions=["Test exit"],
            target_return=0.10,
            max_drawdown=0.20,
            position_size=0.05,
            max_positions=4,
            backtest_start="2023-01-01",
            backtest_end="2023-12-31",
        )
        result = SpecValidator.validate(spec)
        assert result.is_valid is True
        assert any("2 years" in w for w in result.warnings)

    def test_hypothesis_too_short_error(self):
        spec = StrategySpec(
            asset_class="equity",
            symbols=["SPY"],
            timeframe="daily",
            data_source="yfinance",
            strategy_type="momentum",
            market_hypothesis="Buy low",
            entry_conditions=["RSI < 30"],
            exit_conditions=["RSI > 70"],
            target_return=0.10,
            max_drawdown=0.20,
            position_size=0.05,
            max_positions=4,
            backtest_start="2020-01-01",
            backtest_end="2023-12-31",
        )
        result = SpecValidator.validate(spec)
        assert result.is_valid is False
        assert any("hypothesis" in e.lower() for e in result.errors)

    def test_empty_hypothesis_error(self):
        spec = StrategySpec(
            asset_class="equity",
            symbols=["SPY"],
            timeframe="daily",
            data_source="yfinance",
            strategy_type="momentum",
            market_hypothesis="",
            entry_conditions=["RSI < 30"],
            exit_conditions=["RSI > 70"],
            target_return=0.10,
            max_drawdown=0.20,
            position_size=0.05,
            max_positions=4,
            backtest_start="2020-01-01",
            backtest_end="2023-12-31",
        )
        result = SpecValidator.validate(spec)
        assert result.is_valid is False
        assert any("hypothesis" in e.lower() for e in result.errors)

    def test_warns_on_long_backtest(self):
        spec = StrategySpec(
            asset_class="equity",
            symbols=["SPY"],
            timeframe="daily",
            data_source="yfinance",
            strategy_type="momentum",
            market_hypothesis="This is a test hypothesis for long backtest warning validation purposes",
            entry_conditions=["Test entry"],
            exit_conditions=["Test exit"],
            target_return=0.10,
            max_drawdown=0.20,
            position_size=0.05,
            max_positions=4,
            backtest_start="2000-01-01",
            backtest_end="2023-12-31",
        )
        result = SpecValidator.validate(spec)
        assert result.is_valid is True
        assert any("before 2005" in w for w in result.warnings)

    def test_validator_returns_validation_result_type(self):
        spec = StrategySpec(
            asset_class="equity",
            symbols=["SPY"],
            timeframe="daily",
            data_source="yfinance",
            strategy_type="momentum",
            market_hypothesis="This is a sufficiently long hypothesis to pass the minimum word count requirement",
            entry_conditions=["Test entry"],
            exit_conditions=["Test exit"],
            target_return=0.10,
            max_drawdown=0.20,
            position_size=0.05,
            max_positions=4,
            backtest_start="2020-01-01",
            backtest_end="2023-12-31",
        )
        result = SpecValidator.validate(spec)
        assert isinstance(result, ValidationResult)
