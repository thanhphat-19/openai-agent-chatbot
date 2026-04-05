from pydantic import BaseModel


class MessageItem(BaseModel):
    role: str
    content: str


class AIStreamRequest(BaseModel):
    messages: list[MessageItem]
    session_id: str | None = None
