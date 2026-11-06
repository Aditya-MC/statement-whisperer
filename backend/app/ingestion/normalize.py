"""Apply a `ColumnMapping` to every row of a table, producing canonical transactions.

This is deterministic code with no LLM involved. Rows are classified as:

* **transaction**: has an amount and a parseable date.
* **continuation**: only description cells are filled and it follows a transaction. Banks wrap
  long narrations onto extra rows, so its text is appended to the previous transaction.
* **skipped**: no amount (opening-balance lines, repeated headers, page footers), or a
  summary line such as "Total" or "Closing balance". Stated opening/closing balances found
  on such rows are kept for validation.
* **error**: has an amount but the date or amount cannot be parsed. Reported, never dropped
  silently.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from datetime import date, datetime
from decimal import Decimal, InvalidOperation
from typing import Literal

from app.ingestion.loaders import Table
from app.schemas.mapping import ColumnMapping
from app.schemas.report import IssueCollector

DEBIT_WORDS = frozenset({"dr", "d", "db", "debit", "withdrawal", "wd", "out", "dbt", "w"})
CREDIT_WORDS = frozenset({"cr", "c", "credit", "deposit", "dep", "in", "crdt"})

_SUMMARY = re.compile(
    r"\b(total|totals|grand total|closing balance|opening balance|balance b/?f|balance c/?f|"
    r"brought forward|carried forward|statement summary)\b",
    re.IGNORECASE,
)
_SUMMARY_CELL = re.compile(rf"^\s*(?:{_SUMMARY.pattern})\s*:?\s*$", re.IGNORECASE)
_OPENING = re.compile(r"\b(opening balance|balance b/?f|brought forward)\b", re.IGNORECASE)
_CLOSING = re.compile(r"\b(closing balance|balance c/?f|carried forward)\b", re.IGNORECASE)
_DRCR = re.compile(r"(?<![A-Za-z])(dr|cr)(?![A-Za-z])\.?", re.IGNORECASE)
_CURRENCY_SYMBOLS = re.compile(r"[$€£₹¥]")
_ISO_CODE = re.compile(r"(?<![A-Za-z])[A-Za-z]{3}(?![A-Za-z])")
_TRAILING_TIME = re.compile(r"[ T]\d{1,2}:\d{2}(?::\d{2})?(?:\.\d+)?\s*$")
_EMPTY_AMOUNTS = frozenset({"", "-", "--", "—", "–", "nil", "n/a"})  # noqa: RUF001 - em/en dash

#: Formats tried when suggesting a fix for unparseable dates.
CANDIDATE_DATE_FORMATS = [
    "%d/%m/%Y", "%m/%d/%Y", "%Y-%m-%d", "%d-%m-%Y", "%m-%d-%Y", "%d.%m.%Y", "%Y/%m/%d",
    "%d/%m/%y", "%m/%d/%y", "%d-%m-%y", "%d.%m.%y", "%d-%b-%Y", "%d-%b-%y", "%d %b %Y",
    "%d %b %y", "%b %d, %Y", "%d %B %Y", "%B %d, %Y", "%Y%m%d",
]  # fmt: skip


class AmountParseError(ValueError):
    pass


class MappingError(ValueError):
    """The mapping refers to columns that don't exist in the table."""


@dataclass(frozen=True)
class ParsedAmount:
    value: Decimal
    marker: Literal["dr", "cr"] | None


@dataclass
class NormalizedTxn:
    date: date
    amount: Decimal  # signed: negative = money out
    balance: Decimal | None
    raw_narration: str
    row_number: int


@dataclass
class NormalizeResult:
    transactions: list[NormalizedTxn] = field(default_factory=list)
    issues: IssueCollector = field(default_factory=IssueCollector)
    rows_in_file: int = 0
    skipped_rows: int = 0
    continuation_rows: int = 0
    error_rows: int = 0
    stated_opening: Decimal | None = None
    stated_closing: Decimal | None = None
    raw_dates: list[str] = field(default_factory=list)


