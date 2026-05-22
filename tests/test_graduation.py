"""Tests for the ASTRA graduation module."""

import json
import os
import uuid
from dataclasses import asdict
from datetime import datetime, timezone, timedelta

import pytest

from astra.graduation import (
    GraduationGates,
    GraduationCertificate,
    GraduationTracker,
    GateCheckResult,
    GateResult,
    GraduationError,
)
from astra.alpaca.monitor import PerformanceSnapshot, DegradationReport
from astra.pipeline.runner import PipelineResult
from astra.optimizer.history import OptimizationHistory


def _make_snapshot(**overrides) -> PerformanceSnapshot:
    params = dict(
        deployment_id=str(uuid.uuid4()),
        total_return=0.08,
        annualized_return=0.12,
        sharpe_ratio=1.8,
        max_drawdown=0.10,
        win_rate=0.55,
        total_trades=45,
        days_deployed=60,
        equity_curve=[100000.0],
        degradation_report=DegradationReport(
            return_degradation=0.02,
            sharpe_degradation=0.07,
            drawdown_expansion=0.01,
            overall_degradation_score=0.15,
            category="ACCEPTABLE",
            triggers_optimizer=False,
        ),
    )
    params.update(overrides)
    return PerformanceSnapshot(**params)


def _failing_snapshot() -> PerformanceSnapshot:
    return PerformanceSnapshot(
        deployment_id=str(uuid.uuid4()),
        total_return=-0.05,
        annualized_return=-0.02,
        sharpe_ratio=-0.3,
        max_drawdown=0.35,
        win_rate=0.30,
        total_trades=5,
        days_deployed=2,
        equity_curve=[100000.0],
        degradation_report=DegradationReport(
            return_degradation=0.3,
            sharpe_degradation=0.8,
            drawdown_expansion=0.2,
            overall_degradation_score=0.6,
            category="SEVERE",
            triggers_optimizer=True,
        ),
    )


def _make_pipeline_result(**overrides) -> PipelineResult:
    params = dict(
        pipeline_id=str(uuid.uuid4()),
        spec_id=str(uuid.uuid4()),
        cycle_number=1,
        status="DEPLOYED_PAPER",
        leakage_verdict="CLEAN",
        review_board_status="APPROVED",
        cpcv_summary={"mean_sharpe": 1.8, "dsr": 1.6, "overfitting_probability": 0.08, "n_splits": 10},
        backtest_metrics={"mean_sharpe": 1.8, "dsr": 1.6, "overfitting_probability": 0.08},
        paper_deployment_id=str(uuid.uuid4()),
    )
    params.update(overrides)
    return PipelineResult(**params)


# ---- GraduationGates Tests ----

