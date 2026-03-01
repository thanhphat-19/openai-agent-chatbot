import enum
from datetime import datetime, timezone
from typing import Optional
from uuid import UUID, uuid4

import sqlalchemy as sa
from sqlmodel import Column, DateTime, Field, Relationship, SQLModel


class ChatRole(str, enum.Enum):
    """Enum for chat message roles."""

    USER = "user"
    ASSISTANT = "assistant"


class ChatMessage(SQLModel, table=True):
    __tablename__ = "chat_messages"

    id: UUID = Field(default_factory=uuid4, primary_key=True, nullable=False)
    session_id: UUID = Field(foreign_key="chat_sessions.id", ondelete="CASCADE", nullable=False, index=True)
    role: ChatRole = Field(
        sa_column=Column(sa.Enum(ChatRole, name="chatrole"), nullable=False),
    )
    content: str = Field(nullable=False)
    created_at: datetime = Field(
        sa_column=Column(DateTime(timezone=True), nullable=False),
        default_factory=lambda: datetime.now(timezone.utc),
    )
    session: Optional["ChatSession"] = Relationship(back_populates="messages")