def parse_amount(raw: str, decimal_sep: str, thousands_sep: str) -> ParsedAmount | None:
    """Parse an amount cell. Returns None for empty cells; raises AmountParseError otherwise.

    Handles currency symbols/codes, Dr/Cr markers, parentheses and trailing-minus negatives,
    and any decimal/thousands separator pair (e.g. 1.234,56 or 1'234.50 or 1,23,456.78).
    """
    s = raw.replace(" ", " ").strip()  # noqa: RUF001 - no-break space
    if s.lower() in _EMPTY_AMOUNTS:
        return None
    marker: Literal["dr", "cr"] | None = None
    m = _DRCR.search(s)
    if m:
        marker = "dr" if m.group(1).lower() == "dr" else "cr"
        s = (s[: m.start()] + s[m.end() :]).strip()
        s = re.sub(r"\(\s*\)", "", s).strip()  # leftover "()" from "(Cr)"
    s = _CURRENCY_SYMBOLS.sub("", s)
    s = _ISO_CODE.sub("", s).strip()

    negative = False
    if s.startswith("(") and s.endswith(")"):
        negative, s = True, s[1:-1].strip()
    if s.endswith("-"):
        negative, s = True, s[:-1].strip()
    if s.startswith("-"):
        negative, s = not negative, s[1:].strip()
    elif s.startswith("+"):
        s = s[1:].strip()

    if thousands_sep:
        s = s.replace(thousands_sep, "")
    s = re.sub(r"\s", "", s)
    if decimal_sep == ",":
        s = s.replace(",", ".")
    if not re.fullmatch(r"\d+(?:\.\d+)?|\.\d+", s):
        raise AmountParseError("not a number")
    try:
        value = Decimal(s)
    except InvalidOperation as exc:  # pragma: no cover - regex already guards this
        raise AmountParseError("not a number") from exc
    return ParsedAmount(-value if negative else value, marker)


def parse_date(raw: str, fmt: str) -> date:
    """Parse with `fmt`, tolerating a trailing time component and extra whitespace."""
    s = " ".join(raw.split())
    try:
        return datetime.strptime(s, fmt).date()
    except ValueError:
        pass
    stripped = _TRAILING_TIME.sub("", s)
    if stripped != s:
        return datetime.strptime(stripped, fmt).date()
    raise ValueError("date does not match format")


def suggest_date_formats(values: list[str]) -> list[str]:
    """Candidate formats that parse every value (used to help the user fix a bad mapping)."""
    values = [v for v in values if v.strip()]
    if not values:
        return []
    ok: list[str] = []
    for fmt in CANDIDATE_DATE_FORMATS:
        try:
            for v in values:
                parse_date(v, fmt)
        except ValueError:
            continue
        ok.append(fmt)
    return ok


def _cell(row: list[str], idx: int | None) -> str:
    if idx is None or idx >= len(row):
        return ""
    return row[idx].strip()


def _signed_amount(row: list[str], m: ColumnMapping) -> Decimal | None:
    """Compute the signed amount for a row, or None if the row carries no amount at all."""
    dec, thou = m.decimal_separator, m.thousands_separator
    if m.amount_mode == "debit_credit":
        debit = parse_amount(_cell(row, m.debit_column), dec, thou)
        credit = parse_amount(_cell(row, m.credit_column), dec, thou)
        if debit is None and credit is None:
            return None
        return (abs(credit.value) if credit else Decimal(0)) - (
            abs(debit.value) if debit else Decimal(0)
        )

    parsed = parse_amount(_cell(row, m.amount_column), dec, thou)
    if parsed is None:
        return None
    if m.amount_mode == "amount_with_type":
        word = _cell(row, m.type_column).lower().rstrip(".")
        if word in DEBIT_WORDS:
            return -abs(parsed.value)
        if word in CREDIT_WORDS:
            return abs(parsed.value)
        raise AmountParseError("unknown debit/credit type")
    # signed
    if parsed.marker == "dr":
        return -abs(parsed.value)
    if parsed.marker == "cr":
        return abs(parsed.value)
    return -parsed.value if m.sign_convention == "positive_is_debit" else parsed.value


def _balance(row: list[str], m: ColumnMapping) -> Decimal | None:
    parsed = parse_amount(_cell(row, m.balance_column), m.decimal_separator, m.thousands_separator)
    if parsed is None:
        return None
    if parsed.marker == "dr":
        return -abs(parsed.value)
    if parsed.marker == "cr":
        return abs(parsed.value)
    return parsed.value


def _column_label(table: Table, idx: int | None) -> str | None:
    if idx is None:
        return None
    return table.header[idx] if idx < len(table.header) else f"Column {idx + 1}"


def _has_any_amount_cell(row: list[str], m: ColumnMapping) -> bool:
    cols = (
        [m.debit_column, m.credit_column] if m.amount_mode == "debit_credit" else [m.amount_column]
    )
    return any(_cell(row, c).lower() not in _EMPTY_AMOUNTS for c in cols)


def check_mapping_fits(table: Table, mapping: ColumnMapping) -> None:
    width = len(table.header)
    bad = [c for c in mapping.referenced_columns() if c >= width]
    if bad:
        raise MappingError(f"Mapping refers to column(s) {bad} but the table has {width} columns")


