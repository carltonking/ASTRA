"""Final safety check — validates exported strategy files before they leave ASTRA."""

import ast
import re
from dataclasses import dataclass, field


class ExportValidationError(Exception):
    ...


@dataclass
class ExportValidationResult:
    passed: bool = False
    checks: dict[str, bool] = field(default_factory=dict)
    failures: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)


_EXPECTED_HEADER_MARKER = "GRADUATION CERTIFICATE"
_STRATEGY_METADATA_MARKER = "STRATEGY_METADATA"
_DISCLAIMER_MARKERS = [
    "past performance does not predict future results",
    "not profitability guarantees",
    "for research purposes only",
]
_LIMITATION_MARKER = "Limitations"
_NETWORK_IMPORTS = {
    "requests", "urllib", "httpx", "aiohttp",
    "websockets", "websocket", "socket",
    "urllib3", "smtplib", "ftplib",
}
_LIVE_MARKERS = [
    "api.alpaca.markets",
    "paper-api.alpaca.markets",
    "live_trading",
    "LIVE_TRADING",
]


class ExportValidator:
    def validate(self, strategy_file: str) -> ExportValidationResult:
        checks: dict[str, bool] = {}
        failures: list[str] = []
        warnings: list[str] = []

        try:
            with open(strategy_file) as f:
                content = f.read()
        except FileNotFoundError:
            return ExportValidationResult(
                passed=False,
                checks={"file_exists": False},
                failures=[f"File not found: {strategy_file}"],
            )

        checks["file_exists"] = True

        try:
            ast.parse(content)
            checks["valid_python"] = True
        except SyntaxError as e:
            checks["valid_python"] = False
            failures.append(f"Invalid Python syntax: {e}")

        no_network = True
        for imp in _NETWORK_IMPORTS:
            pattern = rf"(^|\n)\s*(import\s+{imp}\b|from\s+{imp}\s+import)"
            if re.search(pattern, content, re.MULTILINE):
                no_network = False
                warnings.append(f"Network import detected: {imp}")
        checks["no_network_imports"] = no_network
        if not no_network:
            failures.append("Network imports are not allowed in exported strategies")

        no_astra = "from astra" not in content and "import astra" not in content
        checks["no_astra_imports"] = no_astra
        if not no_astra:
            failures.append("ASTRA imports found in exported strategy (must be self-contained)")

        no_live = all(m not in content for m in _LIVE_MARKERS)
        checks["no_live_references"] = no_live
        if not no_live:
            warnings.append("Live trading references detected")

        has_header = _EXPECTED_HEADER_MARKER in content
        checks["certificate_header"] = has_header
        if not has_header:
            failures.append("Missing GraduationCertificate comment header")

        has_metadata = _STRATEGY_METADATA_MARKER in content
        checks["metadata_dict"] = has_metadata
        if not has_metadata:
            failures.append("Missing STRATEGY_METADATA dict")

        has_disclaimer = any(m.lower() in content.lower() for m in _DISCLAIMER_MARKERS)
        checks["disclaimer"] = has_disclaimer
        if not has_disclaimer:
            failures.append("Missing disclaimer in docstring")

        has_limitations = _LIMITATION_MARKER in content
        checks["limitations"] = has_limitations
        if not has_limitations:
            failures.append("Missing limitations list in docstring")

        passed = len(failures) == 0

        return ExportValidationResult(
            passed=passed,
            checks=checks,
            failures=failures,
            warnings=warnings,
        )
