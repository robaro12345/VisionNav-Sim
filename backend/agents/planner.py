from services.ai_core.graph import AgentState


def _goal_from_command(command: str):
    command = command.lower()
    goal = {
        "frame_id": "map",
        "position": {"x": 0.0, "y": 0.0, "z": 0.0},
        "orientation": {"x": 0.0, "y": 0.0, "z": 0.0, "w": 1.0},
    }

    if any(token in command for token in ("left", "port")):
        goal["position"]["y"] = 0.5
    elif any(token in command for token in ("right", "starboard")):
        goal["position"]["y"] = -0.5
    elif any(token in command for token in ("back", "reverse", "backward")):
        goal["position"]["x"] = -0.5
    else:
        goal["position"]["x"] = 1.0

    return goal


def _drive_from_command(command: str):
    command = command.lower()

    if not any(token in command for token in ("move", "go", "drive", "turn", "rotate", "forward", "back", "left", "right")):
        return None

    duration_ms = 900
    if any(token in command for token in ("until", "detect", "see", "obstacle", "something in front", "something ahead")):
        duration_ms = 2000

    if any(token in command for token in ("left", "port", "turn left", "rotate left")):
        return {"linear_x": 0.0, "angular_z": 0.8, "pulse_duration_ms": duration_ms}
    if any(token in command for token in ("right", "starboard", "turn right", "rotate right")):
        return {"linear_x": 0.0, "angular_z": -0.8, "pulse_duration_ms": duration_ms}
    if any(token in command for token in ("back", "reverse", "backward")):
        return {"linear_x": -0.14, "angular_z": 0.0, "pulse_duration_ms": duration_ms}

    return {"linear_x": 0.18, "angular_z": 0.0, "pulse_duration_ms": duration_ms}


def planner(state: AgentState) -> AgentState:
    """Planner agent: if a `memory.goal` exists, produce a simple plan.

    The plan is stored under `state['memory']['plan']` as a list of waypoints.
    """
    state.setdefault("memory", {})
    memory = state["memory"]

    goal = memory.get("goal")
    command = str(memory.get("command") or state.get("command") or "").strip()

    drive_request = _drive_from_command(command) if command else None
    if drive_request is not None:
        memory["drive_request"] = drive_request
        memory.pop("goal", None)
        memory["goal_source"] = "planner_drive"
        memory.pop("plan", None)
        return state

    if not goal and command and not any(token in command.lower() for token in ("stop", "cancel", "halt", "wait")):
        goal = _goal_from_command(command)
        memory["goal"] = goal
        memory["goal_source"] = "planner"

    if not goal:
        memory.pop("plan", None)
        return state

    # Simple plan: single waypoint at the goal
    plan = [{
        "frame_id": goal.get("frame_id", "map"),
        "position": goal.get("position", {}),
        "orientation": goal.get("orientation", {}),
    }]

    memory["plan"] = plan
    return state
