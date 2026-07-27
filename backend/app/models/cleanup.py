import uuid
from datetime import datetime, timezone

from sqlalchemy import String, DateTime, ForeignKey, Text, Integer, JSON
from sqlalchemy.orm import Mapped, mapped_column

from app.core.database import Base


class CleanupJob(Base):
    __tablename__ = "cleanup_jobs"

    id: Mapped[str] = mapped_column(
        String(36), primary_key=True, default=lambda: str(uuid.uuid4())
    )
    project_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("migration_projects.id")
    )
    user_id: Mapped[str] = mapped_column(String(36), ForeignKey("users.id"))
    status: Mapped[str] = mapped_column(
        String(20), default="pending"
    )  # pending, running, completed, failed, cancelled

    # Filter mode
    filter_mode: Mapped[str] = mapped_column(
        String(20), default="legacy_crm_id"
    )  # legacy_crm_id, country
    country_code: Mapped[str | None] = mapped_column(String(10), nullable=True)

    # Progress tracking
    total_steps: Mapped[int] = mapped_column(Integer, default=0)
    completed_steps: Mapped[int] = mapped_column(Integer, default=0)
    current_object: Mapped[str | None] = mapped_column(String(255), nullable=True)
    current_phase: Mapped[str | None] = mapped_column(
        String(50), nullable=True
    )  # querying, deleting, done
    records_found: Mapped[int] = mapped_column(Integer, default=0)
    records_deleted: Mapped[int] = mapped_column(Integer, default=0)

    # Per-object results
    step_results: Mapped[dict | None] = mapped_column(JSON, nullable=True)

    error_message: Mapped[str | None] = mapped_column(Text, nullable=True)
    started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(timezone.utc)
    )
