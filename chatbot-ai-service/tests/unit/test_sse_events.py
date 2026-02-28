"""Unit tests for SSE event order.

Mock Runner.run_streamed() so no real OpenAI API call is made.
Verify that events are emitted in the correct order:
  delta* → done
  or delta* → failed (on error)
"""

import json
from collections.abc import AsyncGenerator
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from httpx import ASGITransport, AsyncClient
from fastapi import FastAPI

from src.main import app


def _make_mock_stream(texts: list[str]):
    """Return a mock RunResult whose stream_events() yields fake delta events."""

    class FakeEvent:
        def __init__(self, text: str):
            self.type = "raw_response_event"
            self.data = MagicMock()
            self.data.delta = text
            from openai.types.responses import ResponseTextDeltaEvent  # noqa: F401
            self.data.__class__ = ResponseTextDeltaEvent

    async def _stream_events():
        for text in texts:
            yield FakeEvent(text)

    mock_result = MagicMock()
    mock_result.stream_events = _stream_events
    return mock_result


async def _collect_sse(response_stream) -> list[dict]:
    """Parse raw SSE text into list of {event, data} dicts."""
    events = []
    current: dict = {}
    async for line in response_stream.aiter_lines():
        line = line.strip()
        if line.startswith("event:"):
            current["event"] = line.split(":", 1)[1].strip()
        elif line.startswith("data:"):
            current["data"] = json.loads(line.split(":", 1)[1].strip())
        elif line == "" and current:
            events.append(current)
            current = {}
    if current:
        events.append(current)
    return events


@pytest.mark.asyncio
async def test_sse_delta_events_followed_by_done():
    """Delta events appear before done, no failed event."""
    mock_texts = ["Hello", ", ", "world", "!"]

    with patch(
        "src.streaming.runner.Runner.run_streamed",
        return_value=_make_mock_stream(mock_texts),
    ):
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
            async with ac.stream(
                "POST",
                "/v1/chat/stream",
                json={"messages": [{"role": "user", "content": "Hi"}], "session_id": "test-session"},
            ) as response:
                assert response.status_code == 200
                assert "text/event-stream" in response.headers["content-type"]
                events = await _collect_sse(response)

    event_types = [e["event"] for e in events if e.get("event") not in ("heartbeat",)]

    delta_events = [e for e in events if e.get("event") == "agent.message.delta"]
    done_events = [e for e in events if e.get("event") == "agent.message.done"]

    assert len(delta_events) == len(mock_texts)
    assert len(done_events) == 1
    assert event_types.index("agent.message.done") == len(delta_events)

    assembled = "".join(e["data"]["text"] for e in delta_events)
    assert assembled == "Hello, world!"

    assert done_events[0]["data"]["session_id"] == "test-session"


@pytest.mark.asyncio
async def test_sse_failed_event_on_exception():
    """On runner error, agent.workflow.failed is emitted instead of done."""

    async def _raising_stream(history):
        raise RuntimeError("LLM error")
        yield  # make it an async generator

    with patch("src.streaming.runner.iter_text_deltas", side_effect=_raising_stream):
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
            async with ac.stream(
                "POST",
                "/v1/chat/stream",
                json={"messages": [{"role": "user", "content": "Hi"}]},
            ) as response:
                events = await _collect_sse(response)

    event_types = [e.get("event") for e in events]
    assert "agent.workflow.failed" in event_types
    assert "agent.message.done" not in event_types


@pytest.mark.asyncio
async def test_health_endpoint():
    """Health check returns 200 with status ok."""
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
        response = await ac.get("/health")
    assert response.status_code == 200
    assert response.json() == {"status": "ok"}
