"""AST-based strategy sandbox — validates generated code safety."""

import ast
from dataclasses import dataclass, field


FORBIDDEN_IMPORTS = {
    "requests",
    "httpx",
    "urllib",
    "socket",
    "subprocess",
    "os",
    "shutil",
    "pathlib",
    "sys",
    "multiprocessing",
    "threading",
}


@dataclass
class SandboxResult:
    passed: bool
    violations: list[str] = field(default_factory=list)


class BuildSandbox:
    def validate(self, strategy_file: str) -> SandboxResult:
        violations: list[str] = []

        with open(strategy_file) as f:
            source = f.read()

        try:
            tree = ast.parse(source)
        except SyntaxError as e:
            return SandboxResult(passed=False, violations=[f"Syntax error: {e}"])

        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                for alias in node.names:
                    root_mod = alias.name.split(".")[0]
                    if root_mod in FORBIDDEN_IMPORTS:
                        violations.append(
                            f"Forbidden import: {alias.name}"
                        )

            elif isinstance(node, ast.ImportFrom):
                if node.module:
                    root_mod = node.module.split(".")[0]
                    if root_mod in FORBIDDEN_IMPORTS:
                        violations.append(
                            f"Forbidden import: {node.module}"
                        )

            elif isinstance(node, ast.Call):
                if isinstance(node.func, ast.Name):
                    if node.func.id in ("eval", "exec", "compile", "__import__"):
                        violations.append(
                            f"Forbidden call: {node.func.id}()"
                        )
                elif isinstance(node.func, ast.Attribute):
                    if node.func.attr in ("eval", "exec", "compile", "__import__"):
                        violations.append(
                            f"Forbidden call: {node.func.attr}()"
                        )

            elif isinstance(node, ast.Return):
                self._check_return_for_short(node, violations)

            elif isinstance(node, ast.Assign):
                if isinstance(node.value, ast.UnaryOp) and isinstance(node.value.op, ast.USub):
                    val = node.value
                    if isinstance(val.operand, ast.Constant) and val.operand.value == 1:
                        violations.append(
                            "Short selling detected (assignment of -1)"
                        )

        return SandboxResult(passed=len(violations) == 0, violations=violations)

    @staticmethod
    def _check_return_for_short(node: ast.Return, violations: list[str]) -> None:
        val = node.value
        if val is None:
            return
        if isinstance(val, ast.UnaryOp) and isinstance(val.op, ast.USub):
            if isinstance(val.operand, ast.Constant) and val.operand.value == 1:
                violations.append(
                    "Short selling detected (return of -1)"
                )
        elif isinstance(val, ast.Constant) and val.value == -1:
            violations.append(
                "Short selling detected (return of -1)"
            )
        elif isinstance(val, ast.IfExp):
            BuildSandbox._check_ifexp_for_short(val, violations)

    @staticmethod
    def _check_ifexp_for_short(node: ast.IfExp, violations: list[str]) -> None:
        for branch in (node.body, node.orelse):
            if isinstance(branch, ast.Constant) and branch.value == -1:
                violations.append(
                    "Short selling detected (conditional return of -1)"
                )
            if isinstance(branch, ast.UnaryOp) and isinstance(branch.op, ast.USub):
                if isinstance(branch.operand, ast.Constant) and branch.operand.value == 1:
                    violations.append(
                        "Short selling detected (conditional return of -1)"
                    )
