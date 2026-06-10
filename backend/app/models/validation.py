import uuid
from datetime import datetime, timezone

from sqlalchemy import String, DateTime, ForeignKey, Text, Integer, Float, JSON
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.database import Base


class ValidationRun(Base):
    __tablename__ = "validation_runs"

    id: Mapped[str] = mapped_column(
        String(36), primary_key=True, default=lambda: str(uuid.uuid4())
    )
    project_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("migration_projects.id"), index=True
    )
    user_id: Mapped[str] = mapped_column(String(36), ForeignKey("users.id"))
    status: Mapped[str] = mapped_column(
        String(20), default="pending"
    )  # pending, running, completed, failed
    mode: Mapped[str] = mapped_column(String(20), default="auto")  # auto, realtime, batch
    started_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    completed_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    error_message: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(timezone.utc)
    )
    # Track which object mappings were included in this run
    object_mapping_ids: Mapped[list | None] = mapped_column(JSON, nullable=True)

    summaries: Mapped[list["ValidationSummary"]] = relationship(
        back_populates="validation_run", cascade="all, delete-orphan"
    )


class ValidationSummary(Base):
    __tablename__ = "validation_summaries"

    id: Mapped[str] = mapped_column(
        String(36), primary_key=True, default=lambda: str(uuid.uuid4())
    )
    validation_run_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("validation_runs.id"), index=True
    )
    object_mapping_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("object_mappings.id")
    )
    source_object: Mapped[str] = mapped_column(String(255))
    target_object: Mapped[str] = mapped_column(String(255))
    source_count: Mapped[int] = mapped_column(Integer, default=0)
    target_count: Mapped[int] = mapped_column(Integer, default=0)
    matched_count: Mapped[int] = mapped_column(Integer, default=0)
    mismatched_count: Mapped[int] = mapped_column(Integer, default=0)
    missing_in_target_count: Mapped[int] = mapped_column(Integer, default=0)
    missing_in_source_count: Mapped[int] = mapped_column(Integer, default=0)
    match_percentage: Mapped[float] = mapped_column(Float, default=0.0)
    status: Mapped[str] = mapped_column(String(20), default="pending")
    error_message: Mapped[str | None] = mapped_column(Text, nullable=True)

    validation_run: Mapped["ValidationRun"] = relationship(back_populates="summaries")
    details: Mapped[list["ValidationDetail"]] = relationship(
        back_populates="summary", cascade="all, delete-orphan"
    )


class ValidationDetail(Base):
    __tablename__ = "validation_details"

    id: Mapped[str] = mapped_column(
        String(36), primary_key=True, default=lambda: str(uuid.uuid4())
    )
    summary_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("validation_summaries.id"), index=True
    )
    match_key_value: Mapped[str] = mapped_column(String(500), index=True)
    status: Mapped[str] = mapped_column(
        String(30), index=True
    )  # matched, mismatched, missing_in_target, missing_in_source
    field_diffs: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    # field_diffs example: {"Name": {"source": "Acme Corp", "target": "ACME Corp"}, ...}

    summary: Mapped["ValidationSummary"] = relationship(back_populates="details")
