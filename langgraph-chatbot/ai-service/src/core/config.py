from pydantic_settings import BaseSettings
from pathlib import Path


class Settings(BaseSettings):
    model_config = {"env_file": ".env", "extra": "ignore"}

    OPENAI_API_KEY: str
    PORT: int = 8001
    LOG_LEVEL: str = "INFO"
    DB_PATH: str = "data/sample.db"
    VANNA_MODEL: str = "gpt-4o-mini"
    CHROMA_PATH: str = "data/chroma"

    @property
    def db_abs_path(self) -> str:
        return str(Path(self.DB_PATH).resolve())

    @property
    def chroma_abs_path(self) -> str:
        return str(Path(self.CHROMA_PATH).resolve())


settings = Settings()
