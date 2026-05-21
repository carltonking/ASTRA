"""Tests for the ASTRA UI backend."""

import json
import os
import uuid
from unittest.mock import MagicMock, patch
from datetime import datetime, timezone

import pytest
from fastapi.testclient import TestClient

from astra.ui.backend.main import app, _deps, _trigger_build
from astra.ui.backend.session_store import SessionStore
from astra.ui.backend.websocket import WebSocketManager
from astra.pipeline.state import PipelineState
from astra.planner.spec import StrategySpec
from astra.builder.generator import BuildResult
from astra.pipeline.runner import PipelineResult
from astra.graduation.gates import GateCheckResult, GateResult
from astra.graduation.tracker import GraduationTracker
from astra.graduation.certificate import GraduationCertificate
from astra.export.packager import ExportPackage


@pytest.fixture
def client():
    return TestClient(app)


def _setup_session():
    session_id = str(uuid.uuid4())
    _deps.store.create(session_id)
    return session_id


def _inject_spec_and_build(session_id, spec=None, build_result=None):
    session = _deps.store.get(session_id)
    if spec is None:
        spec = StrategySpec(
            spec_id=str(uuid.uuid4()),
            strategy_type="momentum",
            symbols=["SPY"],
            user_idea="Test momentum strategy",
            asset_class="equity",
            timeframe="daily",
            data_source="yfinance",
            market_hypothesis="Momentum persists",
            entry_conditions=["RSI > 50"],
            exit_conditions=["RSI < 40"],
            target_return=0.15,
            max_drawdown=0.20,
            position_size=0.10,
            max_positions=5,
            backtest_start="2020-01-01",
            backtest_end="2023-12-31",
        )
    state = session["state"]
    state.spec = spec
    state.build_result = build_result or BuildResult(
        success=True,
        spec_id=spec.spec_id,
        strategy_file="/tmp/test_strategy.py",
        strategy_class_name="MomentumStrategy",
        initial_parameters={"lookback_window": 126},
        parameter_bounds={"lookback_window": (5, 252)},
    )
    state.pipeline_results.append(PipelineResult(
        pipeline_id=str(uuid.uuid4()),
        spec_id=spec.spec_id,
        status="DEPLOYED_PAPER",
        backtest_metrics={"mean_sharpe": 0.8, "dsr": 0.5},
        cpcv_summary={"mean_sharpe": 0.8, "dsr": 0.5, "n_splits": 10},
    ))
    state.paper_deployment_id = str(uuid.uuid4())
    state.status = "PAPER_TRADING"
    return spec


# ---- Health ----

class TestHealth:
    def test_health_endpoint(self, client):
        res = client.get("/api/health")
        assert res.status_code == 200
        data = res.json()
        assert data["status"] == "ok"
        assert "disclaimer" in data


# ---- Session Start ----

class TestSessionStart:
    def test_creates_session_and_returns_first_message(self, client):
        with patch("astra.ui.backend.main.PlannerConversation") as MockConv:
            mock_conv = MagicMock()
            mock_conv.start.return_value = "Hello! Tell me about your strategy idea."
            mock_conv.get_history.return_value = []
            MockConv.return_value = mock_conv

            res = client.post("/api/session/start", json={"user_idea": "Test momentum strategy"})
            assert res.status_code == 200
            data = res.json()
            assert "session_id" in data
            assert len(data["message"]) > 0
            assert "disclaimer" in data

    def test_handles_api_error(self, client):
        with patch("astra.ui.backend.main.PlannerConversation") as MockConv:
            mock_conv = MagicMock()
            mock_conv.start.side_effect = Exception("API key invalid")
            MockConv.return_value = mock_conv

            res = client.post("/api/session/start", json={"user_idea": "Test"})
            assert res.status_code == 500


# ---- Chat ----

class TestChat:
    def test_returns_message(self, client):
        session_id = _setup_session()
        with patch("astra.ui.backend.main.PlannerConversation") as MockConv:
            mock_conv = MagicMock()
            mock_conv.reply.return_value = "Good idea! What timeframe?"
            mock_conv.is_complete.return_value = False
            mock_conv.spec = None
            MockConv.return_value = mock_conv

            _deps.store.update(session_id, "conversation", mock_conv)

            res = client.post(f"/api/session/{session_id}/chat", json={"message": "Daily"})
            assert res.status_code == 200
            data = res.json()
            assert data["message"] == "Good idea! What timeframe?"
            assert data["is_complete"] is False

    def test_returns_spec_when_complete(self, client):
        session_id = _setup_session()
        with patch("astra.ui.backend.main.PlannerConversation") as MockConv:
            mock_conv = MagicMock()
            mock_conv.reply.return_value = "SPEC_READY: {\"strategy_type\": \"momentum\"}"
            mock_conv.is_complete.return_value = True
            mock_conv.spec = StrategySpec(strategy_type="momentum", symbols=["SPY"])
            MockConv.return_value = mock_conv

            _deps.store.update(session_id, "conversation", mock_conv)

            res = client.post(f"/api/session/{session_id}/chat", json={"message": "Daily"})
            assert res.status_code == 200
            data = res.json()
            assert data["is_complete"] is True
            assert data["spec"] is not None

    def test_404_for_nonexistent_session(self, client):
        res = client.post("/api/session/nonexistent/chat", json={"message": "Hi"})
        assert res.status_code == 404


# ---- Session State ----

