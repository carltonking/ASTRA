"""Integration tests — end-to-end flows across multiple modules."""

import ast
import os
import uuid

import pytest

from astra.planner.spec import StrategySpec
from astra.builder.generator import BuildResult
from astra.builder.templates import (
    TEMPLATES_BY_TYPE,
    DEFAULT_PARAMETERS_BY_TYPE,
    CLASS_NAME_BY_TYPE,
)
from astra.graduation import GraduationCertificate, GateResult
from astra.pipeline.runner import PipelineResult
from astra.alpaca.monitor import PerformanceSnapshot, DegradationReport
from astra.export import StrategyPackager, ExportValidationError


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture
def valid_spec():
    return StrategySpec(
        spec_id=str(uuid.uuid4()),
        user_idea="Momentum strategy",
        asset_class="equity",
        symbols=["SPY"],
        timeframe="daily",
        data_source="yfinance",
        strategy_type="momentum",
        market_hypothesis="Stocks with strong momentum continue to outperform",
        entry_conditions=["RSI above 50"],
        exit_conditions=["RSI below 40"],
        target_return=0.15,
        max_drawdown=0.20,
        position_size=0.10,
        max_positions=5,
        stop_loss=0.05,
        take_profit=0.15,
        backtest_start="2020-01-01",
        backtest_end="2023-12-31",
    )


@pytest.fixture
def valid_certificate(valid_spec):
    return GraduationCertificate(
        session_id=valid_spec.spec_id,
        spec_id=valid_spec.spec_id,
        strategy_type=valid_spec.strategy_type,
        symbols=list(valid_spec.symbols),
        optimization_cycles=3,
        gate_results={
            "dsr": GateResult(gate_name="dsr", status="PASSED", actual_value=0.8, threshold_value=0.5, gap=-0.3, evidence=""),
            "annual_return": GateResult(gate_name="annual_return", status="PASSED", actual_value=0.12, threshold_value=0.05, gap=-0.07, evidence=""),
            "max_drawdown": GateResult(gate_name="max_drawdown", status="PASSED", actual_value=0.12, threshold_value=0.25, gap=-0.13, evidence=""),
            "min_trades": GateResult(gate_name="min_trades", status="PASSED", actual_value=45.0, threshold_value=20.0, gap=-25.0, evidence=""),
            "max_degradation": GateResult(gate_name="max_degradation", status="PASSED", actual_value=0.15, threshold_value=0.2, gap=-0.05, evidence=""),
            "min_calendar_days": GateResult(gate_name="min_calendar_days", status="PASSED", actual_value=60.0, threshold_value=30.0, gap=-30.0, evidence=""),
        },
    )


@pytest.fixture
def valid_pipeline_result(valid_spec):
    return PipelineResult(
        pipeline_id=str(uuid.uuid4()),
        spec_id=valid_spec.spec_id,
        cycle_number=1,
        status="DEPLOYED_PAPER",
        leakage_verdict="CLEAN",
        review_board_status="APPROVED",
        cpcv_summary={"mean_sharpe": 0.82, "dsr": 0.55, "overfitting_probability": 0.12, "n_splits": 10},
        backtest_metrics={"mean_sharpe": 0.82, "dsr": 0.55},
        paper_deployment_id=str(uuid.uuid4()),
    )


@pytest.fixture
def valid_snapshot():
    return PerformanceSnapshot(
        deployment_id=str(uuid.uuid4()),
        total_return=0.08,
        annualized_return=0.12,
        sharpe_ratio=0.75,
        max_drawdown=0.10,
        win_rate=0.55,
        total_trades=45,
        days_deployed=60,
        equity_curve=[100000, 101000, 102000, 103000, 104000],
        degradation_report=DegradationReport(
            return_degradation=0.02,
            sharpe_degradation=0.07,
            drawdown_expansion=0.01,
            overall_degradation_score=0.15,
            category="ACCEPTABLE",
            triggers_optimizer=False,
        ),
    )


# ---------------------------------------------------------------------------
# Full export pipeline
# ---------------------------------------------------------------------------


def _sample_strategy_code() -> str:
    return '''"""
A sample momentum strategy.
"""

import pandas as pd


class MomentumStrategy:
    STRATEGY_TYPE = "momentum"
    STRATEGY_HYPOTHESIS = "Momentum persists"

    def __init__(self, lookback_window=126, momentum_threshold=0.05, holding_period=21):
        self.lookback_window = lookback_window
        self.momentum_threshold = momentum_threshold
        self.holding_period = holding_period

    def generate_signals(self, data):
        returns = data["close"].pct_change(periods=self.lookback_window)
        raw_signal = (returns > self.momentum_threshold).astype(int)
        signal = raw_signal.rolling(window=self.holding_period).max().fillna(0).astype(int)
        return signal
'''


