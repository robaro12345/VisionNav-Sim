from services.ai_core.graph import AgentState


def reasoning(state: AgentState) -> AgentState:
    """Reasoning agent: inspects detections and decides whether to pursue.

    Adds `memory['decision']` with 'proceed'|'ignore'.
    """
    state.setdefault("memory", {})
    memory = state["memory"]
    dets = memory.get("detections", [])
    command = str(memory.get("command") or state.get("command") or "").lower()

    if any(token in command for token in ("stop", "cancel", "halt", "wait")):
        memory["decision"] = "ignore"
    elif dets or memory.get("goal"):
        memory["decision"] = "proceed"
    else:
        memory["decision"] = "inspect"
    return state