class TestGraduationGates:
    def test_loads_default_thresholds(self):
        gates = GraduationGates()
        assert gates._thresholds["dsr"] == 1.5
        assert gates._thresholds["annual_return"] == 0.05
        assert gates._thresholds["max_drawdown"] == 0.20
        assert gates._thresholds["min_trades"] == 20
        assert gates._thresholds["max_degradation"] == 0.2
        assert gates._thresholds["min_calendar_days"] == 5

    def test_loads_from_config(self):
        gates = GraduationGates(config={"MIN_DSR": 2.0, "MIN_TRADES": 50})
        assert gates._thresholds["dsr"] == 2.0
        assert gates._thresholds["min_trades"] == 50
        assert gates._thresholds["annual_return"] == 0.05

    def test_raises_on_negative_threshold(self):
        with pytest.raises(ValueError):
            GraduationGates(config={"MIN_DSR": -1.0})

    def test_passes_when_all_gates_met(self):
        gates = GraduationGates()
        snapshot = _make_snapshot()
        pipeline_result = _make_pipeline_result()
        result = gates.check(snapshot, pipeline_result)

        assert result.overall_status == "GRADUATED"
        assert result.gates_passed == 6
        assert result.gates_total == 6
        assert result.closest_to_passing is None

    def test_fails_when_dsr_below_threshold(self):
        gates = GraduationGates(config={"MIN_DSR": 10.0})
        snapshot = _make_snapshot()
        pipeline_result = _make_pipeline_result(
            cpcv_summary={"mean_sharpe": 0.5, "dsr": 0.3},
            backtest_metrics={"mean_sharpe": 0.5, "dsr": 0.3},
        )
        result = gates.check(snapshot, pipeline_result)
        assert result.overall_status == "NOT_READY"
        assert result.gates["dsr"].status == "FAILED"

    def test_fails_when_return_below_threshold(self):
        gates = GraduationGates()
        snapshot = _make_snapshot(annualized_return=-0.1)
        pipeline_result = _make_pipeline_result()
        result = gates.check(snapshot, pipeline_result)
        assert result.overall_status == "NOT_READY"
        assert result.gates["annual_return"].status == "FAILED"

    def test_fails_when_drawdown_exceeds_threshold(self):
        gates = GraduationGates()
        snapshot = _make_snapshot(max_drawdown=0.50)
        pipeline_result = _make_pipeline_result()
        result = gates.check(snapshot, pipeline_result)
        assert result.overall_status == "NOT_READY"
        assert result.gates["max_drawdown"].status == "FAILED"

    def test_fails_when_trades_below_threshold(self):
        gates = GraduationGates()
        snapshot = _make_snapshot(total_trades=3)
        pipeline_result = _make_pipeline_result()
        result = gates.check(snapshot, pipeline_result)
        assert result.overall_status == "NOT_READY"
        assert result.gates["min_trades"].status == "FAILED"

    def test_fails_when_degradation_exceeds_threshold(self):
        gates = GraduationGates()
        snapshot = _make_snapshot(
            degradation_report=DegradationReport(
                overall_degradation_score=0.8, category="SEVERE", triggers_optimizer=True,
            )
        )
        pipeline_result = _make_pipeline_result()
        result = gates.check(snapshot, pipeline_result)
        assert result.overall_status == "NOT_READY"
        assert result.gates["max_degradation"].status == "FAILED"

    def test_fails_when_days_below_threshold(self):
        gates = GraduationGates()
        snapshot = _make_snapshot(days_deployed=1)
        pipeline_result = _make_pipeline_result()
        result = gates.check(snapshot, pipeline_result)
        assert result.overall_status == "NOT_READY"
        assert result.gates["min_calendar_days"].status == "FAILED"

    def test_gap_negative_when_passed(self):
        gates = GraduationGates()
        snapshot = _make_snapshot(annualized_return=0.15)
        pipeline_result = _make_pipeline_result()
        result = gates.check(snapshot, pipeline_result)
        assert result.gates["annual_return"].gap < 0

    def test_gap_positive_when_failed(self):
        gates = GraduationGates()
        snapshot = _make_snapshot(annualized_return=-0.10)
        pipeline_result = _make_pipeline_result()
        result = gates.check(snapshot, pipeline_result)
        assert result.gates["annual_return"].gap > 0

    def test_gap_calculation_correct(self):
        gates = GraduationGates(config={"MIN_ANNUAL_RETURN": 0.10})
        snapshot = _make_snapshot(annualized_return=0.07)
        pipeline_result = _make_pipeline_result()
        result = gates.check(snapshot, pipeline_result)
        assert result.gates["annual_return"].gap == pytest.approx(0.03, abs=0.001)
        assert result.gates["annual_return"].status == "FAILED"

    def test_closest_to_passing_correct(self):
        gates = GraduationGates()
        snapshot = _make_snapshot(
            annualized_return=0.03,
            total_trades=15,
            days_deployed=10,
        )
        pipeline_result = _make_pipeline_result(
            cpcv_summary={"mean_sharpe": 0.3, "dsr": 0.2},
            backtest_metrics={"mean_sharpe": 0.3, "dsr": 0.2},
        )
        result = gates.check(snapshot, pipeline_result)
        assert result.overall_status == "NOT_READY"
        assert result.closest_to_passing is not None

    def test_all_failures(self):
        gates = GraduationGates(config={"MIN_DSR": 100, "MIN_ANNUAL_RETURN": 100,
                                         "MAX_DRAWDOWN": 0.001, "MIN_TRADES": 1000,
                                         "MAX_DEGRADATION": 0.001, "MIN_CALENDAR_DAYS": 1000})
        snapshot = _failing_snapshot()
        pipeline_result = _make_pipeline_result(
            cpcv_summary={"mean_sharpe": 0.0, "dsr": 0.0},
            backtest_metrics={"mean_sharpe": 0.0, "dsr": 0.0},
        )
        result = gates.check(snapshot, pipeline_result)
        assert result.gates_passed == 0
        assert result.overall_status == "NOT_READY"

    def test_disclaimer_populated(self):
        gates = GraduationGates()
        result = gates.check(_make_snapshot(), _make_pipeline_result())
        assert len(result.disclaimer) > 0
        assert "research purposes only" in result.disclaimer

    def test_evidence_contains_values(self):
        gates = GraduationGates()
        result = gates.check(_make_snapshot(), _make_pipeline_result())
        for g in result.gates.values():
            assert "threshold" in g.evidence
            assert len(g.evidence) > 10

    def test_drawdown_gap_reversed(self):
        gates = GraduationGates()
        snapshot = _make_snapshot(max_drawdown=0.05)
        result = gates.check(snapshot, _make_pipeline_result())
        assert result.gates["max_drawdown"].status == "PASSED"
        assert result.gates["max_drawdown"].gap < 0

    def test_plain_english_summary(self):
        gates = GraduationGates()
        result = gates.check(_make_snapshot(), _make_pipeline_result())
        assert "6/6" in result.plain_english_summary
        assert "GRADUATED" in result.plain_english_summary


