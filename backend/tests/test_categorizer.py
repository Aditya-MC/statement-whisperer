"""Layered categorization and transfer linking against a real (in-memory) database."""

from __future__ import annotations

from datetime import date
from decimal import Decimal
from itertools import count

import pytest
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.categorization.categorizer import (
    apply_user_correction,
    categorize_transactions,
    load_category_index,
)
from app.categorization.transfers import link_transfers
from app.models import (
    Account,
    CategorySource,
    Import,
    ImportStatus,
    MerchantRule,
    RuleSource,
    Transaction,
    TxnType,
)
from app.services.llm import FakeLLMClient, UnavailableLLMClient

_seq = count()


@pytest.fixture
def imp(db: Session, account: Account) -> Import:
    i = Import(account_id=account.id, file_hash="x" * 64, file_type="csv",
               status=ImportStatus.completed, parser_version="test")  # fmt: skip
    db.add(i)
    db.commit()
    return i


def add_txn(db: Session, imp: Import, narration: str, amount: str, d: int = 1,
            account_id: int | None = None) -> Transaction:  # fmt: skip
    amt = Decimal(amount)
    t = Transaction(
        account_id=account_id or imp.account_id, import_id=imp.id, date=date(2024, 1, d),
        amount=amt, type=TxnType.debit if amt < 0 else TxnType.credit, balance=None,
        currency="USD", raw_narration=narration, row_index=next(_seq),
        dedupe_hash=f"h{next(_seq)}",
    )  # fmt: skip
    db.add(t)
    db.flush()
    return t


def path_of(db: Session, t: Transaction) -> str | None:
    if t.category_id is None:
        return None
    idx = load_category_index(db)
    return next(p for p, i in idx.by_path.items() if i == t.category_id)


def test_layers_rule_heuristic_and_llm(db: Session, imp: Import) -> None:
    llm = FakeLLMClient()
    llm.register_merchant("ZENITH WIDGETS", "Shopping > Electronics")
    seed = add_txn(db, imp, "UPI/0012345678/SWIGGY/jdoe@okaxis", "-250.00")
    atm = add_txn(db, imp, "ATM WDL 0012345678 MG ROAD", "-2000.00")
    salary = add_txn(db, imp, "NEFT CR-0012345678-ACME CORP-SALARY", "85000.00")
    person = add_txn(db, imp, "IMPS-0012345678-JOHN Q PUBLIC-SPLIT", "-500.00")
    unknown = add_txn(db, imp, "BIL/ONL/0012345678/ZENITH WIDGETS", "-499.00")

    result = categorize_transactions(db, llm, [seed, atm, salary, person, unknown])

    assert (
        path_of(db, seed) == "Food > Food Delivery" and seed.category_source == CategorySource.rule
    )
    assert path_of(db, atm) == "Cash > ATM Withdrawal"
    assert path_of(db, salary) == "Income > Salary"
    assert path_of(db, person) == "Transfers > Transfer to Others"
    assert path_of(db, unknown) == "Shopping > Electronics"
    assert unknown.category_source == CategorySource.llm
    assert seed.cleaned_merchant == "SWIGGY"
    assert result.llm_merchants == 1 and result.uncategorized == 0

    # Only the one unknown merchant reached the LLM, and no person name did.
    sent = [m.merchant for batch in llm.merchant_calls for m in batch]
    assert sent == ["ZENITH WIDGETS"]


def test_llm_answer_is_cached_as_rule(db: Session, imp: Import) -> None:
    llm = FakeLLMClient()
    llm.register_merchant("ZENITH WIDGETS", "Shopping > Electronics")
    first = add_txn(db, imp, "BIL/ONL/0012345678/ZENITH WIDGETS", "-499.00")
    categorize_transactions(db, llm, [first])
    rule = db.scalar(select(MerchantRule).where(MerchantRule.pattern == "ZENITH WIDGETS"))
    assert rule is not None and rule.source == RuleSource.llm

    second = add_txn(db, imp, "BIL/ONL/0099999999/ZENITH WIDGETS", "-499.00", d=2)
    categorize_transactions(db, llm, [second])
    assert second.category_source == CategorySource.cache
    assert len(llm.merchant_calls) == 1  # no second LLM call


