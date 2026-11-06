"""Validation report returned by the API and stored on each import.

Issues reference file row numbers and column labels only. They never include cell values, so
the report is safe to store and log.
"""

from __future__ import annotations

from datetime import date
from decimal import Decimal
from typing import Literal

from pydantic import BaseModel, Field

Severity = Literal["error", "warning"]

#: Cap per issue code so a wholly wrong mapping doesn't produce thousands of entries.
MAX_ISSUES_PER_CODE = 25


class Issue(BaseModel):
    severity: Severity
    code: str
    message: str
    row: int | None = None
    column: str | None = None


class ReportStats(BaseModel):
    rows_in_file: int = 0
    transactions: int = 0
    skipped_rows: int = 0
    continuation_rows: int = 0
    error_rows: int = 0
    total_credits: Decimal = Decimal("0")
    total_debits: Decimal = Decimal("0")
    opening_balance: Decimal | None = None
    closing_balance: Decimal | None = None
    date_from: date | None = None
    date_to: date | None = None
    order: Literal["chronological", "reverse"] | None = None


class ValidationReport(BaseModel):
    ok: bool
    errors: list[Issue] = Field(default_factory=list)
    warnings: list[Issue] = Field(default_factory=list)
    issue_counts: dict[str, int] = Field(default_factory=dict)
    stats: ReportStats = Field(default_factory=ReportStats)
    suggestions: dict[str, list[str]] = Field(default_factory=dict)


class IssueCollector:
    """Accumulates issues, capping how many of each code are kept while counting all of them."""

    def __init__(self) -> None:
        self.errors: list[Issue] = []
        self.warnings: list[Issue] = []
        self.counts: dict[str, int] = {}

    def add(
        self,
        severity: Severity,
        code: str,
        message: str,
        row: int | None = None,
        column: str | None = None,
    ) -> None:
        self.counts[code] = self.counts.get(code, 0) + 1
        if self.counts[code] > MAX_ISSUES_PER_CODE:
            return
        issue = Issue(severity=severity, code=code, message=message, row=row, column=column)
        (self.errors if severity == "error" else self.warnings).append(issue)

    def error(
        self, code: str, message: str, row: int | None = None, column: str | None = None
    ) -> None:
        self.add("error", code, message, row, column)

    def warn(
        self, code: str, message: str, row: int | None = None, column: str | None = None
    ) -> None:
        self.add("warning", code, message, row, column)

    @property
    def has_errors(self) -> bool:
        return bool(self.errors)