class TestExportIntegration:
    """End-to-end: write strategy -> package -> validate -> check demo harness."""

    def _package_strategy(self, tmp_path, spec, cert, pipeline_result, snapshot,
                          strategy_code=None, class_name="MomentumStrategy"):
        if strategy_code is None:
            strategy_code = _sample_strategy_code()
        strategy_file = os.path.join(tmp_path, "original.py")
        with open(strategy_file, "w") as f:
            f.write(strategy_code)

        build_result = BuildResult(
            success=True,
            spec_id=spec.spec_id,
            strategy_file=strategy_file,
            strategy_class_name=class_name,
            initial_parameters={"lookback_window": 126, "momentum_threshold": 0.05, "holding_period": 21},
            parameter_bounds={"lookback_window": (5, 252), "momentum_threshold": (0.01, 0.20), "holding_period": (1, 60)},
        )

        export_dir = os.path.join(tmp_path, "exports")
        packager = StrategyPackager(export_dir)
        pkg = packager.package(build_result, spec, cert, pipeline_result, snapshot)
        return pkg

    def test_full_pipeline_produces_valid_export(
        self, tmp_path, valid_spec, valid_certificate, valid_pipeline_result, valid_snapshot
    ):
        pkg = self._package_strategy(tmp_path, valid_spec, valid_certificate,
                                     valid_pipeline_result, valid_snapshot)

        assert os.path.exists(pkg.strategy_file)
        assert os.path.getsize(pkg.strategy_file) > 0

        with open(pkg.strategy_file) as f:
            content = f.read()
        tree = ast.parse(content)
        assert tree is not None

    def test_export_includes_demo_harness(
        self, tmp_path, valid_spec, valid_certificate, valid_pipeline_result, valid_snapshot
    ):
        pkg = self._package_strategy(tmp_path, valid_spec, valid_certificate,
                                     valid_pipeline_result, valid_snapshot)

        with open(pkg.strategy_file) as f:
            content = f.read()

        assert 'if __name__ == "__main__":' in content
        assert "Demo Mode" in content
        assert "generate_signals" in content
        assert "MomentumStrategy" in content

    def test_export_contains_required_sections(
        self, tmp_path, valid_spec, valid_certificate, valid_pipeline_result, valid_snapshot
    ):
        pkg = self._package_strategy(tmp_path, valid_spec, valid_certificate,
                                     valid_pipeline_result, valid_snapshot)

        with open(pkg.strategy_file) as f:
            content = f.read()

        assert "GRADUATION CERTIFICATE" in content
        assert "STRATEGY_METADATA" in content
        assert "past performance does not predict future results" in content.lower()
        assert "Limitations" in content
        assert "STOP_LOSS" in content
        assert "MAX_POSITION_SIZE" in content
        assert "LOOKBACK_WINDOW" in content

    def test_export_checksum_is_sha256(
        self, tmp_path, valid_spec, valid_certificate, valid_pipeline_result, valid_snapshot
    ):
        pkg = self._package_strategy(tmp_path, valid_spec, valid_certificate,
                                     valid_pipeline_result, valid_snapshot)
        assert len(pkg.checksum) == 64
        import hashlib
        with open(pkg.strategy_file) as f:
            content = f.read()
        expected = hashlib.sha256(content.encode("utf-8")).hexdigest()
        assert pkg.checksum == expected


# ---------------------------------------------------------------------------
# Template rendering integration (no AI involved)
# ---------------------------------------------------------------------------


class TestTemplateRenderingIntegration:
    """Verify all templates render without syntax errors."""

    @pytest.mark.parametrize("strategy_type", list(TEMPLATES_BY_TYPE.keys()))
    def test_template_renders_valid_python(self, strategy_type):
        template = TEMPLATES_BY_TYPE[strategy_type]
        params = DEFAULT_PARAMETERS_BY_TYPE[strategy_type]
        code = template.format(hypothesis="Integration test hypothesis", **params)
        tree = ast.parse(code)
        assert tree is not None
        assert CLASS_NAME_BY_TYPE[strategy_type] in code
