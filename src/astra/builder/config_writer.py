"""Writes AURORA-compatible strategy config YAML from a BuildResult."""

import os
from typing import Any


def _yaml_value(val: Any, indent: int = 0) -> str:
    pad = "  " * indent
    if val is None:
        return "null"
    if isinstance(val, bool):
        return "true" if val else "false"
    if isinstance(val, (int, float)):
        return str(val)
    if isinstance(val, str):
        if any(c in val for c in ": #{}[]&*!|>'\"%@`"):
            return f'"{val}"'
        return val
    if isinstance(val, list):
        if not val:
            return "[]"
        lines: list[str] = []
        for item in val:
            v = _yaml_value(item, indent + 1)
            lines.append(f"{pad}  - {v}")
        return "\n".join(lines)
    if isinstance(val, dict):
        if not val:
            return "{}"
        lines = []
        for k, v in val.items():
            if isinstance(v, dict):
                lines.append(f"{pad}{k}:")
                lines.append(_yaml_value(v, indent + 1))
            elif isinstance(v, list) and len(v) > 0:
                lines.append(f"{pad}{k}:")
                lines.append(_yaml_value(v, indent + 1))
            else:
                lines.append(f"{pad}{k}: {_yaml_value(v, indent + 1)}")
        return "\n".join(lines)
    return str(val)


class AuroraConfigWriter:
    def write(self, build_result: "BuildResult", spec: "StrategySpec") -> str:
        config = {
            "meta": {
                "spec_id": spec.spec_id,
                "strategy_type": spec.strategy_type,
                "strategy_class": build_result.strategy_class_name,
            },
            "parameters": dict(build_result.initial_parameters),
            "parameter_bounds": {
                k: [v[0], v[1]] for k, v in build_result.parameter_bounds.items()
            },
            "risk": {
                "allow_short": False,
                "max_position_size": spec.position_size,
                "max_positions": spec.max_positions,
                "use_margin": False,
                "stop_loss": spec.stop_loss,
                "take_profit": spec.take_profit,
            },
            "backtest": {
                "start": spec.backtest_start,
                "end": spec.backtest_end,
                "data_source": spec.data_source,
                "symbols": list(spec.symbols),
            },
        }

        config_path = os.path.join(
            os.path.dirname(build_result.strategy_file),
            "strategy_config.yaml",
        )
        os.makedirs(os.path.dirname(config_path), exist_ok=True)

        yaml_str = _yaml_value(config)
        with open(config_path, "w") as f:
            f.write(yaml_str)
            f.write("\n")

        return config_path
