"""Strategy code generator — transforms a StrategySpec into executable Python."""

import json
import os
from dataclasses import dataclass, field
from typing import Any

from astra.llm.provider import LLMProvider
from astra.planner.spec import StrategySpec
from astra.builder.templates import (
    TEMPLATES_BY_TYPE,
    DEFAULT_PARAMETERS_BY_TYPE,
    CLASS_NAME_BY_TYPE,
)
from astra.builder.sandbox import BuildSandbox


class BuildError(Exception):
    ...


@dataclass
class BuildResult:
    success: bool
    spec_id: str = ""
    strategy_file: str = ""
    strategy_class_name: str = ""
    initial_parameters: dict[str, Any] = field(default_factory=dict)
    parameter_bounds: dict[str, tuple[float, float]] = field(default_factory=dict)
    aurora_config_file: str = ""
    build_log: list[str] = field(default_factory=list)
    error: str | None = None


_PARAM_INFERENCE_PROMPT = """Given this trading strategy specification, return ONLY a JSON object with appropriate initial parameter values for the strategy. No explanation. No code. Just valid JSON.

Strategy type: {strategy_type}
Entry conditions: {entry_conditions}
Exit conditions: {exit_conditions}
Timeframe: {timeframe}
Market hypothesis: {hypothesis}

Available parameters and their default values:
{default_params}

Return a JSON object mapping parameter names to your inferred initial values."""


class StrategyGenerator:
    def __init__(self, llm_provider: LLMProvider, build_dir: str):
        self._llm = llm_provider
        self._build_dir = build_dir
        self._sandbox = BuildSandbox()

    def generate(self, spec: StrategySpec) -> BuildResult:
        build_log: list[str] = []
        build_log.append(f"Starting build for spec {spec.spec_id} ({spec.strategy_type})")

        template = TEMPLATES_BY_TYPE.get(spec.strategy_type)
        if template is None:
            return BuildResult(
                success=False,
                spec_id=spec.spec_id,
                build_log=build_log,
                error=f"Unknown strategy type: {spec.strategy_type}",
            )

        class_name = CLASS_NAME_BY_TYPE.get(spec.strategy_type, "GeneratedStrategy")

        try:
            inferred = self._infer_parameters(spec, build_log)
            build_log.append(f"Inferred parameters: {inferred}")
        except Exception as e:
            build_log.append(f"Parameter inference failed, using defaults: {e}")
            inferred = dict(DEFAULT_PARAMETERS_BY_TYPE.get(spec.strategy_type, {}))

        code = template.format(hypothesis=spec.market_hypothesis, **inferred)

        strategy_dir = os.path.join(self._build_dir, spec.spec_id)
        os.makedirs(strategy_dir, exist_ok=True)

        strategy_file = os.path.join(strategy_dir, f"{spec.spec_id}_strategy.py")
        with open(strategy_file, "w") as f:
            f.write(code)
        build_log.append(f"Wrote strategy file: {strategy_file}")

        sandbox_result = self._sandbox.validate(strategy_file)
        if not sandbox_result.passed:
            build_log.append(f"Sandbox violations: {sandbox_result.violations}")
            try:
                build_log.append("Attempting regeneration with corrected parameters...")
                inferred = dict(DEFAULT_PARAMETERS_BY_TYPE.get(spec.strategy_type, {}))
                code = template.format(hypothesis=spec.market_hypothesis, **inferred)
                with open(strategy_file, "w") as f:
                    f.write(code)
                sandbox_result = self._sandbox.validate(strategy_file)
                if not sandbox_result.passed:
                    return BuildResult(
                        success=False,
                        spec_id=spec.spec_id,
                        build_log=build_log,
                        error=f"Sandbox rejection after regeneration: {sandbox_result.violations}",
                    )
                build_log.append("Regeneration passed sandbox")
            except Exception as e:
                return BuildResult(
                    success=False,
                    spec_id=spec.spec_id,
                    build_log=build_log,
                    error=f"Build failed: {e}",
                )

        build_log.append("Sandbox validation passed")

        param_bounds = self._get_bounds_for_type(spec.strategy_type)

        from astra.builder.config_writer import AuroraConfigWriter

        config_writer = AuroraConfigWriter()
        result = BuildResult(
            success=True,
            spec_id=spec.spec_id,
            strategy_file=strategy_file,
            strategy_class_name=class_name,
            initial_parameters=inferred,
            parameter_bounds=param_bounds,
            build_log=build_log,
        )

        try:
            config_path = config_writer.write(result, spec)
            result.aurora_config_file = config_path
            build_log.append(f"Wrote config: {config_path}")
        except Exception as e:
            build_log.append(f"Config write failed: {e}")
            result.error = f"Config write failed: {e}"

        return result

    def _infer_parameters(self, spec: StrategySpec, build_log: list[str]) -> dict[str, Any]:
        defaults = DEFAULT_PARAMETERS_BY_TYPE.get(spec.strategy_type, {})
        prompt = _PARAM_INFERENCE_PROMPT.format(
            strategy_type=spec.strategy_type,
            entry_conditions="; ".join(spec.entry_conditions),
            exit_conditions="; ".join(spec.exit_conditions),
            timeframe=spec.timeframe,
            hypothesis=spec.market_hypothesis,
            default_params=json.dumps(defaults, indent=2),
        )
        text = self._llm.generate(
            messages=[{"role": "user", "content": prompt}],
            system_prompt="You are a trading strategy parameter estimator. Return ONLY valid JSON.",
            max_tokens=1024,
        ).strip()

        if text.startswith("```"):
            text = text.strip("`").strip()
            if text.startswith("json"):
                text = text[4:].strip()

        inferred = json.loads(text)

        merged = dict(defaults)
        merged.update(inferred)
        return merged

    @staticmethod
    def _get_bounds_for_type(strategy_type: str) -> dict[str, tuple]:

        _BOUNDS_BY_TYPE = {
            "trend_following": {
                "fast_window": (5, 50),
                "slow_window": (20, 200),
                "signal_threshold": (0.01, 0.10),
            },
            "mean_reversion": {
                "rsi_window": (5, 30),
                "oversold_threshold": (20.0, 40.0),
                "overbought_threshold": (60.0, 80.0),
            },
            "momentum": {
                "lookback_window": (5, 252),
                "momentum_threshold": (0.01, 0.20),
                "holding_period": (1, 60),
            },
            "pairs": {
                "z_entry": (1.0, 3.0),
                "z_exit": (0.0, 1.0),
                "lookback_window": (10, 100),
            },
            "breakout": {
                "lookback_window": (10, 100),
                "breakout_multiplier": (1.0, 3.0),
                "volume_threshold": (1.0, 3.0),
            },
            "dca": {
                "investment_interval_days": (1, 30),
                "max_positions": (4, 52),
                "investment_fraction": (0.01, 0.25),
            },
        }
        return _BOUNDS_BY_TYPE.get(strategy_type, {})
