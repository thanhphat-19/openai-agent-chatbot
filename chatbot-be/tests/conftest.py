"""Test fixtures for chatbot-be integration tests.

Uses a real PostgreSQL test DB with Alembic migrations applied.
Mocks AIServiceClient to avoid calling the real AI service.
"""

import os
from collections.abc import AsyncGenerator

import psycopg2
import pytest
import pytest_asyncio
from httpx import ASGITransport, AsyncClient
from psycopg2.extensions import ISOLATION_LEVEL_AUTOCOMMIT
from sqlalchemy import text as sa_text
from sqlalchemy.pool import NullPool
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from src.database import get_db
from src.main import app

TEST_DATABASE_URL = os.getenv(
    "TEST_DATABASE_URL",
    "postgresql+asyncpg://chatbot:chatbot@localhost:5432/chatbot_test",
)


def _ensure_test_db_exists() -> None:
    """Create chatbot_test database if it does not exist."""
    conn = psycopg2.connect(
        host="localhost", port=5432,
        user="chatbot", password="chatbot",
        database="chatbot",
    )
    conn.set_isolation_level(ISOLATION_LEVEL_AUTOCOMMIT)
    cur = conn.cursor()
    cur.execute("SELECT 1 FROM pg_database WHERE datname = 'chatbot_test'")
    if not cur.fetchone():
        cur.execute("CREATE DATABASE chatbot_test")
    cur.close()
    conn.close()


@pytest.fixture(scope="session")
def engine():
    """Create async engine once per test session."""
    _ensure_test_db_exists()
    import subprocess
    env = os.environ.copy()
    env["POSTGRES_HOST"] = "localhost"
    env["POSTGRES_PORT"] = "5432"
    env["POSTGRES_USER"] = "chatbot"
    env["POSTGRES_PASSWORD"] = "chatbot"
    env["POSTGRES_DB"] = "chatbot_test"
    subprocess.run(
        ["alembic", "upgrade", "head"],
        check=True,
        env=env,
        cwd=os.path.dirname(os.path.dirname(__file__)),
    )
    eng = create_async_engine(TEST_DATABASE_URL, echo=False, poolclass=NullPool)
    yield eng


@pytest_asyncio.fixture
async def db_session(engine) -> AsyncGenerator[AsyncSession, None]:
    """Separate session for test assertions (not shared with the app)."""
    factory = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)
    async with factory() as session:
        yield session
        await session.execute(sa_text("DELETE FROM chat_messages"))
        await session.execute(sa_text("DELETE FROM chat_sessions"))
        await session.commit()


@pytest_asyncio.fixture
async def client(engine) -> AsyncGenerator[AsyncClient, None]:
    """AsyncClient where the app gets its own session per request."""
    factory = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)

    async def override_get_db():
        async with factory() as session:
            yield session

    app.dependency_overrides[get_db] = override_get_db
    async with AsyncClient(
        transport=ASGITransport(app=app), base_url="http://test"
    ) as ac:
        yield ac
    app.dependency_overrides.clear()
