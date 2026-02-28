"""SSE streaming helper wrapping the OpenAI Agents SDK.

Responsibility: yield raw text delta strings from the agent.
SSE formatting, heartbeat, done/failed events are handled by the router layer.
"""

from collections.abc import AsyncGenerator

from agents import Runner
from openai.types.responses import ResponseTextDeltaEvent

from src.agents.chat_agent import chat_agent


async def iter_text_deltas(history: list[dict]) -> AsyncGenerator[str, None]:
    """Yield plain text delta strings from the agent for the given message history.

    Args:
        history: List of {role: str, content: str} dicts (full conversation).

    Yields:
        Plain text strings — one per token chunk from the LLM.

    Raises:
        Any exception from the OpenAI Agents SDK (propagated directly to caller).
    """
    result = Runner.run_streamed(chat_agent, input=history)
    async for event in result.stream_events():
        if event.type == "raw_response_event" and isinstance(
            event.data, ResponseTextDeltaEvent
        ):
            text = event.data.delta
            if text:
                yield text
