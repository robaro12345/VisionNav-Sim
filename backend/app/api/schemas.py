"""API-facing schemas built from the shared VisionNav domain models.

These request and response models keep the HTTP layer thin while still
providing a strongly typed contract for every service consumer.
"""

from __future__ import annotations

from typing import Any

from pydantic import BaseModel, ConfigDict, Field

from backend.app.models.types import (
    ActionPlan,
    ConversationMemory,
    Detection,
    NavigationStatus,
    PlannerResponse,
    RobotContext,
    RobotState,
    TaskStatus,
)


class CommandRequest(BaseModel):
    """Natural-language command request sent by the frontend."""

    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)

    user_command: str = Field(..., min_length=1, description="Natural-language robot command.")
    image: str | None = Field(default=None, description="Optional image payload or reference.")
    session_id: str | None = Field(default=None, description="Optional client session identifier.")


class ManualCommandRequest(BaseModel):
    """Manual motion command request that bypasses the planner."""

    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)

    direction: str = Field(..., min_length=1, description="Manual control direction.")
    intensity: float = Field(default=0.35, ge=0.0, le=1.0, description="Normalized drive intensity.")
    duration_seconds: float = Field(
        default=0.25,
        ge=0.0,
        description="Duration of the manual command in seconds.",
    )


class PlannerRequest(BaseModel):
    """Internal request payload used by the planner service."""

    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)

    user_command: str = Field(..., min_length=1)
    robot_context: RobotContext = Field(default_factory=RobotContext)
    memory: ConversationMemory = Field(default_factory=ConversationMemory)
    detections: list[Detection] = Field(default_factory=list)
    scene_summary: str = Field(default="")
    image: str | None = Field(default=None)


class CommandResponse(BaseModel):
    """Standard response returned after processing a command."""

    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)

    accepted: bool = Field(..., description="Whether the request passed validation.")
    message: str = Field(default="", description="Operator-facing status message.")
    reasoning: PlannerResponse | None = Field(default=None, description="Planner output if available.")
    task_status: TaskStatus | None = Field(default=None, description="Current task state.")
    navigation_status: NavigationStatus | None = Field(default=None, description="Navigation state.")
    robot_state: RobotState | None = Field(default=None, description="Latest robot state snapshot.")


class StateResponse(BaseModel):
    """Combined robot state payload exposed by the backend API."""

    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)

    robot_context: RobotContext = Field(default_factory=RobotContext)
    memory: ConversationMemory = Field(default_factory=ConversationMemory)


class ReasoningResponse(BaseModel):
    """Response wrapper for the latest planner reasoning output."""

    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)

    reasoning: PlannerResponse | None = Field(default=None)


class CurrentTaskResponse(BaseModel):
    """Response wrapper for the currently active task."""

    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)

    task_status: TaskStatus = Field(default_factory=TaskStatus)


class NavigationResponse(BaseModel):
    """Response wrapper for the current navigation state."""

    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)

    navigation_status: NavigationStatus = Field(default_factory=NavigationStatus)


class DetectionsResponse(BaseModel):
    """Optional convenience payload for frontend rendering."""

    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)

    detections: list[Detection] = Field(default_factory=list)


class PlannerContextResponse(BaseModel):
    """Planner-ready payload returned by the context builder."""

    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)

    user_command: str = Field(default="")
    robot_context: RobotContext = Field(default_factory=RobotContext)
    memory: ConversationMemory = Field(default_factory=ConversationMemory)
    detections: list[Detection] = Field(default_factory=list)
    scene_summary: str = Field(default="")
    image: str | None = Field(default=None)


class APIErrorResponse(BaseModel):
    """Structured error response used by the HTTP layer."""

    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)

    detail: str = Field(..., description="Human-readable error message.")
    code: str | None = Field(default=None, description="Optional machine-readable error code.")
    meta: dict[str, Any] = Field(default_factory=dict, description="Additional error context.")


__all__ = [
    "APIErrorResponse",
    "CommandRequest",
    "CommandResponse",
    "CurrentTaskResponse",
    "DetectionsResponse",
    "ManualCommandRequest",
    "NavigationResponse",
    "PlannerContextResponse",
    "PlannerRequest",
    "ReasoningResponse",
    "StateResponse",
]