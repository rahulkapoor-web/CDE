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
    ANTHROPIC_MODEL: str = "claude-sonnet-4-5"
    OPENAI_API_KEY: str = ""
    OPENAI_MODEL: str = "gpt-4o"

    # Planning engine
    PLAN_MAX_RETRIES: int = 2

    # RAG embeddings
    EMBEDDING_PROVIDER: str = "openai"  # "openai" | "none"
    EMBEDDING_MODEL: str = "text-embedding-3-small"


@lru_cache
def get_settings() -> Settings:
    return Settings()


settings = get_settings()
