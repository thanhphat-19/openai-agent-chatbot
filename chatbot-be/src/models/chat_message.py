from datetime import datetime
from typing import Optional
from uuid import UUID, uuid4

from sqlmodel import Column, DateTime, Field, Relationship, SQLModel


class ChatMessage(SQLModel, table=True):
    __tablename__ = "chat_messages"

    id: UUID = Field(default_factory=uuid4, primary_key=True, nullable=False)
    session_id: UUID = Field(foreign_key="chat_sessions.id", ondelete="CASCADE", nullable=False, index=True)
    role: str = Field(nullable=False)
    content: str = Field(nullable=False)
    created_at: datetime = Field(
        sa_column=Column(DateTime(timezone=True), nullable=False),
        default_factory=datetime.utcnow,
    )
    session: Optional["ChatSession"] = Relationship(back_populates="messages")
