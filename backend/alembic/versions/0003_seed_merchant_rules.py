"""seed merchant rules; index cleaned_merchant; add transactions.transfer_dismissed

Revision ID: 0003
Revises: 0002
Create Date: 2026-11-06

The rule list is frozen here on purpose. tests/test_migrations.py checks it matches
app/categorization/seed_rules.py.
"""

from __future__ import annotations

from collections.abc import Sequence
from datetime import datetime

import sqlalchemy as sa
from alembic import op

revision: str = "0003"
down_revision: str | None = "0002"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

RULES: list[tuple[str, str, str]] = [
    ("SWIGGY", "Food", "Food Delivery"),
    ("ZOMATO", "Food", "Food Delivery"),
    ("UBER EATS", "Food", "Food Delivery"),
    ("DOORDASH", "Food", "Food Delivery"),
    ("ZEPTO", "Food", "Groceries"),
    ("BLINKIT", "Food", "Groceries"),
    ("BIGBASKET", "Food", "Groceries"),
    ("INSTAMART", "Food", "Groceries"),
    ("GROCERY", "Food", "Groceries"),
    ("SUPERMARKET", "Food", "Groceries"),
    ("STARBUCKS", "Food", "Restaurants"),
    ("CAFE", "Food", "Restaurants"),
    ("RESTAURANT", "Food", "Restaurants"),
    ("CHAI", "Food", "Restaurants"),
    ("AMAZON", "Shopping", "Online Shopping"),
    ("FLIPKART", "Shopping", "Online Shopping"),
    ("MYNTRA", "Shopping", "Clothing"),
    ("NETFLIX", "Bills", "Subscriptions"),
    ("SPOTIFY", "Bills", "Subscriptions"),
    ("YOUTUBE", "Bills", "Subscriptions"),
    ("PRIME VIDEO", "Bills", "Subscriptions"),
    ("TELECOM", "Bills", "Mobile & Internet"),
    ("AIRTEL", "Bills", "Mobile & Internet"),
    ("JIO", "Bills", "Mobile & Internet"),
    ("BROADBAND", "Bills", "Mobile & Internet"),
    ("UBER", "Transport", "Ride Hailing"),
    ("OLA", "Transport", "Ride Hailing"),
    ("LYFT", "Transport", "Ride Hailing"),
    ("SHELL", "Transport", "Fuel"),
    ("HPCL", "Transport", "Fuel"),
    ("BPCL", "Transport", "Fuel"),
    ("IOCL", "Transport", "Fuel"),
    ("FUEL", "Transport", "Fuel"),
    ("PETROL", "Transport", "Fuel"),
    ("METRO", "Transport", "Public Transport"),
    ("IRCTC", "Leisure", "Travel"),
    ("AIRLINES", "Leisure", "Travel"),
    ("ELECTRICITY", "Housing", "Utilities"),
    ("POWER", "Housing", "Utilities"),
    ("UTILITY", "Housing", "Utilities"),
    ("PHARMACY", "Health", "Pharmacy"),
    ("HOSPITAL", "Health", "Medical"),
    ("GYM", "Health", "Fitness"),
    ("MUTUAL FUND", "Financial", "Investments"),
]


def upgrade() -> None:
    op.create_index(op.f("ix_transactions_cleaned_merchant"), "transactions", ["cleaned_merchant"])
    with op.batch_alter_table("transactions") as batch:
        batch.add_column(
            sa.Column("transfer_dismissed", sa.Boolean(), nullable=False, server_default=sa.false())
        )

    conn = op.get_bind()
    cats = sa.table(
        "categories",
        sa.column("id", sa.Integer),
        sa.column("name", sa.String),
        sa.column("parent_id", sa.Integer),
    )
    parent = cats.alias("parent")
    rows = conn.execute(
        sa.select(cats.c.id, parent.c.name, cats.c.name).join(parent, cats.c.parent_id == parent.c.id)
    ).all()
    ids = {(group, name): cid for cid, group, name in rows}

    rules = sa.table(
        "merchant_rules",
        sa.column("pattern", sa.String),
        sa.column("category_id", sa.Integer),
        sa.column("source", sa.String),
        sa.column("priority", sa.Integer),
        sa.column("created_at", sa.DateTime),
    )
    now = datetime(2026, 11, 6)
    conn.execute(
        rules.insert(),
        [
            {"pattern": p, "category_id": ids[(g, c)], "source": "seed", "priority": 0, "created_at": now}
            for p, g, c in RULES
        ],
    )


def downgrade() -> None:
    op.execute("DELETE FROM merchant_rules WHERE source = 'seed'")
    with op.batch_alter_table("transactions") as batch:
        batch.drop_column("transfer_dismissed")
    op.drop_index(op.f("ix_transactions_cleaned_merchant"), table_name="transactions")
