"""The column mapping: how a statement's layout maps onto the canonical schema.

The LLM produces one of these from a small masked sample; plain code then applies it to every
row. Users can also edit it in the review UI and re-run the import with their version.
"""

from __future__ import annotations

from typing import Literal, Self

from pydantic import BaseModel, Field, field_validator, model_validator

AmountMode = Literal["signed", "debit_credit", "amount_with_type"]
SignConvention = Literal["negative_is_debit", "positive_is_debit"]


class ColumnMapping(BaseModel):
    """Column indexes are 0-based positions in the header row."""

    date_column: int = Field(ge=0, description="Transaction (posting) date column.")
    description_columns: list[int] = Field(
        min_length=1,
        description="Narration column(s). Several are joined with a space, in the given order.",
    )
    amount_mode: AmountMode = Field(
        description=(
            "signed: one amount column, sign gives direction. "
            "debit_credit: separate debit (money out) and credit (money in) columns. "
            "amount_with_type: one unsigned amount column plus a column saying debit/credit."
        )
    )
    amount_column: int | None = Field(default=None, ge=0)
    debit_column: int | None = Field(default=None, ge=0)
    credit_column: int | None = Field(default=None, ge=0)
    type_column: int | None = Field(default=None, ge=0)
    balance_column: int | None = Field(default=None, ge=0)

    date_format: str = Field(description="Python strptime format, e.g. %d/%m/%Y.")
    decimal_separator: Literal[".", ","] = "."
    thousands_separator: Literal[",", ".", " ", "'", ""] = ","
    currency: str = Field(min_length=3, max_length=3, description="ISO 4217 code.")
    sign_convention: SignConvention = Field(
        default="negative_is_debit",
        description="Only for amount_mode=signed with no Dr/Cr markers.",
    )
    drcr_markers: bool = Field(
        default=False,
        description="True if amounts/balances carry Dr/Cr markers, e.g. '1,200.00 Dr'.",
    )

    @field_validator("currency")
    @classmethod
    def _upper_currency(cls, v: str) -> str:
        return v.upper()

    @field_validator("date_format")
    @classmethod
    def _check_date_format(cls, v: str) -> str:
        if "%" not in v or len(v) > 40:
            raise ValueError("date_format must be a strptime format such as %d/%m/%Y")
        return v

    @model_validator(mode="after")
    def _check_mode_columns(self) -> Self:
        if self.decimal_separator == self.thousands_separator:
            raise ValueError("decimal and thousands separators must differ")
        if self.amount_mode == "signed" and self.amount_column is None:
            raise ValueError("amount_mode=signed requires amount_column")
        if self.amount_mode == "debit_credit" and (
            self.debit_column is None or self.credit_column is None
        ):
            raise ValueError("amount_mode=debit_credit requires debit_column and credit_column")
        if self.amount_mode == "amount_with_type" and (
            self.amount_column is None or self.type_column is None
        ):
            raise ValueError("amount_mode=amount_with_type requires amount_column and type_column")
        return self

    def referenced_columns(self) -> list[int]:
        cols = [self.date_column, *self.description_columns]
        for c in (
            self.amount_column,
            self.debit_column,
            self.credit_column,
            self.type_column,
            self.balance_column,
        ):
            if c is not None:
                cols.append(c)
        return cols


class LLMColumnMapping(ColumnMapping):
    """What the LLM returns: the mapping plus a short free-text note (never stored with data)."""

    notes: str = Field(default="", max_length=500)

    def to_mapping(self) -> ColumnMapping:
        return ColumnMapping.model_validate(self.model_dump(exclude={"notes"}))
