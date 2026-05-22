"""FastAPI backend — provides REST API and WebSocket for the ASTRA UI."""


import json
import os
import uuid
from contextlib import asynccontextmanager
from datetime import datetime
from pathlib import Path
from typing import Any

from dotenv import load_dotenv
from fastapi import FastAPI, HTTPException, WebSocket, WebSocketDisconnect
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

from astra.llm import create_llm_provider
from astra.llm.provider import LLMProvider
from astra.planner.spec import StrategySpec
from astra.planner.conversation import PlannerConversation
from astra.builder.generator import StrategyGenerator
from astra.pipeline.state import PipelineState, InvalidStatusTransition
from astra.pipeline.runner import PipelineRunner
from astra.pipeline.events import PipelineEventBus
from astra.alpaca.monitor import PerformanceSnapshot
from astra.graduation.gates import GraduationGates
from astra.graduation.tracker import GraduationTracker
from astra.export.packager import StrategyPackager, ExportPackage
from astra.export.report import ReportGenerator
from astra.storage import Storage
from astra.ui.backend.session_store import SessionStore
from astra.ui.backend.websocket import ws_manager

# Load .env from repo root
load_dotenv(dotenv_path=Path(__file__).resolve().parents[4] / ".env")


_DISCLAIMER = (
    "ASTRA research results are not profitability guarantees. "
    "Past performance does not predict future results. "
    "For research purposes only."
)


class AppDependencies:
    def __init__(self) -> None:
        self.store = SessionStore()
        self.build_dir: str = os.environ.get("ASTRA_BUILD_DIR", ".astra_builds")
        self.export_dir: str = os.environ.get("ASTRA_EXPORT_DIR", ".astra_exports")
        self.alpaca_key: str = os.environ.get("APCA_API_KEY_ID", "")
        self.alpaca_secret: str = os.environ.get("APCA_API_SECRET_KEY", "")
        self.alpaca_url: str = os.environ.get("APCA_PAPER_URL", "https://paper-api.alpaca.markets")
        self.packager = StrategyPackager(export_dir=self.export_dir)
        self.report_generator = ReportGenerator(export_dir=self.export_dir)
        self.graduation_gates = GraduationGates()
        self._llm_provider: LLMProvider | None = None

    def get_llm_provider(self) -> LLMProvider:
        if self._llm_provider is None:
            self._llm_provider = create_llm_provider()
        return self._llm_provider

    def get_conversation(self) -> PlannerConversation:
        return PlannerConversation(llm_provider=self.get_llm_provider())

    def get_runner(self, event_bus: PipelineEventBus | None = None) -> PipelineRunner:
        return PipelineRunner(
            llm_provider=self.get_llm_provider(),
            alpaca_paper_key=self.alpaca_key,
            alpaca_paper_secret=self.alpaca_secret,
            alpaca_base_url=self.alpaca_url,
            build_dir=self.build_dir,
            event_bus=event_bus,
        )


_deps = AppDependencies()


@asynccontextmanager
async def lifespan(app: FastAPI):
    try:
        _deps.get_llm_provider()
        app.state.llm_available = True
    except Exception as exc:
        print(f"WARNING: LLM provider unavailable at startup: {exc}")
        print("ASTRA will start, but LLM-dependent features (planning, building) will fail.")
        app.state.llm_available = False

    try:
        from astra.data import lseg_client
        lseg_client.open_session()
    except Exception as exc:
        print(f"WARNING: LSEG session setup failed: {exc}")

    yield

    try:
        from astra.data import lseg_client
        lseg_client.close_session()
    except Exception:
        pass


app = FastAPI(title="ASTRA", version="0.1.0", lifespan=lifespan)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:3000", "http://127.0.0.1:3000"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


class StartRequest(BaseModel):
    user_idea: str


class ChatRequest(BaseModel):
    message: str


@app.get("/api/health")
async def health():
    """Health check endpoint. Returns OK if the server is running."""
    return {"status": "ok", "disclaimer": _DISCLAIMER}


@app.get("/api/config")
async def config():
    """Return Alpaca API keys to auto-populate the UI paper trading tab."""
    return {
        "alpaca_key_id": os.environ.get("APCA_API_KEY_ID", ""),
        "alpaca_secret_key": os.environ.get("APCA_API_SECRET_KEY", ""),
    }


