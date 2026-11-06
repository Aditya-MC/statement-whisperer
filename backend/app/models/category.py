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
    """A node in the category tree (`parent_id` is NULL for top-level groups)."""

    __tablename__ = "categories"
    __table_args__ = (UniqueConstraint("parent_id", "name"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String(100))
    parent_id: Mapped[int | None] = mapped_column(ForeignKey("categories.id", ondelete="CASCADE"))
    kind: Mapped[CategoryKind] = mapped_column(
        Enum(CategoryKind, native_enum=False, length=20, name="category_kind")
    )
    #: Created by the user. Only custom categories can be renamed or deleted: built-in ones are
    #: referenced by name in code (e.g. "Income > Refunds") and by the seed rules.
    is_custom: Mapped[bool] = mapped_column(Boolean, default=False, server_default=false())


class MerchantRule(Base):
    """Maps a cleaned merchant pattern to a category. User corrections become rules (Phase 2)."""

    __tablename__ = "merchant_rules"
    __table_args__ = (UniqueConstraint("pattern"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    pattern: Mapped[str] = mapped_column(String(200))
    category_id: Mapped[int] = mapped_column(ForeignKey("categories.id", ondelete="CASCADE"))
    source: Mapped[RuleSource] = mapped_column(
        Enum(RuleSource, native_enum=False, length=20, name="rule_source")
    )
    priority: Mapped[int] = mapped_column(Integer, default=0)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)
