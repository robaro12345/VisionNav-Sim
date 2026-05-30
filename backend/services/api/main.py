from __future__ import annotations

from fastapi import FastAPI, WebSocket, WebSocketDisconnect
from fastapi.responses import HTMLResponse, Response
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field
from typing import Any, Dict, List, Optional
import asyncio
import json
import logging
import time
from pathlib import Path

from services.ai_core.graph import AgentState, build_graph
from services.ros_bridge import RosBridge

logger = logging.getLogger(__name__)

app = FastAPI(title="Synapse Robotics Copilot", version="0.1.0")
STATIC_DIR = Path(__file__).resolve().parent / "static"

if STATIC_DIR.exists():
    app.mount("/static", StaticFiles(directory=STATIC_DIR), name="static")


class CommandRequest(BaseModel):
    command: str = Field(default="")
    state: Dict[str, Any] = Field(default_factory=dict)


class DriveRequest(BaseModel):
    linear_x: float = Field(default=0.0)
    angular_z: float = Field(default=0.0)
    pulse_duration_ms: int = Field(default=250, ge=0, le=5000)


class ConnectionManager:
    def __init__(self) -> None:
        self._connections: List[WebSocket] = []

    async def connect(self, websocket: WebSocket) -> None:
        await websocket.accept()
        self._connections.append(websocket)

    def disconnect(self, websocket: WebSocket) -> None:
        if websocket in self._connections:
            self._connections.remove(websocket)

    async def broadcast(self, payload: Dict[str, Any]) -> None:
        message = json.dumps(payload, default=str)
        stale: List[WebSocket] = []
        for websocket in list(self._connections):
            try:
                await websocket.send_text(message)
            except Exception:
                stale.append(websocket)
        for websocket in stale:
            self.disconnect(websocket)


manager = ConnectionManager()


def _json_safe(value: Any) -> Any:
    try:
        import numpy as np
    except Exception:
        np = None

    if value is None or isinstance(value, (str, int, float, bool)):
        return value
    if np is not None and isinstance(value, np.ndarray):
        return {"type": "ndarray", "shape": list(value.shape), "dtype": str(value.dtype)}
    if isinstance(value, dict):
        return {str(key): _json_safe(item) for key, item in value.items()}
    if isinstance(value, (list, tuple, set)):
        return [_json_safe(item) for item in value]
    return str(value)


def _prepare_state(command: str, state: Dict[str, Any], bridge: Optional[RosBridge]) -> AgentState:
    runtime_state: AgentState = dict(state or {})
    runtime_state.setdefault("memory", {})
    runtime_state.setdefault("sensors", {})
    runtime_state["command"] = command
    runtime_state["memory"]["command"] = command
    runtime_state["timestamp"] = time.time()

    if bridge is not None:
        try:
            snapshot = bridge.snapshot_sensors()
        except Exception:
            logger.exception("Failed to capture ROS sensor snapshot")
        else:
            runtime_state["sensors"].update({key: value for key, value in snapshot.items() if value is not None})

    return runtime_state


def _summarize_result(state: Any) -> Any:
    return _json_safe(state)


async def _stop_after_delay(bridge: RosBridge, pulse_duration_ms: int) -> None:
    if pulse_duration_ms > 0:
        await asyncio.sleep(pulse_duration_ms / 1000.0)
    try:
        await asyncio.to_thread(bridge.send_velocity, 0.0, 0.0)
    except Exception:
        logger.exception("Failed to stop robot after motion pulse")


def _camera_jpeg_bytes(bridge: Optional[RosBridge]) -> Optional[bytes]:
    if bridge is None or getattr(bridge, "last_image", None) is None:
        return None

    try:
        import cv2

        frame = bridge.last_image
        if frame is None:
            return None
        if getattr(frame, "dtype", None) is not None and str(frame.dtype) != "uint8":
            frame = frame.astype("uint8")
        success, encoded = cv2.imencode(".jpg", frame)
    except Exception:
        logger.exception("Failed to encode camera frame")
        return None

    if not success:
        return None
    return encoded.tobytes()


async def _run_command(command: str, state: Dict[str, Any]) -> Dict[str, Any]:
    runner = app.state.runner
    bridge: Optional[RosBridge] = app.state.bridge
    runtime_state = _prepare_state(command, state, bridge)
    result = await asyncio.to_thread(runner.invoke, runtime_state)

    memory = result.get("memory", {}) if isinstance(result, dict) else {}
    drive_request = memory.get("drive_request") if isinstance(memory, dict) else None
    if drive_request and bridge is not None:
        try:
            await asyncio.to_thread(
                bridge.send_velocity,
                float(drive_request.get("linear_x", 0.0)),
                float(drive_request.get("angular_z", 0.0)),
            )
            pulse_duration_ms = int(drive_request.get("pulse_duration_ms", 900) or 0)
            if pulse_duration_ms > 0 and (
                float(drive_request.get("linear_x", 0.0)) != 0.0 or float(drive_request.get("angular_z", 0.0)) != 0.0
            ):
                asyncio.create_task(_stop_after_delay(bridge, pulse_duration_ms))
        except Exception:
            logger.exception("Failed to publish motion pulse")
    goal = memory.get("goal")
    if goal and bridge is not None and not drive_request:
        try:
            await asyncio.to_thread(bridge.send_goal, goal)
        except Exception:
            logger.exception("Failed to publish goal")

    payload = {"type": "command_result", "command": command, "result": _summarize_result(result)}
    app.state.last_result = payload
    await manager.broadcast(payload)
    return payload