# === Broker Proxy Endpoints ===


@app.get("/api/broker/status")
async def broker_status():
    """Check if broker is configured and available."""
    try:
        from astra.broker.factory import create_broker
        broker = create_broker()
        account = broker.get_account()
        return {"configured": True, "broker": broker.get_name(), "equity": account.equity}
    except Exception as e:
        return {"configured": False, "error": str(e)}


@app.get("/api/broker/account")
async def broker_account():
    """Get broker account info via backend (no API keys exposed to frontend)."""
    from astra.broker.factory import create_broker
    broker = create_broker()
    account = broker.get_account()
    return {
        "equity": account.equity,
        "cash": account.cash,
        "buying_power": account.buying_power,
        "portfolio_value": account.portfolio_value,
        "currency": account.currency,
        "status": account.status,
        "last_equity": account.equity,
    }


@app.get("/api/broker/positions")
async def broker_positions():
    """Get open positions via backend."""
    from astra.broker.factory import create_broker
    broker = create_broker()
    positions = broker.get_positions()
    return [{
        "symbol": p.symbol,
        "qty": p.qty,
        "avg_entry_price": p.avg_entry_price,
        "current_price": p.current_price,
        "unrealized_pl": p.unrealized_pl,
        "unrealized_plpc": p.unrealized_plpc,
        "side": p.side,
        "market_value": abs(p.qty) * p.current_price if p.current_price else 0.0,
        "asset_id": p.symbol,
    } for p in positions]


@app.get("/api/broker/orders")
async def broker_orders(status: str = "all", limit: int = 50):
    """Get orders via backend."""
    from astra.broker.factory import create_broker
    broker = create_broker()
    orders = broker.get_orders(status=status, limit=limit)
    return [{
        "id": o.id,
        "symbol": o.symbol,
        "qty": o.qty,
        "side": o.side,
        "type": o.order_type,
        "status": o.status,
        "filled_avg_price": o.filled_avg_price,
        "filled_qty": o.filled_qty,
        "created_at": o.created_at.isoformat(),
    } for o in orders]


@app.delete("/api/broker/orders/{order_id}")
async def broker_cancel_order(order_id: str):
    """Cancel an order via backend."""
    from astra.broker.factory import create_broker
    broker = create_broker()
    try:
        orders = broker.get_orders(status="open")
        for o in orders:
            if o.id == order_id:
                if hasattr(broker, "_client") and hasattr(broker._client, "_trading_client"):
                    broker._client._trading_client.cancel_order(order_id)
                    return {"status": "cancelled", "order_id": order_id}
        return {"status": "not_found", "order_id": order_id}
    except Exception as e:
        return {"status": "error", "error": str(e)}


@app.post("/api/broker/orders")
async def broker_place_order(symbol: str, qty: float, side: str, order_type: str = "market", time_in_force: str = "day"):
    """Place an order via backend."""
    from astra.broker.factory import create_broker
    broker = create_broker()
    try:
        order = broker.submit_order(symbol, qty, side, order_type, time_in_force)
        return {
            "id": order.id,
            "symbol": order.symbol,
            "qty": order.qty,
            "side": order.side,
            "type": order.order_type,
            "status": order.status,
        }
    except Exception as e:
        return {"status": "error", "error": str(e)}


@app.get("/api/broker/portfolio")
async def broker_portfolio(period: str = "1M", timeframe: str = "1D"):
    """Get portfolio history via backend."""
    from astra.broker.factory import create_broker
    broker = create_broker()
    history = broker.get_portfolio_history(period=period, timeframe=timeframe)
    return {
        "timestamp": history.timestamps,
        "equity": history.equity,
        "profit_loss": history.profit_loss,
        "profit_loss_pct": history.profit_loss_pct,
        "base_value": history.base_value,
    }


@app.get("/api/broker/monitoring")
async def broker_monitoring(session_id: str):
    """Get latest monitoring check result for a deployed session."""
    session = _deps.store.get(session_id)
    if session is None:
        raise HTTPException(status_code=404, detail="Session not found")
    state = session.get("state")
    if not state or not state.pipeline_results:
        return {"status": "no_data"}
    last_result = state.pipeline_results[-1]
    return {
        "status": state.status,
        "deployment_id": state.paper_deployment_id,
        "cycle_number": last_result.cycle_number if last_result else 0,
        "cpcv_summary": getattr(last_result, "cpcv_summary", None),
    }


