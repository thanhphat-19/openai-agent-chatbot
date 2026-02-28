from fastapi import FastAPI

from src.routers.chat import chat_router
from src.routers.health import health_router

app = FastAPI(title="chatbot-ai-service", version="1.0.0")

app.include_router(health_router, tags=["Health"])
app.include_router(chat_router, prefix="/v1/chat", tags=["Chat"])
