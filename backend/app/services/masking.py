"""Masking applied to everything before it leaves the machine.

Two entry points:

* `build_masked_sample` makes the schema-inference sample. Free text such as narrations,
  names and addresses is replaced with a `<text:N>` placeholder. Short Dr/Cr-style type words,
  dates and amounts are kept because the LLM needs them to infer formats. Long digit runs such as
  account, card and reference numbers are masked even when they look numeric.
* `mask_free_text` is for strings that must keep their meaning, such as merchant names for
  categorization (Phase 2). It masks emails, UPI handles, phone/account/card numbers and
  long digit runs.

The `MaskedSample` type is the only input `services.llm` accepts for schema inference. That
makes it hard to send unmasked rows by accident.
"""

from __future__ import annotations

import re
from dataclasses import dataclass

#: Words that indicate a debit/credit type column. Kept verbatim in samples.
TYPE_WORDS = frozenset(
    {
        "dr", "cr", "d", "c", "db", "debit", "credit", "deposit", "withdrawal",
        "dr.", "cr.", "debit.", "credit.", "dep", "wd", "in", "out",
    }
)  # fmt: skip

_EMAIL = re.compile(r"[\w.+-]+@[\w-]+\.[\w.]+")
_UPI = re.compile(r"\b[\w.-]{2,}@[a-zA-Z]{2,}\b")
_DIGIT_RUN = re.compile(r"\d[\d\s-]{2,}\d")  # 4+ digits, possibly spaced/dashed (cards, phones)
_MASKED_DIGITS = re.compile(r"[Xx*]{2,}\d{2,4}")  # e.g. XXXX1234, ****5678

# A cell that is a plain amount: optional sign/currency/parentheses/Dr-Cr marker.
_AMOUNT = re.compile(
    r"""^\s*
    (?:[-+(]\s*)?
    (?:[A-Z]{3}\s*|[$€£₹¥]\s*)?
    [-+]?\d{1,3}(?:[.,'\s]?\d{3})*(?:[.,]\d{1,4})?
    \s*\)?
    \s*(?:-|\(?\s*(?:dr|cr)\.?\s*\)?)?
    \s*$""",
    re.IGNORECASE | re.VERBOSE,
)
_PLAIN_DIGITS = re.compile(r"^\s*\d+\s*$")
_ISO_CURRENCY = re.compile(r"^[A-Z]{3}$")  # e.g. a "Currency" column holding AUD

_MONTHS = r"jan|feb|mar|apr|may|jun|jul|aug|sep|sept|oct|nov|dec"
_DATE = re.compile(
    rf"""^\s*(?:
        \d{{1,4}}[-/.]\d{{1,2}}[-/.]\d{{1,4}}                       # 05/01/2024, 2024-01-05
      | \d{{1,2}}[-\s/.]?(?:{_MONTHS})[a-z]*[-\s/.,]*\d{{2,4}}        # 05 Jan 2024, 5-Jan-24
      | (?:{_MONTHS})[a-z]*[-\s/.]?\d{{1,2}},?[-\s/.]?\d{{2,4}}       # Jan 05, 2024
    )(?:[ T]\d{{1,2}}:\d{{2}}(?::\d{{2}})?)?\s*$""",
    re.IGNORECASE | re.VERBOSE,
)


def is_date_like(value: str) -> bool:
    return bool(_DATE.match(value))


def is_amount_like(value: str) -> bool:
    return bool(_AMOUNT.match(value)) and any(ch.isdigit() for ch in value)


def mask_free_text(text: str) -> str:
    """Mask identifiers inside free text while keeping the words (for merchant strings)."""
    text = _EMAIL.sub("<email>", text)
    text = _UPI.sub("<upi>", text)
    text = _MASKED_DIGITS.sub("<num>", text)
    text = _DIGIT_RUN.sub("<num>", text)
    return text


def mask_cell(value: str) -> str:
    """Mask one sample cell. See the module docstring for the policy."""
    v = value.strip()
    if not v:
        return ""
    if v.lower() in TYPE_WORDS or _ISO_CURRENCY.match(v):
        return v
    if is_date_like(v):
        return v
    if _PLAIN_DIGITS.match(v):
        # Bare integers of 7+ digits are account/reference/cheque numbers, not amounts.
        digits = len(v)
        return v if digits <= 6 else f"<digits:{digits}>"
    if is_amount_like(v):
        # Real amounts rarely exceed 14 digits; longer "amounts" are grouped identifiers.
        return v if sum(ch.isdigit() for ch in v) <= 14 else "<number>"
    return f"<text:{len(v)}>"


def mask_header(value: str) -> str:
    """Headers are kept (they describe columns, not people) apart from any embedded identifiers."""
    return mask_free_text(value.strip())[:60]


@dataclass(frozen=True)
class MaskedSample:
    """A masked header plus a few masked data rows, ready to send for schema inference."""

    header: tuple[str, ...]
    rows: tuple[tuple[str, ...], ...]


@dataclass(frozen=True)
class MaskedMerchant:
    """A cleaned merchant name with identifiers masked, ready to send for categorization."""

    id: int
    merchant: str
    direction: str  # "debit" | "credit"
    hints: tuple[str, ...] = ()


def build_masked_merchant(
    id: int, merchant: str, direction: str, hints: tuple[str, ...] = ()
) -> MaskedMerchant:
    """Mask identifiers in a cleaned merchant name.

    Callers must not pass person names: `categorization.merchant` flags person-to-person
    payments, and the categorizer never sends those.
    """
    masked = mask_free_text(merchant)[:60]
    return MaskedMerchant(id=id, merchant=masked, direction=direction, hints=hints)


def build_masked_sample(
    header: list[str], rows: list[list[str]], max_rows: int = 10
) -> MaskedSample:
    """Build the schema-inference sample from at most `max_rows` data rows."""
    width = len(header)
    chosen = [r for r in rows if any(c.strip() for c in r)][:max_rows]
    masked_rows = tuple(
        tuple(mask_cell(r[i]) if i < len(r) else "" for i in range(width)) for r in chosen
    )
    return MaskedSample(header=tuple(mask_header(h) for h in header), rows=masked_rows)
