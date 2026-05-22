"""Tests for the ASTRA algorithm builder."""

import ast
import importlib.util
import json
import os
import uuid
from dataclasses import asdict
from datetime import datetime, timezone
from unittest.mock import MagicMock

import pytest

from astra.llm.provider import LLMProvider
from astra.planner import StrategySpec
from astra.builder import (
    StrategyGenerator,
    BuildResult,
    AuroraConfigWriter,
    BuildSandbox,
    SandboxResult,
    BaseStrategy,
)
from astra.builder.generator import BuildError


def _make_valid_spec(
    strategy_type: str = "trend_following",
    **overrides,
) -> StrategySpec:
    params = dict(
        spec_id=str(uuid.uuid4()),
        user_idea="Test strategy",
        asset_class="equity",
        symbols=["SPY"],
        timeframe="daily",
        data_source="yfinance",
        strategy_type=strategy_type,
        market_hypothesis="Moving average crossovers capture sustained trends in equity markets with low false signal rates",
        entry_conditions=["Fast MA crosses above slow MA"],
        exit_conditions=["Fast MA crosses below slow MA"],
        target_return=0.15,
        max_drawdown=0.20,
        position_size=0.10,
        max_positions=5,
        backtest_start="2018-01-01",
        backtest_end="2023-12-31",
    )
    params.update(overrides)
    return StrategySpec(**params)


# ---------------------------------------------------------------------------
# BuildResult
# ---------------------------------------------------------------------------


class TestBuildResult:
    def test_serializes_via_asdict(self):
        result = BuildResult(
            success=True,
            spec_id="abc-123",
            strategy_file="/tmp/test.py",
            strategy_class_name="TrendFollowingStrategy",
            initial_parameters={"fast_window": 20},
            parameter_bounds={"fast_window": (5, 50)},
            aurora_config_file="/tmp/config.yaml",
            build_log=["step 1", "step 2"],
        )
        d = asdict(result)
        assert d["success"] is True
        assert d["spec_id"] == "abc-123"
        assert d["initial_parameters"] == {"fast_window": 20}
        assert d["build_log"] == ["step 1", "step 2"]

    def test_error_defaults_to_none(self):
        result = BuildResult(success=True)
        assert result.error is None

    def test_failed_build_has_error(self):
        result = BuildResult(success=False, error="Something broke")
        assert result.error == "Something broke"


# ---------------------------------------------------------------------------
# Templates — syntax validation per type
# ---------------------------------------------------------------------------

_TEMPLATE_TYPES = [
    "trend_following",
    "mean_reversion",
    "momentum",
    "pairs",
    "breakout",
    "dca",
]


class TestTemplates:
    @pytest.mark.parametrize("strategy_type", _TEMPLATE_TYPES)
    def test_template_renders_without_syntax_errors(self, strategy_type):
        from astra.builder.templates import TEMPLATES_BY_TYPE, DEFAULT_PARAMETERS_BY_TYPE

        template = TEMPLATES_BY_TYPE[strategy_type]
        params = DEFAULT_PARAMETERS_BY_TYPE[strategy_type]
        code = template.format(hypothesis="Test hypothesis for template validation purposes only", **params)
        tree = ast.parse(code)
        assert tree is not None

    @pytest.mark.parametrize("strategy_type", _TEMPLATE_TYPES)
    def test_template_generates_signal_returns_0_or_1(self, strategy_type):
        from astra.builder.templates import TEMPLATES_BY_TYPE, DEFAULT_PARAMETERS_BY_TYPE, CLASS_NAME_BY_TYPE

        template = TEMPLATES_BY_TYPE[strategy_type]
        params = DEFAULT_PARAMETERS_BY_TYPE[strategy_type]
        code = template.format(hypothesis="Test hypothesis", **params)
        assert ".astype(int)" in code or "0, index=data.index" in code or "0).astype" in code

    @pytest.mark.parametrize("strategy_type", _TEMPLATE_TYPES)
    def test_template_has_sandbox_compatible_imports(self, strategy_type):
        from astra.builder.templates import TEMPLATES_BY_TYPE, DEFAULT_PARAMETERS_BY_TYPE

        template = TEMPLATES_BY_TYPE[strategy_type]
        params = DEFAULT_PARAMETERS_BY_TYPE[strategy_type]
        code = template.format(hypothesis="Test", **params)
        assert "from astra.builder.templates import BaseStrategy" in code
        assert "import pandas as pd" in code

    def test_all_templates_have_bounds_in_init(self):
        from astra.builder.templates import TEMPLATES_BY_TYPE, DEFAULT_PARAMETERS_BY_TYPE

        for type_name, template in TEMPLATES_BY_TYPE.items():
            params = DEFAULT_PARAMETERS_BY_TYPE[type_name]
            code = template.format(hypothesis="Test", **params)
            tree = ast.parse(code)
            has_get_bounds = any(
                isinstance(n, ast.FunctionDef) and n.name == "get_parameter_bounds"
                for n in ast.walk(tree)
            )
            assert has_get_bounds, f"{type_name} template missing get_parameter_bounds"


