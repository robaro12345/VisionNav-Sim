"""Storage abstraction for robot task memory.

The store layer intentionally does not assume any specific persistence backend.
An in-memory implementation ships now, while Redis, SQLite, or PostgreSQL can
be added behind the same protocol later.
"""

from __future__ import annotations

from collections import OrderedDict
from threading import RLock
from typing import Any, Protocol, runtime_checkable
from uuid import uuid4

from pydantic import BaseModel, ConfigDict, Field

from backend.app.memory.conversation_memory import RobotTaskMemory
from backend.app.models.types import ConversationMemory


class SessionRecord(BaseModel):
    """Stored session snapshot plus lightweight metadata."""

    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)

    robot_id: str = Field(..., description="Robot identifier such as robot_1.")
    session_id: str = Field(..., description="Conversation session identifier.")
    memory: ConversationMemory = Field(..., description="Stored robot task memory snapshot.")
    updated_at: str = Field(..., description="ISO-8601 update timestamp.")


@runtime_checkable
class MemoryStore(Protocol):
    """Persistence boundary for robot task memory."""

    def create_session(self, robot_id: str, session_id: str | None = None) -> RobotTaskMemory:
        """Create a new session snapshot for a robot."""

    def get_session(self, robot_id: str, session_id: str) -> RobotTaskMemory | None:
        """Fetch a stored session snapshot."""

    def delete_session(self, robot_id: str, session_id: str) -> bool:
        """Delete a stored session snapshot."""

    def list_sessions(self, robot_id: str | None = None) -> list[str]:
        """Return all stored session identifiers, optionally filtered by robot identifier."""


class InMemoryMemoryStore:
    """Thread-safe in-memory store for robot task memory sessions."""

    def __init__(self) -> None:
        self._lock = RLock()
        self._sessions: dict[str, OrderedDict[str, RobotTaskMemory]] = {}

    def create_session(self, robot_id: str, session_id: str | None = None) -> RobotTaskMemory:
        with self._lock:
            robot_sessions = self._sessions.setdefault(robot_id, OrderedDict())
            resolved_session_id = session_id or uuid4().hex
            memory = RobotTaskMemory(session_id=resolved_session_id, robot_id=robot_id)
            robot_sessions[memory.session_id] = memory
            return memory

    def get_session(self, robot_id: str, session_id: str) -> RobotTaskMemory | None:
        with self._lock:
            robot_sessions = self._sessions.get(robot_id)
            if robot_sessions is None:
                return None
            return robot_sessions.get(session_id)

    def delete_session(self, robot_id: str, session_id: str) -> bool:
        with self._lock:
            robot_sessions = self._sessions.get(robot_id)
            if robot_sessions is None or session_id not in robot_sessions:
                return False
            del robot_sessions[session_id]
            if not robot_sessions:
                del self._sessions[robot_id]
            return True

    def list_sessions(self, robot_id: str | None = None) -> list[str]:
        with self._lock:
            if robot_id is not None:
                robot_sessions = self._sessions.get(robot_id, OrderedDict())
                return list(robot_sessions.keys())

            sessions: list[str] = []
            for robot_sessions in self._sessions.values():
                sessions.extend(robot_sessions.keys())
            return sessions

    def dump(self) -> dict[str, Any]:
        """Return the complete store as JSON-friendly data for tests or debugging."""

        with self._lock:
            return {
                robot_id: [record.model_dump(mode="json") for record in robot_sessions.values()]
                for robot_id, robot_sessions in self._sessions.items()
            }


__all__ = ["InMemoryMemoryStore", "MemoryStore", "SessionRecord"]