"""Validate a normalized statement before anything is written to the ledger.

Checks:

1. Every row is accounted for: transactions + skipped + continuation + error rows equals the
   number of non-blank rows, so nothing is dropped silently.
2. No date or amount parse errors (these come from normalization).
3. Running-balance chain: for consecutive rows that carry a balance, the previous balance plus
   the amounts in between equals the next balance. This works for statements that print a
   balance on every row or only at the end of each day.
4. Statement order (oldest-first or newest-first) is detected from the balance chain, or from
   the dates when there is no balance column.
5. opening + credits - debits == closing, plus agreement with any explicitly stated
   "Opening balance" / "Closing balance" lines.
"""

from __future__ import annotations

from datetime import date, timedelta
from decimal import Decimal
from itertools import pairwise

from app.ingestion.normalize import NormalizedTxn, NormalizeResult, suggest_date_formats
from app.schemas.report import IssueCollector, ReportStats, ValidationReport

BALANCE_TOLERANCE = Decimal("0.005")


def _chain_mismatches(txns: list[NormalizedTxn]) -> list[NormalizedTxn]:
    """Rows (in the given order) whose balance doesn't follow from the previous balance."""
    bad: list[NormalizedTxn] = []
    running: Decimal | None = None
    for t in txns:
        if running is not None:
            running += t.amount
        if t.balance is not None:
            if running is not None and abs(running - t.balance) > BALANCE_TOLERANCE:
                bad.append(t)
            running = t.balance  # resync so one bad row yields one issue, not a cascade
    return bad


def _dates_sorted(txns: list[NormalizedTxn], reverse: bool = False) -> bool:
    pairs = pairwise(t.date for t in txns)
    return all((b <= a) if reverse else (a <= b) for a, b in pairs)


def order_chronologically(
    txns: list[NormalizedTxn], issues: IssueCollector | None = None
) -> tuple[list[NormalizedTxn], str]:
    """Return transactions oldest-first and the detected source order."""
    if len(txns) < 2:
        return list(txns), "chronological"
    has_balances = sum(1 for t in txns if t.balance is not None) >= 2
    if has_balances:
        fwd = len(_chain_mismatches(txns))
        rev = len(_chain_mismatches(list(reversed(txns))))
        if rev < fwd or (
            rev == fwd and _dates_sorted(txns, reverse=True) and not _dates_sorted(txns)
        ):
            return list(reversed(txns)), "reverse"
        return list(txns), "chronological"
    if _dates_sorted(txns):
        return list(txns), "chronological"
    if _dates_sorted(txns, reverse=True):
        return list(reversed(txns)), "reverse"
    if issues is not None:
        issues.warn("unsorted_dates", "Transactions are not in date order; keeping file order")
    return list(txns), "chronological"


def validate(result: NormalizeResult, *, today: date | None = None) -> ValidationReport:
    issues = result.issues
    txns = result.transactions
    stats = ReportStats(
        rows_in_file=result.rows_in_file,
        transactions=len(txns),
        skipped_rows=result.skipped_rows,
        continuation_rows=result.continuation_rows,
        error_rows=result.error_rows,
    )

    accounted = len(txns) + result.skipped_rows + result.continuation_rows + result.error_rows
    if accounted != result.rows_in_file:  # defensive: indicates a bug in normalization
        issues.error(
            "row_accounting",
            f"{result.rows_in_file} rows read but {accounted} accounted for",
        )

    if not txns and not issues.has_errors:
        issues.error("no_transactions", "No transactions found with this mapping")

    if txns and result.skipped_rows > len(txns):
        issues.warn(
            "many_skipped",
            f"{result.skipped_rows} rows were skipped vs {len(txns)} transactions; "
            "check the amount column mapping",
        )

    chrono, order = order_chronologically(txns, issues)
    stats.order = order  # type: ignore[assignment]

    if chrono:
        stats.date_from = min(t.date for t in chrono)
        stats.date_to = max(t.date for t in chrono)
        stats.total_credits = sum((t.amount for t in chrono if t.amount > 0), Decimal(0))
        stats.total_debits = -sum((t.amount for t in chrono if t.amount < 0), Decimal(0))
        horizon = (today or date.today()) + timedelta(days=1)
        if stats.date_to > horizon:
            issues.warn("future_dates", "Some transactions are dated in the future")

    balanced = [t for t in chrono if t.balance is not None]
    if chrono and not balanced:
        issues.warn(
            "no_balance",
            "No running balance column: balance checks were skipped",
        )
    elif balanced:
        for t in _chain_mismatches(chrono):
            issues.error(
                "balance_mismatch",
                "Running balance does not match previous balance plus this amount",
                t.row_number,
            )
        first = balanced[0]
        idx_first = chrono.index(first)
        opening = first.balance - sum((t.amount for t in chrono[: idx_first + 1]), Decimal(0))  # type: ignore[operator]
        last = balanced[-1]
        idx_last = chrono.index(last)
        closing = last.balance + sum((t.amount for t in chrono[idx_last + 1 :]), Decimal(0))  # type: ignore[operator]
        stats.opening_balance, stats.closing_balance = opening, closing

        net = stats.total_credits - stats.total_debits
        if abs(opening + net - closing) > BALANCE_TOLERANCE and not issues.counts.get(
            "balance_mismatch"
        ):
            issues.error(
                "balance_identity",
                "Opening balance + credits - debits does not equal closing balance",
            )
        if (
            result.stated_opening is not None
            and abs(result.stated_opening - opening) > BALANCE_TOLERANCE
        ):
            issues.error(
                "stated_opening_mismatch",
                "Stated opening balance differs from the one implied by the transactions",
            )
        if (
            result.stated_closing is not None
            and abs(result.stated_closing - closing) > BALANCE_TOLERANCE
        ):
            issues.error(
                "stated_closing_mismatch",
                "Stated closing balance differs from the last running balance",
            )

    suggestions: dict[str, list[str]] = {}
    if issues.counts.get("date_parse"):
        suggestions["date_format"] = suggest_date_formats(result.raw_dates)

    return ValidationReport(
        ok=not issues.has_errors,
        errors=issues.errors,
        warnings=issues.warnings,
        issue_counts=dict(issues.counts),
        stats=stats,
        suggestions=suggestions,
    )
