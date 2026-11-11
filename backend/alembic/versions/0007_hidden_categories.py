"""hidden_categories: built-in categories a user has deleted (hidden for that user only)

Revision ID: 0007
Revises: 0006
Create Date: 2026-11-11
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0007"
down_revision: str | None = "0006"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "hidden_categories",
        sa.Column("user_id", sa.Integer(), nullable=False),
        sa.Column("category_id", sa.Integer(), nullable=False),
        sa.ForeignKeyConstraint(
            ["user_id"],
            ["users.id"],
            name=op.f("fk_hidden_categories_user_id_users"),
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["category_id"],
            ["categories.id"],
            name=op.f("fk_hidden_categories_category_id_categories"),
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("user_id", "category_id", name=op.f("pk_hidden_categories")),
    )


def downgrade() -> None:
    op.drop_table("hidden_categories")
