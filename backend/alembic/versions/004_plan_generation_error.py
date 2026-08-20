"""add generation_error to plans

Background plan generation can fail after the HTTP request has already
returned (the request returns immediately with a "generating" plan). This
column records why a generation failed so the UI can surface the error
instead of leaving the plan stuck in the "generating" state.

Revision ID: 004
Revises: 003
Create Date: 2026-08-20
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "004"
down_revision: Union[str, None] = "003"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "plans",
        sa.Column("generation_error", sa.Text(), nullable=True),
    )


def downgrade() -> None:
    op.drop_column("plans", "generation_error")
