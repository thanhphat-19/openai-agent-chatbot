from contextlib import asynccontextmanager

from fastapi import FastAPI

from src.api.routes.chat import chat_router
from src.api.routes.health import health_router
from src.api.routes.sessions import sessions_router
from src.clients.ai_service import ai_service_client
from src.database import close_db_engine, init_db_engine


@asynccontextmanager
async def lifespan(app: FastAPI):
    await init_db_engine()
    yield
    await ai_service_client.close()
    await close_db_engine()


app = FastAPI(title="chatbot-be", version="1.0.0", lifespan=lifespan)

API_PREFIX = "/api/v1"

app.include_router(health_router, prefix=API_PREFIX, tags=["Health"])
app.include_router(chat_router, prefix=f"{API_PREFIX}/chat", tags=["Chat"])
app.include_router(sessions_router, prefix=f"{API_PREFIX}/sessions", tags=["Sessions"])
