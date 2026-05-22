"""Property-based tests using hypothesis — finds edge cases example-based tests miss."""

import math
from unittest.mock import MagicMock

import numpy as np
import pandas as pd
import pytest
from hypothesis import given, strategies as st, settings, HealthCheck
from scipy import stats

_DAILY_POSITIVE = st.floats(min_value=0.0001, max_value=0.02, allow_nan=False)
_DAILY_NEGATIVE = st.floats(min_value=-0.02, max_value=-0.0001, allow_nan=False)
_DAILY_RETURN = st.floats(min_value=-0.05, max_value=0.05, allow_nan=False)

from astra.backtest.metrics import (
    compute_sharpe_ratio,
    compute_deflated_sharpe_ratio,
    compute_max_drawdown,
    compute_annualized_return,
    compute_win_rate,
    compute_profit_factor,
    compute_returns,
)
from astra.backtest.cpcv import cpcv_split_indices
from astra.backtest.features import compute_features
from astra.builder.sandbox import BuildSandbox
from astra.export.validator import ExportValidator
from astra.pipeline.state import PipelineState, InvalidStatusTransition


# ---------------------------------------------------------------------------
# Backtest Metrics: invariants for Sharpe, DSR, drawdown, returns
# ---------------------------------------------------------------------------

_ANY_RETURN_SERIES = st.lists(
    st.floats(min_value=-0.2, max_value=0.2, allow_nan=False, allow_infinity=False),
    min_size=2,
    max_size=500,
)


@given(returns=st.lists(st.just(0.0), min_size=10, max_size=500))
def test_sharpe_of_constant_returns_is_zero(returns):
    s = compute_sharpe_ratio(pd.Series(returns))
    assert s == 0.0


@given(
    positive=st.lists(
        st.floats(min_value=0.001, max_value=0.02, allow_nan=False),
        min_size=50, max_size=500,
    ).filter(lambda x: len(set(x)) > 1),
)
def test_sharpe_of_positive_series_is_positive(positive):
    s = compute_sharpe_ratio(pd.Series(positive))
    assert s > 0


@given(
    negative=st.lists(
        st.floats(min_value=-0.02, max_value=-0.001, allow_nan=False),
        min_size=50, max_size=500,
    ).filter(lambda x: len(set(x)) > 1),
)
def test_sharpe_of_negative_series_is_negative(negative):
    s = compute_sharpe_ratio(pd.Series(negative))
    assert s < 0


@given(
    returns=st.lists(
        st.floats(min_value=-0.05, max_value=0.05, allow_nan=False),
        min_size=50, max_size=500,
    ).filter(lambda x: len(set(x)) > 1),
)
def test_sharpe_scaling_is_invariant(returns):
    series = pd.Series(returns)
    s1 = compute_sharpe_ratio(series)
    s2 = compute_sharpe_ratio(series * 2)
    assert abs(s1 - s2) < 1e-10


@given(
    returns=st.lists(
        st.floats(min_value=-0.05, max_value=0.05, allow_nan=False),
        min_size=50, max_size=500,
    ).filter(lambda x: len(set(x)) > 1),
)
def test_sharpe_adds_risk_free_rate_bias(returns):
    series = pd.Series(returns)
    s_with_rf = compute_sharpe_ratio(series, risk_free_rate=0.01)
    s_without = compute_sharpe_ratio(series, risk_free_rate=0.0)
    assert s_with_rf <= s_without + 1e-10


@given(
    sharpes=st.floats(min_value=0.01, max_value=3.0),
    n_obs=st.integers(min_value=30, max_value=1000),
)
def test_dsr_one_trial_equals_sharpe_cdf(sharpes, n_obs):
    dsr = compute_deflated_sharpe_ratio(sharpes, n_obs, n_trials=1)
    expected = stats.norm.cdf(
        sharpes / math.sqrt(1 + 0.5 * sharpes**2 / (n_obs - 1))
    )
    assert abs(dsr - expected) < 0.001


