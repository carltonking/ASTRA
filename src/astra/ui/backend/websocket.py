"""WebSocket manager — bridges PipelineEventBus to frontend clients."""

import json
from datetime import datetime, timezone
from typing import Any

from fastapi import WebSocket


class WebSocketManager:
    def __init__(self) -> None:
        self._connections: dict[str, list[WebSocket]] = {}
        self._event_histories: dict[str, list[dict[str, Any]]] = {}

    async def connect(self, session_id: str, websocket: WebSocket) -> None:
        await websocket.accept()
        if session_id not in self._connections:
            self._connections[session_id] = []
            self._event_histories[session_id] = []
        self._connections[session_id].append(websocket)

        for event in self._event_histories.get(session_id, []):
            await websocket.send_text(json.dumps(event))

    def disconnect(self, session_id: str, websocket: WebSocket) -> None:
        conns = self._connections.get(session_id, [])
        if websocket in conns:
            conns.remove(websocket)

    def record_event(self, session_id: str, event: str, data: dict[str, Any]) -> None:
        record = {
            "event": event,
            "data": data,
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "session_id": session_id,
        }
        if session_id not in self._event_histories:
            self._event_histories[session_id] = []
        self._event_histories[session_id].append(record)

    def broadcast(self, session_id: str, event: str, data: dict[str, Any]) -> None:
        self.record_event(session_id, event, data)
        message = json.dumps({
            "event": event,
            "data": data,
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "session_id": session_id,
        })
        conns = self._connections.get(session_id, [])
        for ws in conns[:]:
            try:
                import asyncio
                loop = asyncio.new_event_loop()
                loop.run_until_complete(ws.send_text(message))
                loop.close()
            except Exception:
                conns.remove(ws)


ws_manager = WebSocketManager()
