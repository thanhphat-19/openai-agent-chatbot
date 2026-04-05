"""SupervisorGraph — cyclic LangGraph StateGraph.

Flow:
  user → supervisor → agent(s) → supervisor → ... → supervisor(FINISH) → END

The supervisor is an LLM that reads the full message history after each agent
run and decides the next action: call another agent, or FINISH.
"""
import asyncio
from pathlib import Path
from typing import Annotated, Literal, TypedDict

from langchain_core.messages import BaseMessage, SystemMessage
from langchain_openai import ChatOpenAI
from langgraph.graph import END, StateGraph
from langgraph.graph.message import add_messages
from langgraph.types import Command
from loguru import logger
from pydantic import BaseModel

from src.agents.gen_dashboard_agent import gen_dashboard_graph
from src.agents.gen_report_agent import gen_report_graph
from src.core.config import settings

# ── Shared state ────────────────────────────────────────────────────────────
class SupervisorState(TypedDict):
    messages: Annotated[list[BaseMessage], add_messages]
    next_agent: str                # last routing decision
    completed_agents: list[str]    # agents already run this turn


# ── Supervisor structured output ─────────────────────────────────────────────
class SupervisorDecision(BaseModel):
    next: Literal["gen_report", "gen_dashboard", "general", "FINISH"]


_SUPERVISOR_PROMPT = (Path(__file__).parent.parent / "prompts" / "router.md").read_text()
_SUPERVISOR_LLM = ChatOpenAI(
    model=settings.VANNA_MODEL,
    api_key=settings.OPENAI_API_KEY,
    streaming=False,
).with_structured_output(SupervisorDecision)


# ── Nodes ────────────────────────────────────────────────────────────────────
async def supervisor_node(state: SupervisorState) -> dict:
    """Cyclic supervisor: reads full history + tracks completed agents, decides next step.

    Returns a plain dict — routing to next node is handled by _route_supervisor
    conditional edge (avoids Command(goto=END) channel bugs in LangGraph v0.5).
    """
    # Build completed list from previous turn
    prev_agent = state.get("next_agent", "")
    completed = list(state.get("completed_agents") or [])
    if prev_agent and prev_agent not in completed and prev_agent not in ("", "FINISH"):
        completed = completed + [prev_agent]

    completed_str = ", ".join(completed) if completed else "none"
    prompt = _SUPERVISOR_PROMPT + f"\n\nAlready completed agents this turn: {completed_str}"
    messages = [SystemMessage(content=prompt)] + list(state["messages"])

    decision: SupervisorDecision = await asyncio.to_thread(
        _SUPERVISOR_LLM.invoke, messages
    )
    logger.info(f"[supervisor] → {decision.next} (completed: {completed})")
    return {
        "next_agent": decision.next,
        "completed_agents": completed,
    }


async def general_node(state: SupervisorState) -> dict:
    """Fallback: answer general questions directly without specialist agents."""
    logger.info("[general] answering directly")
    llm = ChatOpenAI(
        model=settings.VANNA_MODEL,
        api_key=settings.OPENAI_API_KEY,
        streaming=True,
    )
    response = await llm.ainvoke(list(state["messages"]))
    logger.info("[general] done")
    return {"messages": [response]}


# ── Graph (compiled ONCE at module load) ────────────────────────────────────
def _route_supervisor(state: SupervisorState) -> str:
    """Conditional edge: read next_agent from state and route accordingly.

    Returns END (the string constant) when decision is FINISH.
    This avoids Command(goto=END) which triggers unknown-channel errors in v0.5.
    """
    decision = state.get("next_agent", "FINISH")
    if decision == "FINISH" or not decision:
        return END
    return decision


def _build_supervisor() -> StateGraph:
    g = StateGraph(SupervisorState)

    # Nodes
    g.add_node("supervisor", supervisor_node)
    g.add_node("gen_report", gen_report_graph)
    g.add_node("gen_dashboard", gen_dashboard_graph)
    g.add_node("general", general_node)

    # Entry: always start at supervisor
    g.set_entry_point("supervisor")

    # Conditional routing from supervisor: goes to agent or END
    g.add_conditional_edges(
        "supervisor",
        _route_supervisor,
        {"gen_report": "gen_report", "gen_dashboard": "gen_dashboard",
         "general": "general", END: END},
    )

    # Cyclic: every agent loops back to supervisor after completing
    g.add_edge("gen_report", "supervisor")
    g.add_edge("gen_dashboard", "supervisor")
    g.add_edge("general", "supervisor")

    return g


supervisor_graph = _build_supervisor().compile()