# ---------------------------------------------------------------------------
# BuildSandbox
# ---------------------------------------------------------------------------


class TestBuildSandbox:
    def test_rejects_network_import(self, tmp_path):
        sandbox = BuildSandbox()
        file_path = tmp_path / "bad_strat.py"
        file_path.write_text("import requests\n")
        result = sandbox.validate(str(file_path))
        assert result.passed is False
        assert any("requests" in v for v in result.violations)

    def test_rejects_eval_call(self, tmp_path):
        sandbox = BuildSandbox()
        file_path = tmp_path / "bad_strat.py"
        file_path.write_text("def f():\n    eval('print(1)')\n")
        result = sandbox.validate(str(file_path))
        assert result.passed is False
        assert any("eval" in v for v in result.violations)

    def test_rejects_exec_call(self, tmp_path):
        sandbox = BuildSandbox()
        file_path = tmp_path / "bad_strat.py"
        file_path.write_text("def f():\n    exec('x = 1')\n")
        result = sandbox.validate(str(file_path))
        assert result.passed is False
        assert any("exec" in v for v in result.violations)

    def test_rejects_short_selling_return_literal(self, tmp_path):
        sandbox = BuildSandbox()
        file_path = tmp_path / "bad_strat.py"
        file_path.write_text("def f():\n    return -1\n")
        result = sandbox.validate(str(file_path))
        assert result.passed is False
        assert any("Short selling" in v for v in result.violations)

    def test_rejects_short_selling_return_unary(self, tmp_path):
        sandbox = BuildSandbox()
        file_path = tmp_path / "bad_strat.py"
        file_path.write_text("def f():\n    x = -1\n    return x\n")
        result = sandbox.validate(str(file_path))
        assert result.passed is False
        assert any("Short selling" in v for v in result.violations)

    def test_rejects_short_selling_conditional(self, tmp_path):
        sandbox = BuildSandbox()
        file_path = tmp_path / "bad_strat.py"
        file_path.write_text("def f():\n    return -1 if condition else 0\n")
        result = sandbox.validate(str(file_path))
        assert result.passed is False
        assert any("Short selling" in v for v in result.violations)

    def test_passes_clean_strategy_code(self, tmp_path):
        from astra.builder.templates import TEMPLATES_BY_TYPE, DEFAULT_PARAMETERS_BY_TYPE

        template = TEMPLATES_BY_TYPE["trend_following"]
        params = DEFAULT_PARAMETERS_BY_TYPE["trend_following"]
        code = template.format(hypothesis="Test", **params)

        sandbox = BuildSandbox()
        file_path = tmp_path / "clean_strat.py"
        file_path.write_text(code)
        result = sandbox.validate(str(file_path))
        assert result.passed is True, f"Unexpected violations: {result.violations}"

    def test_rejects_subprocess_import(self, tmp_path):
        sandbox = BuildSandbox()
        file_path = tmp_path / "bad_strat.py"
        file_path.write_text("import subprocess\n")
        result = sandbox.validate(str(file_path))
        assert result.passed is False
        assert any("subprocess" in v for v in result.violations)

    def test_rejects_syntax_error(self, tmp_path):
        sandbox = BuildSandbox()
        file_path = tmp_path / "bad_strat.py"
        file_path.write_text("def f(:\n    pass\n")
        result = sandbox.validate(str(file_path))
        assert result.passed is False
        assert any("Syntax error" in v for v in result.violations)

    def test_sandbox_result_type(self):
        sr = SandboxResult(passed=True)
        assert isinstance(sr, SandboxResult)
        assert sr.passed is True
        assert sr.violations == []

    def test_sandbox_result_with_violations(self):
        sr = SandboxResult(passed=False, violations=["bad"])
        assert sr.passed is False
        assert "bad" in sr.violations


# ---------------------------------------------------------------------------
# AuroraConfigWriter
# ---------------------------------------------------------------------------


