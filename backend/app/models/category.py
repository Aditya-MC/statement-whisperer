from __future__ import annotations

import enum
from datetime import datetime

from sqlalchemy import Boolean, DateTime, Enum, ForeignKey, Integer, String, UniqueConstraint, false
from sqlalchemy.orm import Mapped, mapped_column

from app.db import Base
from app.models._types import utcnow


class CategoryKind(enum.StrEnum):
    income = "income"
    expense = "expense"
    transfer = "transfer"


class RuleSource(enum.StrEnum):
    seed = "seed"
    user = "user"
    llm = "llm"


class Category(Base):
    """A node in the category tree (`parent_id` is NULL for top-level groups).

    Built-in categories have no owner (`user_id` NULL) and are shared by everyone. Custom ones
    belong to one user and are visible only to them. Name uniqueness among what one user can
    see is enforced in the API, because SQL UNIQUE treats NULL owners/parents as distinct.
    """

    __tablename__ = "categories"

    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String(100))
    parent_id: Mapped[int | None] = mapped_column(ForeignKey("categories.id", ondelete="CASCADE"))
    user_id: Mapped[int | None] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), index=True
    )
    kind: Mapped[CategoryKind] = mapped_column(
        Enum(CategoryKind, native_enum=False, length=20, name="category_kind")
    )
    #: Created by the user. Only custom categories can be renamed or deleted: built-in ones are
    #: referenced by name in code (e.g. "Income > Refunds") and by the seed rules.
    is_custom: Mapped[bool] = mapped_column(Boolean, default=False, server_default=false())


class MerchantRule(Base):
    """Maps a cleaned merchant pattern to a category.

    Seed rules have no owner and apply to everyone. A user's corrections and their cached LLM
    answers belong to that user only: merchant names reveal where someone shops.
    """

    __tablename__ = "merchant_rules"
    __table_args__ = (UniqueConstraint("user_id", "pattern"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int | None] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), index=True
    )
    pattern: Mapped[str] = mapped_column(String(200))
    category_id: Mapped[int] = mapped_column(ForeignKey("categories.id", ondelete="CASCADE"))
    source: Mapped[RuleSource] = mapped_column(
        Enum(RuleSource, native_enum=False, length=20, name="rule_source")
    )
    priority: Mapped[int] = mapped_column(Integer, default=0)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)


class HiddenCategory(Base):
    """A built-in category one user has deleted. Built-ins are shared, so "deleting" one only
    hides it for that user: it disappears from their lists, menus, rules and the AI's choices."""

    __tablename__ = "hidden_categories"

    user_id: Mapped[int] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), primary_key=True
    )
    category_id: Mapped[int] = mapped_column(
        ForeignKey("categories.id", ondelete="CASCADE"), primary_key=True
    )