@given(
    sharpes=st.floats(min_value=0.01, max_value=3.0),
    n_obs=st.integers(min_value=50, max_value=1000),
)
def test_dsr_decreases_with_more_trials(sharpes, n_obs):
    dsr_1 = compute_deflated_sharpe_ratio(sharpes, n_obs, n_trials=3)
    dsr_2 = compute_deflated_sharpe_ratio(sharpes, n_obs, n_trials=100)
    assert dsr_1 >= dsr_2 - 1e-10


@given(
    sharpes=st.floats(min_value=0.01, max_value=3.0),
    n_obs=st.integers(min_value=5, max_value=9),
)
def test_dsr_handles_small_n_obs(sharpes, n_obs):
    dsr = compute_deflated_sharpe_ratio(sharpes, n_obs, n_trials=3)
    assert isinstance(dsr, float)
    assert 0 <= dsr <= 1.0


class TestDrawdownProperty:
    @given(
        prices=st.lists(
            st.floats(min_value=10, max_value=200, allow_nan=False, allow_infinity=False),
            min_size=2, max_size=200,
        )
    )
    def test_drawdown_between_zero_and_one(self, prices):
        dd = compute_max_drawdown(pd.Series(prices))
        assert 0 <= dd <= 1.0

    @given(
        base=st.floats(min_value=10, max_value=200),
        n=st.integers(min_value=2, max_value=50),
        growth=st.floats(min_value=0.0, max_value=0.01),
    )
    def test_monotonic_equity_has_no_drawdown(self, base, n, growth):
        vals = [base * (1 + growth) ** i for i in range(n)]
        dd = compute_max_drawdown(pd.Series(vals))
        assert dd == 0.0


class TestCPCVPIndicesProperty:
    @given(
        n_obs=st.integers(min_value=50, max_value=2000),
        n_splits=st.integers(min_value=2, max_value=10),
        n_test_splits=st.integers(min_value=1, max_value=5),
    )
    def test_split_indices_within_bounds(self, n_obs, n_splits, n_test_splits):
        if n_test_splits >= n_splits:
            return
        splits = cpcv_split_indices(n_obs, n_splits=n_splits, n_test_splits=n_test_splits)
        for s in splits:
            train_start, train_end = s["train"]
            assert 0 <= train_start < train_end <= n_obs
            for test_start, test_end in s["test"]:
                assert 0 <= test_start < test_end <= n_obs

    @given(
        n_obs=st.integers(min_value=100, max_value=1000),
        n_splits=st.integers(min_value=3, max_value=8),
        n_test_splits=st.integers(min_value=1, max_value=3),
    )
    def test_train_test_no_overlap(self, n_obs, n_splits, n_test_splits):
        if n_test_splits >= n_splits:
            return
        splits = cpcv_split_indices(n_obs, n_splits, n_test_splits)
        for s in splits:
            train_start, train_end = s["train"]
            for test_start, test_end in s["test"]:
                assert train_end <= test_start, f"Train ends at {train_end} but test starts at {test_start}"

    @given(
        n_obs=st.integers(min_value=200, max_value=1000),
        n_splits=st.integers(min_value=4, max_value=8),
        n_test_splits=st.integers(min_value=1, max_value=3),
    )
    def test_split_produces_expected_number_of_paths(self, n_obs, n_splits, n_test_splits):
        if n_test_splits >= n_splits:
            return
        from math import comb
        splits = cpcv_split_indices(n_obs, n_splits, n_test_splits)
        expected = comb(n_splits, n_test_splits)
        assert 0 < len(splits) <= expected


