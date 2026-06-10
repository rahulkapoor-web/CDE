import uuid
from datetime import datetime, timezone

from sqlalchemy import String, DateTime, ForeignKey, Text, Boolean, JSON
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.database import Base


class MigrationProject(Base):
    __tablename__ = "migration_projects"

    id: Mapped[str] = mapped_column(
        String(36), primary_key=True, default=lambda: str(uuid.uuid4())
    )
    name: Mapped[str] = mapped_column(String(255))
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    source_connection_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("connection_profiles.id")
    )
    target_connection_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("connection_profiles.id")
    )
    created_by: Mapped[str] = mapped_column(String(36), ForeignKey("users.id"))
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(timezone.utc)
    )

    object_mappings: Mapped[list["ObjectMapping"]] = relationship(
        back_populates="project", cascade="all, delete-orphan"
    )


class ObjectMapping(Base):
    __tablename__ = "object_mappings"

    id: Mapped[str] = mapped_column(
        String(36), primary_key=True, default=lambda: str(uuid.uuid4())
    )
    project_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("migration_projects.id"), index=True
    )
    source_object: Mapped[str] = mapped_column(String(255))
    target_object: Mapped[str] = mapped_column(String(255))
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(timezone.utc)
    )

    project: Mapped["MigrationProject"] = relationship(back_populates="object_mappings")
    field_mappings: Mapped[list["FieldMapping"]] = relationship(
        back_populates="object_mapping", cascade="all, delete-orphan"
    )
    match_key_configs: Mapped[list["MatchKeyConfig"]] = relationship(
        back_populates="object_mapping", cascade="all, delete-orphan"
    )


class FieldMapping(Base):
    __tablename__ = "field_mappings"

    id: Mapped[str] = mapped_column(
        String(36), primary_key=True, default=lambda: str(uuid.uuid4())
    )
    object_mapping_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("object_mappings.id"), index=True
    )
    source_field: Mapped[str] = mapped_column(String(255))
    target_field: Mapped[str] = mapped_column(String(255))
    source_field_type: Mapped[str | None] = mapped_column(String(100), nullable=True)
    target_field_type: Mapped[str | None] = mapped_column(String(100), nullable=True)
    transformation: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    # transformation example: {"type": "picklist_map", "mapping": {"Active": "active__v"}}
    confidence_score: Mapped[float | None] = mapped_column(nullable=True)
    is_auto_mapped: Mapped[bool] = mapped_column(Boolean, default=False)
    is_confirmed: Mapped[bool] = mapped_column(Boolean, default=False)

    object_mapping: Mapped["ObjectMapping"] = relationship(back_populates="field_mappings")


class MatchKeyConfig(Base):
    __tablename__ = "match_key_configs"

    id: Mapped[str] = mapped_column(
        String(36), primary_key=True, default=lambda: str(uuid.uuid4())
    )
    object_mapping_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("object_mappings.id"), index=True
    )
    source_field: Mapped[str] = mapped_column(String(255))
    target_field: Mapped[str] = mapped_column(String(255))
    key_order: Mapped[int] = mapped_column(default=0)

    object_mapping: Mapped["ObjectMapping"] = relationship(back_populates="match_key_configs")
