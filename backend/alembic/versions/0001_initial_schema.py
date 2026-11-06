"""initial schema: accounts, imports, categories, merchant_rules, transactions

Revision ID: 0001
Revises:
Create Date: 2026-11-06
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0001"
down_revision: str | None = None
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

MONEY = sa.Numeric(18, 4)


def upgrade() -> None:
    op.create_table(
        "accounts",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("bank_name", sa.String(100), nullable=False),
        sa.Column("nickname", sa.String(100), nullable=False),
        sa.Column("currency", sa.String(3), nullable=False),
        sa.Column("last4", sa.String(4), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.CheckConstraint("last4 IS NULL OR length(last4) = 4", name=op.f("ck_accounts_last4_len")),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_accounts")),
    )

    op.create_table(
        "categories",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("name", sa.String(100), nullable=False),
        sa.Column("parent_id", sa.Integer(), nullable=True),
        sa.Column("kind", sa.Enum("income", "expense", "transfer", name="category_kind", native_enum=False, length=20), nullable=False),
        sa.ForeignKeyConstraint(["parent_id"], ["categories.id"], name=op.f("fk_categories_parent_id_categories"), ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_categories")),
        sa.UniqueConstraint("parent_id", "name", name=op.f("uq_categories_parent_id")),
    )

    op.create_table(
        "imports",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("account_id", sa.Integer(), nullable=False),
        sa.Column("file_hash", sa.String(64), nullable=False),
        sa.Column("file_type", sa.String(10), nullable=False),
        sa.Column("status", sa.Enum("completed", "needs_review", "failed", name="import_status", native_enum=False, length=20), nullable=False),
        sa.Column("parser_version", sa.String(20), nullable=False),
        sa.Column("mapping_source", sa.String(10), nullable=True),
        sa.Column("mapping", sa.JSON(), nullable=True),
        sa.Column("columns", sa.JSON(), nullable=True),
        sa.Column("validation", sa.JSON(), nullable=True),
        sa.Column("error_message", sa.Text(), nullable=True),
        sa.Column("date_from", sa.Date(), nullable=True),
        sa.Column("date_to", sa.Date(), nullable=True),
        sa.Column("opening_balance", MONEY, nullable=True),
        sa.Column("closing_balance", MONEY, nullable=True),
        sa.Column("row_count", sa.Integer(), nullable=False),
        sa.Column("inserted_count", sa.Integer(), nullable=False),
        sa.Column("duplicate_count", sa.Integer(), nullable=False),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("completed_at", sa.DateTime(), nullable=True),
        sa.ForeignKeyConstraint(["account_id"], ["accounts.id"], name=op.f("fk_imports_account_id_accounts"), ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_imports")),
    )
    op.create_index(op.f("ix_imports_account_id"), "imports", ["account_id"])
    op.create_index(op.f("ix_imports_file_hash"), "imports", ["file_hash"])

    op.create_table(
        "merchant_rules",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("pattern", sa.String(200), nullable=False),
        sa.Column("category_id", sa.Integer(), nullable=False),
        sa.Column("source", sa.Enum("seed", "user", "llm", name="rule_source", native_enum=False, length=20), nullable=False),
        sa.Column("priority", sa.Integer(), nullable=False),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.ForeignKeyConstraint(["category_id"], ["categories.id"], name=op.f("fk_merchant_rules_category_id_categories"), ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_merchant_rules")),
        sa.UniqueConstraint("pattern", name=op.f("uq_merchant_rules_pattern")),
    )

    op.create_table(
        "transactions",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("account_id", sa.Integer(), nullable=False),
        sa.Column("import_id", sa.Integer(), nullable=False),
        sa.Column("date", sa.Date(), nullable=False),
        sa.Column("amount", MONEY, nullable=False),
        sa.Column("type", sa.Enum("debit", "credit", name="txn_type", native_enum=False, length=10), nullable=False),
        sa.Column("balance", MONEY, nullable=True),
        sa.Column("currency", sa.String(3), nullable=False),
        sa.Column("raw_narration", sa.Text(), nullable=False),
        sa.Column("row_index", sa.Integer(), nullable=False),
        sa.Column("dedupe_hash", sa.String(64), nullable=False),
        sa.Column("cleaned_merchant", sa.String(200), nullable=True),
        sa.Column("category_id", sa.Integer(), nullable=True),
        sa.Column("category_source", sa.Enum("rule", "cache", "llm", "user", name="category_source", native_enum=False, length=10), nullable=True),
        sa.Column("rules_version", sa.Integer(), nullable=True),
        sa.Column("is_transfer", sa.Boolean(), nullable=False),
        sa.Column("transfer_peer_id", sa.Integer(), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.ForeignKeyConstraint(["account_id"], ["accounts.id"], name=op.f("fk_transactions_account_id_accounts"), ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["category_id"], ["categories.id"], name=op.f("fk_transactions_category_id_categories"), ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["import_id"], ["imports.id"], name=op.f("fk_transactions_import_id_imports"), ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["transfer_peer_id"], ["transactions.id"], name=op.f("fk_transactions_transfer_peer_id_transactions"), ondelete="SET NULL"),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_transactions")),
        sa.UniqueConstraint("dedupe_hash", name=op.f("uq_transactions_dedupe_hash")),
    )
    op.create_index("ix_transactions_account_date", "transactions", ["account_id", "date"])
    op.create_index(op.f("ix_transactions_category_id"), "transactions", ["category_id"])
    op.create_index(op.f("ix_transactions_import_id"), "transactions", ["import_id"])


def downgrade() -> None:
    op.drop_table("transactions")
    op.drop_table("merchant_rules")
    op.drop_table("imports")
    op.drop_table("categories")
    op.drop_table("accounts")
