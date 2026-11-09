from __future__ import annotations

from datetime import datetime

from sqlalchemy import CheckConstraint, DateTime, ForeignKey, String
from sqlalchemy.orm import Mapped, mapped_column

from app.db import Base
from app.models._types import utcnow


class Account(Base):
    """A bank account. Only the last four digits of the account number are ever stored."""

    __tablename__ = "accounts"
    __table_args__ = (CheckConstraint("last4 IS NULL OR length(last4) = 4", name="last4_len"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    #: Owner. Imports and transactions belong to a user through their account. NULL only for
    #: data created before multi-user support, until the first admin claims it.
    user_id: Mapped[int | None] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), index=True
    )
    bank_name: Mapped[str] = mapped_column(String(100))
    nickname: Mapped[str] = mapped_column(String(100))
    currency: Mapped[str] = mapped_column(String(3))
    last4: Mapped[str | None] = mapped_column(String(4))
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)