@app.post("/api/session/start")
async def start_session(req: StartRequest):
    """Start a new planning session. Creates a session and begins LLM conversation."""
    session_id = str(uuid.uuid4())
    _deps.store.create(session_id)

    try:
        conv = _deps.get_conversation()
        response = conv.start(req.user_idea)
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Conversation start failed: {e}")

    _deps.store.update(session_id, "conversation", conv)

    state = _deps.store.get(session_id)["state"]
    state.spec = StrategySpec(user_idea=req.user_idea)

    return {
        "session_id": session_id,
        "message": response,
        "conversation_history": conv.get_history(),
        "disclaimer": _DISCLAIMER,
    }


@app.post("/api/session/{session_id}/chat")
async def chat(session_id: str, req: ChatRequest):
    """Send a chat message in the planning conversation. Returns updated status and spec when complete."""
    session = _deps.store.get(session_id)
    if session is None:
        raise HTTPException(status_code=404, detail="Session not found")

    conv: PlannerConversation | None = session.get("conversation")
    if conv is None:
        raise HTTPException(status_code=400, detail="No active conversation")

    try:
        response = conv.reply(req.message)
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Chat failed: {e}")

    _deps.store.update(session_id, "conversation", conv)

    result: dict[str, Any] = {
        "message": response,
        "is_complete": conv.is_complete(),
        "spec": None,
    }

    if conv.is_complete() and conv.spec is not None:
        state = session["state"]
        state.spec = conv.spec
        try:
            state.transition_to("BUILDING")
        except InvalidStatusTransition:
            pass

        result["spec"] = _spec_to_dict(conv.spec)
        _trigger_build(session_id, session, state)

    return result


@app.get("/api/session/{session_id}/state")
async def get_session_state(session_id: str):
    """Get the current pipeline state for a session."""
    session = _deps.store.get(session_id)
    if session is None:
        raise HTTPException(status_code=404, detail="Session not found")
    state = session.get("state")
    if state is None:
        raise HTTPException(status_code=404, detail="State not found")
    from dataclasses import asdict
    data = asdict(state)
    if isinstance(data.get("created_at"), datetime):
        data["created_at"] = data["created_at"].isoformat()
    if isinstance(data.get("updated_at"), datetime):
        data["updated_at"] = data["updated_at"].isoformat()
    data["disclaimer"] = _DISCLAIMER
    return data


@app.get("/api/session/{session_id}/snapshot")
async def get_snapshot(session_id: str):
    """Get the latest performance snapshot for a deployed strategy."""
    session = _deps.store.get(session_id)
    if session is None:
        raise HTTPException(status_code=404, detail="Session not found")
    return {"disclaimer": _DISCLAIMER, "message": "No active paper trading deployment"}


# === Parameter Presets ===


class PresetRequest(BaseModel):
    name: str
    strategy_type: str
    params: dict[str, Any]


@app.post("/api/session/{session_id}/presets")
async def save_preset(session_id: str, req: PresetRequest):
    """Save optimizer parameter preset for a session."""
    import json
    storage = Storage()
    preset_id = storage.save_preset(
        session_id=session_id,
        name=req.name,
        strategy_type=req.strategy_type,
        params_json=json.dumps(req.params),
    )
    return {"preset_id": preset_id, "name": req.name}


@app.get("/api/session/{session_id}/presets")
async def list_presets(session_id: str):
    """List saved optimizer parameter presets for a session."""
    storage = Storage()
    presets = storage.list_presets(session_id)
    import json
    return [{
        "preset_id": p["preset_id"],
        "name": p["name"],
        "strategy_type": p["strategy_type"],
        "params": json.loads(p["params_json"]),
        "created_at": p["created_at"],
    } for p in presets]


@app.delete("/api/session/{session_id}/presets/{preset_id}")
async def delete_preset(session_id: str, preset_id: str):
    """Delete a saved parameter preset."""
    storage = Storage()
    storage.delete_preset(preset_id)
    return {"status": "deleted"}


# === Backtest Export (CSV/JSON) ===