# ---- GateCheckResult Tests ----

class TestGateCheckResult:
    def test_serializes_to_dict(self):
        result = GateCheckResult(
            overall_status="GRADUATED",
            gates={"a": GateResult(gate_name="a", status="PASSED")},
            gates_passed=1,
            gates_total=6,
            closest_to_passing=None,
            plain_english_summary="1/6 passed",
        )
        data = asdict(result)
        assert data["overall_status"] == "GRADUATED"
        assert "a" in data["gates"]

    def test_defaults(self):
        result = GateCheckResult()
        assert result.overall_status == "NOT_READY"
        assert result.gates_total == 6
        assert result.gates_passed == 0
        assert result.disclaimer is not None


# ---- GraduationCertificate Tests ----

class TestGraduationCertificate:
    def test_has_five_immutable_limitations(self):
        cert = GraduationCertificate()
        assert len(cert.limitations) == 5
        assert "Past performance does not guarantee future results" in cert.limitations
        assert "This strategy was validated only in specific market conditions" in cert.limitations
        assert "Paper trading does not account for slippage, fees, or liquidity constraints" in cert.limitations
        assert "Live trading may produce substantially different results" in cert.limitations
        assert "This certificate does not constitute financial advice" in cert.limitations

    def test_auto_generates_certificate_id(self):
        cert = GraduationCertificate()
        assert len(cert.certificate_id) > 0

    def test_from_gate_check_raises_when_not_graduated(self):
        gate_result = GateCheckResult(overall_status="NOT_READY", gates_passed=3)
        snapshot = _make_snapshot()
        pipeline_result = _make_pipeline_result()
        with pytest.raises(GraduationError) as excinfo:
            GraduationCertificate.from_gate_check(
                session_id="test",
                gate_result=gate_result,
                snapshot=snapshot,
                pipeline_result=pipeline_result,
                optimization_cycles=3,
            )
        assert "GRADUATED" in str(excinfo.value)

    def test_from_gate_check_succeeds_when_graduated(self):
        gates = GraduationGates()
        snapshot = _make_snapshot()
        pipeline_result = _make_pipeline_result()
        gate_result = gates.check(snapshot, pipeline_result)

        cert = GraduationCertificate.from_gate_check(
            session_id="test-session",
            gate_result=gate_result,
            snapshot=snapshot,
            pipeline_result=pipeline_result,
            optimization_cycles=5,
        )
        assert cert.session_id == "test-session"
        assert cert.optimization_cycles == 5
        assert len(cert.gate_results) == 6
        assert len(cert.limitations) == 5

    def test_to_json_roundtrip(self):
        gates = GraduationGates()
        snapshot = _make_snapshot()
        pipeline_result = _make_pipeline_result()
        gate_result = gates.check(snapshot, pipeline_result)
        cert = GraduationCertificate.from_gate_check(
            session_id="roundtrip",
            gate_result=gate_result,
            snapshot=snapshot,
            pipeline_result=pipeline_result,
            optimization_cycles=3,
        )
        json_str = cert.to_json()
        restored = GraduationCertificate.from_json(json_str)
        assert restored.certificate_id == cert.certificate_id
        assert restored.session_id == cert.session_id
        assert len(restored.gate_results) == 6
        assert restored.limitations == cert.limitations

    def test_to_text_block_contains_all_limitations(self):
        cert = GraduationCertificate()
        block = cert.to_text_block()
        for lim in cert.limitations:
            assert lim in block

    def test_to_text_block_contains_certificate_id(self):
        cert = GraduationCertificate()
        block = cert.to_text_block()
        assert cert.certificate_id in block
        assert "GRADUATION CERTIFICATE" in block

    def test_to_text_block_contains_disclaimer(self):
        cert = GraduationCertificate()
        block = cert.to_text_block()
        assert "profitability guarantees" in block
        assert "past performance" in block.lower()

    def test_certificate_from_json_with_no_gate_results(self):
        cert = GraduationCertificate()
        json_str = cert.to_json()
        restored = GraduationCertificate.from_json(json_str)
        assert restored.certificate_id == cert.certificate_id
        assert len(restored.limitations) == 5


