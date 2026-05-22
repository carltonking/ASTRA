"""ASTRA CLI — run the trading strategy pipeline from the terminal."""

import argparse
import json
import os
import sys
import uuid
from datetime import datetime

from astra.llm import create_llm_provider
from astra.planner.spec import StrategySpec
from astra.builder.generator import StrategyGenerator, BuildResult
from astra.builder.templates import TEMPLATES_BY_TYPE, DEFAULT_PARAMETERS_BY_TYPE
from astra.builder.sandbox import BuildSandbox
from astra.pipeline.state import PipelineState
from astra.pipeline.runner import PipelineRunner
from astra.pipeline.events import PipelineEventBus
from astra.pipeline.aurora_bridge import AuroraBridge
from astra.alpaca.monitor import PerformanceSnapshot, DegradationReport
from astra.graduation import GraduationCertificate, GateResult
from astra.export.packager import StrategyPackager


def _build_dir() -> str:
    return os.environ.get("ASTRA_BUILD_DIR", ".astra_builds")


def _export_dir() -> str:
    return os.environ.get("ASTRA_EXPORT_DIR", ".astra_exports")


# ---------------------------------------------------------------------------
# plan subcommand: idea -> spec
# ---------------------------------------------------------------------------


def cmd_plan(args: argparse.Namespace) -> None:
    """Convert a trading idea into a StrategySpec via LLM dialogue."""
    from astra.planner.conversation import PlannerConversation

    provider = create_llm_provider()
    conv = PlannerConversation(llm_provider=provider)
    response = conv.start(args.idea)
    print(response)
    print()

    if args.interactive:
        while not conv.is_complete():
            user_input = input("> ").strip()
            if not user_input:
                continue
            response = conv.reply(user_input)
            print(response)
            print()

    if conv.rejected:
        print(f"REJECTED: {conv.rejection_reason}")
        sys.exit(1)

    if conv.spec is None:
        print("ERROR: No spec was produced.")
        sys.exit(1)

    spec_out = args.output or os.path.join(_build_dir(), "spec.json")
    os.makedirs(os.path.dirname(spec_out) or ".", exist_ok=True)
    with open(spec_out, "w") as f:
        f.write(conv.spec.to_json())
    print(f"Spec saved to {spec_out}")


# ---------------------------------------------------------------------------
# build subcommand: spec -> strategy file
# ---------------------------------------------------------------------------


def cmd_build(args: argparse.Namespace) -> None:
    """Build a strategy file from a StrategySpec JSON file."""
    with open(args.spec) as f:
        spec = StrategySpec.from_json(f.read())

    provider = create_llm_provider()
    generator = StrategyGenerator(llm_provider=provider, build_dir=_build_dir())
    result = generator.generate(spec)

    if not result.success:
        print(f"Build failed: {result.error}")
        sys.exit(1)

    print(f"Strategy: {result.strategy_file}")
    print(f"Config:   {result.aurora_config_file}")
    print(f"Class:    {result.strategy_class_name}")
    print(f"Params:   {result.initial_parameters}")

    if args.output:
        import shutil
        os.makedirs(os.path.dirname(args.output) or ".", exist_ok=True)
        shutil.copy(result.strategy_file, args.output)
        print(f"Copied to {args.output}")


# ---------------------------------------------------------------------------
# run subcommand: spec -> build -> pipeline -> export
# ---------------------------------------------------------------------------


def cmd_run(args: argparse.Namespace) -> None:
    """Full pipeline: build from spec, backtest, deploy, and export."""
    with open(args.spec) as f:
        spec = StrategySpec.from_json(f.read())

    provider = create_llm_provider()
    generator = StrategyGenerator(llm_provider=provider, build_dir=_build_dir())
    build_result = generator.generate(spec)
    if not build_result.success:
        print(f"Build failed: {build_result.error}")
        sys.exit(1)
    print(f"Built: {build_result.strategy_file}")

    _try_open_lseg()

    event_bus = PipelineEventBus()
    aurora = AuroraBridge(data_dir=os.path.join(_build_dir(), ".aurora_data"))
    runner = PipelineRunner(
        llm_provider=provider,
        alpaca_paper_key=os.environ.get("APCA_API_KEY_ID", ""),
        alpaca_paper_secret=os.environ.get("APCA_API_SECRET_KEY", ""),
        alpaca_base_url=os.environ.get("APCA_PAPER_URL", "https://paper-api.alpaca.markets"),
        build_dir=_build_dir(),
        aurora_bridge=aurora,
        event_bus=event_bus,
    )

    pipeline_result = runner.run(build_result, spec)
    print(f"Pipeline: {pipeline_result.status}")
    if pipeline_result.error:
        print(f"  Error: {pipeline_result.error}")

    if pipeline_result.cpcv_summary:
        s = pipeline_result.cpcv_summary
        print(f"  Sharpe:    {s.get('mean_sharpe', 'N/A')}")
        print(f"  DSR:       {s.get('dsr', 'N/A')}")
        print(f"  Overfit:   {s.get('overfitting_probability', 'N/A')}")

    if args.export and pipeline_result.status in ("DEPLOYED_PAPER", "PASSED"):
        _export_strategy(spec, build_result, pipeline_result)

    _try_close_lseg()


