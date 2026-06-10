from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    APP_NAME: str = "Migration Bridge"
    DEBUG: bool = False

    # Database
    DATABASE_URL: str = "postgresql+asyncpg://postgres:postgres@db:5432/migration_bridge"
    DATABASE_URL_SYNC: str = "postgresql+psycopg2://postgres:postgres@db:5432/migration_bridge"

    # Redis
    REDIS_URL: str = "redis://redis:6379/0"

    # Auth
    SECRET_KEY: str = "change-me-in-production-use-a-real-secret"
    ALGORITHM: str = "HS256"
    ACCESS_TOKEN_EXPIRE_MINUTES: int = 480

    # Encryption key for stored credentials
    CREDENTIAL_ENCRYPTION_KEY: str = "change-me-generate-with-fernet"

    # Batch processing
    REALTIME_RECORD_THRESHOLD: int = 100_000
    BATCH_CHUNK_SIZE: int = 10_000

    class Config:
        env_file = ".env"


settings = Settings()
