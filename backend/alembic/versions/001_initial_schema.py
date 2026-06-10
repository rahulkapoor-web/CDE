"""Initial schema

Revision ID: 001
Revises:
Create Date: 2025-01-01 00:00:00.000000
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

revision: str = "001"
down_revision: Union[str, None] = None
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # Users
    op.create_table(
        "users",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("username", sa.String(100), unique=True, nullable=False),
        sa.Column("email", sa.String(255), unique=True, nullable=False),
        sa.Column("hashed_password", sa.String(255), nullable=False),
        sa.Column("full_name", sa.String(255), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_index("ix_users_username", "users", ["username"])

    # Connection Profiles
    op.create_table(
        "connection_profiles",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("user_id", sa.String(36), sa.ForeignKey("users.id"), nullable=False),
        sa.Column("name", sa.String(255), nullable=False),
        sa.Column("system_type", sa.String(20), nullable=False),
        sa.Column("environment", sa.String(20), nullable=False),
        sa.Column("sf_instance_url", sa.String(500), nullable=True),
        sa.Column("sf_username", sa.String(255), nullable=True),
        sa.Column("sf_password_encrypted", sa.Text, nullable=True),
        sa.Column("sf_security_token_encrypted", sa.Text, nullable=True),
        sa.Column("sf_consumer_key", sa.String(500), nullable=True),
        sa.Column("sf_consumer_secret_encrypted", sa.Text, nullable=True),
        sa.Column("vault_dns", sa.String(500), nullable=True),
        sa.Column("vault_username", sa.String(255), nullable=True),
        sa.Column("vault_password_encrypted", sa.Text, nullable=True),
        sa.Column("oauth_access_token_encrypted", sa.Text, nullable=True),
        sa.Column("oauth_refresh_token_encrypted", sa.Text, nullable=True),
        sa.Column("auth_method", sa.String(20), nullable=False, server_default="credentials"),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_index("ix_connection_profiles_user_id", "connection_profiles", ["user_id"])

    # Migration Projects
    op.create_table(
        "migration_projects",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("name", sa.String(255), nullable=False),
        sa.Column("description", sa.Text, nullable=True),
        sa.Column("source_connection_id", sa.String(36), sa.ForeignKey("connection_profiles.id"), nullable=False),
        sa.Column("target_connection_id", sa.String(36), sa.ForeignKey("connection_profiles.id"), nullable=False),
        sa.Column("created_by", sa.String(36), sa.ForeignKey("users.id"), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
    )

    # Object Mappings
    op.create_table(
        "object_mappings",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("project_id", sa.String(36), sa.ForeignKey("migration_projects.id"), nullable=False),
        sa.Column("source_object", sa.String(255), nullable=False),
        sa.Column("target_object", sa.String(255), nullable=False),
        sa.Column("is_active", sa.Boolean, nullable=False, server_default="true"),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_index("ix_object_mappings_project_id", "object_mappings", ["project_id"])

    # Field Mappings
    op.create_table(
        "field_mappings",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("object_mapping_id", sa.String(36), sa.ForeignKey("object_mappings.id"), nullable=False),
        sa.Column("source_field", sa.String(255), nullable=False),
        sa.Column("target_field", sa.String(255), nullable=False),
        sa.Column("source_field_type", sa.String(100), nullable=True),
        sa.Column("target_field_type", sa.String(100), nullable=True),
        sa.Column("transformation", sa.JSON, nullable=True),
        sa.Column("confidence_score", sa.Float, nullable=True),
        sa.Column("is_auto_mapped", sa.Boolean, nullable=False, server_default="false"),
        sa.Column("is_confirmed", sa.Boolean, nullable=False, server_default="false"),
    )
    op.create_index("ix_field_mappings_object_mapping_id", "field_mappings", ["object_mapping_id"])

    # Match Key Configs
    op.create_table(
        "match_key_configs",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("object_mapping_id", sa.String(36), sa.ForeignKey("object_mappings.id"), nullable=False),
        sa.Column("source_field", sa.String(255), nullable=False),
        sa.Column("target_field", sa.String(255), nullable=False),
        sa.Column("key_order", sa.Integer, nullable=False, server_default="0"),
    )
    op.create_index("ix_match_key_configs_object_mapping_id", "match_key_configs", ["object_mapping_id"])

    # Validation Runs
    op.create_table(
        "validation_runs",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("project_id", sa.String(36), sa.ForeignKey("migration_projects.id"), nullable=False),
        sa.Column("user_id", sa.String(36), sa.ForeignKey("users.id"), nullable=False),
        sa.Column("status", sa.String(20), nullable=False, server_default="pending"),
        sa.Column("mode", sa.String(20), nullable=False, server_default="auto"),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("completed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("error_message", sa.Text, nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("object_mapping_ids", sa.JSON, nullable=True),
    )
    op.create_index("ix_validation_runs_project_id", "validation_runs", ["project_id"])

    # Validation Summaries
    op.create_table(
        "validation_summaries",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("validation_run_id", sa.String(36), sa.ForeignKey("validation_runs.id"), nullable=False),
        sa.Column("object_mapping_id", sa.String(36), sa.ForeignKey("object_mappings.id"), nullable=False),
        sa.Column("source_object", sa.String(255), nullable=False),
        sa.Column("target_object", sa.String(255), nullable=False),
        sa.Column("source_count", sa.Integer, nullable=False, server_default="0"),
        sa.Column("target_count", sa.Integer, nullable=False, server_default="0"),
        sa.Column("matched_count", sa.Integer, nullable=False, server_default="0"),
        sa.Column("mismatched_count", sa.Integer, nullable=False, server_default="0"),
        sa.Column("missing_in_target_count", sa.Integer, nullable=False, server_default="0"),
        sa.Column("missing_in_source_count", sa.Integer, nullable=False, server_default="0"),
        sa.Column("match_percentage", sa.Float, nullable=False, server_default="0"),
        sa.Column("status", sa.String(20), nullable=False, server_default="pending"),
        sa.Column("error_message", sa.Text, nullable=True),
    )
    op.create_index("ix_validation_summaries_run_id", "validation_summaries", ["validation_run_id"])

    # Validation Details
    op.create_table(
        "validation_details",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("summary_id", sa.String(36), sa.ForeignKey("validation_summaries.id"), nullable=False),
        sa.Column("match_key_value", sa.String(500), nullable=False),
        sa.Column("status", sa.String(30), nullable=False),
        sa.Column("field_diffs", sa.JSON, nullable=True),
    )
    op.create_index("ix_validation_details_summary_id", "validation_details", ["summary_id"])
    op.create_index("ix_validation_details_match_key", "validation_details", ["match_key_value"])
    op.create_index("ix_validation_details_status", "validation_details", ["status"])


def downgrade() -> None:
    op.drop_table("validation_details")
    op.drop_table("validation_summaries")
    op.drop_table("validation_runs")
    op.drop_table("match_key_configs")
    op.drop_table("field_mappings")
    op.drop_table("object_mappings")
    op.drop_table("migration_projects")
    op.drop_table("connection_profiles")
    op.drop_table("users")