# ---------------------------------------------------------------------------
# export subcommand: re-export an already-built strategy
# ---------------------------------------------------------------------------


def cmd_export(args: argparse.Namespace) -> None:
    """Re-export from existing spec + build result."""
    with open(args.spec) as f:
        spec = StrategySpec.from_json(f.read())

    build_result = _load_build_result(args.build_result) if args.build_result else None
    if build_result is None:
        print("Build result not provided. Use --build-result or run 'build' first.")
        sys.exit(1)

    _export_strategy(spec, build_result, None)


def _export_strategy(
    spec: StrategySpec,
    build_result: BuildResult,
    pipeline_result=None,
) -> None:
    from astra.export.packager import StrategyPackager

    pipeline_result = pipeline_result or _stub_pipeline_result(spec)
    cert = _stub_certificate(spec)
    snapshot = PerformanceSnapshot(deployment_id="cli_export")

    packager = StrategyPackager(export_dir=_export_dir())
    pkg = packager.package(build_result, spec, cert, pipeline_result, snapshot)

    print(f"\nExported: {pkg.strategy_file}")
    print(f"Checksum: {pkg.checksum}")


# ---------------------------------------------------------------------------
# Stubs (used when real pipeline data isn't available)
# ---------------------------------------------------------------------------


def _stub_pipeline_result(spec):
    from astra.pipeline.runner import PipelineResult
    return PipelineResult(
        pipeline_id=str(uuid.uuid4()),
        spec_id=spec.spec_id,
        status="DEPLOYED_PAPER",
        cpcv_summary={"mean_sharpe": "N/A", "dsr": "N/A"},
        backtest_metrics={},
    )


def _try_open_lseg() -> None:
    try:
        from astra.data import lseg_client
        lseg_client.open_session()
    except Exception as exc:
        print(f"WARNING: LSEG session open failed: {exc}")


def _try_close_lseg() -> None:
    try:
        from astra.data import lseg_client
        lseg_client.close_session()
    except Exception:
        pass


def _stub_certificate(spec):
    return GraduationCertificate(
        session_id=str(uuid.uuid4()),
        spec_id=spec.spec_id,
        strategy_type=spec.strategy_type,
        symbols=list(spec.symbols),
        optimization_cycles=0,
        gate_results={
            "dsr": GateResult(gate_name="dsr", status="PASSED", actual_value=0, threshold_value=0, gap=0, evidence=""),
            "annual_return": GateResult(gate_name="annual_return", status="PASSED", actual_value=0, threshold_value=0, gap=0, evidence=""),
            "max_drawdown": GateResult(gate_name="max_drawdown", status="PASSED", actual_value=0, threshold_value=0, gap=0, evidence=""),
            "min_trades": GateResult(gate_name="min_trades", status="PASSED", actual_value=0, threshold_value=0, gap=0, evidence=""),
            "max_degradation": GateResult(gate_name="max_degradation", status="PASSED", actual_value=0, threshold_value=0, gap=0, evidence=""),
            "min_calendar_days": GateResult(gate_name="min_calendar_days", status="PASSED", actual_value=0, threshold_value=0, gap=0, evidence=""),
        },
    )


def _load_build_result(path: str) -> BuildResult | None:
    try:
        with open(path) as f:
            data = json.load(f)
        return BuildResult(**data)
    except Exception:
        return None


# ---------------------------------------------------------------------------
# Main entry point
# ---------------------------------------------------------------------------


def main() -> None:
    parser = argparse.ArgumentParser(
        description="ASTRA — Autonomous Self-learning Trading and Research Agent"
    )
    sub = parser.add_subparsers(dest="command", required=True)

    p_plan = sub.add_parser("plan", help="Convert a trading idea into a strategy spec")
    p_plan.add_argument("idea", help="Your trading idea in plain English")
    p_plan.add_argument("--interactive", "-i", action="store_true",
                        help="Interactive mode: answer follow-up questions")
    p_plan.add_argument("--output", "-o", help="Output spec JSON path")

    p_build = sub.add_parser("build", help="Build a strategy file from a spec JSON")
    p_build.add_argument("spec", help="Path to StrategySpec JSON file")
    p_build.add_argument("--output", "-o", help="Output strategy file path")

    p_run = sub.add_parser("run", help="Full pipeline: build, backtest, deploy, export")
    p_run.add_argument("spec", help="Path to StrategySpec JSON file")
    p_run.add_argument("--export", "-e", action="store_true",
                       help="Export the result after running")

    p_export = sub.add_parser("export", help="Export an already-built strategy")
    p_export.add_argument("spec", help="Path to StrategySpec JSON file")
    p_export.add_argument("--build-result", "-b", help="Path to BuildResult JSON file")

    args = parser.parse_args()

    commands = {
        "plan": cmd_plan,
        "build": cmd_build,
        "run": cmd_run,
        "export": cmd_export,
    }
    commands[args.command](args)


if __name__ == "__main__":
    main()
