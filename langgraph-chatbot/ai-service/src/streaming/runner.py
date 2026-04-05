"""SSE streaming helper wrapping the LangGraph supervisor graph.

Yields typed (event_type, payload) tuples:
  ("text",  str)   — one token delta from an LLM
  ("step",  dict)  — agent lifecycle event (routing, tool call, finish)
"""
from collections.abc import AsyncGenerator

from langchain_core.messages import AIMessageChunk, HumanMessage, ToolMessage

from src.agents.supervisor import SupervisorState, supervisor_graph


async def iter_events(history: list[dict]) -> AsyncGenerator[tuple[str, object], None]:
    """Yield typed (event_type, payload) tuples from the supervisor graph.

    Args:
        history: List of {role, content} dicts (full conversation history).

    Yields:
        ("text", str)  — LLM token delta
        ("step", dict) — step metadata (routing decision, tool call, finish)
    """
    from langchain_core.messages import AIMessage
    messages = []
    for msg in history:
        if msg["role"] == "user":
            messages.append(HumanMessage(content=msg["content"]))
        elif msg["role"] == "assistant":
            messages.append(AIMessage(content=msg["content"]))

    input_state: SupervisorState = {"messages": messages, "next_agent": "", "completed_agents": []}

    async for event in supervisor_graph.astream(
        input_state, stream_mode=["messages", "updates"], subgraphs=True
    ):
        namespace, stream_type, data = event

        # ── State updates — capture supervisor routing decision ──────────────
        if stream_type == "updates":
            if not namespace and "supervisor" in data:
                next_agent = (data["supervisor"] or {}).get("next_agent")
                if next_agent:
                    yield ("step", {"node": "supervisor", "action": "route", "to": next_agent})
            continue

        # ── Message chunks ───────────────────────────────────────────────────
        chunk, metadata = data
        node = metadata.get("langgraph_node", "")

        # Skip supervisor's raw LLM output (routing is already emitted via updates)
        if not namespace and node == "supervisor":
            continue

        # ── Tool call started ────────────────────────────────────────────────
        if isinstance(chunk, AIMessageChunk) and chunk.tool_call_chunks:
            for tc in chunk.tool_call_chunks:
                if tc.get("name"):          # first chunk of a tool call has the name
                    yield ("step", {
                        "node": node,
                        "action": "tool_call",
                        "tool": tc["name"],
                    })
            continue

        # ── Tool result ──────────────────────────────────────────────────────
        if isinstance(chunk, ToolMessage):
            yield ("step", {
                "node": node,
                "action": "tool_result",
                "tool": chunk.name,
            })
            continue

        # ── LLM text delta ───────────────────────────────────────────────────
        if isinstance(chunk, AIMessageChunk) and chunk.content:
            yield ("text", chunk.content)
