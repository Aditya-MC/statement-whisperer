from __future__ import annotations

import enum
from datetime import date, datetime
from decimal import Decimal
from typing import Any

from sqlalchemy import JSON, Date, DateTime, Enum, ForeignKey, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from app.db import Base
from app.models._types import Money, utcnow


class ImportStatus(enum.StrEnum):
    completed = "completed"
    needs_review = "needs_review"
    failed = "failed"


class Import(Base):
    """One uploaded statement file. The file itself is never stored, only its SHA-256 hash.

    `mapping` holds the column mapping that was applied (inferred or user-supplied) and `columns`
    the statement's header labels, so the review UI can let the user correct the mapping.
    `validation` is the full validation report (row numbers and messages, never raw values).
    """

    __tablename__ = "imports"

    id: Mapped[int] = mapped_column(primary_key=True)
    account_id: Mapped[int] = mapped_column(
        ForeignKey("accounts.id", ondelete="CASCADE"), index=True
    )
    file_hash: Mapped[str] = mapped_column(String(64), index=True)
    file_type: Mapped[str] = mapped_column(String(10))
    status: Mapped[ImportStatus] = mapped_column(
        Enum(ImportStatus, native_enum=False, length=20, name="import_status")
    )
    parser_version: Mapped[str] = mapped_column(String(20))
    mapping_source: Mapped[str | None] = mapped_column(String(10))  # "llm" | "user"
    mapping: Mapped[dict[str, Any] | None] = mapped_column(JSON)
    columns: Mapped[list[str] | None] = mapped_column(JSON)
    validation: Mapped[dict[str, Any] | None] = mapped_column(JSON)
    error_message: Mapped[str | None] = mapped_column(Text)

    date_from: Mapped[date | None] = mapped_column(Date)
    date_to: Mapped[date | None] = mapped_column(Date)
    opening_balance: Mapped[Decimal | None] = mapped_column(Money)
    closing_balance: Mapped[Decimal | None] = mapped_column(Money)
    row_count: Mapped[int] = mapped_column(Integer, default=0)
    inserted_count: Mapped[int] = mapped_column(Integer, default=0)
    duplicate_count: Mapped[int] = mapped_column(Integer, default=0)

    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)
    completed_at: Mapped[datetime | None] = mapped_column(DateTime)