# ---- GraduationTracker Tests ----

class TestGraduationTracker:
    def test_records_check_correctly(self):
        tracker = GraduationTracker(session_id="test")
        gate_result = GateCheckResult(
            overall_status="NOT_READY",
            gates_passed=3,
            gates_total=6,
            gates={"dsr": GateResult(gate_name="dsr", status="PASSED")},
        )
        tracker.record_check(1, gate_result)
        assert len(tracker.history) == 1
        assert tracker.history[0]["cycle_number"] == 1
        assert tracker.history[0]["gates_passed"] == 3

    def test_rejects_duplicate_cycle(self):
        tracker = GraduationTracker(session_id="test")
        gate_result = GateCheckResult(gates_passed=3)
        tracker.record_check(1, gate_result)
        with pytest.raises(ValueError, match="already recorded"):
            tracker.record_check(1, gate_result)

    def test_is_graduated_false_initially(self):
        tracker = GraduationTracker(session_id="test")
        assert tracker.is_graduated() is False

    def test_is_graduated_true_after_issuing(self):
        tracker = GraduationTracker(session_id="test")
        snapshot = _make_snapshot()
        pipeline_result = _make_pipeline_result()
        gates_checker = GraduationGates()
        gate_result = gates_checker.check(snapshot, pipeline_result)

        tracker.record_check(1, gate_result)
        tracker.issue_certificate(snapshot, pipeline_result, 3)
        assert tracker.is_graduated() is True

    def test_get_certificate_returns_none_before_issuing(self):
        tracker = GraduationTracker(session_id="test")
        assert tracker.get_certificate() is None

    def test_get_certificate_returns_certificate_after_issuing(self):
        tracker = GraduationTracker(session_id="test")
        snapshot = _make_snapshot()
        pipeline_result = _make_pipeline_result()
        gates_checker = GraduationGates()
        gate_result = gates_checker.check(snapshot, pipeline_result)

        tracker.record_check(1, gate_result)
        cert = tracker.issue_certificate(snapshot, pipeline_result, 3)
        assert tracker.get_certificate() is cert

    def test_cannot_issue_certificate_twice(self):
        tracker = GraduationTracker(session_id="test")
        snapshot = _make_snapshot()
        pipeline_result = _make_pipeline_result()
        gates_checker = GraduationGates()
        gate_result = gates_checker.check(snapshot, pipeline_result)

        tracker.record_check(1, gate_result)
        tracker.issue_certificate(snapshot, pipeline_result, 3)
        with pytest.raises(GraduationError, match="already been issued"):
            tracker.issue_certificate(snapshot, pipeline_result, 3)

    def test_cannot_issue_without_graduated_check(self):
        tracker = GraduationTracker(session_id="test")
        snapshot = _make_snapshot()
        pipeline_result = _make_pipeline_result()

        gate_result = GateCheckResult(overall_status="NOT_READY", gates_passed=2, gates_total=6)
        tracker.record_check(1, gate_result)
        with pytest.raises(GraduationError, match="Cannot issue certificate"):
            tracker.issue_certificate(snapshot, pipeline_result, 3)

    def test_cannot_issue_with_no_history(self):
        tracker = GraduationTracker(session_id="test")
        snapshot = _make_snapshot()
        pipeline_result = _make_pipeline_result()
        with pytest.raises(GraduationError, match="No gate checks recorded"):
            tracker.issue_certificate(snapshot, pipeline_result, 3)

    def test_progress_over_time(self):
        tracker = GraduationTracker(session_id="test")
        tracker.record_check(1, GateCheckResult(overall_status="NOT_READY", gates_passed=2))
        tracker.record_check(2, GateCheckResult(overall_status="NOT_READY", gates_passed=4))
        tracker.record_check(3, GateCheckResult(overall_status="GRADUATED", gates_passed=6))

        progress = tracker.progress_over_time()
        assert len(progress) == 3
        assert progress[0]["cycle"] == 1
        assert progress[0]["gates_passed"] == 2
        assert progress[0]["overall_status"] == "NOT_READY"
        assert progress[2]["gates_passed"] == 6
        assert progress[2]["overall_status"] == "GRADUATED"

    def test_gate_trend(self):
        tracker = GraduationTracker(session_id="test")

        gates1 = {"dsr": GateResult(gate_name="dsr", status="FAILED", actual_value=0.5, threshold_value=1.5, gap=1.0)}
        tracker.record_check(1, GateCheckResult(gates=gates1, gates_passed=0))

        gates2 = {"dsr": GateResult(gate_name="dsr", status="FAILED", actual_value=1.0, threshold_value=1.5, gap=0.5)}
        tracker.record_check(2, GateCheckResult(gates=gates2, gates_passed=0))

        gates3 = {"dsr": GateResult(gate_name="dsr", status="PASSED", actual_value=2.0, threshold_value=1.5, gap=-0.5)}
        tracker.record_check(3, GateCheckResult(gates=gates3, gates_passed=6))

        trend = tracker.gate_trend("dsr")
        assert len(trend) == 3
        assert trend[0]["cycle"] == 1
        assert trend[0]["actual_value"] == 0.5
        assert trend[0]["passed"] is False
        assert trend[2]["passed"] is True
        assert trend[2]["actual_value"] == 2.0

    def test_gate_trend_empty_for_unknown_gate(self):
        tracker = GraduationTracker(session_id="test")
        tracker.record_check(1, GateCheckResult(gates={}, gates_passed=0))
        assert tracker.gate_trend("nonexistent") == []

    def test_save_and_load_roundtrip(self, tmp_path):
        snapshot = _make_snapshot()
        pipeline_result = _make_pipeline_result()

        gates_checker = GraduationGates()
        gate_result = gates_checker.check(snapshot, pipeline_result)

        tracker = GraduationTracker(session_id="save-load-test")
        tracker.record_check(1, GateCheckResult(overall_status="NOT_READY", gates_passed=3))
        tracker.record_check(2, gate_result)
        tracker.issue_certificate(snapshot, pipeline_result, 5)

        store_dir = str(tmp_path / "graduation_store")
        tracker.save(store_dir)

        loaded = GraduationTracker.load("save-load-test", store_dir)
        assert loaded.session_id == "save-load-test"
        assert len(loaded.history) == 2
        assert loaded.is_graduated() is True
        assert loaded.get_certificate() is not None
        assert loaded.get_certificate().certificate_id == tracker.get_certificate().certificate_id
        assert loaded.get_certificate().optimization_cycles == 5

    def test_load_raises_when_no_save(self):
        with pytest.raises(FileNotFoundError):
            GraduationTracker.load("nonexistent", "/tmp/no_such_dir")

    def test_save_without_certificate(self, tmp_path):
        tracker = GraduationTracker(session_id="no-cert")
        tracker.record_check(1, GateCheckResult(overall_status="NOT_READY", gates_passed=2))

        store_dir = str(tmp_path / "store")
        tracker.save(store_dir)

        loaded = GraduationTracker.load("no-cert", store_dir)
        assert loaded.is_graduated() is False
        assert loaded.get_certificate() is None
        assert len(loaded.history) == 1


