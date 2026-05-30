from services.ai_core.graph import AgentState


def safety(state: AgentState) -> AgentState:
    """Safety agent: check `sensors.scan` for near obstacles and possibly veto navigation.

    Sets `memory['safe_to_navigate']` boolean.
    """
    state.setdefault("sensors", {})
    state.setdefault("memory", {})
    memory = state["memory"]

    scan = state["sensors"].get("scan")
    safe = True
    if scan:
        # expect scan to be a dict with 'ranges' or a sequence
        ranges = None
        if isinstance(scan, dict):
            ranges = scan.get("ranges")
        else:
            try:
                ranges = list(scan)
            except Exception:
                ranges = None

        if ranges:
            min_r = min((r for r in ranges if r is not None), default=9999)
            if min_r < 0.5:
                safe = False

    memory["safe_to_navigate"] = safe
    if not safe:
        memory["navigation_blocked"] = "obstacle_detected"
    else:
        memory.pop("navigation_blocked", None)
    return state
