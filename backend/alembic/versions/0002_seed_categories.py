"""seed the fixed category tree

Revision ID: 0002
Revises: 0001
Create Date: 2026-11-06

The list is frozen here on purpose (not imported from app code), so that later edits to
app/categories.py need their own migration. tests/test_migrations.py checks the two agree.
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0002"
down_revision: str | None = "0001"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

TREE: list[tuple[str, str, list[str]]] = [
    ("Income", "income", ["Salary", "Interest", "Refunds", "Other Income"]),
    ("Housing", "expense", ["Rent", "Utilities", "Maintenance"]),
    ("Food", "expense", ["Groceries", "Restaurants", "Food Delivery"]),
    ("Transport", "expense", ["Fuel", "Public Transport", "Ride Hailing", "Vehicle"]),
    ("Shopping", "expense", ["Online Shopping", "Electronics", "Clothing"]),
    ("Bills", "expense", ["Mobile & Internet", "Subscriptions", "Insurance"]),
    ("Health", "expense", ["Medical", "Pharmacy", "Fitness"]),
    ("Leisure", "expense", ["Entertainment", "Travel"]),
    ("Education", "expense", ["Tuition", "Books & Courses"]),
    ("Financial", "expense", ["Investments", "Loan EMI", "Credit Card Payment", "Bank Fees", "Taxes"]),
    ("Cash", "expense", ["ATM Withdrawal"]),
    ("Transfers", "transfer", ["Self Transfer", "Transfer to Others"]),
    ("Other", "expense", ["Uncategorized"]),
]

categories = sa.table(
    "categories",
    sa.column("id", sa.Integer),
    sa.column("name", sa.String),
    sa.column("parent_id", sa.Integer),
    sa.column("kind", sa.String),
)


def upgrade() -> None:
    conn = op.get_bind()
    for group, kind, children in TREE:
        conn.execute(categories.insert().values(name=group, parent_id=None, kind=kind))
        parent_id = conn.execute(
            sa.select(categories.c.id).where(
                categories.c.name == group, categories.c.parent_id.is_(None)
            )
        ).scalar_one()
        conn.execute(
            categories.insert(),
            [{"name": c, "parent_id": parent_id, "kind": kind} for c in children],
        )


def downgrade() -> None:
    op.execute(categories.delete())