class TestSessionState:
    def test_returns_valid_state(self, client):
        session_id = _setup_session()
        _inject_spec_and_build(session_id)

        res = client.get(f"/api/session/{session_id}/state")
        assert res.status_code == 200
        data = res.json()
        assert data["session_id"] == session_id
        assert data["status"] == "PAPER_TRADING"
        assert data["spec"] is not None

    def test_404_for_nonexistent(self, client):
        res = client.get("/api/session/nonexistent/state")
        assert res.status_code == 404


# ---- Snapshot ----

class TestSnapshot:
    def test_returns_snapshot_response(self, client):
        session_id = _setup_session()
        res = client.get(f"/api/session/{session_id}/snapshot")
        assert res.status_code == 200
        assert "disclaimer" in res.json()


# ---- Graduation ----

class TestGraduation:
    def test_returns_not_graduated_when_no_certificate(self, client):
        session_id = _setup_session()
        res = client.get(f"/api/session/{session_id}/graduation")
        assert res.status_code == 200
        data = res.json()
        assert data["is_graduated"] is False

    def test_returns_graduation_data_when_issued(self, client):
        session_id = _setup_session()
        session = _deps.store.get(session_id)
        tracker = session["graduation_tracker"]

        gr = GateResult(gate_name="dsr", status="PASSED", actual_value=2.0, threshold_value=1.5, gap=-0.5)
        gate_result = GateCheckResult(
            overall_status="GRADUATED",
            gates={"dsr": gr},
            gates_passed=6,
            gates_total=6,
        )
        tracker.record_check(1, gate_result)
        tracker._certificate = GraduationCertificate(
            certificate_id="test-cert",
            session_id=session_id,
            gate_results={"dsr": gr},
        )

        res = client.get(f"/api/session/{session_id}/graduation")
        assert res.status_code == 200
        data = res.json()
        assert data["is_graduated"] is True
        assert data["certificate"] is not None


# ---- Sessions List ----

class TestSessionsList:
    def test_lists_sessions(self, client):
        _setup_session()
        res = client.get("/api/sessions")
        assert res.status_code == 200
        data = res.json()
        assert "sessions" in data
        assert len(data["sessions"]) >= 1
        assert "disclaimer" in data


# ---- SessionStore ----

class TestSessionStore:
    def test_create_and_get(self):
        store = SessionStore()
        store.create("test-session")
        session = store.get("test-session")
        assert session is not None
        assert session["session_id"] == "test-session"
        assert isinstance(session["state"], PipelineState)
        assert isinstance(session["graduation_tracker"], GraduationTracker)

    def test_raises_on_duplicate_create(self):
        store = SessionStore()
        store.create("dup")
        with pytest.raises(KeyError):
            store.create("dup")

    def test_update(self):
        store = SessionStore()
        store.create("test")
        store.update("test", "custom_key", {"foo": "bar"})
        assert store.get("test")["custom_key"] == {"foo": "bar"}

    def test_list_sessions(self):
        store = SessionStore()
        store.create("s1")
        store.create("s2")
        sessions = store.list_sessions()
        assert len(sessions) == 2

    def test_get_nonexistent(self):
        store = SessionStore()
        assert store.get("nope") is None

    def test_update_nonexistent_raises(self):
        store = SessionStore()
        with pytest.raises(KeyError):
            store.update("nope", "k", "v")

    def test_save_and_load_persistence(self, tmp_path):
        store = SessionStore()
        store.create("persist-session")
        store.update("persist-session", "test_data", "hello")

        store_dir = str(tmp_path / "sessions")
        store.save_all(store_dir)

        store2 = SessionStore()
        store2.load_all(store_dir)
        loaded = store2.get("persist-session")
        assert loaded is not None
        assert loaded["test_data"] == "hello"


# ---- Export ----

class TestExport:
    def test_returns_403_when_not_graduated(self, client, tmp_path):
        session_id = _setup_session()
        _inject_spec_and_build(session_id)

        _deps.export_dir = str(tmp_path / "exports")

        res = client.post(f"/api/session/{session_id}/export")
        assert res.status_code == 403
        assert "GRADUATED" in res.json()["detail"]

    def test_returns_404_for_nonexistent_session(self, client):
        res = client.post("/api/session/nonexistent/export")
        assert res.status_code == 404


# ---- Downloads ----

class TestDownloads:
    def test_strategy_404_when_no_export(self, client):
        session_id = _setup_session()
        res = client.get(f"/api/session/{session_id}/download/strategy")
        assert res.status_code == 404

    def test_report_404_when_no_export(self, client):
        session_id = _setup_session()
        res = client.get(f"/api/session/{session_id}/download/report")
        assert res.status_code == 404


# ---- WebSocket Manager ----

class TestWebSocketManager:
    def test_record_event(self):
        mgr = WebSocketManager()
        mgr.record_event("sid", "pipeline.test", {"key": "val"})
        history = mgr._event_histories.get("sid", [])
        assert len(history) == 1
        assert history[0]["event"] == "pipeline.test"
        assert history[0]["data"] == {"key": "val"}
        assert "timestamp" in history[0]
        assert "session_id" in history[0]

    def test_multiple_events_accumulate(self):
        mgr = WebSocketManager()
        mgr.record_event("sid", "event1", {})
        mgr.record_event("sid", "event2", {})
        assert len(mgr._event_histories["sid"]) == 2

    def test_separate_session_histories(self):
        mgr = WebSocketManager()
        mgr.record_event("s1", "e1", {})
        mgr.record_event("s2", "e2", {})
        assert len(mgr._event_histories["s1"]) == 1
        assert len(mgr._event_histories["s2"]) == 1
