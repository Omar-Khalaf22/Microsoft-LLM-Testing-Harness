import os
from functools import lru_cache

from pydantic import AnyHttpUrl, Field, SecretStr
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    app_env: str = "development"
    database_url: str
    llm_provider: str = "demo"
    openai_base_url: str = "https://api.openai.com/v1"
    openai_api_key: SecretStr = SecretStr("")
    cors_origins: list[AnyHttpUrl] = Field(
        default_factory=lambda: [AnyHttpUrl("http://localhost:5173")]
    )

    model_config = SettingsConfigDict(env_file=("../.env", ".env"), extra="ignore")


@lru_cache
def get_settings() -> Settings:
    env_file = os.getenv("LLM_ENV_FILE")
    if env_file:
        return Settings(_env_file=env_file)  # type: ignore[call-arg]
    return Settings()  # type: ignore[call-arg]
