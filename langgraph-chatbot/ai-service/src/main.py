from contextlib import asynccontextmanager

from fastapi import FastAPI
from loguru import logger

from src.routers.chat import chat_router
from src.routers.health import health_router


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Pre-warm Vanna and compile graphs at startup — never inside request handlers."""
    logger.info("Starting up: initialising Vanna + compiling LangGraph graphs...")
    from src.tools.vanna_setup import get_vanna  # noqa: F401 — triggers singleton init
    from src.agents.gen_report_agent import gen_report_graph  # noqa: F401 — already compiled
    from src.agents.gen_dashboard_agent import gen_dashboard_graph  # noqa: F401
    from src.agents.supervisor import supervisor_graph  # noqa: F401
    logger.info("All graphs compiled and ready.")
    yield
    logger.info("Shutting down.")


app = FastAPI(
    title="langgraph-local-chatbot",
    version="1.0.0",
    lifespan=lifespan,
)

app.include_router(health_router, tags=["Health"])
app.include_router(chat_router, prefix="/v1/chat", tags=["Chat"])
