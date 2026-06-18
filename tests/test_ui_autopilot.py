"""Wiring tests for the autopilot UI endpoints (no real broker / trading)."""

from fastapi.testclient import TestClient

from astra.ui.backend.main import app, _deps
from astra.pipeline.state import PipelineState
from astra.planner.spec import StrategySpec

client = TestClient(app)


def test_status_unknown_session_is_inactive():
    r = client.get("/api/session/does-not-exist/autopilot/status")
    assert r.status_code == 200
    body = r.json()
    assert body["active"] is False
    assert body["running"] is False


def test_stop_unknown_session_404():
    r = client.post("/api/session/does-not-exist/autopilot/stop")
    assert r.status_code == 404


def test_start_unknown_session_404():
    r = client.post("/api/session/nope/autopilot/start", json={})
    assert r.status_code == 404


def test_start_without_built_strategy_returns_400():
    sid = "sess-autopilot-test"
    _deps.store.create(sid)
    # State exists but no build_result yet -> autopilot cannot start.
    state = PipelineState(session_id=sid, spec=StrategySpec(spec_id=sid, symbols=["SPY"]))
    _deps.store.update(sid, "state", state)

    r = client.post(f"/api/session/{sid}/autopilot/start", json={"interval_seconds": 5})
    assert r.status_code == 400
    assert "built strategy" in r.json()["detail"].lower()
