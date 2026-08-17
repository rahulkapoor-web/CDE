"""add approval and deployment tracking to plans

Adds the approval gate and Metadata API deployment bookkeeping columns so a
developer can review a generated plan and, on "Go ahead", deploy it to a
connected Salesforce org.

Revision ID: 003
Revises: 002
Create Date: 2026-08-17
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "003"
down_revision: Union[str, None] = "002"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "plans",
        sa.Column("approved_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.add_column(
        "plans",
        sa.Column("approved_by_id", sa.Integer(), nullable=True),
    )
    op.add_column(
        "plans",
        sa.Column("deploy_connection_id", sa.Integer(), nullable=True),
    )
    op.add_column(
        "plans",
        sa.Column("deploy_async_id", sa.String(length=64), nullable=True),
    )
    op.add_column(
        "plans",
        sa.Column("deploy_started_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.add_column(
        "plans",
        sa.Column("deploy_finished_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.add_column(
        "plans",
        sa.Column(
            "deploy_result",
            postgresql.JSONB(astext_type=sa.Text()),
            nullable=True,
        ),
    )
    op.create_foreign_key(
        "fk_plans_approved_by_id_users",
        "plans",
        "users",
        ["approved_by_id"],
        ["id"],
        ondelete="SET NULL",
    )
    op.create_foreign_key(
        "fk_plans_deploy_connection_id_connections",
        "plans",
        "connections",
        ["deploy_connection_id"],
        ["id"],
        ondelete="SET NULL",
    )


def downgrade() -> None:
    op.drop_constraint(
        "fk_plans_deploy_connection_id_connections", "plans", type_="foreignkey"
    )
    op.drop_constraint(
        "fk_plans_approved_by_id_users", "plans", type_="foreignkey"
    )
    op.drop_column("plans", "deploy_result")
    op.drop_column("plans", "deploy_finished_at")
    op.drop_column("plans", "deploy_started_at")
    op.drop_column("plans", "deploy_async_id")
    op.drop_column("plans", "deploy_connection_id")
    op.drop_column("plans", "approved_by_id")
    op.drop_column("plans", "approved_at")
