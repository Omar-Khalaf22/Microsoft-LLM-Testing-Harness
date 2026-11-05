import os
from functools import lru_cache

from pydantic import AnyHttpUrl, Field, SecretStr, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    app_env: str = "development"
    database_url: str
    llm_provider: str = "demo"
    assistant_model: str = "gpt-4o-mini"
    judge_model: str = ""
    judge_profile_id: str = ""
    judge_profile_revision: int = 1
    project_id: str = "prototype"
    auth_mode: str = "disabled"
    dev_subject: str = ""
    oidc_issuer: str = ""
    oidc_audience: str = ""
    oidc_jwks_url: str = ""
    authorized_subjects: list[str] = Field(default_factory=list)
    assistant_timeout_seconds: float = Field(default=30.0, gt=0, le=120, allow_inf_nan=False)
    openai_base_url: str = "https://api.openai.com/v1"
    approved_model_endpoints: list[str] = Field(
        default_factory=lambda: ["https://api.openai.com/v1"]
    )
    openai_api_key: SecretStr = SecretStr("")
    cors_origins: list[AnyHttpUrl] = Field(
        default_factory=lambda: [AnyHttpUrl("http://localhost:5173")]
    )

    model_config = SettingsConfigDict(env_file=("../.env", ".env"), extra="ignore")

    @model_validator(mode="after")
    def shared_endpoints(self):
        if self.app_env != "development":
            if (
                self.openai_base_url not in self.approved_model_endpoints
                or not self.openai_base_url.startswith("https://")
            ):
                raise ValueError("Shared mode requires a server-approved HTTPS model endpoint.")
            if self.oidc_jwks_url and not self.oidc_jwks_url.startswith("https://"):
                raise ValueError("Shared mode requires an HTTPS JWKS endpoint.")
        return self


@lru_cache
def get_settings() -> Settings:
    env_file = os.getenv("LLM_ENV_FILE")
    if env_file:
        return Settings(_env_file=env_file)  # type: ignore[call-arg]
    return Settings()  # type: ignore[call-arg]
