from __future__ import annotations

import datetime as dt
import enum
from decimal import Decimal

from sqlalchemy import (
    Boolean,
    Date,
    DateTime,
    Enum,
    ForeignKey,
    Index,
    Integer,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy import (
    false as sa_false,
)
from sqlalchemy.orm import Mapped, mapped_column

from app.db import Base
from app.models._types import Money, utcnow


class TxnType(enum.StrEnum):
    debit = "debit"
    credit = "credit"


class CategorySource(enum.StrEnum):
    rule = "rule"
    cache = "cache"
    llm = "llm"
    user = "user"


class Transaction(Base):
    """A normalized transaction.

    `raw_narration` is stored exactly as it appeared in the statement and is never modified, so
    categorization can be re-run later. `amount` is signed: negative = money out.
    """

    __tablename__ = "transactions"
    __table_args__ = (
        UniqueConstraint("dedupe_hash"),
        Index("ix_transactions_account_date", "account_id", "date"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    account_id: Mapped[int] = mapped_column(ForeignKey("accounts.id", ondelete="CASCADE"))
    import_id: Mapped[int] = mapped_column(ForeignKey("imports.id", ondelete="CASCADE"), index=True)
    date: Mapped[dt.date] = mapped_column(Date)
    amount: Mapped[Decimal] = mapped_column(Money)
    type: Mapped[TxnType] = mapped_column(
        Enum(TxnType, native_enum=False, length=10, name="txn_type")
    )
    balance: Mapped[Decimal | None] = mapped_column(Money)
    currency: Mapped[str] = mapped_column(String(3))
    raw_narration: Mapped[str] = mapped_column(Text)
    #: Position within its statement in chronological order (stable ordering for same-day rows).
    row_index: Mapped[int] = mapped_column(Integer)
    dedupe_hash: Mapped[str] = mapped_column(String(64))

    cleaned_merchant: Mapped[str | None] = mapped_column(String(200), index=True)
    category_id: Mapped[int | None] = mapped_column(
        ForeignKey("categories.id", ondelete="SET NULL"), index=True
    )
    category_source: Mapped[CategorySource | None] = mapped_column(
        Enum(CategorySource, native_enum=False, length=10, name="category_source")
    )
    rules_version: Mapped[int | None] = mapped_column(Integer)

    #: Transfers between the user's own accounts are excluded from income/expense totals.
    is_transfer: Mapped[bool] = mapped_column(Boolean, default=False)
    transfer_peer_id: Mapped[int | None] = mapped_column(
        ForeignKey("transactions.id", ondelete="SET NULL")
    )
    #: Set when the user unlinks a detected transfer, so it is never auto-linked again.
    transfer_dismissed: Mapped[bool] = mapped_column(
        Boolean, default=False, server_default=sa_false()
    )

    created_at: Mapped[dt.datetime] = mapped_column(DateTime, default=utcnow)
