"""LSC Configuration Guide document chunks for retrieval (RAG).

Embeddings are stored as a JSON array of floats. When pgvector is available a
migration may convert this to a vector column; the service layer computes cosine
similarity in Python as a portable fallback.
"""

from datetime import datetime

from sqlalchemy import DateTime, Integer, String, Text, func
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from app.core.database import Base


class GuideDocument(Base):
    __tablename__ = "guide_documents"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    module: Mapped[str | None] = mapped_column(String(128), nullable=True)
    section: Mapped[str | None] = mapped_column(String(255), nullable=True)
    source: Mapped[str | None] = mapped_column(String(512), nullable=True)
    content: Mapped[str] = mapped_column(Text)
    embedding: Mapped[list | None] = mapped_column(JSONB, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
