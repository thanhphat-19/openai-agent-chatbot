from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    model_config = {"env_file": ".env", "extra": "ignore"}

    OPENAI_API_KEY: str
    PORT: int = 8001
    LOG_LEVEL: str = "INFO"


settings = Settings()
 