from __future__ import annotations

from typing import Any, Awaitable, Callable, Dict, List, Optional, TypedDict, Union
import asyncio
import importlib
import inspect
import logging
import time

try:
    from langgraph.graph import END, StateGraph
except Exception:  # pragma: no cover - optional dependency
    END = "__end__"
    StateGraph = None

logger = logging.getLogger(__name__)


class AgentState(TypedDict, total=False):
    id: str
    command: str
    timestamp: float
    pose: Any
    sensors: dict
    memory: dict


AgentResult = Union[AgentState, Awaitable[AgentState]]
AgentCallable = Callable[[AgentState], AgentResult]


class GraphRunner:
    DEFAULT_SEQUENCE = [
        "planner",
        "exploration",
        "vision",
        "reasoning",
        "safety",
        "navigation",
        "explainer",
    ]

    def __init__(self, sequence: Optional[List[str]] = None, bridge: Any = None) -> None:
        self.sequence = sequence or list(self.DEFAULT_SEQUENCE)
        self.bridge = bridge
        self._agents: Dict[str, AgentCallable] = {}
        self._compiled = None

    def set_bridge(self, bridge: Any) -> None:
        self.bridge = bridge

    def register_agent(self, name: str, func: AgentCallable) -> None:
        self._agents[name] = func
        self._compiled = None
        logger.debug("Registered agent '%s'", name)

    def load_agent(self, name: str) -> bool:
        try:
            mod = importlib.import_module(f"agents.{name}")
        except Exception as exc:
            logger.debug("Failed importing agents.%s: %s", name, exc)
            return False

        candidate = None
        for attr in (name, "agent", "run"):
            candidate = getattr(mod, attr, None)
            if callable(candidate):
                break

        if not callable(candidate):
            for value in vars(mod).values():
                if callable(value) and inspect.isfunction(value):
                    candidate = value
                    break

        if not callable(candidate):
            logger.debug("No callable agent found in agents.%s", name)
            return False

        self.register_agent(name, candidate)
        return True

    def load_default_agents(self) -> None:
        for name in self.sequence:
            self.load_agent(name)

    def _resolve_agent(self, name: str) -> Optional[AgentCallable]:
        func = self._agents.get(name)
        if func is not None:
            return func
        if self.load_agent(name):
            return self._agents.get(name)
        return None

    def _merge_bridge_sensors(self, state: AgentState, bridge: Any = None) -> AgentState:
        bridge = bridge or self.bridge
        if bridge is None:
            return state

        sensors = state.setdefault("sensors", {})
        try:
            snapshot = bridge.snapshot_sensors()
        except Exception:
            logger.exception("Failed to read sensor snapshot from ROS bridge")
            return state

        for key, value in snapshot.items():
            if value is not None and key not in sensors:
                sensors[key] = value

        memory = state.setdefault("memory", {})
        memory.setdefault("bridge_running", bool(getattr(bridge, "is_running", False)))
        return state

    def _route_after_safety(self, state: AgentState) -> str:
        memory = state.get("memory", {})
        if memory.get("decision") == "proceed" and memory.get("safe_to_navigate", True):
            return "navigation"
        return "explainer"

    def _record_trace(self, state: AgentState, agent_name: str) -> AgentState:
        memory = state.setdefault("memory", {})
        trace = memory.setdefault("agent_trace", [])
        detections = memory.get("detections")
        trace.append(
            {
                "agent": agent_name,
                "decision": memory.get("decision"),
                "safe_to_navigate": memory.get("safe_to_navigate"),
                "detections": len(detections) if isinstance(detections, list) else 0,
                "goal": bool(memory.get("goal")),
                "explore_mode": bool(memory.get("explore_mode")),
                "frontier_count": memory.get("frontier_count"),
                "explanation": memory.get("explanation"),
            }
        )
        return state

    def _wrap_agent(self, name: str) -> Callable[[AgentState], AgentState]:
        def _node(state: AgentState) -> AgentState:
            func = self._resolve_agent(name)
            if func is None:
                logger.info("No agent for '%s', skipping", name)
                return state

            logger.info("Running agent '%s'", name)
            result = func(state)
            if inspect.isawaitable(result):
                raise RuntimeError(
                    f"Async agent '{name}' was returned from a compiled graph node. "
                    "Use GraphRunner.invoke() fallback or convert the agent to sync."
                )

            return self._record_trace(result, name)

        return _node

    def _compile(self):
        if StateGraph is None:
            return None

        graph = StateGraph(AgentState)
        for name in self.sequence:
            graph.add_node(name, self._wrap_agent(name))

        if self.sequence:
            graph.set_entry_point(self.sequence[0])

        for current, nxt in zip(self.sequence, self.sequence[1:]):
            if current == "safety":
                graph.add_conditional_edges(
                    "safety",
                    self._route_after_safety,
                    {"navigation": "navigation", "explainer": "explainer"},
                )
                continue
            if current == "explainer":
                graph.add_edge("explainer", END)
                continue
            if current != "safety":
                graph.add_edge(current, nxt)

        if "navigation" in self.sequence and "explainer" in self.sequence:
            graph.add_edge("navigation", "explainer")
        if "explainer" in self.sequence:
            graph.add_edge("explainer", END)

        return graph.compile()

    async def _call_agent(
        self,
        func: AgentCallable,
        state: AgentState,
        timeout: Optional[float] = None,
    ) -> AgentState:
        try:
            if inspect.iscoroutinefunction(func):
                coro = func(state)
                result = await asyncio.wait_for(coro, timeout=timeout) if timeout else await coro
            else:
                result = func(state)
                if inspect.isawaitable(result):
                    result = await asyncio.wait_for(result, timeout=timeout) if timeout else await result

            return result if inspect.isawaitable(result) else self._record_trace(result, getattr(func, "__name__", "agent"))
        except Exception:
            logger.exception("Agent execution failed")
            raise

    async def _invoke_fallback(
        self,
        state: AgentState,
        *,
        stop_on_error: bool = True,
        timeout_per_agent: Optional[float] = None,
    ) -> AgentState:
        current = self._merge_bridge_sensors(state)
        route = None

        for name in self.sequence:
            if name == "navigation" and route != "navigation":
                logger.info("Skipping navigation because safety routed to explainer")
                continue

            func = self._resolve_agent(name)
            if func is None:
                continue

            try:
                current = await self._call_agent(func, current, timeout=timeout_per_agent)
            except Exception:
                if stop_on_error:
                    raise
                logger.exception("Agent '%s' failed but continuing", name)

            if name == "safety":
                route = self._route_after_safety(current)

        return current

    def invoke(
        self,
        state: Optional[AgentState] = None,
        *,
        stop_on_error: bool = True,
        timeout_per_agent: Optional[float] = None,
        use_bridge: bool = True,
    ) -> AgentState:
        current: AgentState = state or {}
        current.setdefault("timestamp", time.time())
        current.setdefault("sensors", {})
        current.setdefault("memory", {})

        if "command" in current and "command" not in current["memory"]:
            current["memory"]["command"] = current["command"]

        if use_bridge:
            current = self._merge_bridge_sensors(current)

        compiled = self._compiled
        if compiled is None and StateGraph is not None:
            compiled = self._compiled = self._compile()

        async def _runner() -> AgentState:
            if compiled is not None:
                logger.info("Running compiled graph")
                result = compiled.invoke(current)
                if isinstance(result, dict):
                    return result
                return current
            return await self._invoke_fallback(
                current,
                stop_on_error=stop_on_error,
                timeout_per_agent=timeout_per_agent,
            )

        try:
            return asyncio.run(_runner())
        except RuntimeError:
            loop = asyncio.new_event_loop()
            try:
                asyncio.set_event_loop(loop)
                return loop.run_until_complete(_runner())
            finally:
                asyncio.set_event_loop(None)
                loop.close()

    def run(
        self,
        state: Optional[AgentState] = None,
        *,
        stop_on_error: bool = True,
        timeout_per_agent: Optional[float] = None,
    ) -> AgentState:
        return self.invoke(
            state,
            stop_on_error=stop_on_error,
            timeout_per_agent=timeout_per_agent,
        )


def build_graph(bridge: Any = None) -> GraphRunner:
    runner = GraphRunner(bridge=bridge)
    runner.load_default_agents()
    if StateGraph is not None:
        runner._compiled = runner._compile()
    return runner


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    runner = build_graph()
    state: AgentState = {"id": "demo", "memory": {}, "command": "move forward"}
    try:
        out = runner.run(state)
        print("Run complete. State:", out)
    except Exception as exc:
        print("Graph run failed:", exc)
