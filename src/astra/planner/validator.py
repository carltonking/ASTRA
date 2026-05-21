"""Strategy specification validator — gates specs before they leave the planner."""

from dataclasses import dataclass, field

from astra.planner.spec import StrategySpec


@dataclass
class ValidationResult:
    is_valid: bool
    errors: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)
    validated_spec: StrategySpec | None = None


class SpecValidator:
    WARNING_TARGET_RETURN = "Target return above 50% annually is extremely unlikely to be sustainable"
    WARNING_DRAWDOWN_TOO_LOW = "Max drawdown below 2% may make the strategy impossible to trade"
    ERROR_POSITION_SIZING = "Position sizing exceeds 100% of portfolio (position_size * max_positions > 1.0)"
    WARNING_BACKTEST_SHORT = "Backtest period under 2 years is insufficient for reliable validation"
    WARNING_BACKTEST_LONG = "Data quality degrades significantly before 2005 for most instruments"
    ERROR_HYPOTHESIS_EMPTY = "Market hypothesis is required and must be specific"

    @staticmethod
    def validate(spec: StrategySpec) -> ValidationResult:
        errors: list[str] = []
        warnings: list[str] = []

        spec_errors = SpecValidator._validate_symbols(spec)
        errors.extend(spec_errors)

        risk_errors, risk_warnings = SpecValidator._validate_risk_parameters(spec)
        errors.extend(risk_errors)
        warnings.extend(risk_warnings)

        bt_warnings = SpecValidator._validate_backtest_period(spec)
        warnings.extend(bt_warnings)

        hyp_errors = SpecValidator._validate_hypothesis(spec)
        errors.extend(hyp_errors)

        return ValidationResult(
            is_valid=len(errors) == 0,
            errors=errors,
            warnings=warnings,
            validated_spec=spec,
        )

    @staticmethod
    def _validate_symbols(spec: StrategySpec) -> list[str]:
        errors: list[str] = []
        if not spec.symbols:
            errors.append("At least one symbol is required")
        return errors

    @staticmethod
    def _validate_risk_parameters(spec: StrategySpec) -> tuple[list[str], list[str]]:
        errors: list[str] = []
        warnings: list[str] = []

        if spec.target_return > 0.50:
            warnings.append(SpecValidator.WARNING_TARGET_RETURN)

        if spec.max_drawdown < 0.02:
            warnings.append(SpecValidator.WARNING_DRAWDOWN_TOO_LOW)

        if spec.position_size * spec.max_positions > 1.0:
            errors.append(SpecValidator.ERROR_POSITION_SIZING)

        return errors, warnings

    @staticmethod
    def _validate_backtest_period(spec: StrategySpec) -> list[str]:
        import datetime

        warnings: list[str] = []

        if not spec.backtest_start or not spec.backtest_end:
            return warnings

        try:
            start = datetime.datetime.strptime(spec.backtest_start, "%Y-%m-%d")
            end = datetime.datetime.strptime(spec.backtest_end, "%Y-%m-%d")
            years = (end - start).days / 365.25

            if years < 2:
                warnings.append(SpecValidator.WARNING_BACKTEST_SHORT)
            if years > 20:
                warnings.append(SpecValidator.WARNING_BACKTEST_LONG)
        except ValueError:
            warnings.append("Backtest dates are not valid YYYY-MM-DD format")

        return warnings

    @staticmethod
    def _validate_hypothesis(spec: StrategySpec) -> list[str]:
        errors: list[str] = []
        hypothesis = spec.market_hypothesis.strip() if spec.market_hypothesis else ""
        word_count = len(hypothesis.split())
        if not hypothesis or word_count < 10:
            errors.append(SpecValidator.ERROR_HYPOTHESIS_EMPTY)
        return errors
