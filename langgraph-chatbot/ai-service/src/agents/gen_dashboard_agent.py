"""GenDashboardAgent — ReAct loop that produces ECharts-compatible JSON."""
from pathlib import Path
from typing import Annotated, TypedDict

from langchain_core.messages import AIMessage, BaseMessage, SystemMessage
from langchain_openai import ChatOpenAI
from langgraph.graph import END, StateGraph
from langgraph.graph.message import add_messages
from langgraph.prebuilt import ToolNode
from loguru import logger

from src.core.config import settings
from src.tools.sql_tools import list_tables, query_data

# ── State ──────────────────────────────────────────────────────────────────
class DashboardState(TypedDict):
    messages: Annotated[list[BaseMessage], add_messages]
    # Same message-as-state pattern as ReportState.
    # Final AIMessage content will be the ECharts JSON string.


# ── Constants ──────────────────────────────────────────────────────────────
_SYSTEM_PROMPT = (Path(__file__).parent.parent / "prompts" / "gen_dashboard.md").read_text()
_TOOLS = [query_data, list_tables]
_LLM = ChatOpenAI(
    model=settings.VANNA_MODEL,   
    api_key=settings.OPENAI_API_KEY,
    streaming=True,
).bind_tools(_TOOLS)


# ── Nodes ──────────────────────────────────────────────────────────────────
async def agent_node(state: DashboardState) -> dict:
    """Core ReAct node: LLM queries data iteratively then emits ECharts JSON."""
    messages = state["messages"]
    if not isinstance(messages[0], SystemMessage):
        messages = [SystemMessage(content=_SYSTEM_PROMPT)] + messages
    iteration = sum(1 for m in messages if isinstance(m, AIMessage)) + 1

    # ── Input logging ──────────────────────────────────────────────────────
    logger.info(f"[gen_dashboard] ===== turn {iteration} | {len(messages)} messages in context =====")
    if iteration == 1:
        logger.info(f"[gen_dashboard] SYSTEM PROMPT:\n{_SYSTEM_PROMPT}")
    for i, m in enumerate(messages):
        role = type(m).__name__.replace("Message", "").replace("HumanM", "Human").lower()
        if isinstance(m, SystemMessage):
            continue  # already logged above
        preview = (m.content[:200] + "...") if len(str(m.content)) > 200 else str(m.content)
        logger.info(f"  [{i}] {role}: {preview}")
    # ──────────────────────────────────────────────────────────────────────

    response: AIMessage = await _LLM.ainvoke(messages)
    if response.tool_calls:
        tools = [tc["name"] for tc in response.tool_calls]
        logger.info(f"[gen_dashboard] turn {iteration} → tool_calls: {tools}")
    else:
        logger.info(f"[gen_dashboard] turn {iteration} → final response ({len(response.content)} chars)")
    return {"messages": [response]}


def _should_continue(state: DashboardState) -> str:
    """Same ReAct routing: tool_calls → loop, no tool_calls → done."""
    last: AIMessage = state["messages"][-1]
    if hasattr(last, "tool_calls") and last.tool_calls:
        return "tools"
    return END


# ── Graph (compiled ONCE at module load) ──────────────────────────────────
def _build_graph() -> StateGraph:
    g = StateGraph(DashboardState)

    g.add_node("agent", agent_node)
    g.add_node("tools", ToolNode(_TOOLS))

    g.set_entry_point("agent")

    g.add_conditional_edges(
        "agent",
        _should_continue,
        {"tools": "tools", END: END},
    )
    g.add_edge("tools", "agent")   # ← back-edge = cycle

    return g


gen_dashboard_graph = _build_graph().compile()
