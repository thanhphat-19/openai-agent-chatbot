"""Integration tests for chat persistence.

Uses a real PostgreSQL test DB (chatbot_test).
Mocks AIServiceClient.chat_stream to avoid calling the real AI service.
"""

import json
import uuid
from unittest.mock import AsyncMock, patch

import pytest
from httpx import AsyncClient
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from src.models.chat_message import ChatMessage
from src.models.chat_session import ChatSession


async def _fake_chat_stream(messages, session_id=None):
    """Yields fake SSE lines simulating the AI service response."""
    deltas = ["Hello", " there", "!"]
    for text in deltas:
        yield f"event: agent.message.delta"
        yield f"data: {json.dumps({'text': text})}"
        yield ""
    yield f"event: agent.message.done"
    yield f"data: {json.dumps({'session_id': session_id})}"
    yield ""


@pytest.mark.asyncio
async def test_user_and_assistant_messages_persisted(
    client: AsyncClient, db_session: AsyncSession
):
    """After a chat turn, both user and assistant messages exist in the DB."""
    session_id = str(uuid.uuid4())
    user_id = "test-user-1"
    message = "Hello, assistant!"

    with patch(
        "src.api.routes.chat.ai_service_client.chat_stream",
        side_effect=_fake_chat_stream,
    ):
        async with client.stream(
            "POST",
            "/api/v1/chat/stream",
            json={"session_id": session_id, "user_id": user_id, "message": message},
        ) as response:
            assert response.status_code == 200
            async for _ in response.aiter_lines():
                pass

    result = await db_session.execute(
        select(ChatMessage)
        .join(ChatSession, ChatMessage.session_id == ChatSession.id)
        .where(ChatSession.id == uuid.UUID(session_id))
        .order_by(ChatMessage.created_at.asc())
    )
    messages = result.scalars().all()

    assert len(messages) == 2
    assert messages[0].role == "user"
    assert messages[0].content == message
    assert messages[1].role == "assistant"
    assert messages[1].content == "Hello there!"


@pytest.mark.asyncio
async def test_session_created_automatically(
    client: AsyncClient, db_session: AsyncSession
):
    """Session is auto-created if session_id does not exist yet."""
    session_id = str(uuid.uuid4())
    user_id = "test-user-2"

    with patch(
        "src.api.routes.chat.ai_service_client.chat_stream",
        side_effect=_fake_chat_stream,
    ):
        async with client.stream(
            "POST",
            "/api/v1/chat/stream",
            json={"session_id": session_id, "user_id": user_id, "message": "Hi"},
        ) as response:
            async for _ in response.aiter_lines():
                pass

    result = await db_session.execute(
        select(ChatSession).where(ChatSession.id == uuid.UUID(session_id))
    )
    session = result.scalar_one_or_none()
    assert session is not None
    assert session.user_id == user_id


@pytest.mark.asyncio
async def test_wrong_user_gets_403(client: AsyncClient, db_session: AsyncSession):
    """A different user_id on an existing session gets 403 Forbidden."""
    session_id = str(uuid.uuid4())

    with patch(
        "src.api.routes.chat.ai_service_client.chat_stream",
        side_effect=_fake_chat_stream,
    ):
        async with client.stream(
            "POST",
            "/api/v1/chat/stream",
            json={"session_id": session_id, "user_id": "owner", "message": "Hi"},
        ) as response:
            async for _ in response.aiter_lines():
                pass

        response2 = await client.post(
            "/api/v1/chat/stream",
            json={"session_id": session_id, "user_id": "intruder", "message": "Hi"},
        )
    assert response2.status_code == 403


@pytest.mark.asyncio
async def test_get_session_history(client: AsyncClient, db_session: AsyncSession):
    """GET /sessions/{session_id}/history returns messages in order."""
    session_id = str(uuid.uuid4())
    user_id = "test-user-3"

    with patch(
        "src.api.routes.chat.ai_service_client.chat_stream",
        side_effect=_fake_chat_stream,
    ):
        async with client.stream(
            "POST",
            "/api/v1/chat/stream",
            json={"session_id": session_id, "user_id": user_id, "message": "Test"},
        ) as response:
            async for _ in response.aiter_lines():
                pass

    response = await client.get(
        f"/api/v1/sessions/{session_id}/history",
        params={"user_id": user_id},
    )
    assert response.status_code == 200
    data = response.json()
    assert data["session_id"] == session_id
    assert len(data["messages"]) == 2
    assert data["messages"][0]["role"] == "user"
    assert data["messages"][1]["role"] == "assistant"


@pytest.mark.asyncio
async def test_delete_session(client: AsyncClient, db_session: AsyncSession):
    """DELETE /sessions/{session_id} removes session and messages."""
    session_id = str(uuid.uuid4())
    user_id = "test-user-4"

    with patch(
        "src.api.routes.chat.ai_service_client.chat_stream",
        side_effect=_fake_chat_stream,
    ):
        async with client.stream(
            "POST",
            "/api/v1/chat/stream",
            json={"session_id": session_id, "user_id": user_id, "message": "Delete me"},
        ) as response:
            async for _ in response.aiter_lines():
                pass

    response = await client.delete(
        f"/api/v1/sessions/{session_id}",
        params={"user_id": user_id},
    )
    assert response.status_code == 204

    result = await db_session.execute(
        select(ChatSession).where(ChatSession.id == uuid.UUID(session_id))
    )
    assert result.scalar_one_or_none() is None
