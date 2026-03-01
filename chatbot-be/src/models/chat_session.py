from datetime import datetime, timezone
from typing import List, Optional
from uuid import UUID, uuid4

from sqlalchemy import func
from sqlmodel import Column, DateTime, Field, Relationship, SQLModel


class ChatSession(SQLModel, table=True):
    __tablename__ = "chat_sessions"

    id: UUID = Field(default_factory=uuid4, primary_key=True, nullable=False)
    user_id: str = Field(nullable=False, index=True)
    created_at: datetime = Field(
        sa_column=Column(DateTime(timezone=True), nullable=False, server_default=func.now()),
        default_factory=lambda: datetime.now(timezone.utc),
    )
    updated_at: datetime = Field(
        sa_column=Column(
            DateTime(timezone=True), nullable=False,
            server_default=func.now(), onupdate=func.now(),
        ),
        default_factory=lambda: datetime.now(timezone.utc),
    )
    messages: List["ChatMessage"] = Relationship(
        back_populates="session", cascade_delete=True
    )
