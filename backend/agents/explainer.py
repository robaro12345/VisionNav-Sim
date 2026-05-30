from services.ai_core.graph import AgentState
from langchain_ollama import ChatOllama
from langchain_core.messages import HumanMessage, SystemMessage
import json


def explainer(state: AgentState) -> AgentState:
    """Explainer agent: produce a human-readable summary under `memory['explanation']`.
    """
    state.setdefault("memory", {})
    memory = state["memory"]

    command = str(memory.get("command", ""))
    detections = memory.get("detections", [])
    decision = str(memory.get("decision", "none"))
    scene = str(memory.get("scene_description", "none"))

    try:
        llm = ChatOllama(model="gemma4:e4b", temperature=0.7)
        system_prompt = (
            "You are a friendly robotic assistant communicating with the user. "
            "You have just processed a command, looked at the camera feed, and made a decision. "
            "Explain to the user what you see in the scene and what action you are taking. "
            "Keep your response concise, natural, and conversational (1-3 sentences). "
            "Do not include any JSON formatting, markdown wrappers, or robot inner monologue."
        )
        
        user_prompt = f"User Command: {command}\nScene context: {scene}\nDetections: {json.dumps(detections)}\nMy Decision/Action: {decision}"
        
        response = llm.invoke([SystemMessage(content=system_prompt), HumanMessage(content=user_prompt)])
        memory["explanation"] = response.content.strip()
    except Exception as e:
        # Fallback if LLM fails
        parts = []
        if command:
            parts.append(f"Command: {command}")
        if detections:
            parts.append(f"Detections: {len(detections)}")
        if decision:
            parts.append(f"Decision: {decision}")
        if memory.get("safe_to_navigate") is not None:
            parts.append(f"Safe: {memory['safe_to_navigate']}")
        if memory.get("goal"):
            parts.append("Goal set")
        elif memory.get("navigation_blocked"):
            parts.append(f"Blocked: {memory['navigation_blocked']}")

        memory["explanation"] = "; ".join(parts) if parts else "No notable state"

    return state
