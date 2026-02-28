import json
import uuid
from collections.abc import AsyncGenerator

from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import StreamingResponse
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from src.clients.ai_service import ai_service_client
from src.database import get_db
from src.models.chat_message import ChatMessage
from src.models.chat_session import ChatSession
from src.schemas.chat import ChatStreamRequest

chat_router = APIRouter()


async def _upsert_session(
    session_id: uuid.UUID, user_id: str, db: AsyncSession
) -> ChatSession:
    """Return existing session or create a new one.

    Raises 403 if the session_id already exists but belongs to a different user.
    """
    result = await db.execute(select(ChatSession).where(ChatSession.id == session_id))
    session = result.scalar_one_or_none()

    if session is None:
        session = ChatSession(id=session_id, user_id=user_id)
        db.add(session)
        await db.commit()
        await db.refresh(session)
    elif session.user_id != user_id:
        raise HTTPException(
            status_code=403, detail="Access denied: session belongs to another user"
        )

    return session


async def _save_message(
    session_id: uuid.UUID, role: str, content: str, db: AsyncSession
) -> ChatMessage:
    """Persist a message to the database."""
    msg = ChatMessage(session_id=session_id, role=role, content=content)
    db.add(msg)
    await db.commit()
    await db.refresh(msg)
    return msg


async def _load_history(session_id: uuid.UUID, db: AsyncSession) -> list[dict]:
    """Load all messages for a session ordered by created_at."""
    result = await db.execute(
        select(ChatMessage)
        .where(ChatMessage.session_id == session_id)
        .order_by(ChatMessage.created_at.asc())
    )
    messages = result.scalars().all()
    return [{"role": msg.role, "content": msg.content} for msg in messages]


async def _proxy_sse_stream(
    history: list[dict],
    session_id: uuid.UUID,
    db: AsyncSession,
) -> AsyncGenerator[str, None]:
    """Proxy SSE stream from AI service, collecting assistant reply for DB persistence.

    Forwards SSE lines from AI service, intercepts agent.message.done to inject
    session_id, then saves assistant reply to DB after stream completes.
    """
    complete_content = ""
    inject_session_id = False

    try:
        async for line in ai_service_client.chat_stream(
            messages=history, session_id=str(session_id)
        ):
            if line == "event: agent.message.done":
                inject_session_id = True
                yield line + "\n"
                continue

            if inject_session_id and line.startswith("data:"):
                yield f"data: {json.dumps({'session_id': str(session_id)})}\n\n"
                inject_session_id = False
                continue

            yield line + "\n"

            if line.startswith("data:"):
                try:
                    data = json.loads(line[5:].strip())
                    if "text" in data:
                        complete_content += data["text"]
                except (json.JSONDecodeError, KeyError):
                    pass

        if complete_content:
            await _save_message(session_id, "assistant", complete_content, db)

    except Exception as e:
        yield "event: agent.workflow.failed\n"
        yield f"data: {json.dumps({'error': str(e)})}\n\n"


@chat_router.post("/stream")
async def chat_stream(
    request: ChatStreamRequest,
    db: AsyncSession = Depends(get_db),
) -> StreamingResponse:
    """Stream a chat response using Server-Sent Events.

    Flow:
      1. Resolve session_id (use provided UUID or auto-generate one)
      2. Upsert session (403 if session belongs to another user)
      3. Save user message to DB
      4. Load full session history
      5. Proxy SSE stream from AI service (done event carries session_id back)
      6. Save assistant reply after stream completes
    """
    session_id = request.session_id or uuid.uuid4()
    await _upsert_session(session_id, request.user_id, db)
    await _save_message(session_id, "user", request.message, db)
    history = await _load_history(session_id, db)

    return StreamingResponse(
        _proxy_sse_stream(history, session_id, db),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "X-Accel-Buffering": "no",
        },
    )
