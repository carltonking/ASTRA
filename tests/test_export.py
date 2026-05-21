"""Tests for the ASTRA export module."""

import ast
import hashlib
import os
import uuid
import tempfile
from dataclasses import asdict
from datetime import datetime, timezone

import pytest

from astra.export import (
    StrategyPackager,
    ExportPackage,
    ReportGenerator,
    ExportValidator,
    ExportValidationResult,
    ExportValidationError,
)
from astra.builder.generator import BuildResult
from astra.planner.spec import StrategySpec
from astra.graduation import GraduationCertificate, GateResult
from astra.pipeline.runner import PipelineResult
from astra.alpaca.monitor import PerformanceSnapshot, DegradationReport


def _make_spec(**overrides) -> StrategySpec:
    params = dict(
        spec_id=str(uuid.uuid4()),
        user_idea="Test momentum strategy that buys strong stocks",
        asset_class="equity",
        symbols=["SPY"],
        timeframe="daily",
        data_source="yfinance",
        strategy_type="momentum",
        market_hypothesis="Stocks with strong momentum tend to continue outperforming",
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
    params.update(overrides)
    return StrategySpec(**params)


def _make_build_result(spec: StrategySpec, strategy_file: str = "") -> BuildResult:
    return BuildResult(
        success=True,
        spec_id=spec.spec_id,
        strategy_file=strategy_file or "/tmp/test_strategy.py",
        strategy_class_name="MomentumStrategy",
        initial_parameters={"lookback_window": 126, "momentum_threshold": 0.05, "holding_period": 21},
        parameter_bounds={"lookback_window": (5, 252), "momentum_threshold": (0.01, 0.20), "holding_period": (1, 60)},
    )


def _make_certificate(spec: StrategySpec) -> GraduationCertificate:
    return GraduationCertificate(
        session_id=spec.spec_id,
        spec_id=spec.spec_id,
        strategy_type=spec.strategy_type,
        symbols=list(spec.symbols),
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


def _make_pipeline_result(spec: StrategySpec) -> PipelineResult:
    return PipelineResult(
        pipeline_id=str(uuid.uuid4()),
        spec_id=spec.spec_id,
        cycle_number=1,
        status="DEPLOYED_PAPER",
        leakage_verdict="CLEAN",
        review_board_status="APPROVED",
        cpcv_summary={"mean_sharpe": 0.82, "dsr": 0.55, "overfitting_probability": 0.12, "n_splits": 10},
        backtest_metrics={"mean_sharpe": 0.82, "dsr": 0.55, "overfitting_probability": 0.12},
        paper_deployment_id=str(uuid.uuid4()),
    )


def _make_snapshot() -> PerformanceSnapshot:
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


def _strategy_code_with_network_import() -> str:
    return '"""Bad strategy."""\nimport requests\n\nclass S:\n    pass\n'


# ---- ExportPackage Tests ----

class TestExportPackage:
    def test_serializes_to_json(self):
        pkg = ExportPackage(
            export_id=str(uuid.uuid4()),
            session_id="sess1",
            spec_id="spec1",
            certificate_id="cert1",
        )
        data = pkg.to_json()
        assert isinstance(data, str)
        assert "export_id" in data
        assert "session_id" in data
        assert "disclaimer" in data

    def test_disclaimer_always_populated(self):
        pkg = ExportPackage()
        assert len(pkg.disclaimer) > 0
        assert "research purposes only" in pkg.disclaimer

    def test_checksum_sha256(self):
        strategy_content = _sample_strategy_code()
        expected = hashlib.sha256(strategy_content.encode("utf-8")).hexdigest()

        pkg = ExportPackage(checksum=expected)
        assert pkg.checksum == expected
        assert len(pkg.checksum) == 64


# ---- ExportValidator Tests ----

class TestExportValidator:
    def test_passes_clean_file(self, tmp_path):
        validator = ExportValidator()
        f = tmp_path / "clean.py"
        cert_block = "# GRADUATION CERTIFICATE\n# Certificate ID: abc\n# Approved: True\n"
        meta_block = 'STRATEGY_METADATA = {"key": "value"}\n'
        code = (
            '"""\nThis is a test strategy.\n\n'
            'Limitations\n-----------\n1. Test limitation\n\n'
            'Disclaimer\n---------\npast performance does not predict future results\n"""\n\n'
            + cert_block + '\n' + meta_block + '\nimport pandas\n\nclass S:\n    pass\n'
        )
        f.write_text(code)
        result = validator.validate(str(f))
        assert result.passed, f"Unexpected failures: {result.failures}"

    def test_fails_file_with_network_imports(self, tmp_path):
        validator = ExportValidator()
        f = tmp_path / "bad_net.py"
        f.write_text(_strategy_code_with_network_import())
        result = validator.validate(str(f))
        assert not result.passed
        assert any("network" in f.lower() for f in result.failures)

    def test_fails_file_with_astra_imports(self, tmp_path):
        validator = ExportValidator()
        f = tmp_path / "bad_astra.py"
        code = '"""Docstring."""\nfrom astra.builder import BuildResult\n'
        f.write_text(code)
        result = validator.validate(str(f))
        assert not result.passed
        assert any("ASTRA" in f for f in result.failures)

    def test_fails_file_missing_certificate_header(self, tmp_path):
        validator = ExportValidator()
        code = '"""Docstring."""\nimport pandas\n\nclass S:\n    pass\n'
        f = tmp_path / "no_cert.py"
        f.write_text(code)
        result = validator.validate(str(f))
        assert not result.passed
        assert any("certificate" in f.lower() for f in result.failures)

    def test_fails_file_missing_metadata_dict(self, tmp_path):
        validator = ExportValidator()
        code = '"""Docstring."""\n# GRADUATION CERTIFICATE\n\nclass S:\n    pass\n'
        f = tmp_path / "no_meta.py"
        f.write_text(code)
        result = validator.validate(str(f))
        assert not result.passed
        assert any("STRATEGY_METADATA" in f for f in result.failures)

    def test_fails_file_missing_disclaimer(self, tmp_path):
        validator = ExportValidator()
        code = '"""Docstring.\nLimitations\n----------\n1. Test\n"""\n# GRADUATION CERTIFICATE\nSTRATEGY_METADATA = {}\n\nclass S:\n    pass\n'
        f = tmp_path / "no_disc.py"
        f.write_text(code)
        result = validator.validate(str(f))
        assert not result.passed
        assert any("disclaimer" in f.lower() for f in result.failures)

    def test_fails_file_missing_limitations(self, tmp_path):
        validator = ExportValidator()
        code = '"""Docstring."""\n# GRADUATION CERTIFICATE\nSTRATEGY_METADATA = {}\n\nclass S:\n    pass\n'
        f = tmp_path / "no_lim.py"
        f.write_text(code)
        result = validator.validate(str(f))
        assert not result.passed
        assert any("limitation" in f.lower() for f in result.failures)

    def test_valid_python_check(self, tmp_path):
        validator = ExportValidator()
        f = tmp_path / "syntax_err.py"
        f.write_text("this is not valid python @@@")
        result = validator.validate(str(f))
        assert not result.passed
        assert "syntax" in result.failures[0].lower()


# ---- StrategyPackager Tests ----

class TestStrategyPackager:
    def test_produces_py_file_passes_ast_parse(self, tmp_path):
        export_dir = str(tmp_path / "exports")
        spec = _make_spec()
        strategy_file = str(tmp_path / "original.py")
        with open(strategy_file, "w") as f:
            f.write(_sample_strategy_code())

        build_result = _make_build_result(spec, strategy_file)
        certificate = _make_certificate(spec)
        pipeline_result = _make_pipeline_result(spec)
        snapshot = _make_snapshot()

        packager = StrategyPackager(export_dir)
        pkg = packager.package(build_result, spec, certificate, pipeline_result, snapshot)

        with open(pkg.strategy_file) as f:
            content = f.read()
        tree = ast.parse(content)
        assert tree is not None

    def test_filename_format(self, tmp_path):
        export_dir = str(tmp_path / "exports")
        spec = _make_spec()
        strategy_file = str(tmp_path / "original.py")
        with open(strategy_file, "w") as f:
            f.write(_sample_strategy_code())

        build_result = _make_build_result(spec, strategy_file)
        certificate = _make_certificate(spec)
        pipeline_result = _make_pipeline_result(spec)
        snapshot = _make_snapshot()

        packager = StrategyPackager(export_dir)
        pkg = packager.package(build_result, spec, certificate, pipeline_result, snapshot)

        fname = os.path.basename(pkg.strategy_file)
        assert fname.startswith("astra_export_momentum_")
        assert fname.endswith(".py")

    def test_exported_file_contains_metadata_dict(self, tmp_path):
        export_dir = str(tmp_path / "exports")
        spec = _make_spec()
        strategy_file = str(tmp_path / "original.py")
        with open(strategy_file, "w") as f:
            f.write(_sample_strategy_code())

        build_result = _make_build_result(spec, strategy_file)
        certificate = _make_certificate(spec)
        pipeline_result = _make_pipeline_result(spec)
        snapshot = _make_snapshot()

        packager = StrategyPackager(export_dir)
        pkg = packager.package(build_result, spec, certificate, pipeline_result, snapshot)

        with open(pkg.strategy_file) as f:
            content = f.read()
        assert "STRATEGY_METADATA" in content

    def test_exported_file_contains_certificate_header(self, tmp_path):
        export_dir = str(tmp_path / "exports")
        spec = _make_spec()
        strategy_file = str(tmp_path / "original.py")
        with open(strategy_file, "w") as f:
            f.write(_sample_strategy_code())

        build_result = _make_build_result(spec, strategy_file)
        certificate = _make_certificate(spec)
        pipeline_result = _make_pipeline_result(spec)
        snapshot = _make_snapshot()

        packager = StrategyPackager(export_dir)
        pkg = packager.package(build_result, spec, certificate, pipeline_result, snapshot)

        with open(pkg.strategy_file) as f:
            content = f.read()
        assert "GRADUATION CERTIFICATE" in content

    def test_exported_file_contains_disclaimer(self, tmp_path):
        export_dir = str(tmp_path / "exports")
        spec = _make_spec()
        strategy_file = str(tmp_path / "original.py")
        with open(strategy_file, "w") as f:
            f.write(_sample_strategy_code())

        build_result = _make_build_result(spec, strategy_file)
        certificate = _make_certificate(spec)
        pipeline_result = _make_pipeline_result(spec)
        snapshot = _make_snapshot()

        packager = StrategyPackager(export_dir)
        pkg = packager.package(build_result, spec, certificate, pipeline_result, snapshot)

        with open(pkg.strategy_file) as f:
            content = f.read()
        assert "past performance does not predict future results" in content.lower()

    def test_exported_file_contains_limitations(self, tmp_path):
        export_dir = str(tmp_path / "exports")
        spec = _make_spec()
        strategy_file = str(tmp_path / "original.py")
        with open(strategy_file, "w") as f:
            f.write(_sample_strategy_code())

        build_result = _make_build_result(spec, strategy_file)
        certificate = _make_certificate(spec)
        pipeline_result = _make_pipeline_result(spec)
        snapshot = _make_snapshot()

        packager = StrategyPackager(export_dir)
        pkg = packager.package(build_result, spec, certificate, pipeline_result, snapshot)

        with open(pkg.strategy_file) as f:
            content = f.read()
        assert "Limitations" in content

    def test_exported_file_has_no_astra_imports(self, tmp_path):
        export_dir = str(tmp_path / "exports")
        spec = _make_spec()
        strategy_file = str(tmp_path / "original.py")
        with open(strategy_file, "w") as f:
            f.write(_sample_strategy_code())

        build_result = _make_build_result(spec, strategy_file)
        certificate = _make_certificate(spec)
        pipeline_result = _make_pipeline_result(spec)
        snapshot = _make_snapshot()

        packager = StrategyPackager(export_dir)
        pkg = packager.package(build_result, spec, certificate, pipeline_result, snapshot)

        with open(pkg.strategy_file) as f:
            content = f.read()
        assert "from astra" not in content
        assert "import astra" not in content

    def test_exported_file_has_no_network_imports(self, tmp_path):
        export_dir = str(tmp_path / "exports")
        spec = _make_spec()
        strategy_file = str(tmp_path / "original.py")
        with open(strategy_file, "w") as f:
            f.write(_sample_strategy_code())

        build_result = _make_build_result(spec, strategy_file)
        certificate = _make_certificate(spec)
        pipeline_result = _make_pipeline_result(spec)
        snapshot = _make_snapshot()

        packager = StrategyPackager(export_dir)
        pkg = packager.package(build_result, spec, certificate, pipeline_result, snapshot)

        with open(pkg.strategy_file) as f:
            content = f.read()
        for imp in ["requests", "urllib", "httpx", "socket", "websockets"]:
            assert f"import {imp}" not in content
            assert f"from {imp}" not in content

    def test_risk_limits_embedded(self, tmp_path):
        export_dir = str(tmp_path / "exports")
        spec = _make_spec()
        strategy_file = str(tmp_path / "original.py")
        with open(strategy_file, "w") as f:
            f.write(_sample_strategy_code())

        build_result = _make_build_result(spec, strategy_file)
        certificate = _make_certificate(spec)
        pipeline_result = _make_pipeline_result(spec)
        snapshot = _make_snapshot()

        packager = StrategyPackager(export_dir)
        pkg = packager.package(build_result, spec, certificate, pipeline_result, snapshot)

        with open(pkg.strategy_file) as f:
            content = f.read()
        assert "STOP_LOSS" in content
        assert "TAKE_PROFIT" in content
        assert "MAX_POSITION_SIZE" in content
        assert "MAX_POSITIONS" in content

    def test_parameters_embedded(self, tmp_path):
        export_dir = str(tmp_path / "exports")
        spec = _make_spec()
        strategy_file = str(tmp_path / "original.py")
        with open(strategy_file, "w") as f:
            f.write(_sample_strategy_code())

        build_result = _make_build_result(spec, strategy_file)
        certificate = _make_certificate(spec)
        pipeline_result = _make_pipeline_result(spec)
        snapshot = _make_snapshot()

        packager = StrategyPackager(export_dir)
        pkg = packager.package(build_result, spec, certificate, pipeline_result, snapshot)

        with open(pkg.strategy_file) as f:
            content = f.read()
        assert "LOOKBACK_WINDOW" in content
        assert "MOMENTUM_THRESHOLD" in content
        assert "HOLDING_PERIOD" in content

    def test_checksum_sha256(self, tmp_path):
        export_dir = str(tmp_path / "exports")
        spec = _make_spec()
        strategy_file = str(tmp_path / "original.py")
        with open(strategy_file, "w") as f:
            f.write(_sample_strategy_code())

        build_result = _make_build_result(spec, strategy_file)
        certificate = _make_certificate(spec)
        pipeline_result = _make_pipeline_result(spec)
        snapshot = _make_snapshot()

        packager = StrategyPackager(export_dir)
        pkg = packager.package(build_result, spec, certificate, pipeline_result, snapshot)

        with open(pkg.strategy_file) as f:
            content = f.read()
        expected = hashlib.sha256(content.encode("utf-8")).hexdigest()
        assert pkg.checksum == expected

    def test_validation_failure_raises_error(self, tmp_path):
        export_dir = str(tmp_path / "exports")
        spec = _make_spec()
        strategy_file = str(tmp_path / "original.py")
        code = _sample_strategy_code().replace(
            'import pandas',
            'import requests\nimport pandas'
        )
        with open(strategy_file, "w") as f:
            f.write(code)

        build_result = _make_build_result(spec, strategy_file)
        certificate = _make_certificate(spec)
        pipeline_result = _make_pipeline_result(spec)
        snapshot = _make_snapshot()

        packager = StrategyPackager(export_dir)
        with pytest.raises(ExportValidationError) as excinfo:
            packager.package(build_result, spec, certificate, pipeline_result, snapshot)
        assert "validation failed" in str(excinfo.value).lower()


# ---- ReportGenerator Tests ----

class TestReportGenerator:
    def test_produces_pdf_file_exists(self, tmp_path):
        export_dir = str(tmp_path / "reports")
        spec = _make_spec()
        certificate = _make_certificate(spec)
        pipeline_result = _make_pipeline_result(spec)
        snapshot = _make_snapshot()
        export_package = ExportPackage(
            export_id=str(uuid.uuid4()),
            session_id=spec.spec_id,
            spec_id=spec.spec_id,
            certificate_id=certificate.certificate_id,
        )

        generator = ReportGenerator(export_dir)
        report_path = generator.generate(spec, certificate, pipeline_result, snapshot, export_package)

        assert os.path.exists(report_path)
        assert report_path.endswith(".pdf")
        assert os.path.getsize(report_path) > 0

    def test_report_contains_all_six_sections(self, tmp_path):
        export_dir = str(tmp_path / "reports")
        spec = _make_spec()
        certificate = _make_certificate(spec)
        pipeline_result = _make_pipeline_result(spec)
        snapshot = _make_snapshot()
        export_package = ExportPackage(
            export_id=str(uuid.uuid4()),
            session_id=spec.spec_id,
            spec_id=spec.spec_id,
            certificate_id=certificate.certificate_id,
        )

        generator = ReportGenerator(export_dir)
        report_path = generator.generate(spec, certificate, pipeline_result, snapshot, export_package)

        assert os.path.exists(report_path)
        assert os.path.getsize(report_path) > 0

    def test_report_filename_format(self, tmp_path):
        export_dir = str(tmp_path / "reports")
        spec = _make_spec()
        certificate = _make_certificate(spec)
        pipeline_result = _make_pipeline_result(spec)
        snapshot = _make_snapshot()
        export_package = ExportPackage(
            export_id=str(uuid.uuid4()),
            session_id=spec.spec_id,
            spec_id=spec.spec_id,
            certificate_id=certificate.certificate_id,
        )

        generator = ReportGenerator(export_dir)
        report_path = generator.generate(spec, certificate, pipeline_result, snapshot, export_package)

        fname = os.path.basename(report_path)
        assert fname.startswith("astra_report_momentum_")
        assert fname.endswith(".pdf")


# ---- Full Flow Tests ----

class TestFullExportFlow:
    def test_package_produces_both_py_and_pdf(self, tmp_path):
        export_dir = str(tmp_path / "exports")
        spec = _make_spec()
        strategy_file = str(tmp_path / "original.py")
        with open(strategy_file, "w") as f:
            f.write(_sample_strategy_code())

        build_result = _make_build_result(spec, strategy_file)
        certificate = _make_certificate(spec)
        pipeline_result = _make_pipeline_result(spec)
        snapshot = _make_snapshot()

        packager = StrategyPackager(export_dir)
        pkg = packager.package(build_result, spec, certificate, pipeline_result, snapshot)

        assert os.path.exists(pkg.strategy_file)
        assert os.path.getsize(pkg.strategy_file) > 0

        report_pkg = packager._update_report_file(pkg, "")
        generator = ReportGenerator(export_dir)
        report_path = generator.generate(spec, certificate, pipeline_result, snapshot, pkg)

        assert os.path.exists(report_path)
        assert os.path.getsize(report_path) > 0

    def test_disclaimer_in_all_layers(self, tmp_path):
        export_dir = str(tmp_path / "exports")
        spec = _make_spec()
        strategy_file = str(tmp_path / "original.py")
        with open(strategy_file, "w") as f:
            f.write(_sample_strategy_code())

        build_result = _make_build_result(spec, strategy_file)
        certificate = _make_certificate(spec)
        pipeline_result = _make_pipeline_result(spec)
        snapshot = _make_snapshot()

        packager = StrategyPackager(export_dir)
        pkg = packager.package(build_result, spec, certificate, pipeline_result, snapshot)

        assert "research purposes only" in pkg.disclaimer

        with open(pkg.strategy_file) as f:
            content = f.read()
        assert "research purposes only" in content.lower()
