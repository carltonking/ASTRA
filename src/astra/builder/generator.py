"""Strategy code generator — transforms a StrategySpec into executable Python."""

import hashlib
import json
import os
from dataclasses import dataclass, field
from typing import Any

from astra.llm.provider import LLMProvider
from astra.planner.spec import StrategySpec
from astra.strategy import (
    ExecutionAssumptions,
    LeverageConstraints,
    RegimeContract,
    RiskControls,
    SizingModel,
    StrategyLineage,
    StrategyMetadata,
    StrategySpecSchema,
)
from astra.builder.templates import (
    TEMPLATES_BY_TYPE,
    DEFAULT_PARAMETERS_BY_TYPE,
    CLASS_NAME_BY_TYPE,
)
from astra.builder.sandbox import BuildSandbox
from astra.builder.compiler import CompileReport, StrategyCompiler


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
    metadata_file: str = ""
    lineage_file: str = ""
    strategy_hash: str = ""
    spec_hash: str = ""
    prompt_hash: str = ""
    compiler_report: dict[str, Any] = field(default_factory=dict)
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
    def __init__(
        self,
        llm_provider: LLMProvider,
        build_dir: str,
        deterministic_parameters: bool = False,
    ):
        self._llm = llm_provider
        self._build_dir = build_dir
        self._deterministic_parameters = deterministic_parameters
        self._sandbox = BuildSandbox()
        self._compiler = StrategyCompiler(self._sandbox)

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
        param_bounds = self._get_bounds_for_type(spec.strategy_type)
        prompt_text = self._build_parameter_prompt(spec)
        prompt_hash = _stable_hash(prompt_text)

        try:
            if self._deterministic_parameters:
                inferred = dict(DEFAULT_PARAMETERS_BY_TYPE.get(spec.strategy_type, {}))
            else:
                inferred = self._infer_parameters(spec, build_log)
            build_log.append(f"Inferred parameters: {inferred}")
        except Exception as e:
            build_log.append(f"Parameter inference failed, using defaults: {e}")
            inferred = dict(DEFAULT_PARAMETERS_BY_TYPE.get(spec.strategy_type, {}))
        inferred = self._normalize_parameters(inferred, param_bounds)

        spec_schema = self._build_spec_schema(spec, prompt_hash)
        code = template.format(hypothesis=spec.market_hypothesis, **inferred)
        code = self._augment_code(code, spec, spec_schema, class_name, inferred, param_bounds)

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
                inferred = self._normalize_parameters(inferred, param_bounds)
                spec_schema = self._build_spec_schema(spec, prompt_hash)
                code = template.format(hypothesis=spec.market_hypothesis, **inferred)
                code = self._augment_code(code, spec, spec_schema, class_name, inferred, param_bounds)
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

        compile_report = self._compiler.compile(strategy_file, class_name)
        build_log.append(f"Compiler validation passed: {compile_report.passed}")
        if not compile_report.passed:
            return BuildResult(
                success=False,
                spec_id=spec.spec_id,
                strategy_file=strategy_file,
                strategy_class_name=class_name,
                initial_parameters=inferred,
                parameter_bounds=param_bounds,
                prompt_hash=prompt_hash,
                compiler_report=_compile_report_dict(compile_report),
                build_log=build_log,
                error=f"Compiler rejection: {compile_report.failures}",
            )

        with open(strategy_file) as f:
            final_code = f.read()
        strategy_hash = hashlib.sha256(final_code.encode("utf-8")).hexdigest()
        spec_hash = _stable_hash(spec.to_json())

        metadata = self._build_metadata(
            spec=spec,
            spec_schema=spec_schema,
            class_name=class_name,
            parameters=inferred,
            parameter_bounds=param_bounds,
            strategy_hash=strategy_hash,
            spec_hash=spec_hash,
        )
        metadata_file = os.path.join(strategy_dir, "strategy_metadata.json")
        with open(metadata_file, "w") as f:
            f.write(metadata.model_dump_json(indent=2))
        lineage_file = os.path.join(strategy_dir, "strategy_lineage.json")
        with open(lineage_file, "w") as f:
            f.write(spec_schema.lineage.model_dump_json(indent=2))
        build_log.append(f"Wrote metadata: {metadata_file}")
        build_log.append(f"Wrote lineage: {lineage_file}")

        from astra.builder.config_writer import AuroraConfigWriter

        config_writer = AuroraConfigWriter()
        result = BuildResult(
            success=True,
            spec_id=spec.spec_id,
            strategy_file=strategy_file,
            strategy_class_name=class_name,
            initial_parameters=inferred,
            parameter_bounds=param_bounds,
            metadata_file=metadata_file,
            lineage_file=lineage_file,
            strategy_hash=strategy_hash,
            spec_hash=spec_hash,
            prompt_hash=prompt_hash,
            compiler_report=_compile_report_dict(compile_report),
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
        prompt = self._build_parameter_prompt(spec)
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
    def _build_parameter_prompt(spec: StrategySpec) -> str:
        defaults = DEFAULT_PARAMETERS_BY_TYPE.get(spec.strategy_type, {})
        return _PARAM_INFERENCE_PROMPT.format(
            strategy_type=spec.strategy_type,
            entry_conditions="; ".join(spec.entry_conditions),
            exit_conditions="; ".join(spec.exit_conditions),
            timeframe=spec.timeframe,
            hypothesis=spec.market_hypothesis,
            default_params=json.dumps(defaults, indent=2),
        )

    @staticmethod
    def _normalize_parameters(
        parameters: dict[str, Any],
        bounds: dict[str, tuple[float, float]],
    ) -> dict[str, Any]:
        normalized: dict[str, Any] = {}
        for key in sorted(parameters):
            value = parameters[key]
            if key in bounds and isinstance(value, (int, float)):
                low, high = bounds[key]
                value = min(max(value, low), high)
                if isinstance(low, int) and isinstance(high, int):
                    value = int(round(value))
            normalized[key] = value
        return normalized

    @staticmethod
    def _build_spec_schema(spec: StrategySpec, prompt_hash: str) -> StrategySpecSchema:
        sizing = SizingModel(**spec.sizing_model)
        leverage = LeverageConstraints(**spec.leverage_constraints)
        risk = RiskControls(**spec.risk_controls)
        regime = RegimeContract(
            assumptions=list(spec.regime_assumptions),
            allowed_regimes=dict(spec.allowed_regimes),
            prohibited_regimes=dict(spec.prohibited_regimes),
            min_confidence=spec.min_regime_confidence,
        )
        execution = ExecutionAssumptions(**spec.execution_assumptions)
        lineage = StrategyLineage(
            strategy_id=spec.spec_id,
            parent_strategy_id=spec.parent_strategy_id,
            mutation_source=spec.mutation_source,
            generation_number=spec.generation_number,
            prompt_ancestry=list(spec.prompt_ancestry),
            prompt_hash=prompt_hash,
            validation_scores=dict(spec.validation_scores),
            failure_reasons=list(spec.failure_reasons),
        )
        return StrategySpecSchema(
            spec_id=spec.spec_id,
            user_idea=spec.user_idea,
            asset_class=spec.asset_class,
            symbols=list(spec.symbols),
            timeframe=spec.timeframe,
            data_source=spec.data_source,
            strategy_type=spec.strategy_type,
            market_hypothesis=spec.market_hypothesis,
            entry_conditions=list(spec.entry_conditions),
            exit_conditions=list(spec.exit_conditions),
            target_return=spec.target_return,
            max_drawdown=spec.max_drawdown,
            sizing_model=sizing,
            leverage_constraints=leverage,
            risk_controls=risk,
            regime_contract=regime,
            execution_assumptions=execution,
            indicator_dependencies=list(spec.indicator_dependencies),
            backtest_start=spec.backtest_start,
            backtest_end=spec.backtest_end,
            lineage=lineage,
        )

    @staticmethod
    def _augment_code(
        code: str,
        spec: StrategySpec,
        spec_schema: StrategySpecSchema,
        class_name: str,
        parameters: dict[str, Any],
        parameter_bounds: dict[str, tuple[float, float]],
    ) -> str:
        metadata = {
            "strategy_id": spec.spec_id,
            "spec_id": spec.spec_id,
            "strategy_type": spec.strategy_type,
            "strategy_class_name": class_name,
            "generated_at": spec.created_at.isoformat(),
            "entry_logic": list(spec.entry_conditions),
            "exit_logic": list(spec.exit_conditions),
            "parameters": parameters,
            "parameter_bounds": {k: list(v) for k, v in parameter_bounds.items()},
            "sizing_model": spec_schema.sizing_model.model_dump(),
            "leverage_constraints": spec_schema.leverage_constraints.model_dump(),
            "risk_controls": spec_schema.risk_controls.model_dump(),
            "regime_contract": spec_schema.regime_contract.model_dump(),
            "execution_assumptions": spec_schema.execution_assumptions.model_dump(),
            "indicator_dependencies": list(spec.indicator_dependencies),
            "lineage": spec_schema.lineage.model_dump(),
        }
        metadata_block = "STRATEGY_METADATA = " + repr(metadata) + "\n\n"
        class_block = (
            f'    STRATEGY_METADATA = STRATEGY_METADATA\n'
            f"    SIZING_MODEL = {spec_schema.sizing_model.model_dump()!r}\n"
            f"    LEVERAGE_CONSTRAINTS = {spec_schema.leverage_constraints.model_dump()!r}\n"
            f"    RISK_CONTROLS = {spec_schema.risk_controls.model_dump()!r}\n"
            f"    REGIME_ASSUMPTIONS = {spec_schema.regime_contract.assumptions!r}\n"
            f"    ALLOWED_REGIMES = {spec_schema.regime_contract.allowed_regimes!r}\n"
            f"    PROHIBITED_REGIMES = {spec_schema.regime_contract.prohibited_regimes!r}\n"
            f"    MIN_REGIME_CONFIDENCE = {spec_schema.regime_contract.min_confidence!r}\n"
            f"    EXECUTION_ASSUMPTIONS = {spec_schema.execution_assumptions.model_dump()!r}\n"
            f"    INDICATOR_DEPENDENCIES = {list(spec.indicator_dependencies)!r}\n"
        )
        lines = code.splitlines()
        insert_at = 0
        for i, line in enumerate(lines):
            if line.startswith("from astra.builder.templates import BaseStrategy"):
                insert_at = i + 1
                break
        lines.insert(insert_at, "")
        lines.insert(insert_at + 1, metadata_block.rstrip())
        code = "\n".join(lines) + "\n"
        return code.replace(
            f'class {class_name}(BaseStrategy):\n',
            f'class {class_name}(BaseStrategy):\n{class_block}',
            1,
        )

    @staticmethod
    def _build_metadata(
        spec: StrategySpec,
        spec_schema: StrategySpecSchema,
        class_name: str,
        parameters: dict[str, Any],
        parameter_bounds: dict[str, tuple[float, float]],
        strategy_hash: str,
        spec_hash: str,
    ) -> StrategyMetadata:
        return StrategyMetadata(
            strategy_id=spec.spec_id,
            spec_id=spec.spec_id,
            strategy_type=spec.strategy_type,
            strategy_class_name=class_name,
            generated_at=spec.created_at,
            code_hash=strategy_hash,
            spec_hash=spec_hash,
            parameters=parameters,
            parameter_bounds=parameter_bounds,
            entry_logic=list(spec.entry_conditions),
            exit_logic=list(spec.exit_conditions),
            sizing_model=spec_schema.sizing_model,
            leverage_constraints=spec_schema.leverage_constraints,
            risk_controls=spec_schema.risk_controls,
            regime_contract=spec_schema.regime_contract,
            execution_assumptions=spec_schema.execution_assumptions,
            indicator_dependencies=list(spec.indicator_dependencies),
            lineage=spec_schema.lineage,
        )

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


def _stable_hash(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


def _compile_report_dict(report: CompileReport) -> dict[str, Any]:
    return {
        "passed": report.passed,
        "syntax_ok": report.syntax_ok,
        "sandbox_ok": report.sandbox_ok,
        "import_ok": report.import_ok,
        "unit_test_ok": report.unit_test_ok,
        "lint_warnings": list(report.lint_warnings),
        "type_warnings": list(report.type_warnings),
        "failures": list(report.failures),
    }
