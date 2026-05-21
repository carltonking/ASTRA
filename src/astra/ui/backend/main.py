"""FastAPI backend — provides REST API and WebSocket for the ASTRA UI."""

import os
import uuid
from contextlib import asynccontextmanager
from typing import Any

from fastapi import FastAPI, HTTPException, WebSocket, WebSocketDisconnect
from fastapi.responses import FileResponse
from pydantic import BaseModel

from astra.planner.spec import StrategySpec
from astra.planner.conversation import PlannerConversation
from astra.builder.generator import StrategyGenerator
from astra.pipeline.state import PipelineState, InvalidStatusTransition
from astra.pipeline.runner import PipelineRunner
from astra.pipeline.aurora_bridge import AuroraBridge
from astra.alpaca.monitor import PerformanceMonitor, PerformanceSnapshot
from astra.alpaca.deployer import StrategyDeployer, Deployment
from astra.alpaca.client import AstraAlpacaClient
from astra.graduation.gates import GraduationGates
from astra.graduation.tracker import GraduationTracker
from astra.graduation.certificate import GraduationCertificate
from astra.graduation.gates import GraduationError
from astra.optimizer.history import OptimizationHistory
from astra.export.packager import StrategyPackager, ExportPackage
from astra.export.report import ReportGenerator
from astra.ui.backend.session_store import SessionStore
from astra.ui.backend.websocket import ws_manager


_DISCLAIMER = (
    "ASTRA research results are not profitability guarantees. "
    "Past performance does not predict future results. "
    "For research purposes only."
)


class AppDependencies:
    def __init__(self) -> None:
        self.store = SessionStore()
        self.anthropic_key: str = os.environ.get("ANTHROPIC_API_KEY", "")
        self.build_dir: str = os.environ.get("ASTRA_BUILD_DIR", ".astra_builds")
        self.export_dir: str = os.environ.get("ASTRA_EXPORT_DIR", ".astra_exports")
        self.alpaca_key: str = os.environ.get("APCA_API_KEY_ID", "")
        self.alpaca_secret: str = os.environ.get("APCA_API_SECRET_KEY", "")
        self.alpaca_url: str = os.environ.get("APCA_PAPER_URL", "https://paper-api.alpaca.markets")
        self.packager = StrategyPackager(export_dir=self.export_dir)
        self.report_generator = ReportGenerator(export_dir=self.export_dir)
        self.graduation_gates = GraduationGates()

    def get_conversation(self) -> PlannerConversation:
        return PlannerConversation(anthropic_api_key=self.anthropic_key)

    def get_runner(self) -> PipelineRunner:
        return PipelineRunner(
            anthropic_api_key=self.anthropic_key,
            alpaca_paper_key=self.alpaca_key,
            alpaca_paper_secret=self.alpaca_secret,
            alpaca_base_url=self.alpaca_url,
            build_dir=self.build_dir,
        )


_deps = AppDependencies()


@asynccontextmanager
async def lifespan(app: FastAPI):
    yield


app = FastAPI(title="ASTRA", version="0.1.0", lifespan=lifespan)


class StartRequest(BaseModel):
    user_idea: str


class ChatRequest(BaseModel):
    message: str


@app.get("/api/health")
async def health():
    return {"status": "ok", "disclaimer": _DISCLAIMER}


@app.post("/api/session/start")
async def start_session(req: StartRequest):
    session_id = str(uuid.uuid4())
    _deps.store.create(session_id)

    conv = _deps.get_conversation()
    try:
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
    session = _deps.store.get(session_id)
    if session is None:
        raise HTTPException(status_code=404, detail="Session not found")
    return {"disclaimer": _DISCLAIMER, "message": "No active paper trading deployment"}


@app.get("/api/session/{session_id}/graduation")
async def get_graduation(session_id: str):
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


import json
from datetime import datetime


@app.post("/api/session/{session_id}/export")
async def export_strategy(session_id: str):
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
    return {"sessions": _deps.store.list_sessions(), "disclaimer": _DISCLAIMER}


@app.websocket("/ws/{session_id}")
async def websocket_endpoint(websocket: WebSocket, session_id: str):
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
                anthropic_api_key=_deps.anthropic_key,
                build_dir=_deps.build_dir,
            )
            result = gen.generate(state.spec)
            state.build_result = result
            state.transition_to("RUNNING")
            _deps.store.update(session_id, "state", state)
            ws_manager.broadcast(session_id, "pipeline.build_complete", {"success": result.success})

            if result.success:
                runner = _deps.get_runner()
                pipeline_result = runner.run(result, state.spec)
                state.pipeline_results.append(pipeline_result)
                state.paper_deployment_id = pipeline_result.paper_deployment_id
                state.transition_to("PAPER_TRADING")
                _deps.store.update(session_id, "state", state)
                ws_manager.broadcast(session_id, "pipeline.deployed", {
                    "status": pipeline_result.status,
                    "deployment_id": pipeline_result.paper_deployment_id,
                })

        except Exception as e:
            ws_manager.broadcast(session_id, "pipeline.error", {"error": str(e)})

    t = threading.Thread(target=_build_task, daemon=True)
    t.start()
