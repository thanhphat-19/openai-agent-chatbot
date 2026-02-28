import os
from pydantic_settings import BaseSettings

class DatabaseConfig(BaseSettings):
    model_config = {"env_file": ".env", "extra": "ignore"}

    POSTGRES_HOST: str = "localhost"
    POSTGRES_PORT: str = "5432"
    POSTGRES_USER: str
    POSTGRES_PASSWORD: str
    POSTGRES_DB: str

    @property
    def async_url(self) -> str:
        return f"postgresql+asyncpg://{self.POSTGRES_USER}:{self.POSTGRES_PASSWORD}@{self.POSTGRES_HOST}:{self.POSTGRES_PORT}/{self.POSTGRES_DB}"

    @property
    def sync_url(self) -> str:                  # ← alembic dùng cái này
        return f"postgresql://{self.POSTGRES_USER}:{self.POSTGRES_PASSWORD}@{self.POSTGRES_HOST}:{self.POSTGRES_PORT}/{self.POSTGRES_DB}"


class AIServiceConfig(BaseSettings):
    model_config = {"env_file": ".env", "extra": "ignore"}
    AI_SERVICE_URL: str = "http://localhost:8001"
    AI_SERVICE_TIMEOUT: int = 300


class Settings:
    def __init__(self):
        self.database = DatabaseConfig()
        self.aiservice = AIServiceConfig()


settings = Settings()
