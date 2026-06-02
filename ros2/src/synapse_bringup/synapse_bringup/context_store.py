"""Thread-safe runtime context store for the ROS side of VisionNav-Sim.

The store keeps the latest robot snapshot in memory and exposes a small API
for the ROS context node and any future bridge components.
"""

from __future__ import annotations

from copy import deepcopy
from datetime import datetime, timezone
from threading import RLock
from typing import Any


class ContextStore:
    """Maintain the latest robot context snapshot in a thread-safe way."""

    def __init__(self) -> None:
        self._lock = RLock()
        self._context: dict[str, Any] = {
            "robot_pose": {},
            "navigation_status": {},
            "current_goal": {},
            "current_task": "",
            "detected_objects": [],
            "map_progress": 0.0,
            "battery": 0.0,
            "scene_summary": "",
            "last_update": "",
        }

    def _touch(self) -> None:
        self._context["last_update"] = datetime.now(timezone.utc).isoformat()

    def get_context(self) -> dict[str, Any]:
        """Return a deep copy of the latest context snapshot."""

        with self._lock:
            return deepcopy(self._context)

    def update_pose(self, pose: dict[str, Any]) -> dict[str, Any]:
        """Update the stored robot pose and motion state."""

        with self._lock:
            self._context["robot_pose"] = deepcopy(pose)
            battery = pose.get("battery")
            if isinstance(battery, (int, float)) and battery >= 0.0:
                self._context["battery"] = float(battery)
            self._touch()
            return self.get_context()

    def update_nav_status(self, navigation_status: dict[str, Any]) -> dict[str, Any]:
        """Update the stored navigation status."""

        with self._lock:
            self._context["navigation_status"] = deepcopy(navigation_status)
            self._touch()
            return self.get_context()

    def update_goal(self, goal: dict[str, Any]) -> dict[str, Any]:
        """Update the currently selected goal or target."""

        with self._lock:
            self._context["current_goal"] = deepcopy(goal)
            self._touch()
            return self.get_context()

    def update_detections(self, detections: list[dict[str, Any]]) -> dict[str, Any]:
        """Replace the detection list with the latest perception snapshot."""

        with self._lock:
            self._context["detected_objects"] = [deepcopy(detection) for detection in detections]
            self._touch()
            return self.get_context()

    def update_scene_summary(self, scene_summary: str) -> dict[str, Any]:
        """Update the current scene summary string."""

        with self._lock:
            self._context["scene_summary"] = scene_summary
            self._touch()
            return self.get_context()

    def update_task(self, current_task: str) -> dict[str, Any]:
        """Update the current task label."""

        with self._lock:
            self._context["current_task"] = current_task
            self._touch()
            return self.get_context()

    def update_map_progress(self, map_progress: float) -> dict[str, Any]:
        """Update the current map completion estimate."""

        with self._lock:
            self._context["map_progress"] = max(0.0, min(1.0, map_progress))
            self._touch()
            return self.get_context()

    def update_battery(self, battery: float) -> dict[str, Any]:
        """Update the robot battery percentage."""

        with self._lock:
            self._context["battery"] = max(0.0, min(100.0, battery))
            self._touch()
            return self.get_context()

    def serialize(self) -> dict[str, Any]:
        """Return the context as a JSON-serializable dictionary."""

        with self._lock:
            return deepcopy(self._context)
