"""Duplicate protection at two levels.

* File: SHA-256 of the uploaded bytes. Re-uploading a file that was already imported into the
  same account is rejected.
* Transaction: hash of (account, date, amount, normalized narration, balance, occurrence).
  The occurrence index tells genuinely repeated rows apart, such as two identical coffees on the
  same day in a statement without balances. Because the index is computed per statement, the
  same pair appearing in an overlapping statement produces the same two hashes and is skipped.
"""

from __future__ import annotations

import hashlib
import re
from collections import Counter
from collections.abc import Iterable, Sequence
from decimal import Decimal

from app.ingestion.normalize import NormalizedTxn

_QUANT = Decimal("0.0001")
_NON_ALNUM = re.compile(r"[^a-z0-9]+")


def file_sha256(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def normalize_narration(text: str) -> str:
    """Case/spacing/punctuation-insensitive form, so cosmetic export differences still match."""
    return _NON_ALNUM.sub(" ", text.lower()).strip()


def _money(value: Decimal | None) -> str:
    return "" if value is None else format(value.quantize(_QUANT), "f")


def transaction_hashes(account_id: int, txns: Sequence[NormalizedTxn]) -> list[str]:
    seen: Counter[str] = Counter()
    hashes: list[str] = []
    for t in txns:
        base = "|".join(
            [
                str(account_id),
                t.date.isoformat(),
                _money(t.amount),
                normalize_narration(t.raw_narration),
                _money(t.balance),
            ]
        )
        occurrence = seen[base]
        seen[base] += 1
        hashes.append(hashlib.sha256(f"{base}|{occurrence}".encode()).hexdigest())
    return hashes


def chunked(items: Sequence[str], size: int = 500) -> Iterable[Sequence[str]]:
    for i in range(0, len(items), size):
        yield items[i : i + size]