class TestFeaturesProperty:
    @given(
        n=st.integers(min_value=50, max_value=500),
        seed=st.integers(min_value=0, max_value=1000),
    )
    def test_feature_columns_present(self, n, seed):
        rng = np.random.default_rng(seed)
        df = pd.DataFrame({
            "open": 100 + rng.normal(0, 1, n).cumsum(),
            "high": 100 + rng.normal(0, 1, n).cumsum() + abs(rng.normal(0, 0.5, n)),
            "low": 100 + rng.normal(0, 1, n).cumsum() - abs(rng.normal(0, 0.5, n)),
            "close": 100 + rng.normal(0, 1, n).cumsum(),
            "volume": rng.integers(100000, 10000000, n),
        })
        feats = compute_features(df)
        required = {"returns", "log_returns", "rsi_14", "macd", "bb_upper", "bb_lower", "atr_14", "volume_sma_20"}
        assert required.issubset(set(feats.columns)), f"Missing: {required - set(feats.columns)}"

    @given(
        n=st.integers(min_value=5, max_value=30),
        seed=st.integers(min_value=0, max_value=100),
    )
    def test_short_dataset_produces_nans(self, n, seed):
        rng = np.random.default_rng(seed)
        df = pd.DataFrame({
            "open": 100 + rng.normal(0, 1, n).cumsum(),
            "high": 100 + rng.normal(0, 1, n).cumsum() + abs(rng.normal(0, 0.5, n)),
            "low": 100 + rng.normal(0, 1, n).cumsum() - abs(rng.normal(0, 0.5, n)),
            "close": 100 + rng.normal(0, 1, n).cumsum(),
            "volume": rng.integers(100000, 10000000, n),
        })
        feats = compute_features(df)
        assert feats.isna().any().any()


# ---------------------------------------------------------------------------
# BuildSandbox: for any Python code with forbidden patterns, sandbox rejects it
# ---------------------------------------------------------------------------

_FORBIDDEN_IMPORTS = ["requests", "httpx", "urllib", "socket", "subprocess",
                       "os", "shutil", "pathlib", "sys", "multiprocessing", "threading"]
_FORBIDDEN_CALLS = ["eval", "exec", "compile", "__import__"]
_SAFE_IMPORTS = ["pandas", "numpy", "json", "math", "datetime", "typing", "abc"]


def _make_code_with_import(mod_name: str) -> str:
    return f"import {mod_name}\n"


def _make_code_with_from_import(mod_name: str) -> str:
    return f"from {mod_name} import something\n"


def _make_code_with_call(call_name: str) -> str:
    return f"def f():\n    {call_name}('x')\n"


class TestBuildSandboxProperty:
    @given(mod_name=st.sampled_from(_FORBIDDEN_IMPORTS))
    @settings(suppress_health_check=[HealthCheck.function_scoped_fixture])
    def test_rejects_forbidden_import(self, mod_name, tmp_path):
        sandbox = BuildSandbox()
        f = tmp_path / "test.py"
        f.write_text(_make_code_with_import(mod_name))
        result = sandbox.validate(str(f))
        assert not result.passed
        assert any(mod_name in v for v in result.violations)

    @given(mod_name=st.sampled_from(_FORBIDDEN_IMPORTS))
    @settings(suppress_health_check=[HealthCheck.function_scoped_fixture])
    def test_rejects_forbidden_from_import(self, mod_name, tmp_path):
        sandbox = BuildSandbox()
        f = tmp_path / "test.py"
        f.write_text(_make_code_with_from_import(mod_name))
        result = sandbox.validate(str(f))
        assert not result.passed
        assert any(mod_name in v for v in result.violations)

    @given(call_name=st.sampled_from(_FORBIDDEN_CALLS))
    @settings(suppress_health_check=[HealthCheck.function_scoped_fixture])
    def test_rejects_forbidden_call(self, call_name, tmp_path):
        sandbox = BuildSandbox()
        f = tmp_path / "test.py"
        f.write_text(_make_code_with_call(call_name))
        result = sandbox.validate(str(f))
        assert not result.passed
        assert any(call_name in v for v in result.violations)

    @given(mod_name=st.sampled_from(_SAFE_IMPORTS))
    @settings(suppress_health_check=[HealthCheck.function_scoped_fixture])
    def test_passes_safe_import(self, mod_name, tmp_path):
        sandbox = BuildSandbox()
        f = tmp_path / "test.py"
        f.write_text(f"import {mod_name}\n\ndef f():\n    return 1\n")
        result = sandbox.validate(str(f))
        assert result.passed, f"Safe import {mod_name} was rejected: {result.violations}"

    @given(val=st.integers(min_value=0, max_value=1))
    @settings(suppress_health_check=[HealthCheck.function_scoped_fixture])
    def test_passes_signal_return(self, val, tmp_path):
        sandbox = BuildSandbox()
        f = tmp_path / "test.py"
        f.write_text(
            f'"""Docstring."""\nimport pandas\n\ndef generate_signals(data):\n    return {val}\n'
        )
        result = sandbox.validate(str(f))
        assert result.passed, f"Signal return {val} was rejected: {result.violations}"


