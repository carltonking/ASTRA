"""Tests for the ASTRA CLI (astra.cli)."""

import argparse
import json
import sys
from argparse import Namespace
from unittest.mock import MagicMock, patch, ANY

import pytest

from astra.cli import main, cmd_plan, cmd_build, cmd_run, cmd_export


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture
def mock_provider():
    return MagicMock()


@pytest.fixture
def mock_conversation():
    conv = MagicMock()
    conv.start.return_value = "What timeframe?"
    conv.is_complete.return_value = False
    conv.rejected = False
    conv.spec = None
    conv.rejection_reason = ""
    return conv


@pytest.fixture
def sample_spec(tmp_path):
    spec_data = {
        "spec_id": "test-spec-id",
        "user_idea": "Momentum on SPY",
        "asset_class": "equity",
        "symbols": ["SPY"],
        "timeframe": "daily",
        "data_source": "yfinance",
        "strategy_type": "momentum",
        "market_hypothesis": "SPY exhibits momentum",
        "entry_conditions": ["Close > 50-day SMA"],
        "exit_conditions": ["Close < 200-day SMA"],
        "target_return": 0.12,
        "max_drawdown": 0.20,
        "position_size": 0.05,
        "max_positions": 5,
        "backtest_start": "2020-01-01",
        "backtest_end": "2023-12-31",
    }
    p = tmp_path / "spec.json"
    p.write_text(json.dumps(spec_data))
    return str(p)


@pytest.fixture
def sample_build_result(tmp_path):
    strategy_file = tmp_path / "strategy.py"
    strategy_file.write_text("# fake strategy")
    result_data = {
        "success": True,
        "strategy_file": str(strategy_file),
        "aurora_config_file": str(tmp_path / "config.toml"),
        "strategy_class_name": "MomentumStrategy",
        "initial_parameters": {"lookback": 50},
        "error": None,
    }
    p = tmp_path / "build_result.json"
    p.write_text(json.dumps(result_data, default=str))
    return result_data, str(p)


# ---------------------------------------------------------------------------
# Argument parsing tests — test parser directly without dispatching
# ---------------------------------------------------------------------------


def _make_parser():
    """Replicate the parser from main() for isolated testing."""
    parser = argparse.ArgumentParser(description="ASTRA — Autonomous Self-learning Trading and Research Agent")
    sub = parser.add_subparsers(dest="command", required=True)

    p_plan = sub.add_parser("plan")
    p_plan.add_argument("idea")
    p_plan.add_argument("--interactive", "-i", action="store_true")
    p_plan.add_argument("--output", "-o")

    p_build = sub.add_parser("build")
    p_build.add_argument("spec")
    p_build.add_argument("--output", "-o")

    p_run = sub.add_parser("run")
    p_run.add_argument("spec")
    p_run.add_argument("--export", "-e", action="store_true")

    p_export = sub.add_parser("export")
    p_export.add_argument("spec")
    p_export.add_argument("--build-result", "-b")

    return parser


class TestArgParsing:
    def test_plan_parses_idea(self):
        args = _make_parser().parse_args(["plan", "momentum on spy"])
        assert args.command == "plan"
        assert args.idea == "momentum on spy"
        assert args.interactive is False

    def test_plan_parses_interactive_flag(self):
        args = _make_parser().parse_args(["plan", "idea", "-i"])
        assert args.interactive is True

    def test_plan_parses_output(self):
        args = _make_parser().parse_args(["plan", "idea", "-o", "out.json"])
        assert args.output == "out.json"

    def test_build_parses_spec(self):
        args = _make_parser().parse_args(["build", "spec.json"])
        assert args.command == "build"
        assert args.spec == "spec.json"

    def test_build_parses_output(self):
        args = _make_parser().parse_args(["build", "spec.json", "-o", "strategy.py"])
        assert args.output == "strategy.py"

    def test_run_parses_spec(self):
        args = _make_parser().parse_args(["run", "spec.json"])
        assert args.command == "run"
        assert args.export is False

    def test_run_parses_export_flag(self):
        args = _make_parser().parse_args(["run", "spec.json", "--export"])
        assert args.export is True

    def test_export_parses_spec(self):
        args = _make_parser().parse_args(["export", "spec.json"])
        assert args.command == "export"

    def test_export_parses_build_result(self):
        args = _make_parser().parse_args(["export", "spec.json", "-b", "result.json"])
        assert args.build_result == "result.json"

    def test_no_command_errors(self):
        with pytest.raises(SystemExit):
            _make_parser().parse_args([])


