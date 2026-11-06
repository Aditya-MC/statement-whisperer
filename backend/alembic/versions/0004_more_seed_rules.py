"""seed more merchant rules (brands common in Indian UPI statements)

Revision ID: 0004
Revises: 0003
Create Date: 2026-11-06

Frozen copy; tests/test_migrations.py checks the union of 0003 + 0004 matches
app/categorization/seed_rules.py.
"""

from __future__ import annotations

from collections.abc import Sequence
from datetime import datetime

import sqlalchemy as sa
from alembic import op

revision: str = "0004"
down_revision: str | None = "0003"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

RULES: list[tuple[str, str, str]] = [
    ("VODAFONE", "Bills", "Mobile & Internet"),
    ("MYJIO", "Bills", "Mobile & Internet"),
    ("BSNL", "Bills", "Mobile & Internet"),
    ("GOOGLE", "Bills", "Subscriptions"),
    ("PUMP", "Transport", "Fuel"),
    ("RAPIDO", "Transport", "Ride Hailing"),
    ("REDBUS", "Leisure", "Travel"),
    ("DMART", "Food", "Groceries"),
    ("MILK", "Food", "Groceries"),
    ("DAIRY", "Food", "Groceries"),
    ("BAKERY", "Food", "Restaurants"),
    ("SWEETS", "Food", "Restaurants"),
    ("MEDICALS", "Health", "Pharmacy"),
    ("PHARMEASY", "Health", "Pharmacy"),
    ("APY", "Financial", "Investments"),
]


def upgrade() -> None:
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
    existing = {p for (p,) in conn.execute(sa.select(rules.c.pattern))}
    now = datetime(2026, 11, 6)
    new = [
        {"pattern": p, "category_id": ids[(g, c)], "source": "seed", "priority": 0, "created_at": now}
        for p, g, c in RULES
        if p not in existing  # a user may already have a rule with this exact pattern
    ]
    if new:
        conn.execute(rules.insert(), new)


def downgrade() -> None:
    patterns = ", ".join(f"'{p}'" for p, _, _ in RULES)
    op.execute(f"DELETE FROM merchant_rules WHERE source = 'seed' AND pattern IN ({patterns})")
