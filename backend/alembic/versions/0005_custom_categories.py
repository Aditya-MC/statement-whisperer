"""add categories.is_custom for user-created categories

Revision ID: 0005
Revises: 0004
Create Date: 2026-11-06
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0005"
down_revision: str | None = "0004"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    with op.batch_alter_table("categories") as batch:
        batch.add_column(
            sa.Column("is_custom", sa.Boolean(), nullable=False, server_default=sa.false())
        )


def downgrade() -> None:
    # Custom categories can't exist without the flag; remove them first (rules cascade,
    # transactions fall back to uncategorized via ON DELETE SET NULL).
    op.execute("DELETE FROM categories WHERE is_custom AND parent_id IS NOT NULL")
    op.execute("DELETE FROM categories WHERE is_custom")
    with op.batch_alter_table("categories") as batch:
        batch.drop_column("is_custom")