# ---------------------------------------------------------------------------
# cmd_plan tests
# ---------------------------------------------------------------------------


class TestCmdPlan:
    def test_plan_happy_path(self, tmp_path, mock_provider, mock_conversation):
        mock_conversation.is_complete.return_value = True
        mock_conversation.spec = MagicMock()
        mock_conversation.spec.to_json.return_value = '{"strategy_type": "momentum"}'
        mock_conversation.spec.spec_id = "abc12345"
        mock_conversation.rejected = False

        args = Namespace(idea="momentum on spy", interactive=False, output=str(tmp_path / "out.json"))

        with (
            patch("astra.cli.create_llm_provider", return_value=mock_provider),
            patch("astra.planner.conversation.PlannerConversation", return_value=mock_conversation),
        ):
            cmd_plan(args)

        assert (tmp_path / "out.json").exists()
        assert (tmp_path / "out.json").read_text() == '{"strategy_type": "momentum"}'

    def test_plan_rejected(self, mock_provider, mock_conversation):
        mock_conversation.is_complete.return_value = True
        mock_conversation.rejected = True
        mock_conversation.rejection_reason = "Not suitable"
        mock_conversation.spec = None

        args = Namespace(idea="bad idea", interactive=False, output=None)

        with (
            patch("astra.cli.create_llm_provider", return_value=mock_provider),
            patch("astra.planner.conversation.PlannerConversation", return_value=mock_conversation),
        ):
            with pytest.raises(SystemExit) as exc:
                cmd_plan(args)
            assert exc.value.code == 1

    def test_plan_no_spec(self, mock_provider, mock_conversation):
        mock_conversation.is_complete.return_value = True
        mock_conversation.rejected = False
        mock_conversation.spec = None

        args = Namespace(idea="idea", interactive=False, output=None)

        with (
            patch("astra.cli.create_llm_provider", return_value=mock_provider),
            patch("astra.planner.conversation.PlannerConversation", return_value=mock_conversation),
        ):
            with pytest.raises(SystemExit) as exc:
                cmd_plan(args)
            assert exc.value.code == 1


# ---------------------------------------------------------------------------
# cmd_build tests
# ---------------------------------------------------------------------------


class TestCmdBuild:
    def test_build_happy_path(self, tmp_path, mock_provider, sample_spec):
        strategy_file = tmp_path / "strategy.py"
        strategy_file.write_text("# hello")
        mock_build_result = MagicMock()
        mock_build_result.success = True
        mock_build_result.strategy_file = str(strategy_file)
        mock_build_result.aurora_config_file = str(tmp_path / "config.toml")
        mock_build_result.strategy_class_name = "MomentumStrategy"
        mock_build_result.initial_parameters = {"lookback": 50}
        mock_build_result.error = None

        args = Namespace(spec=sample_spec, output=None)

        with (
            patch("astra.cli.create_llm_provider", return_value=mock_provider),
            patch("astra.cli.StrategyGenerator") as mock_gen_cls,
        ):
            mock_gen = mock_gen_cls.return_value
            mock_gen.generate.return_value = mock_build_result
            cmd_build(args)

        mock_gen_cls.assert_called_once_with(llm_provider=mock_provider, build_dir=ANY)

    def test_build_failure(self, mock_provider, sample_spec):
        mock_build_result = MagicMock()
        mock_build_result.success = False
        mock_build_result.error = "Build error"

        args = Namespace(spec=sample_spec, output=None)

        with (
            patch("astra.cli.create_llm_provider", return_value=mock_provider),
            patch("astra.cli.StrategyGenerator") as mock_gen_cls,
        ):
            mock_gen = mock_gen_cls.return_value
            mock_gen.generate.return_value = mock_build_result
            with pytest.raises(SystemExit) as exc:
                cmd_build(args)
            assert exc.value.code == 1


# ---------------------------------------------------------------------------
# cmd_run tests
# ---------------------------------------------------------------------------


