"""Shared column types and helpers."""

from __future__ import annotations

from datetime import UTC, datetime

from sqlalchemy import Numeric

#: Money column: 18 digits, 4 decimal places (covers 0/2/3-decimal currencies exactly).
Money = Numeric(18, 4, asdecimal=True)


def utcnow() -> datetime:
    return datetime.now(UTC).replace(tzinfo=None)
