"""Multi-robot session manager for VisionNav-Sim task memory.

This layer owns the session lifecycle and keeps the storage implementation
abstract so the project can move from in-memory persistence to Redis, SQLite,
or PostgreSQL without changing the planner-facing API.
"""

from __future__ import annotations

from backend.app.memory.conversation_memory import RobotTaskMemory
from backend.app.memory.memory_store import InMemoryMemoryStore, MemoryStore


class SessionManager:
    """Create, load, delete, and list robot memory sessions."""

    def __init__(self, store: MemoryStore | None = None) -> None:
        self._store = store or InMemoryMemoryStore()
        self._active_sessions: dict[str, str] = {}

    def create_session(self, robot_id: str = "robot_1", session_id: str | None = None) -> RobotTaskMemory:
        """Create a new robot task memory session."""

        memory = self._store.create_session(robot_id=robot_id, session_id=session_id)
        self._active_sessions[robot_id] = memory.session_id
        return memory

    def get_session(self, robot_id: str = "robot_1", session_id: str | None = None) -> RobotTaskMemory | None:
        """Load a robot task memory session by robot and session identifier."""

        if session_id is None:
            session_id = self._active_sessions.get(robot_id)
        if session_id is None:
            return None
        session = self._store.get_session(robot_id, session_id)
        if session is None:
            return None
        return session

    def delete_session(self, robot_id: str, session_id: str) -> bool:
        """Delete a stored robot session."""

        return self._store.delete_session(robot_id, session_id)

    def list_sessions(self, robot_id: str | None = None) -> list[str]:
        """List sessions for one robot or all robots."""

        return self._store.list_sessions(robot_id=robot_id)


__all__ = ["SessionManager"]