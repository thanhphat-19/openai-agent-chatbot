import uuid
from datetime import datetime

from pydantic import BaseModel


class ChatStreamRequest(BaseModel):
    session_id: uuid.UUID | None = None
    user_id: str
    message: str


class MessageItem(BaseModel):
    id: uuid.UUID
    session_id: uuid.UUID
    role: str
    content: str
    created_at: datetime

    model_config = {"from_attributes": True}


class HistoryResponse(BaseModel):
    session_id: uuid.UUID
    messages: list[MessageItem]