# ---- Edge Case Tests ----

class TestEdgeCases:
    def test_snapshot_with_zero_trades(self):
        gates = GraduationGates()
        snapshot = _make_snapshot(total_trades=0, days_deployed=0)
        pipeline_result = _make_pipeline_result(
            cpcv_summary={"mean_sharpe": 0.0, "dsr": 0.0},
            backtest_metrics={"mean_sharpe": 0.0, "dsr": 0.0},
        )
        result = gates.check(snapshot, pipeline_result)
        assert result.overall_status == "NOT_READY"
        assert result.gates["min_trades"].status == "FAILED"
        assert result.gates["min_calendar_days"].status == "FAILED"

    def test_no_degradation_report(self):
        gates = GraduationGates()
        snapshot = _make_snapshot(degradation_report=None)
        pipeline_result = _make_pipeline_result()
        result = gates.check(snapshot, pipeline_result)
        assert result.gates["max_degradation"].status == "FAILED"

    def test_no_cpcv_summary(self):
        gates = GraduationGates()
        snapshot = _make_snapshot()
        pipeline_result = _make_pipeline_result(cpcv_summary=None, backtest_metrics=None)
        result = gates.check(snapshot, pipeline_result)
        assert result.gates["dsr"].status == "FAILED"
        assert result.gates["dsr"].actual_value == 0.0

    def test_empty_history_progress(self):
        tracker = GraduationTracker(session_id="empty")
        assert tracker.progress_over_time() == []
        assert tracker.gate_trend("anything") == []

    def test_gate_result_defaults(self):
        gr = GateResult()
        assert gr.status == "FAILED"
        assert gr.gap == 0.0


