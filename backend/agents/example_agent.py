from services.ai_core.graph import AgentState

def example_agent(state: AgentState) -> AgentState:
    """A minimal example agent: echoes state with a note."""
    state.setdefault("memory", {})
    state["memory"]["example"] = "ran"
    return state
