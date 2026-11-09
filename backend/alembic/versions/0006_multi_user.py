"""multi-user: users, sessions, invites; owners on accounts, categories and rules

Revision ID: 0006
Revises: 0005
Create Date: 2026-11-09

Existing rows keep user_id NULL ("unclaimed"). The first admin to sign up claims them, so
a single-user ledger carries over to its owner.
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0006"
down_revision: str | None = "0005"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "users",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("email", sa.String(254), nullable=False),
        sa.Column("password_hash", sa.String(255), nullable=False),
        sa.Column("is_admin", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("last_login_at", sa.DateTime(), nullable=True),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_users")),
        sa.UniqueConstraint("email", name=op.f("uq_users_email")),
    )
    op.create_table(
        "sessions",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("user_id", sa.Integer(), nullable=False),
        sa.Column("token_hash", sa.String(64), nullable=False),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("expires_at", sa.DateTime(), nullable=False),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], name=op.f("fk_sessions_user_id_users"), ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_sessions")),
        sa.UniqueConstraint("token_hash", name=op.f("uq_sessions_token_hash")),
    )
    op.create_index(op.f("ix_sessions_user_id"), "sessions", ["user_id"])
    op.create_table(
        "invites",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("code", sa.String(64), nullable=False),
        sa.Column("note", sa.String(200), nullable=True),
        sa.Column("created_by", sa.Integer(), nullable=True),
        sa.Column("used_by", sa.Integer(), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("used_at", sa.DateTime(), nullable=True),
        sa.ForeignKeyConstraint(["created_by"], ["users.id"], name=op.f("fk_invites_created_by_users"), ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["used_by"], ["users.id"], name=op.f("fk_invites_used_by_users"), ondelete="SET NULL"),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_invites")),
        sa.UniqueConstraint("code", name=op.f("uq_invites_code")),
    )

    with op.batch_alter_table("accounts") as batch:
        batch.add_column(sa.Column("user_id", sa.Integer(), nullable=True))
        batch.create_foreign_key(op.f("fk_accounts_user_id_users"), "users", ["user_id"], ["id"], ondelete="CASCADE")
        batch.create_index(op.f("ix_accounts_user_id"), ["user_id"])

    with op.batch_alter_table("categories") as batch:
        # Uniqueness becomes per user and is enforced in the API (NULL owners/parents).
        batch.drop_constraint("uq_categories_parent_id", type_="unique")
        batch.add_column(sa.Column("user_id", sa.Integer(), nullable=True))
        batch.create_foreign_key(op.f("fk_categories_user_id_users"), "users", ["user_id"], ["id"], ondelete="CASCADE")
        batch.create_index(op.f("ix_categories_user_id"), ["user_id"])

    with op.batch_alter_table("merchant_rules") as batch:
        batch.drop_constraint("uq_merchant_rules_pattern", type_="unique")
        batch.add_column(sa.Column("user_id", sa.Integer(), nullable=True))
        batch.create_foreign_key(op.f("fk_merchant_rules_user_id_users"), "users", ["user_id"], ["id"], ondelete="CASCADE")
        batch.create_index(op.f("ix_merchant_rules_user_id"), ["user_id"])
        batch.create_unique_constraint(op.f("uq_merchant_rules_user_id"), ["user_id", "pattern"])


def downgrade() -> None:
    with op.batch_alter_table("merchant_rules") as batch:
        batch.drop_constraint(op.f("uq_merchant_rules_user_id"), type_="unique")
        batch.drop_index(op.f("ix_merchant_rules_user_id"))
        batch.drop_constraint(op.f("fk_merchant_rules_user_id_users"), type_="foreignkey")
        batch.drop_column("user_id")
        batch.create_unique_constraint("uq_merchant_rules_pattern", ["pattern"])
    with op.batch_alter_table("categories") as batch:
        batch.drop_index(op.f("ix_categories_user_id"))
        batch.drop_constraint(op.f("fk_categories_user_id_users"), type_="foreignkey")
        batch.drop_column("user_id")
        batch.create_unique_constraint("uq_categories_parent_id", ["parent_id", "name"])
    with op.batch_alter_table("accounts") as batch:
        batch.drop_index(op.f("ix_accounts_user_id"))
        batch.drop_constraint(op.f("fk_accounts_user_id_users"), type_="foreignkey")
        batch.drop_column("user_id")
    op.drop_table("invites")
    op.drop_index(op.f("ix_sessions_user_id"), table_name="sessions")
    op.drop_table("sessions")
    op.drop_table("users")