def normalize(table: Table, mapping: ColumnMapping) -> NormalizeResult:
    check_mapping_fits(table, mapping)
    res = NormalizeResult()
    issues = res.issues
    header_norm = [h.strip().lower() for h in table.header]
    date_label = _column_label(table, mapping.date_column)
    debit_label = _column_label(table, mapping.debit_column)
    credit_label = _column_label(table, mapping.credit_column)
    amount_label = (
        f"{debit_label}/{credit_label}"
        if mapping.amount_mode == "debit_credit"
        else _column_label(table, mapping.amount_column)
    )
    desc_cols = set(mapping.description_columns)

    for offset, row in enumerate(table.body):
        if not any(c.strip() for c in row):
            continue
        res.rows_in_file += 1
        row_no = table.first_row_number + offset

        if table.has_header and [c.strip().lower() for c in row] == header_norm:
            res.skipped_rows += 1  # header repeated on every page of some exports
            continue

        date_raw = _cell(row, mapping.date_column)
        row_text = " ".join(c for c in row if c)
        has_amount = _has_any_amount_cell(row, mapping)

        if not has_amount:
            filled = {i for i, c in enumerate(row) if c.strip()}
            if filled and filled <= desc_cols and not date_raw and res.transactions:
                extra = " ".join(
                    _cell(row, i) for i in mapping.description_columns if _cell(row, i)
                )
                last = res.transactions[-1]
                last.raw_narration = f"{last.raw_narration} {extra}".strip()
                res.continuation_rows += 1
                continue
            res.skipped_rows += 1
            _capture_stated_balance(res, row, mapping, row_text)
            continue

        # Summary lines ("Total", "Closing balance") are skipped when a cell is exactly such a
        # label, or when the line mentions one and has no valid date. A real transaction like
        # "TOTAL GAS STATION" with a proper date is kept.
        if any(_SUMMARY_CELL.match(c) for c in row if c) or (
            _SUMMARY.search(row_text) and not _date_ok(date_raw, mapping)
        ):
            res.skipped_rows += 1
            _capture_stated_balance(res, row, mapping, row_text)
            continue
        if not date_raw:
            res.error_rows += 1
            issues.error("missing_date", "Row has an amount but no date", row_no, date_label)
            continue

        res.raw_dates.append(date_raw)
        row_failed = False
        try:
            txn_date = parse_date(date_raw, mapping.date_format)
        except ValueError:
            issues.error(
                "date_parse",
                f"Date does not match format {mapping.date_format}",
                row_no,
                date_label,
            )
            row_failed = True
        try:
            amount = _signed_amount(row, mapping)
        except AmountParseError as exc:
            issues.error("amount_parse", f"Could not parse amount ({exc})", row_no, amount_label)
            row_failed = True
            amount = None
        try:
            balance = _balance(row, mapping)
        except AmountParseError:
            issues.error(
                "balance_parse",
                "Could not parse balance",
                row_no,
                _column_label(table, mapping.balance_column),
            )
            row_failed = True
            balance = None

        if row_failed or amount is None:
            res.error_rows += 1
            continue

        narration = " ".join(_cell(row, i) for i in mapping.description_columns if _cell(row, i))
        res.transactions.append(
            NormalizedTxn(
                date=txn_date,
                amount=amount,
                balance=balance,
                raw_narration=narration,
                row_number=row_no,
            )
        )
    return res


def _date_ok(raw: str, mapping: ColumnMapping) -> bool:
    try:
        parse_date(raw, mapping.date_format)
        return True
    except ValueError:
        return False


def _capture_stated_balance(
    res: NormalizeResult, row: list[str], mapping: ColumnMapping, row_text: str
) -> None:
    """Remember an explicit opening/closing balance line for cross-checking in validation."""
    is_open, is_close = bool(_OPENING.search(row_text)), bool(_CLOSING.search(row_text))
    if not (is_open or is_close):
        return
    value: Decimal | None = None
    try:
        value = _balance(row, mapping) if mapping.balance_column is not None else None
    except AmountParseError:
        value = None
    if value is None:
        # Fall back to the last amount-looking cell on the line.
        for cell in reversed(row):
            try:
                parsed = parse_amount(cell, mapping.decimal_separator, mapping.thousands_separator)
            except AmountParseError:
                continue
            if parsed is not None:
                value = -abs(parsed.value) if parsed.marker == "dr" else parsed.value
                break
    if value is None:
        return
    if is_open and not res.transactions:
        res.stated_opening = value
    elif is_close and res.transactions:
        res.stated_closing = value
