from collections.abc import AsyncGenerator

from src.clients.base import BaseAPIClient
from src.core.config import settings


class AIServiceClient(BaseAPIClient):
    def __init__(self):
        super().__init__(
            base_url=settings.aiservice.AI_SERVICE_URL,
            timeout=settings.aiservice.AI_SERVICE_TIMEOUT,
        )

    async def chat_stream(
        self, messages: list[dict], session_id: str | None = None
    ) -> AsyncGenerator[str, None]:
        """Stream SSE lines from the AI service for the given message history."""
        payload: dict = {"messages": messages}
        if session_id:
            payload["session_id"] = session_id
        async for line in self.stream_post("/v1/chat/stream", payload):
            yield line


ai_service_client = AIServiceClient()
