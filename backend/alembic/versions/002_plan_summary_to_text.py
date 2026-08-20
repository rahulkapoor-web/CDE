"""widen plans.summary to unbounded text

The plan summary is authored by the LLM and regularly exceeds 512 characters,
causing StringDataRightTruncationError on insert. Switch it to TEXT.

Revision ID: 002
Revises: 001
Create Date: 2026-08-17
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "002"
down_revision: Union[str, None] = "001"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.alter_column(
        "plans",
        "summary",
        existing_type=sa.String(length=512),
        type_=sa.Text(),
        existing_nullable=True,
    )


def downgrade() -> None:
    op.alter_column(
        "plans",
        "summary",
        existing_type=sa.Text(),
        type_=sa.String(length=512),
        existing_nullable=True,
    )
