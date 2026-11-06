"""Request/response models for the HTTP API."""

from __future__ import annotations

from datetime import date, datetime
from decimal import Decimal
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator

from app.models import CategoryKind, CategorySource, ImportStatus, RuleSource, TxnType


class AccountCreate(BaseModel):
    bank_name: str = Field(min_length=1, max_length=100)
    nickname: str = Field(min_length=1, max_length=100)
    currency: str = Field(min_length=3, max_length=3)
    last4: str | None = Field(
        default=None,
        description="Last four digits only. Full account numbers are rejected and never stored.",
    )

    @field_validator("currency")
    @classmethod
    def _upper(cls, v: str) -> str:
        if not v.isalpha():
            raise ValueError("currency must be a 3-letter ISO 4217 code")
        return v.upper()

    @field_validator("last4")
    @classmethod
    def _last4(cls, v: str | None) -> str | None:
        if v is None or v == "":
            return None
        if not (len(v) == 4 and v.isdigit()):
            raise ValueError("last4 must be exactly 4 digits (never the full account number)")
        return v


class AccountOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    bank_name: str
    nickname: str
    currency: str
    last4: str | None
    created_at: datetime


class ImportOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    account_id: int
    status: ImportStatus
    file_type: str
    parser_version: str
    mapping_source: str | None
    mapping: dict[str, Any] | None
    columns: list[str] | None
    validation: dict[str, Any] | None
    error_message: str | None
    date_from: date | None
    date_to: date | None
    opening_balance: Decimal | None
    closing_balance: Decimal | None
    row_count: int
    inserted_count: int
    duplicate_count: int
    created_at: datetime
    completed_at: datetime | None


class TransactionOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    account_id: int
    import_id: int
    date: date
    amount: Decimal
    type: TxnType
    balance: Decimal | None
    currency: str
    raw_narration: str
    cleaned_merchant: str | None
    category_id: int | None
    category_source: CategorySource | None
    rules_version: int | None
    is_transfer: bool
    transfer_peer_id: int | None
    transfer_dismissed: bool


class TransactionPage(BaseModel):
    total: int
    items: list[TransactionOut]


class TransactionUpdate(BaseModel):
    """Manual correction. `category_id` sets the category (and saves a merchant rule);
    `is_transfer=false` unlinks a detected transfer pair."""

    category_id: int | None = None
    apply_to_similar: bool = Field(
        default=True,
        description="Also apply the category to other non-manual rows with the same merchant.",
    )
    is_transfer: Literal[False] | None = None


class TransactionUpdateOut(BaseModel):
    transaction: TransactionOut
    updated_similar: int


class CategorizeRequest(BaseModel):
    account_id: int | None = None
    only_uncategorized: bool = Field(
        default=False,
        description="Only rows with no category yet. Otherwise every non-manual row is redone.",
    )


class CategorizeOut(BaseModel):
    processed: int
    by_source: dict[str, int]
    llm_merchants: int
    uncategorized: int
    llm_error: str | None
    transfers_linked: int


class MerchantRuleOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    pattern: str
    category_id: int
    source: RuleSource
    priority: int
    created_at: datetime


class CategoryOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    name: str
    parent_id: int | None
    kind: CategoryKind


class ErrorOut(BaseModel):
    detail: str
    existing_import_id: int | None = None
