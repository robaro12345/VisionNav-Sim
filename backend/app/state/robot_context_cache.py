"""In-memory cache for the latest robot context snapshot.

This cache is intentionally free of ROS dependencies so the backend can
consume a single snapshot and later fan it out to HTTP and websocket clients.
"""

from __future__ import annotations

from threading import RLock
from typing import Any, Callable

from backend.app.models.types import RobotContext


class RobotContextCache:
    """Store and broadcast the latest robot context snapshot."""

    def __init__(self, initial_context: RobotContext | None = None) -> None:
        self._lock = RLock()
        self._context = initial_context or RobotContext()
        self._listeners: list[Callable[[RobotContext], None]] = []

    def get_context(self) -> RobotContext:
        """Return a deep copy of the current cached context."""

        with self._lock:
            return self._context.model_copy(deep=True)

    def update_context(self, context: RobotContext | dict[str, Any]) -> RobotContext:
        """Replace the cached context with the latest snapshot."""

        validated_context = context if isinstance(context, RobotContext) else RobotContext.model_validate(context)
        with self._lock:
            self._context = validated_context
            listeners = list(self._listeners)

        for listener in listeners:
            listener(validated_context.model_copy(deep=True))

        return self.get_context()

    def register_listener(self, listener: Callable[[RobotContext], None]) -> None:
        """Register a listener for future websocket or push updates."""

        with self._lock:
            self._listeners.append(listener)

    def serialize(self) -> dict[str, Any]:
        """Return the current context as JSON-compatible data."""

        with self._lock:
            return self._context.model_dump(mode="json")