# ---- End-to-End Graduation Flow ----

class TestGraduationEndToEnd:
    def test_full_graduation_to_export_flow(self, tmp_path):
        tracker = GraduationTracker(session_id="e2e-test")

        snapshot = PerformanceSnapshot(
            deployment_id=str(uuid.uuid4()),
            total_return=0.12,
            annualized_return=0.18,
            sharpe_ratio=2.0,
            max_drawdown=0.08,
            win_rate=0.60,
            total_trades=45,
            days_deployed=60,
            equity_curve=[100000.0, 105000.0, 110000.0, 112000.0],
            degradation_report=DegradationReport(
                return_degradation=0.01,
                sharpe_degradation=0.05,
                drawdown_expansion=0.01,
                overall_degradation_score=0.12,
                category="ACCEPTABLE",
                triggers_optimizer=False,
            ),
        )

        pipeline_result = PipelineResult(
            pipeline_id=str(uuid.uuid4()),
            spec_id=str(uuid.uuid4()),
            cycle_number=1,
            status="DEPLOYED_PAPER",
            leakage_verdict="CLEAN",
            review_board_status="APPROVED",
            cpcv_summary={
                "mean_sharpe": 2.0,
                "dsr": 1.8,
                "overfitting_probability": 0.05,
                "n_splits": 10,
                "annualized_return": 0.18,
                "max_drawdown": 0.08,
                "n_trades": 45,
                "win_rate": 0.60,
            },
            backtest_metrics={
                "mean_sharpe": 2.0,
                "dsr": 1.8,
                "overfitting_probability": 0.05,
                "annualized_return": 0.18,
                "max_drawdown": 0.08,
            },
        )

        gates = GraduationGates()
        gate_result = gates.check(snapshot, pipeline_result)
        assert gate_result.overall_status == "GRADUATED"
        assert gate_result.gates_passed == 6

        tracker.record_check(1, gate_result)

        cert = tracker.issue_certificate(
            snapshot=snapshot,
            pipeline_result=pipeline_result,
            optimization_cycles=3,
            gate_result=gate_result,
        )
        assert tracker.is_graduated()
        assert cert.certificate_id != ""
        assert len(cert.gate_results) == 6
        assert cert.optimization_cycles == 3

        json_str = cert.to_json()
        restored = GraduationCertificate.from_json(json_str)
        assert restored.certificate_id == cert.certificate_id
        assert restored.optimization_cycles == 3

        progress = tracker.progress_over_time()
        assert len(progress) == 1
        assert progress[0]["gates_passed"] == 6
        assert progress[0]["overall_status"] == "GRADUATED"

        store_dir = str(tmp_path / "graduation_e2e")
        tracker.save(store_dir)
        loaded = GraduationTracker.load("e2e-test", store_dir)
        assert loaded.is_graduated()
        assert loaded.get_certificate().certificate_id == cert.certificate_id

    def test_graduation_with_multiple_checks_before_passing(self, tmp_path):
        tracker = GraduationTracker(session_id="multi-check")

        gates = GraduationGates()

        snapshot_failing = PerformanceSnapshot(
            deployment_id=str(uuid.uuid4()),
            total_return=0.01,
            annualized_return=0.02,
            sharpe_ratio=0.5,
            max_drawdown=0.15,
            win_rate=0.40,
            total_trades=5,
            days_deployed=2,
            equity_curve=[100000.0, 100100.0],
            degradation_report=DegradationReport(
                overall_degradation_score=0.5, category="ELEVATED", triggers_optimizer=False,
            ),
        )

        pipeline_result = PipelineResult(
            pipeline_id=str(uuid.uuid4()),
            spec_id=str(uuid.uuid4()),
            status="DEPLOYED_PAPER",
            cpcv_summary={"mean_sharpe": 0.5, "dsr": 0.3, "n_splits": 6},
            backtest_metrics={"mean_sharpe": 0.5, "dsr": 0.3},
        )

        pipeline_passing = PipelineResult(
            pipeline_id=str(uuid.uuid4()),
            spec_id=str(uuid.uuid4()),
            status="DEPLOYED_PAPER",
            cpcv_summary={"mean_sharpe": 2.0, "dsr": 1.6, "n_splits": 10},
            backtest_metrics={"mean_sharpe": 2.0, "dsr": 1.6},
        )

        for cycle in range(1, 4):
            result = gates.check(snapshot_failing, pipeline_result)
            assert result.overall_status == "NOT_READY"
            tracker.record_check(cycle, result)

        snapshot_passing = PerformanceSnapshot(
            deployment_id=str(uuid.uuid4()),
            total_return=0.12,
            annualized_return=0.18,
            sharpe_ratio=2.0,
            max_drawdown=0.08,
            win_rate=0.60,
            total_trades=45,
            days_deployed=60,
            equity_curve=[100000.0, 112000.0],
            degradation_report=DegradationReport(
                overall_degradation_score=0.1, category="ACCEPTABLE", triggers_optimizer=False,
            ),
        )

        result = gates.check(snapshot_passing, pipeline_passing)
        assert result.overall_status == "GRADUATED"
        tracker.record_check(4, result)

        cert = tracker.issue_certificate(snapshot_passing, pipeline_passing, 5)
        assert tracker.is_graduated()

        progress = tracker.progress_over_time()
        assert len(progress) == 4
        assert progress[0]["gates_passed"] < 6
        assert progress[3]["gates_passed"] == 6

        trend = tracker.gate_trend("dsr")
        assert len(trend) == 4

    def test_pipeline_result_summary_contains_cpcv_metrics(self):
        pipeline_result = PipelineResult(
            pipeline_id=str(uuid.uuid4()),
            spec_id=str(uuid.uuid4()),
            status="DEPLOYED_PAPER",
            cpcv_summary={
                "mean_sharpe": 1.8,
                "dsr": 1.5,
                "overfitting_probability": 0.08,
                "n_splits": 10,
                "annualized_return": 0.15,
                "max_drawdown": 0.10,
                "n_trades": 40,
                "win_rate": 0.55,
            },
            backtest_metrics={
                "mean_sharpe": 1.8,
                "dsr": 1.5,
                "overfitting_probability": 0.08,
                "annualized_return": 0.15,
                "max_drawdown": 0.10,
                "n_trades": 40,
                "win_rate": 0.55,
            },
        )

        cert = GraduationCertificate.from_gate_check(
            session_id="summary-test",
            gate_result=GateCheckResult(
                overall_status="GRADUATED",
                gates={"test": GateResult(gate_name="test", status="PASSED")},
                gates_passed=1,
                gates_total=6,
            ),
            snapshot=_make_snapshot(),
            pipeline_result=pipeline_result,
            optimization_cycles=3,
        )

        summary = cert.pipeline_result_summary
        assert "cpcv_summary" in summary
        assert summary["cpcv_summary"]["mean_sharpe"] == 1.8
        assert summary["cpcv_summary"]["annualized_return"] == 0.15
        assert summary["cpcv_summary"]["win_rate"] == 0.55