class TestAuroraConfigWriter:
    def test_writes_valid_yaml(self, tmp_path):
        writer = AuroraConfigWriter()
        strategy_file = os.path.join(str(tmp_path), "strat.py")
        spec = _make_valid_spec()

        result = BuildResult(
            success=True,
            spec_id=spec.spec_id,
            strategy_file=strategy_file,
            strategy_class_name="TrendFollowingStrategy",
            initial_parameters={"fast_window": 20, "slow_window": 50},
            parameter_bounds={"fast_window": (5, 50), "slow_window": (20, 200)},
        )

        config_path = writer.write(result, spec)
        assert os.path.exists(config_path)

        with open(config_path) as f:
            content = f.read()

        assert spec.spec_id in content
        assert "trend_following" in content
        assert "allow_short: false" in content or "allow_short: False" in content
        assert "max_position_size: 0.1" in content

    def test_config_contains_spec_id(self, tmp_path):
        writer = AuroraConfigWriter()
        strategy_file = os.path.join(str(tmp_path), "strat.py")
        spec = _make_valid_spec()

        result = BuildResult(
            success=True,
            spec_id=spec.spec_id,
            strategy_file=strategy_file,
            strategy_class_name="TrendFollowingStrategy",
            initial_parameters={},
            parameter_bounds={},
        )

        config_path = writer.write(result, spec)
        with open(config_path) as f:
            content = f.read()

        assert spec.spec_id in content

    def test_config_contains_risk_section(self, tmp_path):
        writer = AuroraConfigWriter()
        strategy_file = os.path.join(str(tmp_path), "strat.py")
        spec = _make_valid_spec(position_size=0.05, max_positions=10)

        result = BuildResult(
            success=True,
            spec_id=spec.spec_id,
            strategy_file=strategy_file,
            strategy_class_name="TestStrategy",
            initial_parameters={},
            parameter_bounds={},
        )

        config_path = writer.write(result, spec)
        with open(config_path) as f:
            content = f.read()

        assert "max_position_size: 0.05" in content
        assert "max_positions: 10" in content
        assert "allow_short: false" in content or "allow_short: False" in content
        assert "use_margin: false" in content or "use_margin: False" in content

    def test_config_contains_backtest_section(self, tmp_path):
        writer = AuroraConfigWriter()
        strategy_file = os.path.join(str(tmp_path), "strat.py")
        spec = _make_valid_spec(symbols=["SPY", "QQQ"])

        result = BuildResult(
            success=True,
            spec_id=spec.spec_id,
            strategy_file=strategy_file,
            strategy_class_name="TestStrategy",
            initial_parameters={},
            parameter_bounds={},
        )

        config_path = writer.write(result, spec)
        with open(config_path) as f:
            content = f.read()

        assert "start: 2018-01-01" in content
        assert "end: 2023-12-31" in content
        assert "SPY" in content
        assert "QQQ" in content


# ---------------------------------------------------------------------------
# StrategyGenerator
# ---------------------------------------------------------------------------


def _make_mock_provider(response_text: str) -> MagicMock:
    """Build a mock LLMProvider that returns the given text from generate()."""
    mock_provider = MagicMock(spec=LLMProvider)
    mock_provider.generate.return_value = response_text
    return mock_provider


def _make_mock_provider_error() -> MagicMock:
    """Build a mock LLMProvider that raises on generate()."""
    mock_provider = MagicMock(spec=LLMProvider)
    mock_provider.generate.side_effect = Exception("API error")
    return mock_provider


