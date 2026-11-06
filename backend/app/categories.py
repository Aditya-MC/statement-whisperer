"""The fixed category tree.

The LLM categorizer (Phase 2) may only choose from this list, which keeps outputs stable and
comparable across years. Changing it requires a new Alembic data migration.
"""

from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import Category, CategoryKind

#: (group, kind, [children])
CATEGORY_TREE: list[tuple[str, CategoryKind, list[str]]] = [
    ("Income", CategoryKind.income, ["Salary", "Interest", "Refunds", "Other Income"]),
    ("Housing", CategoryKind.expense, ["Rent", "Utilities", "Maintenance"]),
    ("Food", CategoryKind.expense, ["Groceries", "Restaurants", "Food Delivery"]),
    ("Transport", CategoryKind.expense, ["Fuel", "Public Transport", "Ride Hailing", "Vehicle"]),
    ("Shopping", CategoryKind.expense, ["Online Shopping", "Electronics", "Clothing"]),
    ("Bills", CategoryKind.expense, ["Mobile & Internet", "Subscriptions", "Insurance"]),
    ("Health", CategoryKind.expense, ["Medical", "Pharmacy", "Fitness"]),
    ("Leisure", CategoryKind.expense, ["Entertainment", "Travel"]),
    ("Education", CategoryKind.expense, ["Tuition", "Books & Courses"]),
    (
        "Financial",
        CategoryKind.expense,
        ["Investments", "Loan EMI", "Credit Card Payment", "Bank Fees", "Taxes"],
    ),
    ("Cash", CategoryKind.expense, ["ATM Withdrawal"]),
    ("Transfers", CategoryKind.transfer, ["Self Transfer", "Transfer to Others"]),
    ("Other", CategoryKind.expense, ["Uncategorized"]),
]


def seed_categories(session: Session) -> int:
    """Insert any missing categories. Idempotent; returns the number of rows added."""
    added = 0
    for group, kind, children in CATEGORY_TREE:
        parent = session.scalar(
            select(Category).where(Category.name == group, Category.parent_id.is_(None))
        )
        if parent is None:
            parent = Category(name=group, kind=kind, parent_id=None)
            session.add(parent)
            session.flush()
            added += 1
        for child in children:
            exists = session.scalar(
                select(Category.id).where(Category.name == child, Category.parent_id == parent.id)
            )
            if exists is None:
                session.add(Category(name=child, kind=kind, parent_id=parent.id))
                added += 1
    session.flush()
    return added
