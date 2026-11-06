from __future__ import annotations

from datetime import date
from decimal import Decimal

from app.ingestion.dedupe import file_sha256, normalize_narration, transaction_hashes
from app.ingestion.normalize import NormalizedTxn


def txn(narr: str, amount: str = "-3.50", bal: str | None = None, d: int = 1) -> NormalizedTxn:
    return NormalizedTxn(
        date=date(2024, 1, d),
        amount=Decimal(amount),
        balance=Decimal(bal) if bal else None,
        raw_narration=narr,
        row_number=1,
    )


def test_identical_rows_get_distinct_hashes() -> None:
    hashes = transaction_hashes(1, [txn("Coffee"), txn("Coffee")])
    assert hashes[0] != hashes[1]


def test_overlapping_statements_produce_same_hashes() -> None:
    a = transaction_hashes(1, [txn("Rent", d=1), txn("Coffee", d=2), txn("Coffee", d=2)])
    b = transaction_hashes(1, [txn("Coffee", d=2), txn("Coffee", d=2), txn("Gym", d=3)])
    assert set(a) & set(b) == set(a[1:])


def test_hash_ignores_cosmetic_narration_and_amount_scale() -> None:
    assert normalize_narration("  POS*Coffee   Shop ") == normalize_narration("pos coffee shop")
    assert transaction_hashes(1, [txn("POS*Coffee", "-3.5")]) == transaction_hashes(
        1, [txn("pos coffee", "-3.5000")]
    )


def test_hash_depends_on_account_and_balance() -> None:
    assert transaction_hashes(1, [txn("A")]) != transaction_hashes(2, [txn("A")])
    assert transaction_hashes(1, [txn("A", bal="1")]) != transaction_hashes(1, [txn("A", bal="2")])


def test_file_hash() -> None:
    assert file_sha256(b"abc") == file_sha256(b"abc") != file_sha256(b"abd")
