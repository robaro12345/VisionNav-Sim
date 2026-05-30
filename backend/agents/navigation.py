from services.ai_core.graph import AgentState


def navigation(state: AgentState) -> AgentState:
    """Navigation agent: if decision is 'proceed' and safe, ensure a `memory['goal']` exists.

    It leaves the goal for the RosBridge to publish.
    """
    state.setdefault("memory", {})
    memory = state["memory"]

    decision = memory.get("decision")
    safe = memory.get("safe_to_navigate", True)

    if memory.get("drive_request"):
        memory.pop("goal", None)
        memory.pop("blocked_goal", None)
        memory["navigation_ready"] = False
        memory.pop("blocked_goal", None)
        memory.pop("navigation_blocked", None)
        return state

    if decision == "proceed" and safe:
        # ensure there's a goal (maybe created by vision or planner)
        goal = memory.get("goal")
        if not goal:
            # fallback: create a short forward goal
            memory["goal"] = {
                "frame_id": "map",
                "position": {"x": 0.5, "y": 0.0, "z": 0.0},
                "orientation": {"x": 0.0, "y": 0.0, "z": 0.0, "w": 1.0},
            }
        memory["navigation_ready"] = True
    else:
        if memory.get("goal"):
            memory["blocked_goal"] = memory["goal"]
        memory.pop("goal", None)
        memory["navigation_ready"] = False
        if not safe:
            memory["navigation_blocked"] = "unsafe"
        elif decision != "proceed":
            memory["navigation_blocked"] = "decision"

    return state