# ---------------------------------------------------------------------------
# ExportValidator: files with required elements pass, missing any fail
# ---------------------------------------------------------------------------

_VALID_FILE_CONTENT = """
\"\"\"
Docstring with Limitations
--------------------------
1. Test limitation

Disclaimer
---------
past performance does not predict future results
\"\"\"

# GRADUATION CERTIFICATE
# Certificate ID: abc

STRATEGY_METADATA = {"key": "value"}

import pandas

class Strategy:
    def generate(self):
        return 0
"""


class TestExportValidatorProperty:
    def test_passes_file_with_all_required_elements(self, tmp_path):
        validator = ExportValidator()
        f = tmp_path / "valid.py"
        f.write_text(_VALID_FILE_CONTENT)
        result = validator.validate(str(f))
        assert result.passed, f"Expected pass but got failures: {result.failures}"

    @given(
        element=st.sampled_from(["header", "metadata", "disclaimer", "limitations"])
    )
    @settings(suppress_health_check=[HealthCheck.function_scoped_fixture])
    def test_fails_when_element_missing(self, element, tmp_path):
        validator = ExportValidator()
        code = _VALID_FILE_CONTENT

        if element == "header":
            code = code.replace("GRADUATION CERTIFICATE", "NO CERTIFICATE HERE")
        elif element == "metadata":
            code = code.replace("STRATEGY_METADATA", "METADATA_DICT")
        elif element == "disclaimer":
            code = code.replace("past performance does not predict future results", "")
        elif element == "limitations":
            code = code.replace("Limitations", "")

        f = tmp_path / "test_export.py"
        f.write_text(code)
        result = validator.validate(str(f))
        assert not result.passed, f"Expected failure for missing {element}"
        assert len(result.failures) > 0


# ---------------------------------------------------------------------------
# PipelineState: state machine invariants (mirrors state.py VALID_TRANSITIONS)
# ---------------------------------------------------------------------------

_VALID_TRANSITIONS = {
    "PLANNING": ["BUILDING", "ABANDONED"],
    "BUILDING": ["RUNNING", "ABANDONED"],
    "RUNNING": ["OPTIMIZING", "PAPER_TRADING", "FAILED", "ABANDONED"],
    "OPTIMIZING": ["RUNNING", "PAPER_TRADING", "GRADUATED", "FAILED", "ABANDONED"],
    "PAPER_TRADING": ["OPTIMIZING", "GRADUATED", "FAILED", "ABANDONED"],
    "GRADUATED": [],
    "FAILED": ["ABANDONED"],
    "ABANDONED": [],
}

_ALL_STATUSES = list(_VALID_TRANSITIONS.keys())


class TestPipelineStateProperty:
    @given(from_status=st.sampled_from(_ALL_STATUSES))
    def test_transition_to_self_always_raises(self, from_status):
        state = PipelineState(status=from_status)
        with pytest.raises(InvalidStatusTransition):
            state.transition_to(from_status)

    @given(
        from_status=st.sampled_from(_ALL_STATUSES),
        to_status=st.sampled_from(_ALL_STATUSES),
    )
    def test_transition_raises_only_when_invalid(self, from_status, to_status):
        state = PipelineState(status=from_status)
        valid = to_status in _VALID_TRANSITIONS[from_status]
        if valid:
            state.transition_to(to_status)
            assert state.status == to_status
        else:
            with pytest.raises(InvalidStatusTransition):
                state.transition_to(to_status)

    @given(
        st.lists(
            st.sampled_from([s for s in _ALL_STATUSES if s != "PLANNING"]),
            min_size=1, max_size=15,
        )
    )
    def test_random_walk_from_planning_produces_valid_chain(self, status_chain):
        state = PipelineState(status="PLANNING")
        for target in status_chain:
            valid = target in _VALID_TRANSITIONS[state.status]
            if valid:
                state.transition_to(target)
            else:
                with pytest.raises(InvalidStatusTransition):
                    state.transition_to(target)
