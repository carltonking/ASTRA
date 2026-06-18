"""Deterministic strategy compiler and validation hooks."""

import ast
import importlib.util
import py_compile
import sys
import uuid
from dataclasses import dataclass, field
from pathlib import Path

import pandas as pd

from astra.builder.sandbox import BuildSandbox
from astra.builder.templates import BaseStrategy


@dataclass
class CompileReport:
    passed: bool
    syntax_ok: bool = False
    sandbox_ok: bool = False
    import_ok: bool = False
    unit_test_ok: bool = False
    lint_warnings: list[str] = field(default_factory=list)
    type_warnings: list[str] = field(default_factory=list)
    failures: list[str] = field(default_factory=list)


class StrategyCompiler:
    """Compile generated code into importable, sandbox-validated strategy artifact."""

    def __init__(self, sandbox: BuildSandbox | None = None):
        self._sandbox = sandbox or BuildSandbox()

    def compile(self, strategy_file: str, class_name: str) -> CompileReport:
        path = Path(strategy_file)
        report = CompileReport(passed=False)

        try:
            source = path.read_text()
            tree = ast.parse(source)
            report.syntax_ok = True
        except SyntaxError as e:
            report.failures.append(f"Syntax error: {e}")
            return report

        report.lint_warnings.extend(self._lint(tree))
        report.type_warnings.extend(self._type_check(tree, class_name))

        sandbox_result = self._sandbox.validate(strategy_file)
        report.sandbox_ok = sandbox_result.passed
        if not sandbox_result.passed:
            report.failures.extend(sandbox_result.violations)
            return report

        try:
            py_compile.compile(strategy_file, doraise=True)
        except py_compile.PyCompileError as e:
            report.failures.append(f"Compile error: {e.msg}")
            return report

        try:
            strategy_cls = self._import_strategy(strategy_file, class_name)
            report.import_ok = True
            self._run_unit_test(strategy_cls)
            report.unit_test_ok = True
        except Exception as e:
            report.failures.append(f"Validation hook failed: {e}")
            return report

        report.passed = True
        return report

    @staticmethod
    def _lint(tree: ast.AST) -> list[str]:
        warnings: list[str] = []
        for node in ast.walk(tree):
            if isinstance(node, ast.FunctionDef) and node.name == "generate_signals":
                has_return = any(isinstance(n, ast.Return) for n in ast.walk(node))
                if not has_return:
                    warnings.append("generate_signals has no return statement")
        return warnings

    @staticmethod
    def _type_check(tree: ast.AST, class_name: str) -> list[str]:
        warnings: list[str] = []
        class_node = next(
            (n for n in ast.walk(tree) if isinstance(n, ast.ClassDef) and n.name == class_name),
            None,
        )
        if class_node is None:
            return [f"Missing strategy class: {class_name}"]
        methods = {n.name: n for n in class_node.body if isinstance(n, ast.FunctionDef)}
        for method in ("generate_signals", "get_parameters", "get_parameter_bounds"):
            if method not in methods:
                warnings.append(f"Missing method: {method}")
        return warnings

    @staticmethod
    def _import_strategy(strategy_file: str, class_name: str) -> type[BaseStrategy]:
        module_name = f"astra_compiled_{uuid.uuid4().hex}"
        spec = importlib.util.spec_from_file_location(module_name, strategy_file)
        if spec is None or spec.loader is None:
            raise ImportError(f"Cannot load module spec: {strategy_file}")
        mod = importlib.util.module_from_spec(spec)
        sys.modules[module_name] = mod
        try:
            spec.loader.exec_module(mod)
            strategy_cls = getattr(mod, class_name)
            if not issubclass(strategy_cls, BaseStrategy):
                raise TypeError(f"{class_name} must inherit BaseStrategy")
            return strategy_cls
        finally:
            sys.modules.pop(module_name, None)

    @staticmethod
    def _run_unit_test(strategy_cls: type[BaseStrategy]) -> None:
        data = pd.DataFrame(
            {
                "open": [100.0, 101.0, 102.0, 101.0, 103.0] * 80,
                "high": [101.0, 102.0, 103.0, 102.0, 104.0] * 80,
                "low": [99.0, 100.0, 101.0, 100.0, 102.0] * 80,
                "close": [100.0, 101.0, 102.0, 101.0, 103.0] * 80,
                "close_leg1": [100.0, 101.0, 102.0, 101.0, 103.0] * 80,
                "close_leg2": [99.0, 100.0, 100.5, 100.0, 101.0] * 80,
                "volume": [1_000_000, 1_100_000, 900_000, 950_000, 1_200_000] * 80,
            }
        )
        strategy = strategy_cls()
        signals = strategy.generate_signals(data)
        if not isinstance(signals, pd.Series):
            raise TypeError("generate_signals must return pandas.Series")
        if len(signals) != len(data):
            raise ValueError("signals length must match input data length")
        if signals.isna().any():
            raise ValueError("signals must not contain NaN values")
        invalid = set(signals.dropna().astype(int).unique()) - {0, 1}
        if invalid:
            raise ValueError(f"signals contain unsupported values: {sorted(invalid)}")
        params = strategy.get_parameters()
        if not isinstance(params, dict):
            raise TypeError("get_parameters must return dict")
        bounds = strategy.get_parameter_bounds()
        if not isinstance(bounds, dict):
            raise TypeError("get_parameter_bounds must return dict")
