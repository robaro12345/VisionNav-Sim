"""Robot task memory for VisionNav-Sim.

This module manages short-term and current-session memory for one robot session
without mixing in chatbot-style conversation state. It stores the minimal
structured context needed for reference resolution such as "it", "that object",
and "go back".
"""

from __future__ import annotations

from copy import deepcopy
from datetime import datetime, timezone
from threading import RLock
from typing import Any

from backend.app.models.types import (
    ConversationMemory as ConversationMemoryModel,
    ExecutionState,
    NavigationHistoryEntry,
    RobotState,
    TaskHistoryEntry,
)


class RobotTaskMemory:
    """Thread-safe task memory wrapper for a single robot session."""

    def __init__(
        self,
        session_id: str,
        robot_id: str = "robot_1",
        state: ConversationMemoryModel | dict[str, Any] | None = None,
    ) -> None:
        self.session_id = session_id
        self.robot_id = robot_id
        self._lock = RLock()
        self._updated_at = datetime.now(timezone.utc).isoformat()
        self._state = self._coerce_state(state)

    def _coerce_state(self, state: ConversationMemoryModel | dict[str, Any] | None) -> ConversationMemoryModel:
        if state is None:
            return ConversationMemoryModel(session_id=self.session_id)

        memory_state = state if isinstance(state, ConversationMemoryModel) else ConversationMemoryModel.model_validate(state)
        if not memory_state.session_id:
            memory_state.session_id = self.session_id
        return memory_state

    def _touch(self) -> None:
        self._updated_at = datetime.now(timezone.utc).isoformat()

    @property
    def updated_at(self) -> str:
        """Return the last update timestamp for session metadata."""

        return self._updated_at

    def add_command(self, command: str) -> ConversationMemoryModel:
        """Record a natural-language command in short-term memory."""

        command = command.strip()
        if not command:
            return self.get_context()

        with self._lock:
            self._state.recent_commands.append(command)
            if len(self._state.recent_commands) > 15:
                self._state.recent_commands = self._state.recent_commands[-15:]
            self._touch()
            return self.get_context()

    def set_current_goal(self, goal: str) -> ConversationMemoryModel:
        """Set the active goal and preserve the previous goal for reference resolution."""

        goal = goal.strip()
        with self._lock:
            if self._state.current_goal and self._state.current_goal != goal:
                self._state.previous_goals.append(self._state.current_goal)
            self._state.current_goal = goal
            if len(self._state.previous_goals) > 20:
                self._state.previous_goals = self._state.previous_goals[-20:]
            self._touch()
            return self.get_context()

    def set_current_target(self, target: str) -> ConversationMemoryModel:
        """Set the active target and preserve the previous target for pronoun resolution."""

        target = target.strip()
        with self._lock:
            if self._state.current_target and self._state.current_target != target:
                self._state.previous_targets.append(self._state.current_target)
            self._state.current_target = target
            if len(self._state.previous_targets) > 20:
                self._state.previous_targets = self._state.previous_targets[-20:]
            self._touch()
            return self.get_context()

    def start_task(self, task: str) -> ConversationMemoryModel:
        """Mark a task as active and capture the starting pose when available."""

        task = task.strip()
        with self._lock:
            self._state.active_task = task
            if self._state.last_known_pose is not None and self._state.start_pose is None:
                self._state.start_pose = self._state.last_known_pose.model_copy(deep=True)
            self._state.task_history.append(
                TaskHistoryEntry(
                    task=task,
                    status=ExecutionState.RUNNING,
                    started_at=self._now(),
                    note="task started",
                )
            )
            self._touch()
            return self.get_context()

    def complete_task(self, task: str) -> ConversationMemoryModel:
        """Record task completion and clear the active task if it matches."""

        task = task.strip()
        with self._lock:
            self._state.completed_tasks.append(
                TaskHistoryEntry(
                    task=task,
                    status=ExecutionState.SUCCEEDED,
                    started_at=self._now(),
                    ended_at=self._now(),
                    note="task completed",
                )
            )
            self._state.task_history.append(
                TaskHistoryEntry(
                    task=task,
                    status=ExecutionState.SUCCEEDED,
                    started_at=self._now(),
                    ended_at=self._now(),
                    note="task completed",
                )
            )
            if self._state.active_task == task:
                self._state.active_task = ""
            self._touch()
            return self.get_context()

    def cancel_task(self, task: str) -> ConversationMemoryModel:
        """Record task cancellation and clear the active task if needed."""

        task = task.strip()
        with self._lock:
            self._state.task_history.append(
                TaskHistoryEntry(
                    task=task,
                    status=ExecutionState.CANCELLED,
                    started_at=self._now(),
                    ended_at=self._now(),
                    note="task cancelled",
                )
            )
            if self._state.active_task == task:
                self._state.active_task = ""
            self._touch()
            return self.get_context()

    def record_navigation(self, target: str | dict[str, Any]) -> ConversationMemoryModel:
        """Add a navigation record for reference-aware planning."""

        with self._lock:
            record = self._navigation_entry(target)
            self._state.navigation_history.append(record)
            if len(self._state.navigation_history) > 50:
                self._state.navigation_history = self._state.navigation_history[-50:]
            self._touch()
            return self.get_context()

    def record_pose(self, pose: RobotState | dict[str, Any]) -> ConversationMemoryModel:
        """Store the last known pose and snapshot the task start pose when needed."""

        pose_model = pose if isinstance(pose, RobotState) else RobotState.model_validate(pose)
        with self._lock:
            if self._state.start_pose is None and self._state.active_task:
                self._state.start_pose = pose_model.model_copy(deep=True)
            self._state.last_known_pose = pose_model.model_copy(deep=True)
            self._touch()
            return self.get_context()

    def get_context(self) -> ConversationMemoryModel:
        """Return a deep copy of the current memory snapshot."""

        with self._lock:
            return self._state.model_copy(deep=True)

    def clear(self) -> ConversationMemoryModel:
        """Clear the session memory while keeping the session identity."""

        with self._lock:
            self._state = ConversationMemoryModel(session_id=self.session_id)
            self._touch()
            return self.get_context()

    def serialize(self) -> dict[str, Any]:
        """Return the memory snapshot as JSON-serializable data."""

        with self._lock:
            return self._state.model_dump(mode="json")

    def snapshot(self) -> ConversationMemoryModel:
        """Alias for get_context for store integrations."""

        return self.get_context()

    @classmethod
    def from_snapshot(
        cls,
        state: ConversationMemoryModel | dict[str, Any],
        robot_id: str = "robot_1",
    ) -> "RobotTaskMemory":
        """Create a runtime memory wrapper from a stored snapshot."""

        memory_state = state if isinstance(state, ConversationMemoryModel) else ConversationMemoryModel.model_validate(state)
        return cls(session_id=memory_state.session_id, robot_id=robot_id, state=memory_state)

    @staticmethod
    def _now() -> str:
        return datetime.now(timezone.utc).isoformat()

    def _navigation_entry(self, target: str | dict[str, Any]) -> NavigationHistoryEntry:
        if isinstance(target, dict):
            return NavigationHistoryEntry(
                target=str(target.get("target") or target.get("label") or target.get("name") or ""),
                goal=str(target.get("goal") or self._state.current_goal),
                pose_before=deepcopy(self._state.last_known_pose),
                pose_after=target.get("pose_after")
                if isinstance(target.get("pose_after"), RobotState)
                else (RobotState.model_validate(target["pose_after"]) if target.get("pose_after") else None),
                result=str(target.get("result") or "recorded"),
                timestamp=self._now(),
            )

        return NavigationHistoryEntry(
            target=target.strip(),
            goal=self._state.current_goal,
            pose_before=deepcopy(self._state.last_known_pose),
            pose_after=None,
            result="navigation recorded",
            timestamp=self._now(),
        )


__all__ = ["RobotTaskMemory"]