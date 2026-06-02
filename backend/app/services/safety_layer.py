"""Safety verification layer for VisionNav-Sim.

Validates AI-generated action plans and manual control commands against whitelists,
ensuring parameter limits are respected and operations are safe to execute.
"""

from __future__ import annotations

from typing import Tuple

from backend.app.constants.actions import ALLOWED_ACTIONS
from backend.app.models.types import PlannerResponse


class SafetyLayer:
    """Validate action plans and teleop controls for safe operation."""

    def __init__(self, x_min: float = -20.0, x_max: float = 20.0, y_min: float = -20.0, y_max: float = 20.0) -> None:
        # TODO: Derive bounds dynamically from map occupancy grid size and origin
        self.x_min = x_min
        self.x_max = x_max
        self.y_min = y_min
        self.y_max = y_max

        # Allowed manual control directions
        self.allowed_manual_directions = {
            "forward",
            "backward",
            "left",
            "right",
            "rotate_left",
            "rotate_right",
            "stop"
        }

    def validate_plan(self, response: PlannerResponse) -> Tuple[bool, str]:
        """Validate all steps in an AI-generated action plan.
        
        Returns:
            (is_safe, error_message)
        """
        # If clarification is required, no plan validation is needed
        if response.clarification_required:
            return True, ""

        # Validate confidence score is within the [0.0, 1.0] range
        confidence = response.reasoning.confidence
        if not isinstance(confidence, (int, float)) or not (0.0 <= confidence <= 1.0):
            return False, f"Planner confidence score {confidence} is outside the allowed range [0.0, 1.0]."

        if not response.plan:
            # Empty plans are allowed as failure indicators but contain nothing to execute
            return True, ""

        for step in response.plan:
            action = step.action
            params = step.parameters

            # 1. Action Whitelisting
            if action not in ALLOWED_ACTIONS:
                return False, f"Action '{action}' in step {step.step} is not in the whitelist of allowed actions."

            # 2. Parameter Integrity Checks
            if action == "navigate_to_pose":
                # Must specify x, y, yaw coordinates
                for coord in ("x", "y", "yaw"):
                    if coord not in params:
                        return False, f"Action 'navigate_to_pose' in step {step.step} is missing parameter '{coord}'."
                    try:
                        float(params[coord])
                    except (ValueError, TypeError):
                        return False, f"Parameter '{coord}' in step {step.step} must be a valid number."
                
                # Check boundary safety
                x, y = float(params["x"]), float(params["y"])
                if not (self.x_min <= x <= self.x_max) or not (self.y_min <= y <= self.y_max):
                    return False, (
                        f"Target pose ({x}, {y}) in step {step.step} is outside the allowed "
                        f"simulation boundaries (X: [{self.x_min}, {self.x_max}], Y: [{self.y_min}, {self.y_max}])."
                    )

            elif action in ("navigate_to_object", "search_for_object", "inspect_object", "count_objects"):
                # Must specify a label to target
                if "label" not in params:
                    return False, f"Action '{action}' in step {step.step} is missing parameter 'label'."
                label = params["label"]
                if not isinstance(label, str) or not label.strip():
                    return False, f"Parameter 'label' in step {step.step} must be a non-empty string."

        return True, ""

    def validate_manual_command(self, direction: str, intensity: float) -> Tuple[bool, str]:
        """Validate a manual teleop drive request.
        
        Returns:
            (is_safe, error_message)
        """
        # 1. Direction check
        if direction not in self.allowed_manual_directions:
            return False, f"Manual command direction '{direction}' is not whitelisted."

        # 2. Intensity value check (should be between 0.0 and 1.0)
        if not isinstance(intensity, (int, float)) or not (0.0 <= intensity <= 1.0):
            return False, f"Manual control intensity must be a number between 0.0 and 1.0. Received: {intensity}."

        return True, ""
