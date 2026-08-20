"""Connection profiles for JIRA, GitHub, and Salesforce.

Secret fields are stored encrypted in `secrets_encrypted` (Fernet). Non-secret
config lives in `config` (plain JSON).
"""

from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, Integer, String, Text, func
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from app.core.database import Base

# Connection types
JIRA = "jira"
GITHUB = "github"
SALESFORCE = "salesforce"


class Connection(Base):
    __tablename__ = "connections"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    user_id: Mapped[int] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), index=True
    )
    name: Mapped[str] = mapped_column(String(255))
    conn_type: Mapped[str] = mapped_column(String(32), index=True)
    # Non-secret configuration (e.g. base_url, repo, username, is_sandbox).
    config: Mapped[dict] = mapped_column(JSONB, default=dict)
    # Encrypted secret bundle (Fernet ciphertext of a JSON blob).
    secrets_encrypted: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