class TestStrategyGenerator:
    def test_initializes_with_provider_and_build_dir(self):
        gen = StrategyGenerator(llm_provider=MagicMock(spec=LLMProvider), build_dir="/tmp/astra")
        assert gen._build_dir == "/tmp/astra"

    def test_unknown_strategy_type_returns_failed_build(self, tmp_path):
        gen = StrategyGenerator(llm_provider=MagicMock(spec=LLMProvider), build_dir=str(tmp_path))
        spec = _make_valid_spec(strategy_type="unknown_strategy_type")
        result = gen.generate(spec)
        assert result.success is False
        assert "unknown" in result.error.lower()

    def test_generate_creates_strategy_file(self, tmp_path):
        mock_provider = _make_mock_provider(
            json.dumps({"fast_window": 20, "slow_window": 50, "signal_threshold": 0.02})
        )

        gen = StrategyGenerator(llm_provider=mock_provider, build_dir=str(tmp_path))
        spec = _make_valid_spec(strategy_type="trend_following")
        result = gen.generate(spec)

        assert result.success is True
        assert os.path.exists(result.strategy_file)
        assert result.strategy_class_name == "TrendFollowingStrategy"
        assert result.spec_id == spec.spec_id

        with open(result.strategy_file) as f:
            code = f.read()
        assert "class TrendFollowingStrategy" in code
        assert "generate_signals" in code

    def test_full_generate_produces_yaml_config(self, tmp_path):
        mock_provider = _make_mock_provider(
            json.dumps({"fast_window": 20, "slow_window": 50, "signal_threshold": 0.02})
        )

        gen = StrategyGenerator(llm_provider=mock_provider, build_dir=str(tmp_path))
        spec = _make_valid_spec(strategy_type="trend_following")
        result = gen.generate(spec)

        assert result.success is True
        assert os.path.exists(result.aurora_config_file)

        with open(result.aurora_config_file) as f:
            content = f.read()
        assert spec.spec_id in content

    def test_generate_sandbox_reject_triggers_fallback(self, tmp_path):
        mock_provider = _make_mock_provider(
            json.dumps({"investment_interval_days": 7, "max_positions": 52, "investment_fraction": 0.05})
        )

        gen = StrategyGenerator(llm_provider=mock_provider, build_dir=str(tmp_path))
        spec = _make_valid_spec(strategy_type="dca")
        result = gen.generate(spec)

        assert result.success is True
        assert os.path.exists(result.strategy_file)

    def test_build_log_populated(self, tmp_path):
        mock_provider = _make_mock_provider(
            json.dumps({"fast_window": 20, "slow_window": 50, "signal_threshold": 0.02})
        )

        gen = StrategyGenerator(llm_provider=mock_provider, build_dir=str(tmp_path))
        spec = _make_valid_spec()
        result = gen.generate(spec)

        assert len(result.build_log) > 2
        assert any("Starting build" in m for m in result.build_log)
        assert any("Sandbox validation passed" in m for m in result.build_log)

    def test_generated_code_imports_cleanly(self, tmp_path):
        mock_provider = _make_mock_provider(
            json.dumps({"fast_window": 20, "slow_window": 50, "signal_threshold": 0.02})
        )

        gen = StrategyGenerator(llm_provider=mock_provider, build_dir=str(tmp_path))
        spec = _make_valid_spec(strategy_type="trend_following")
        result = gen.generate(spec)

        spec_name = os.path.splitext(os.path.basename(result.strategy_file))[0]
        spec_name = spec_name.replace(".", "_").replace("-", "_")

        import sys
        if spec_name in sys.modules:
            del sys.modules[spec_name]

        spec_mod = importlib.util.spec_from_file_location(
            spec_name, result.strategy_file
        )
        assert spec_mod is not None
        mod = importlib.util.module_from_spec(spec_mod)
        sys.modules[spec_name] = mod
        spec_mod.loader.exec_module(mod)

        assert hasattr(mod, "TrendFollowingStrategy")
        strategy_cls = mod.TrendFollowingStrategy
        assert strategy_cls.STRATEGY_TYPE == "trend_following"
        assert strategy_cls.STRATEGY_HYPOTHESIS != ""

    def test_parameter_inference_uses_defaults_when_llm_fails(self, tmp_path):
        mock_provider = _make_mock_provider_error()

        gen = StrategyGenerator(llm_provider=mock_provider, build_dir=str(tmp_path))
        spec = _make_valid_spec(strategy_type="trend_following")
        result = gen.generate(spec)

        assert result.success is True
        assert result.initial_parameters.get("fast_window") == 20

    def test_param_inference_response_handles_code_block(self, tmp_path):
        mock_provider = _make_mock_provider(
            "```json\n{\"fast_window\": 25, \"slow_window\": 60, \"signal_threshold\": 0.03}\n```"
        )

        gen = StrategyGenerator(llm_provider=mock_provider, build_dir=str(tmp_path))
        spec = _make_valid_spec(strategy_type="trend_following")
        result = gen.generate(spec)

        assert result.success is True
        assert result.initial_parameters["fast_window"] == 25
        assert result.initial_parameters["slow_window"] == 60


# ---------------------------------------------------------------------------
# BuildError
# ---------------------------------------------------------------------------


class TestBuildError:
    def test_is_exception(self):
        err = BuildError("something went wrong")
        assert isinstance(err, Exception)
        assert str(err) == "something went wrong"


# ---------------------------------------------------------------------------
# BaseStrategy ABC
# ---------------------------------------------------------------------------


class TestBaseStrategy:
    def test_cannot_be_instantiated_directly(self):
        with pytest.raises(TypeError):
            BaseStrategy()



