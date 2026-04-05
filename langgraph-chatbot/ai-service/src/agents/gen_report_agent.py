"""GenReportAgent — ReAct loop: LLM decides when to call Vanna SQL tools."""
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
class ReportState(TypedDict):
    messages: Annotated[list[BaseMessage], add_messages]
    # messages IS the full state: HumanMsg → AIMsg(tool_calls) → ToolMsg → AIMsg → ...
    # No boolean flags. The LLM reads the full message history and decides next action.


# ── Constants ──────────────────────────────────────────────────────────────
_SYSTEM_PROMPT = (Path(__file__).parent.parent / "prompts" / "gen_report.md").read_text()
_TOOLS = [query_data, list_tables]
_LLM = ChatOpenAI(
    model=settings.VANNA_MODEL,
    api_key=settings.OPENAI_API_KEY,
    streaming=True,
).bind_tools(_TOOLS)


# ── Nodes ──────────────────────────────────────────────────────────────────
async def agent_node(state: ReportState) -> dict:
    """Core ReAct node: LLM receives all messages and either calls a tool or stops."""
    messages = state["messages"]
    if not isinstance(messages[0], SystemMessage):
        messages = [SystemMessage(content=_SYSTEM_PROMPT)] + messages
    iteration = sum(1 for m in messages if isinstance(m, AIMessage)) + 1

    # ── Input logging ──────────────────────────────────────────────────────
    logger.info(f"[gen_report] ===== turn {iteration} | {len(messages)} messages in context =====")
    if iteration == 1:
        logger.info(f"[gen_report] SYSTEM PROMPT:\n{_SYSTEM_PROMPT}")
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
        logger.info(f"[gen_report] turn {iteration} → tool_calls: {tools}")
    else:
        logger.info(f"[gen_report] turn {iteration} → final response ({len(response.content)} chars)")
    return {"messages": [response]}


def _should_continue(state: ReportState) -> str:
    """Routing function for the ReAct cycle.

    - If the LLM emitted tool_calls → execute tools, loop back
    - Otherwise → LLM is done, exit to END
    """
    last: AIMessage = state["messages"][-1]
    if hasattr(last, "tool_calls") and last.tool_calls:
        return "tools"
    return END


# ── Graph (compiled ONCE at module load — never inside run()) ───────────────
def _build_graph() -> StateGraph:
    g = StateGraph(ReportState)

    g.add_node("agent", agent_node)
    g.add_node("tools", ToolNode(_TOOLS))

    g.set_entry_point("agent")

    # THE CYCLE: agent → (has tool_calls?) → tools → agent
    g.add_conditional_edges(
        "agent",
        _should_continue,
        {"tools": "tools", END: END},
    )
    g.add_edge("tools", "agent")   # ← back-edge that makes this a true graph, not a DAG

    return g


gen_report_graph = _build_graph().compile()