@app.get("/api/session/{session_id}/export/csv")
async def export_csv(session_id: str):
    """Download backtest results as CSV."""
    import io
    import pandas as pd
    session = _deps.store.get(session_id)
    if session is None:
        raise HTTPException(status_code=404, detail="Session not found")
    state = session.get("state")
    if not state or not state.pipeline_results:
        raise HTTPException(status_code=404, detail="No pipeline results")
    last = state.pipeline_results[-1]
    metrics = getattr(last, "cpcv_summary", None) or getattr(last, "backtest_metrics", {})
    df = pd.DataFrame([metrics])
    buf = io.StringIO()
    df.to_csv(buf, index=False)
    from fastapi.responses import Response
    return Response(
        content=buf.getvalue(),
        media_type="text/csv",
        headers={"Content-Disposition": f"attachment; filename={session_id}_backtest.csv"},
    )


@app.get("/api/session/{session_id}/export/json")
async def export_json(session_id: str):
    """Download backtest results as JSON."""
    session = _deps.store.get(session_id)
    if session is None:
        raise HTTPException(status_code=404, detail="Session not found")
    state = session.get("state")
    if not state or not state.pipeline_results:
        raise HTTPException(status_code=404, detail="No pipeline results")
    last = state.pipeline_results[-1]
    from dataclasses import asdict
    data = asdict(last)
    if isinstance(data.get("created_at"), datetime):
        data["created_at"] = data["created_at"].isoformat()
    from fastapi.responses import JSONResponse
    return JSONResponse(content=data)


@app.get("/api/session/{session_id}/graduation")
async def get_graduation(session_id: str):
    """Get graduation status, gate progress, and certificate for a session."""
    session = _deps.store.get(session_id)
    if session is None:
        raise HTTPException(status_code=404, detail="Session not found")
    tracker: GraduationTracker | None = session.get("graduation_tracker")
    if tracker is None:
        raise HTTPException(status_code=404, detail="No graduation tracking")

    cert = tracker.get_certificate()
    progress = tracker.progress_over_time()

    return {
        "is_graduated": tracker.is_graduated(),
        "progress": progress,
        "certificate": json.loads(cert.to_json()) if cert else None,
        "disclaimer": _DISCLAIMER,
    }


@app.post("/api/session/{session_id}/export")
async def export_strategy(session_id: str):
    """Export a graduated strategy as a standalone package + PDF report."""
    session = _deps.store.get(session_id)
    if session is None:
        raise HTTPException(status_code=404, detail="Session not found")

    tracker: GraduationTracker | None = session.get("graduation_tracker")
    if tracker is None or not tracker.is_graduated():
        raise HTTPException(status_code=403, detail="Strategy not GRADUATED")

    cert = tracker.get_certificate()
    state = session.get("state")
    if state is None or state.spec is None or state.build_result is None:
        raise HTTPException(status_code=400, detail="Incomplete session state for export")

    pipeline_result = state.pipeline_results[-1] if state.pipeline_results else None
    if pipeline_result is None:
        raise HTTPException(status_code=400, detail="No pipeline results for export")

    snapshot = PerformanceSnapshot(
        deployment_id=state.paper_deployment_id or "unknown",
    )

    pkg = _deps.packager.package(
        build_result=state.build_result,
        spec=state.spec,
        certificate=cert,
        pipeline_result=pipeline_result,
        snapshot=snapshot,
    )

    report_path = _deps.report_generator.generate(
        spec=state.spec,
        certificate=cert,
        pipeline_result=pipeline_result,
        snapshot=snapshot,
        export_package=pkg,
    )

    pkg = _deps.packager._update_report_file(pkg, report_path)
    _deps.store.update(session_id, "export_package", pkg)

    return {
        "export_id": pkg.export_id,
        "strategy_file": os.path.basename(pkg.strategy_file),
        "report_file": os.path.basename(pkg.report_file) if pkg.report_file else None,
        "checksum": pkg.checksum,
        "disclaimer": _DISCLAIMER,
    }


