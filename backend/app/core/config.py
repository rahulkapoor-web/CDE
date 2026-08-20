"""Application configuration loaded from environment variables."""

from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    APP_NAME: str = "ONA — AI Planning Engine"

    # Database
    DATABASE_URL: str = (
        "postgresql+asyncpg://postgres:postgres@localhost:5432/ona_planner"
    )
    # Sync URL used by Alembic migrations.
    DATABASE_URL_SYNC: str = (
        "postgresql+psycopg2://postgres:postgres@localhost:5432/ona_planner"
    )

    # Auth
    SECRET_KEY: str = "dev-secret-change-in-production"
    JWT_ALGORITHM: str = "HS256"
    ACCESS_TOKEN_EXPIRE_MINUTES: int = 60 * 24

    # Credential encryption (Fernet key). A dev default is generated if unset.
    CREDENTIAL_ENCRYPTION_KEY: str = ""

    # LLM provider selection: "anthropic" | "openai"
    LLM_PROVIDER: str = "anthropic"
    ANTHROPIC_API_KEY: str = ""
    # Gateway/proxy support: when ANTHROPIC_API_KEY is absent, the SDK can
    # authenticate via an auth token + base URL + custom headers (e.g. an
    # Anthropic-compatible gateway that injects the real credentials).
    ANTHROPIC_AUTH_TOKEN: str = ""
    ANTHROPIC_BASE_URL: str = ""
    ANTHROPIC_CUSTOM_HEADERS: str = ""
    ANTHROPIC_MODEL: str = "claude-sonnet-4-5"
    OPENAI_API_KEY: str = ""
    OPENAI_MODEL: str = "gpt-4o"

    # Planning engine
    PLAN_MAX_RETRIES: int = 2
    # Max output tokens per generation. Plans are large JSON documents; the
    # previous 8000 default truncated responses mid-JSON. Sonnet 4.5 supports
    # much higher output limits.
    PLAN_MAX_OUTPUT_TOKENS: int = 16000

    # RAG embeddings
    EMBEDDING_PROVIDER: str = "openai"  # "openai" | "none"
    EMBEDDING_MODEL: str = "text-embedding-3-small"


@lru_cache
def get_settings() -> Settings:
    return Settings()


settings = get_settings()