def test_same_merchant_sent_once_per_batch(db: Session, imp: Import) -> None:
    llm = FakeLLMClient()
    rows = [add_txn(db, imp, f"POS XXXX1234 MYSTERY SHOP {i}", "-10.00") for i in range(5)]
    categorize_transactions(db, llm, rows)
    assert [m.merchant for m in llm.merchant_calls[0]] == ["MYSTERY SHOP"]
    assert all(path_of(db, r) == "Other > Uncategorized" for r in rows)
    # "Uncategorized" answers are not cached as rules.
    assert db.scalar(select(MerchantRule).where(MerchantRule.pattern == "MYSTERY SHOP")) is None


def test_llm_unavailable_leaves_rows_uncategorized(db: Session, imp: Import) -> None:
    t = add_txn(db, imp, "POS XXXX1234 MYSTERY SHOP", "-10.00")
    result = categorize_transactions(db, UnavailableLLMClient("no key"), [t])
    assert t.category_id is None
    assert result.llm_error == "no key" and result.uncategorized == 1


def test_credit_from_expense_merchant_is_refund(db: Session, imp: Import) -> None:
    t = add_txn(db, imp, "POS XXXX1234 AMAZON MKTPLACE", "35.00")
    categorize_transactions(db, FakeLLMClient(), [t])
    assert path_of(db, t) == "Income > Refunds"


def test_user_correction_creates_rule_and_applies_to_similar(db: Session, imp: Import) -> None:
    llm = FakeLLMClient()
    a = add_txn(db, imp, "POS XXXX1234 CORNER BAKERY", "-5.00")
    b = add_txn(db, imp, "POS XXXX5678 CORNER BAKERY", "-7.00", d=2)
    categorize_transactions(db, llm, [a, b])
    groceries = load_category_index(db).by_path["Food > Groceries"]

    changed = apply_user_correction(db, a, groceries)
    assert changed == 1
    assert a.category_source == CategorySource.user and path_of(db, a) == "Food > Groceries"
    assert b.category_source == CategorySource.rule and path_of(db, b) == "Food > Groceries"
    rule = db.scalar(select(MerchantRule).where(MerchantRule.pattern == "CORNER BAKERY"))
    assert rule is not None and rule.source == RuleSource.user

    # Future rows use the user rule, ahead of everything else.
    c = add_txn(db, imp, "POS XXXX9999 CORNER BAKERY", "-6.00", d=3)
    categorize_transactions(db, llm, [c])
    assert path_of(db, c) == "Food > Groceries" and c.category_source == CategorySource.rule
    assert a.rules_version is not None and c.rules_version == a.rules_version


def test_user_categories_are_never_overwritten(db: Session, imp: Import) -> None:
    t = add_txn(db, imp, "UPI/0012345678/SWIGGY/jdoe@okaxis", "-250.00")
    travel = load_category_index(db).by_path["Leisure > Travel"]
    apply_user_correction(db, t, travel, apply_to_similar=False)
    db.flush()
    categorize_transactions(db, FakeLLMClient())  # full re-run
    assert path_of(db, t) == "Leisure > Travel" and t.category_source == CategorySource.user


def test_transfers_between_own_accounts(db: Session, imp: Import) -> None:
    savings = Account(bank_name="Other Bank", nickname="Savings", currency="USD")
    db.add(savings)
    db.flush()
    out = add_txn(db, imp, "NEFT DR-0012345678-SELF", "-1000.00", d=5)
    into = add_txn(db, imp, "NEFT CR-0012345678-SELF", "1000.00", d=6, account_id=savings.id)
    unrelated = add_txn(db, imp, "NEFT CR-0012345678-SELF", "1000.00", d=20, account_id=savings.id)

    assert link_transfers(db) == 1
    assert out.is_transfer and into.is_transfer and not unrelated.is_transfer
    assert out.transfer_peer_id == into.id and into.transfer_peer_id == out.id
    assert path_of(db, out) == "Transfers > Self Transfer"
    # Transfers are skipped by the categorizer.
    categorize_transactions(db, FakeLLMClient())
    assert path_of(db, into) == "Transfers > Self Transfer"


def test_no_transfers_with_single_account(db: Session, imp: Import) -> None:
    add_txn(db, imp, "A", "-50.00")
    add_txn(db, imp, "B", "50.00")
    assert link_transfers(db) == 0
