"""FastAPI entry point for the VisionNav-Sim backend.

Integrates the ROSService, MemoryStore, OllamaPlanner, SafetyLayer, and ROSExecutor
into a unified REST API for the frontend dashboard.
"""

from __future__ import annotations

import logging
from contextlib import asynccontextmanager
from typing import Any

from fastapi import BackgroundTasks, FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
import os
from geometry_msgs.msg import Twist
from pydantic import BaseModel, Field

from backend.app.memory.memory_store import InMemoryMemoryStore
from backend.app.models.types import PlannerResponse, ReasoningBreakdown
from backend.app.services.ollama_planner import OllamaPlanner
from backend.app.services.ros_service import ROSService
from backend.app.services.safety_layer import SafetyLayer
from backend.app.state.robot_context_cache import RobotContextCache

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# --- Global Infrastructure ---
memory_store = InMemoryMemoryStore()
context_cache = RobotContextCache()
ros_service = ROSService(memory_store, context_cache)
planner = OllamaPlanner()
safety = SafetyLayer()

# Simple in-memory cache for the latest reasoning breakdown by session ID
latest_reasoning: dict[str, ReasoningBreakdown] = {}


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Manage global dependencies on startup and shutdown."""
    logger.info("Starting VisionNav-Sim API...")
    ros_service.start()
    yield
    logger.info("Shutting down VisionNav-Sim API...")
    ros_service.shutdown()


app = FastAPI(title="VisionNav-Sim API", lifespan=lifespan)

# Allow frontend dashboard to communicate with the backend
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# --- API Schemas ---

class CommandRequest(BaseModel):
    session_id: str = Field(..., description="Unique ID for the conversation session.")
    command: str = Field(..., description="Natural language command from the operator.")


class ManualControlRequest(BaseModel):
    linear_x: float = Field(default=0.0)
    angular_z: float = Field(default=0.0)


# --- Endpoints ---

@app.post("/api/command", response_model=PlannerResponse)
def process_command(request: CommandRequest, background_tasks: BackgroundTasks):
    """Process a natural language command and dispatch to the ROS executor."""
    
    # 1. Fetch or create session memory
    memory = memory_store.create_session("robot_1", request.session_id)
    memory.add_command(request.command)
    
    # 2. Extract current context and history
    context = context_cache.get_context()
    
    # 3. Generate plan via Ollama
    try:
        planner_response = planner.generate_plan(request.command, context, memory.get_context())
    except Exception as e:
        logger.error(f"Planner failed: {e}")
        raise HTTPException(status_code=500, detail="Failed to generate plan from LLM.")
        
    # 4. Cache reasoning for dashboard
    latest_reasoning[request.session_id] = planner_response.reasoning
        
    # 5. Safety Validation
    is_safe, error_msg = safety.validate_plan(planner_response)
    if not is_safe:
        logger.warning(f"Safety violation: {error_msg}")
        raise HTTPException(status_code=400, detail=f"Unsafe plan rejected: {error_msg}")
        
    # 6. Execute in background
    executor = ros_service.get_executor()
    background_tasks.add_task(executor.execute_plan, request.session_id, planner_response)
    # 7. Return generated plan immediately
    return planner_response


@app.post("/api/manual")
async def manual_control(request: ManualControlRequest):
    """Fallback manual teleoperation via /cmd_vel."""
    try:
        executor = ros_service.get_executor()
        msg = Twist()
        msg.linear.x = request.linear_x
        msg.angular.z = request.angular_z
        executor.node.cmd_vel_pub.publish(msg)
        return {"status": "ok"}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/api/state")
async def get_robot_state():
    """Return the cached real-time robot context."""
    return context_cache.serialize()


@app.get("/api/reasoning")
async def get_reasoning(session_id: str):
    """Return the latest reasoning breakdown for a specific session."""
    reasoning = latest_reasoning.get(session_id)
    if not reasoning:
        return {}
    return reasoning.model_dump(mode="json")


@app.get("/api/current-task")
async def get_current_task(session_id: str):
    """Return the active task state from memory."""
    memory = memory_store.get_session("robot_1", session_id)
    if not memory:
        return {"status": "idle", "active_task": ""}
    
    state = memory.get_context()
    return {
        "active_task": state.active_task,
        "task_history": [t.model_dump(mode="json") for t in state.task_history[-5:]]
    }


@app.get("/api/navigation")
async def get_navigation_history(session_id: str):
    """Return the navigation history from memory."""
    memory = memory_store.get_session("robot_1", session_id)
    if not memory:
        return {"navigation_history": []}
    
    state = memory.get_context()
    return {
        "navigation_history": [n.model_dump(mode="json") for n in state.navigation_history]
    }


@app.get("/api/camera/frame.jpg")
async def get_camera_frame():
    """Return the latest camera frame."""
    file_path = "backend/app/api/camera_frame.jpg"
    if os.path.exists(file_path):
        return FileResponse(file_path)
    return {"error": "Camera frame not found"}
