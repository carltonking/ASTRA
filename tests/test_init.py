"""Smoke test for ASTRA project scaffolding."""

import os
import re
import tomllib
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent


def test_all_submodules_importable():
    """All 8 astra submodules must be importable with their public exports."""
    import astra
    import astra.planner
    import astra.builder
    import astra.pipeline
    import astra.alpaca
    import astra.optimizer
    import astra.graduation
    import astra.export
    import astra.ui

    assert astra.__version__ == "0.1.0"

    from astra.planner import PlannerConversation, StrategySpec, SpecValidator, ValidationResult
    assert PlannerConversation is not None
    assert StrategySpec is not None
    assert SpecValidator is not None
    assert ValidationResult is not None


def test_env_example_has_required_vars():
    """.env.example must contain all required environment variables."""
    env_path = PROJECT_ROOT / ".env.example"
    assert env_path.exists(), ".env.example not found"

    content = env_path.read_text()

    required = [
        "ANTHROPIC_API_KEY",
        "APCA_API_KEY_ID",
        "APCA_API_SECRET_KEY",
        "APCA_PAPER_URL",
        "MIN_DSR",
        "MIN_ANNUAL_RETURN",
        "MAX_DRAWDOWN",
        "MIN_TRADES",
        "MAX_DEGRADATION",
        "MIN_CALENDAR_DAYS",
    ]

    for var in required:
        assert var in content, f"Missing env var: {var}"


def test_architecture_doc_exists_and_nonempty():
    """docs/ASTRA_ARCHITECTURE.md must exist and have content."""
    arch_path = PROJECT_ROOT / "docs" / "ASTRA_ARCHITECTURE.md"
    assert arch_path.exists(), "ASTRA_ARCHITECTURE.md not found"
    assert arch_path.stat().st_size > 0, "ASTRA_ARCHITECTURE.md is empty"


def test_pyproject_toml_version():
    """pyproject.toml must have version 0.2.0."""
    toml_path = PROJECT_ROOT / "pyproject.toml"
    assert toml_path.exists(), "pyproject.toml not found"

    with open(toml_path, "rb") as f:
        data = tomllib.load(f)

    assert data["project"]["name"] == "astra-trading-agent"
    assert data["project"]["version"] == "0.2.0"
    assert data["project"]["requires-python"] == ">=3.11"


def test_dependencies_in_pyproject():
    """"pyproject.toml must list all required dependencies."""
    toml_path = PROJECT_ROOT / "pyproject.toml"
    with open(toml_path, "rb") as f:
        data = tomllib.load(f)

    deps = data["project"]["dependencies"]
    dep_names = [d.split(">")[0].split("=")[0].split("@")[0].strip() for d in deps]

    required = [
        "aurora-trading-research",
        "anthropic",
        "fastapi",
        "uvicorn",
        "alpaca-py",
        "websockets",
        "pydantic",
        "python-dotenv",
        "yfinance",
        "pandas",
        "numpy",
    ]

    for r in required:
        assert any(r in d for d in dep_names), f"Missing dependency: {r}"
