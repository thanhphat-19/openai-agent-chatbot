import uuid

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from src.database import get_db
from src.models.chat_message import ChatMessage
from src.models.chat_session import ChatSession
from src.schemas.chat import HistoryResponse, MessageItem

sessions_router = APIRouter()


async def _get_session_for_user(
    session_id: uuid.UUID, user_id: str, db: AsyncSession
) -> ChatSession:
    """Fetch session and verify ownership. Raises 404 if not found, 403 if wrong user."""
    result = await db.execute(select(ChatSession).where(ChatSession.id == session_id))
    session = result.scalar_one_or_none()
    if session is None:
        raise HTTPException(status_code=404, detail="Session not found")
    if session.user_id != user_id:
        raise HTTPException(
            status_code=403, detail="Access denied: session belongs to another user"
        )
    return session


@sessions_router.get("/{session_id}/history", response_model=HistoryResponse)
async def get_session_history(
    session_id: uuid.UUID,
    user_id: str,
    db: AsyncSession = Depends(get_db),
) -> HistoryResponse:
    """Return all messages for a session, scoped to the requesting user."""
    await _get_session_for_user(session_id, user_id, db)

    result = await db.execute(
        select(ChatMessage)
        .where(ChatMessage.session_id == session_id)
        .order_by(ChatMessage.created_at.asc())
    )
    messages = result.scalars().all()

    return HistoryResponse(
        session_id=session_id,
        messages=[MessageItem.model_validate(msg) for msg in messages],
    )


@sessions_router.delete("/{session_id}", status_code=204)
async def delete_session(
    session_id: uuid.UUID,
    user_id: str,
    db: AsyncSession = Depends(get_db),
) -> None:
    """Delete a session and all its messages (cascade). Verifies ownership first."""
    session = await _get_session_for_user(session_id, user_id, db)
    await db.delete(session)
    await db.commit()