@app.get("/api/session/{session_id}/download/strategy")
async def download_strategy(session_id: str):
    """Download the exported standalone strategy Python file."""
    session = _deps.store.get(session_id)
    if session is None:
        raise HTTPException(status_code=404, detail="Session not found")
    pkg: ExportPackage | None = session.get("export_package")
    if pkg is None or not pkg.strategy_file or not os.path.exists(pkg.strategy_file):
        raise HTTPException(status_code=404, detail="Strategy file not found")
    return FileResponse(pkg.strategy_file, media_type="text/x-python",
                        filename=os.path.basename(pkg.strategy_file))


@app.get("/api/session/{session_id}/download/report")
async def download_report(session_id: str):
    """Download the PDF strategy report for a graduated session."""
    session = _deps.store.get(session_id)
    if session is None:
        raise HTTPException(status_code=404, detail="Session not found")
    pkg: ExportPackage | None = session.get("export_package")
    if pkg is None or not pkg.report_file or not os.path.exists(pkg.report_file):
        raise HTTPException(status_code=404, detail="Report file not found")
    return FileResponse(pkg.report_file, media_type="application/pdf",
                        filename=os.path.basename(pkg.report_file))


@app.get("/api/sessions")
async def list_sessions():
    """List all active sessions."""
    return {"sessions": _deps.store.list_sessions(), "disclaimer": _DISCLAIMER}


@app.websocket("/ws/{session_id}")
async def websocket_endpoint(websocket: WebSocket, session_id: str):
    """WebSocket endpoint for real-time pipeline events."""
    await ws_manager.connect(session_id, websocket)
    try:
        while True:
            await websocket.receive_text()
    except WebSocketDisconnect:
        ws_manager.disconnect(session_id, websocket)


def _spec_to_dict(spec: StrategySpec) -> dict[str, Any]:
    from dataclasses import asdict
    data = asdict(spec)
    if isinstance(data.get("created_at"), datetime):
        data["created_at"] = data["created_at"].isoformat()
    return data


def _trigger_build(session_id: str, session: dict[str, Any], state: PipelineState) -> None:
    import threading

    def _build_task():
        try:
            gen = StrategyGenerator(
                llm_provider=_deps.get_llm_provider(),
                build_dir=_deps.build_dir,
            )
            result = gen.generate(state.spec)
            state.build_result = result
            state.transition_to("RUNNING")
            _deps.store.update(session_id, "state", state)
            ws_manager.broadcast(session_id, "pipeline.build_complete", {"success": result.success})

            if result.success:
                event_bus = PipelineEventBus()
                def forward_event(event, data):
                    ws_manager.broadcast(session_id, event, data)
                event_bus.subscribe(forward_event)
                runner = _deps.get_runner(event_bus=event_bus)
                pipeline_result = runner.run(result, state.spec)
                state.pipeline_results.append(pipeline_result)
                state.paper_deployment_id = pipeline_result.paper_deployment_id
                state.transition_to("PAPER_TRADING")
                _deps.store.update(session_id, "state", state)
                ws_manager.broadcast(session_id, "pipeline.deployed", {
                    "status": pipeline_result.status,
                    "deployment_id": pipeline_result.paper_deployment_id,
                })

                tracker = GraduationTracker(session_id=session_id)
                snapshot = PerformanceSnapshot(deployment_id=pipeline_result.paper_deployment_id or "")
                gate_result = _deps.graduation_gates.check(snapshot, pipeline_result)
                tracker.record_check(0, gate_result)
                _deps.store.update(session_id, "graduation_tracker", tracker)

        except Exception as e:
            ws_manager.broadcast(session_id, "pipeline.error", {"error": str(e)})

    t = threading.Thread(target=_build_task, daemon=True)
    t.start()


# ---- Production frontend serving ----

FRONTEND_BUILD = os.path.join(
    os.path.dirname(os.path.dirname(__file__)),
    "frontend", "build",
)

if os.path.isfile(os.path.join(FRONTEND_BUILD, "index.html")):
    app.mount("/static", StaticFiles(directory=os.path.join(FRONTEND_BUILD, "static")), name="frontend_static")

    @app.get("/{full_path:path}", include_in_schema=False)
    async def serve_frontend(full_path: str):
        file_path = os.path.join(FRONTEND_BUILD, full_path)
        if full_path and os.path.isfile(file_path):
            return FileResponse(file_path)
        return FileResponse(os.path.join(FRONTEND_BUILD, "index.html"))
