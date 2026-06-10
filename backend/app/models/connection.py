import uuid
from datetime import datetime, timezone

from sqlalchemy import String, DateTime, ForeignKey, Text
from sqlalchemy.orm import Mapped, mapped_column

from app.core.database import Base


class ConnectionProfile(Base):
    __tablename__ = "connection_profiles"

    id: Mapped[str] = mapped_column(
        String(36), primary_key=True, default=lambda: str(uuid.uuid4())
    )
    user_id: Mapped[str] = mapped_column(String(36), ForeignKey("users.id"), index=True)
    name: Mapped[str] = mapped_column(String(255))
    system_type: Mapped[str] = mapped_column(String(20))  # "salesforce" or "veeva_vault"
    environment: Mapped[str] = mapped_column(String(20))  # "sandbox" or "production"

    # Salesforce-specific
    sf_instance_url: Mapped[str | None] = mapped_column(String(500), nullable=True)
    sf_username: Mapped[str | None] = mapped_column(String(255), nullable=True)
    sf_password_encrypted: Mapped[str | None] = mapped_column(Text, nullable=True)
    sf_security_token_encrypted: Mapped[str | None] = mapped_column(Text, nullable=True)
    sf_consumer_key: Mapped[str | None] = mapped_column(String(500), nullable=True)
    sf_consumer_secret_encrypted: Mapped[str | None] = mapped_column(Text, nullable=True)

    # Veeva Vault-specific
    vault_dns: Mapped[str | None] = mapped_column(String(500), nullable=True)
    vault_username: Mapped[str | None] = mapped_column(String(255), nullable=True)
    vault_password_encrypted: Mapped[str | None] = mapped_column(Text, nullable=True)

    # OAuth tokens (for both systems)
    oauth_access_token_encrypted: Mapped[str | None] = mapped_column(Text, nullable=True)
    oauth_refresh_token_encrypted: Mapped[str | None] = mapped_column(Text, nullable=True)

    auth_method: Mapped[str] = mapped_column(String(20), default="credentials")  # "credentials" or "oauth"

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(timezone.utc)
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now(timezone.utc),
        onupdate=lambda: datetime.now(timezone.utc),
    )