class TestCmdRun:
    def test_run_happy_path(self, tmp_path, mock_provider, sample_spec):
        mock_build_result = MagicMock()
        mock_build_result.success = True
        mock_build_result.strategy_file = str(tmp_path / "strategy.py")
        mock_build_result.error = None

        mock_pipeline_result = MagicMock()
        mock_pipeline_result.status = "PASSED"
        mock_pipeline_result.error = None
        mock_pipeline_result.cpcv_summary = {
            "mean_sharpe": 1.5,
            "dsr": 2.0,
            "overfitting_probability": 0.3,
        }

        args = Namespace(spec=sample_spec, export=False)

        with (
            patch("astra.cli.create_llm_provider", return_value=mock_provider),
            patch("astra.cli.StrategyGenerator") as mock_gen_cls,
            patch("astra.cli.PipelineRunner") as mock_runner_cls,
        ):
            mock_gen = mock_gen_cls.return_value
            mock_gen.generate.return_value = mock_build_result
            mock_runner = mock_runner_cls.return_value
            mock_runner.run.return_value = mock_pipeline_result
            cmd_run(args)

    def test_run_build_fails_exits(self, mock_provider, sample_spec):
        mock_build_result = MagicMock()
        mock_build_result.success = False
        mock_build_result.error = "fail"

        args = Namespace(spec=sample_spec, export=False)

        with (
            patch("astra.cli.create_llm_provider", return_value=mock_provider),
            patch("astra.cli.StrategyGenerator") as mock_gen_cls,
        ):
            mock_gen = mock_gen_cls.return_value
            mock_gen.generate.return_value = mock_build_result
            with pytest.raises(SystemExit) as exc:
                cmd_run(args)
            assert exc.value.code == 1


# ---------------------------------------------------------------------------
# cmd_export tests
# ---------------------------------------------------------------------------


class TestCmdExport:
    def test_export_happy_path(self, tmp_path, mock_provider, sample_spec, sample_build_result):
        mock_pkg = MagicMock()
        mock_pkg.strategy_file = str(tmp_path / "exported.py")
        mock_pkg.checksum = "abc123"

        args = Namespace(spec=sample_spec, build_result=sample_build_result[1])

        with (
            patch("astra.cli.create_llm_provider", return_value=mock_provider),
            patch("astra.cli.StrategyPackager") as mock_pkg_cls,
        ):
            mock_pkg_cls_instance = mock_pkg_cls.return_value
            mock_pkg_cls_instance.package.return_value = mock_pkg
            cmd_export(args)

    def test_export_no_build_result(self, mock_provider, sample_spec):
        args = Namespace(spec=sample_spec, build_result=None)

        with (
            patch("astra.cli.create_llm_provider", return_value=mock_provider),
        ):
            with pytest.raises(SystemExit) as exc:
                cmd_export(args)
            assert exc.value.code == 1


# ---------------------------------------------------------------------------
# main() dispatch test
# ---------------------------------------------------------------------------


class TestMainDispatch:
    def test_dispatches_plan(self):
        with patch("astra.cli.cmd_plan") as mock_fn:
            with patch.object(sys, "argv", ["astra", "plan", "some idea"]):
                main()
        mock_fn.assert_called_once()

    def test_dispatches_build(self):
        with patch("astra.cli.cmd_build") as mock_fn:
            with patch.object(sys, "argv", ["astra", "build", "spec.json"]):
                main()
        mock_fn.assert_called_once()

    def test_dispatches_run(self):
        with patch("astra.cli.cmd_run") as mock_fn:
            with patch.object(sys, "argv", ["astra", "run", "spec.json"]):
                main()
        mock_fn.assert_called_once()

    def test_dispatches_export(self):
        with patch("astra.cli.cmd_export") as mock_fn:
            with patch.object(sys, "argv", ["astra", "export", "spec.json"]):
                main()
        mock_fn.assert_called_once()

    def test_no_command_exits(self):
        with patch.object(sys, "argv", ["astra"]):
            with pytest.raises(SystemExit):
                main()


# ---------------------------------------------------------------------------
# Module-level helpers
# ---------------------------------------------------------------------------


class TestHelpers:
    def test_load_build_result_valid(self, tmp_path):
        from astra.cli import _load_build_result

        data = {
            "success": True,
            "strategy_file": "s.py",
            "aurora_config_file": "c.toml",
            "strategy_class_name": "A",
            "initial_parameters": {},
            "error": None,
        }
        p = tmp_path / "data.json"
        p.write_text(json.dumps(data))
        result = _load_build_result(str(p))
        assert result is not None
        assert result.success is True

    def test_load_build_result_invalid(self, tmp_path):
        from astra.cli import _load_build_result

        p = tmp_path / "bad.json"
        p.write_text("not json")
        result = _load_build_result(str(p))
        assert result is None
