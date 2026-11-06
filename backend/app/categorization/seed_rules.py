"""Curated brand -> category rules, shipped so common merchants never need an LLM call.

Patterns match as whole words anywhere in the cleaned merchant name. The same list is frozen
in Alembic migration 0003, and a test checks the two agree.
"""

from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.categorization.categorizer import PRIORITY_SEED, load_category_index
from app.models import MerchantRule, RuleSource

#: (pattern, "Group > Category")
SEED_RULES: list[tuple[str, str]] = [
    ("SWIGGY", "Food > Food Delivery"),
    ("ZOMATO", "Food > Food Delivery"),
    ("UBER EATS", "Food > Food Delivery"),
    ("DOORDASH", "Food > Food Delivery"),
    ("ZEPTO", "Food > Groceries"),
    ("BLINKIT", "Food > Groceries"),
    ("BIGBASKET", "Food > Groceries"),
    ("INSTAMART", "Food > Groceries"),
    ("GROCERY", "Food > Groceries"),
    ("SUPERMARKET", "Food > Groceries"),
    ("STARBUCKS", "Food > Restaurants"),
    ("CAFE", "Food > Restaurants"),
    ("RESTAURANT", "Food > Restaurants"),
    ("CHAI", "Food > Restaurants"),
    ("AMAZON", "Shopping > Online Shopping"),
    ("FLIPKART", "Shopping > Online Shopping"),
    ("MYNTRA", "Shopping > Clothing"),
    ("NETFLIX", "Bills > Subscriptions"),
    ("SPOTIFY", "Bills > Subscriptions"),
    ("YOUTUBE", "Bills > Subscriptions"),
    ("PRIME VIDEO", "Bills > Subscriptions"),
    ("TELECOM", "Bills > Mobile & Internet"),
    ("AIRTEL", "Bills > Mobile & Internet"),
    ("JIO", "Bills > Mobile & Internet"),
    ("BROADBAND", "Bills > Mobile & Internet"),
    ("UBER", "Transport > Ride Hailing"),
    ("OLA", "Transport > Ride Hailing"),
    ("LYFT", "Transport > Ride Hailing"),
    ("SHELL", "Transport > Fuel"),
    ("HPCL", "Transport > Fuel"),
    ("BPCL", "Transport > Fuel"),
    ("IOCL", "Transport > Fuel"),
    ("FUEL", "Transport > Fuel"),
    ("PETROL", "Transport > Fuel"),
    ("METRO", "Transport > Public Transport"),
    ("IRCTC", "Leisure > Travel"),
    ("AIRLINES", "Leisure > Travel"),
    ("ELECTRICITY", "Housing > Utilities"),
    ("POWER", "Housing > Utilities"),
    ("UTILITY", "Housing > Utilities"),
    ("PHARMACY", "Health > Pharmacy"),
    ("HOSPITAL", "Health > Medical"),
    ("GYM", "Health > Fitness"),
    ("MUTUAL FUND", "Financial > Investments"),
    # Migration 0004: brands common in Indian UPI statements.
    ("VODAFONE", "Bills > Mobile & Internet"),
    ("MYJIO", "Bills > Mobile & Internet"),
    ("BSNL", "Bills > Mobile & Internet"),
    ("GOOGLE", "Bills > Subscriptions"),
    ("PUMP", "Transport > Fuel"),
    ("RAPIDO", "Transport > Ride Hailing"),
    ("REDBUS", "Leisure > Travel"),
    ("DMART", "Food > Groceries"),
    ("MILK", "Food > Groceries"),
    ("DAIRY", "Food > Groceries"),
    ("BAKERY", "Food > Restaurants"),
    ("SWEETS", "Food > Restaurants"),
    ("MEDICALS", "Health > Pharmacy"),
    ("PHARMEASY", "Health > Pharmacy"),
    ("APY", "Financial > Investments"),
]


def seed_merchant_rules(session: Session) -> int:
    """Insert missing seed rules (idempotent). Returns the number added."""
    idx = load_category_index(session)
    existing = set(session.scalars(select(MerchantRule.pattern)))
    added = 0
    for pattern, path in SEED_RULES:
        if pattern in existing:
            continue
        session.add(
            MerchantRule(
                pattern=pattern,
                category_id=idx.by_path[path],
                source=RuleSource.seed,
                priority=PRIORITY_SEED,
            )
        )
        added += 1
    session.flush()
    return added
