"""Generated plan records with input snapshot and output JSON."""

from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, Integer, String, Text, func
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from app.core.database import Base


class PlanStatus:
    """Plan lifecycle states. Free-text in the DB; centralized here for reuse."""

    GENERATED = "generated"
    APPROVED = "approved"
    DEPLOYING = "deploying"
    DEPLOYED = "deployed"
    DEPLOY_FAILED = "deploy_failed"


class Plan(Base):
    __tablename__ = "plans"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    user_id: Mapped[int] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), index=True
    )
    jira_ticket: Mapped[str] = mapped_column(String(64), index=True)
    # LLM-authored free text; length is unbounded to avoid truncation errors.
    summary: Mapped[str | None] = mapped_column(Text, nullable=True)
    # Lifecycle: generated -> approved -> deploying -> deployed | deploy_failed.
    status: Mapped[str] = mapped_column(String(32), default="generated")
    provider: Mapped[str | None] = mapped_column(String(32), nullable=True)
    model: Mapped[str | None] = mapped_column(String(128), nullable=True)
    # Consolidated context object used as generation input.
    context_snapshot: Mapped[dict] = mapped_column(JSONB, default=dict)
    # Validated plan JSON.
    plan_json: Mapped[dict] = mapped_column(JSONB, default=dict)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )

    # Approval gate: set when a developer clicks "Go ahead".
    approved_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    approved_by_id: Mapped[int | None] = mapped_column(
        ForeignKey("users.id", ondelete="SET NULL"), nullable=True
    )
    # Metadata API deployment tracking.
    deploy_connection_id: Mapped[int | None] = mapped_column(
        ForeignKey("connections.id", ondelete="SET NULL"), nullable=True
    )
    deploy_async_id: Mapped[str | None] = mapped_column(String(64), nullable=True)
    deploy_started_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    deploy_finished_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    # Structured result from checkDeployStatus (success flag, component errors).
    deploy_result: Mapped[dict | None] = mapped_column(JSONB, nullable=True)