@app.get("/", response_class=HTMLResponse)
async def dashboard() -> HTMLResponse:
    index_file = STATIC_DIR / "index.html"
    if index_file.exists():
        return HTMLResponse(index_file.read_text(encoding="utf-8"))

    return HTMLResponse("<h1>Dashboard not found</h1>", status_code=404)


@app.on_event("startup")
async def _startup() -> None:
    bridge = RosBridge()
    app.state.bridge = bridge
    try:
        bridge.start()
        logger.info("RosBridge started")
    except Exception as exc:
        logger.warning("RosBridge could not start on startup: %s", exc)
    app.state.runner = build_graph(bridge=bridge)
    app.state.last_result = None


@app.on_event("shutdown")
async def _shutdown() -> None:
    try:
        bridge: RosBridge = app.state.bridge
        if bridge:
            bridge.stop()
            logger.info("RosBridge stopped")
    except Exception:
        logger.exception("Error stopping RosBridge")


@app.get("/health")
async def health() -> Dict[str, Any]:
    bridge = getattr(app.state, "bridge", None)
    return {
        "status": "ok",
        "bridge_running": bool(getattr(bridge, "is_running", False)),
        "agents": list(getattr(app.state.runner, "sequence", [])),
    }


@app.get("/state")
async def state() -> Dict[str, Any]:
    bridge = getattr(app.state, "bridge", None)
    sensors = {}
    if bridge is not None:
        try:
            sensors = _json_safe(bridge.snapshot_sensors())
        except Exception:
            logger.exception("Failed to serialize ROS sensor snapshot")
    return {"sensors": sensors, "last_result": getattr(app.state, "last_result", None)}


@app.get("/camera/frame.jpg")
async def camera_frame() -> Response:
    bridge = getattr(app.state, "bridge", None)
    frame = _camera_jpeg_bytes(bridge)
    if frame is None:
        return Response(status_code=204)
    return Response(content=frame, media_type="image/jpeg")


@app.post("/command")
async def command(request: CommandRequest) -> Dict[str, Any]:
    return await _run_command(request.command, request.state)


@app.post("/drive")
async def drive(request: DriveRequest) -> Dict[str, Any]:
    bridge = getattr(app.state, "bridge", None)
    if bridge is None:
        return {"ok": False, "error": "ROS bridge unavailable"}

    try:
        await asyncio.to_thread(bridge.send_velocity, request.linear_x, request.angular_z)
        if request.pulse_duration_ms > 0 and (request.linear_x != 0.0 or request.angular_z != 0.0):
            asyncio.create_task(_stop_after_delay(bridge, request.pulse_duration_ms))
    except Exception as exc:
        logger.exception("Failed to publish velocity")
        return {"ok": False, "error": str(exc)}

    payload = {
        "type": "drive_result",
        "linear_x": request.linear_x,
        "angular_z": request.angular_z,
        "ok": True,
    }
    await manager.broadcast(payload)
    return payload


@app.post("/stop")
async def stop_robot() -> Dict[str, Any]:
    return await drive(DriveRequest(linear_x=0.0, angular_z=0.0))


@app.websocket("/ws")
async def ws_endpoint(websocket: WebSocket) -> None:
    await manager.connect(websocket)
    try:
        await websocket.send_text(json.dumps({"type": "connected"}))
        while True:
            text = await websocket.receive_text()
            try:
                payload = json.loads(text)
            except Exception:
                await websocket.send_text(json.dumps({"type": "error", "error": "invalid json"}))
                continue

            action = payload.get("action")
            if action == "ping":
                await websocket.send_text(json.dumps({"type": "pong"}))
            elif action == "state":
                await websocket.send_text(json.dumps({"type": "state", "state": await state()}))
            elif action == "command":
                result = await _run_command(str(payload.get("command", "")), payload.get("state", {}) or {})
                await websocket.send_text(json.dumps(result, default=str))
            else:
                await websocket.send_text(json.dumps({"type": "error", "error": "unknown action"}))
    except WebSocketDisconnect:
        pass
    finally:
        manager.disconnect(websocket)


if __name__ == "__main__":
    import uvicorn

    uvicorn.run("services.api.main:app", host="0.0.0.0", port=8000, reload=False)
