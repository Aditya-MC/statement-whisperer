"""Layered transaction categorizer.

For each transaction (never one the user categorized by hand):

1. **Merchant cleanup**: `clean_merchant(raw_narration)` gives a short merchant name, stored
   in `cleaned_merchant`.
2. **User rules** (`merchant_rules.source = user`, highest priority).
3. **Built-in hints**: ATM withdrawals, SALARY/INTEREST/REFUND credits, EMI/SIP/RENT/fee
   debits.
4. **Seed rules**: curated brand patterns such as SWIGGY -> Food Delivery.
5. **Cache**: earlier LLM answers, stored as `merchant_rules.source = llm`.
6. **People**: person-to-person payments become Transfer to Others and are never sent to the
   LLM. This runs after brand rules, so a truncated "VODAFONE IDEA" still matches VODAFONE.
7. **LLM**: the remaining unique merchants are sent in one batched request with the fixed
   category list. Answers are cached as rules for next time.

A rule matches when its words appear as a contiguous run in the merchant name. Higher priority
wins, then the longer pattern. Money coming in from an expense-type merchant (e.g. AMAZON) is
recorded as Income > Refunds.

`rules_version` on each transaction is the highest `merchant_rules.id` at the time it was
categorized. Corrections replace a rule (new id), so a stale version shows a re-run would use
newer rules.
"""

from __future__ import annotations

import logging
from collections import Counter, defaultdict
from collections.abc import Sequence
from dataclasses import dataclass, field

from sqlalchemy import ColumnElement, func, or_, select
from sqlalchemy.orm import Session

from app.categorization.merchant import CleanMerchant, clean_merchant
from app.models import (
    Account,
    Category,
    CategoryKind,
    CategorySource,
    MerchantRule,
    RuleSource,
    Transaction,
)
from app.services.llm import UNCATEGORIZED, LLMClient, LLMError
from app.services.masking import build_masked_merchant

log = logging.getLogger(__name__)

PRIORITY_USER = 100
PRIORITY_LLM = 10
PRIORITY_SEED = 0

REFUNDS = "Income > Refunds"
SELF_TRANSFER = "Transfers > Self Transfer"
TRANSFER_TO_OTHERS = "Transfers > Transfer to Others"


@dataclass
class CategoryIndex:
    """Lookup between leaf category paths ("Food > Groceries") and ids."""

    by_path: dict[str, int]
    by_id: dict[int, Category]

    @property
    def leaf_paths(self) -> list[str]:
        return sorted(self.by_path)

    def kind(self, category_id: int) -> CategoryKind:
        return self.by_id[category_id].kind


def load_category_index(db: Session, user_id: int | None = None) -> CategoryIndex:
    """Built-in categories plus `user_id`'s own (only built-ins when user_id is None)."""
    visible: ColumnElement[bool] = Category.user_id.is_(None)
    if user_id is not None:
        visible = or_(visible, Category.user_id == user_id)
    cats = list(db.scalars(select(Category).where(visible)))
    by_id = {c.id: c for c in cats}
    by_path = {
        f"{by_id[c.parent_id].name} > {c.name}": c.id for c in cats if c.parent_id is not None
    }
    return CategoryIndex(by_path=by_path, by_id=by_id)


@dataclass(frozen=True)
class _Rule:
    id: int
    words: tuple[str, ...]
    category_id: int
    source: RuleSource
    priority: int


def _load_rules(db: Session, user_id: int | None) -> list[_Rule]:
    """Shared seed rules plus `user_id`'s own corrections and cached LLM answers."""
    visible: ColumnElement[bool] = MerchantRule.user_id.is_(None)
    if user_id is not None:
        visible = or_(visible, MerchantRule.user_id == user_id)
    rules = [
        _Rule(r.id, tuple(r.pattern.upper().split()), r.category_id, r.source, r.priority)
        for r in db.scalars(select(MerchantRule).where(visible))
    ]
    return sorted(rules, key=lambda r: (-r.priority, -len(r.words), r.id))


def _contains(haystack: tuple[str, ...], needle: tuple[str, ...]) -> bool:
    n = len(needle)
    return n > 0 and any(haystack[i : i + n] == needle for i in range(len(haystack) - n + 1))


def match_rule(
    rules: Sequence[_Rule],
    merchant: str,
    *,
    min_priority: int | None = None,
    max_priority: int | None = None,
) -> _Rule | None:
    words = tuple(merchant.upper().split())
    for r in rules:
        if min_priority is not None and r.priority < min_priority:
            continue
        if max_priority is not None and r.priority > max_priority:
            continue
        if _contains(words, r.words):
            return r
    return None


def current_rules_version(db: Session) -> int:
    return int(db.scalar(select(func.max(MerchantRule.id))) or 0)


def heuristic_category(clean: CleanMerchant, is_credit: bool) -> str | None:
    """Category paths implied by the narration itself, without any rule or LLM."""
    kw = clean.keywords
    if clean.is_atm and not is_credit:
        return "Cash > ATM Withdrawal"
    if is_credit:
        if kw & {"SALARY", "SAL", "PAYROLL"}:
            return "Income > Salary"
        if kw & {"INTEREST", "DIVIDEND"}:
            return "Income > Interest"
        if kw & {"REFUND", "REVERSAL", "CASHBACK"}:
            return REFUNDS
    else:
        if kw & {"EMI", "LOAN"}:
            return "Financial > Loan EMI"
        if "SIP" in kw:
            return "Financial > Investments"
        if "RENT" in kw:
            return "Housing > Rent"
        if kw & {"INSURANCE", "PREMIUM"}:
            return "Bills > Insurance"
        if "TAX" in kw:
            return "Financial > Taxes"
        if kw & {"FEE", "FEES", "CHARGES", "CHARGE", "GST"}:
            return "Financial > Bank Fees"
    return None


@dataclass
class CategorizeResult:
    processed: int = 0
    by_source: Counter[str] = field(default_factory=Counter)
    llm_merchants: int = 0
    uncategorized: int = 0
    llm_error: str | None = None

    def as_dict(self) -> dict[str, object]:
        return {
            "processed": self.processed,
            "by_source": dict(self.by_source),
            "llm_merchants": self.llm_merchants,
            "uncategorized": self.uncategorized,
            "llm_error": self.llm_error,
        }


class _Assigner:
    def __init__(self, idx: CategoryIndex, version: int, result: CategorizeResult) -> None:
        self.idx, self.version, self.result = idx, version, result

    def assign(self, txn: Transaction, category_id: int, source: CategorySource) -> None:
        # Money in from an expense-type merchant is a refund, not spending.
        if txn.amount > 0 and self.idx.kind(category_id) == CategoryKind.expense:
            refunds = self.idx.by_path.get(REFUNDS)
            if refunds is not None and category_id != self.idx.by_path.get(UNCATEGORIZED):
                category_id = refunds
        txn.category_id = category_id
        txn.category_source = source
        txn.rules_version = self.version
        self.result.by_source[source.value] += 1


def _target_query(user_id: int, account_id: int | None, only_uncategorized: bool):  # type: ignore[no-untyped-def]
    stmt = select(Transaction).where(
        Transaction.account_id.in_(select(Account.id).where(Account.user_id == user_id)),
        Transaction.is_transfer.is_(False),
        or_(
            Transaction.category_source.is_(None),
            Transaction.category_source != CategorySource.user,
        ),
    )
    if account_id is not None:
        stmt = stmt.where(Transaction.account_id == account_id)
    if only_uncategorized:
        stmt = stmt.where(Transaction.category_id.is_(None))
    return stmt.order_by(Transaction.id)


def categorize_transactions(
    db: Session,
    llm: LLMClient,
    txns: Sequence[Transaction] | None = None,
    *,
    user_id: int | None = None,
    account_id: int | None = None,
    only_uncategorized: bool = False,
) -> CategorizeResult:
    """Categorize `txns` (or all of `user_id`'s eligible transactions). Flushes, no commit.

    Uses the owner's rules and categories only. When `txns` is given, the owner is taken from
    their account, and they must all belong to one user.
    """
    if txns is None:
        if user_id is None:
            raise ValueError("user_id is required when no transactions are given")
        txns = list(db.scalars(_target_query(user_id, account_id, only_uncategorized)))
    elif user_id is None and txns:
        owners = set(
            db.scalars(select(Account.user_id).where(Account.id.in_({t.account_id for t in txns})))
        )
        if len(owners) != 1:
            raise ValueError("transactions from several users can't be categorized together")
        user_id = owners.pop()
    txns = [t for t in txns if t.category_source != CategorySource.user and not t.is_transfer]

    idx = load_category_index(db, user_id)
    rules = _load_rules(db, user_id)
    result = CategorizeResult(processed=len(txns))
    assigner = _Assigner(idx, current_rules_version(db), result)
    pending: dict[str, list[Transaction]] = defaultdict(list)
    pending_info: dict[str, tuple[str, tuple[str, ...]]] = {}

    for t in txns:
        clean = clean_merchant(t.raw_narration)
        t.cleaned_merchant = clean.merchant
        is_credit = t.amount > 0

        user_rule = match_rule(rules, clean.merchant, min_priority=PRIORITY_USER)
        if user_rule is not None:
            assigner.assign(t, user_rule.category_id, CategorySource.rule)
            continue
        path = heuristic_category(clean, is_credit)
        if path is not None and path in idx.by_path:
            assigner.assign(t, idx.by_path[path], CategorySource.rule)
            continue
        rule = match_rule(rules, clean.merchant, max_priority=PRIORITY_USER - 1)
        # A cached income category says nothing about money going *out* to that merchant.
        if rule is not None and not (
            not is_credit and idx.kind(rule.category_id) == CategoryKind.income
        ):
            source = CategorySource.cache if rule.source == RuleSource.llm else CategorySource.rule
            assigner.assign(t, rule.category_id, source)
            continue
        # Payments to people: after brand rules (so "VODAFONE IDEA" isn't mistaken for a
        # person) and never sent to the LLM.
        if clean.is_person and TRANSFER_TO_OTHERS in idx.by_path:
            assigner.assign(t, idx.by_path[TRANSFER_TO_OTHERS], CategorySource.rule)
            continue
        if clean.merchant == "UNKNOWN":
            t.category_id, t.category_source = None, None  # nothing useful to send
            continue
        key = f"{clean.merchant}|{'credit' if is_credit else 'debit'}"
        pending[key].append(t)
        pending_info[key] = (clean.merchant, tuple(sorted(clean.keywords)))

    if pending:
        _categorize_with_llm(db, llm, idx, rules, pending, pending_info, assigner, user_id)

    result.uncategorized = sum(1 for t in txns if t.category_id is None)
    db.flush()
    return result


def _categorize_with_llm(
    db: Session,
    llm: LLMClient,
    idx: CategoryIndex,
    rules: list[_Rule],
    pending: dict[str, list[Transaction]],
    pending_info: dict[str, tuple[str, tuple[str, ...]]],
    assigner: _Assigner,
    user_id: int | None,
) -> None:
    keys = list(pending)
    masked = [
        build_masked_merchant(i, pending_info[k][0], k.rsplit("|", 1)[1], pending_info[k][1])
        for i, k in enumerate(keys)
    ]
    try:
        answers = llm.categorize_merchants(masked, idx.leaf_paths)
    except LLMError as exc:
        assigner.result.llm_error = str(exc)
        log.warning("LLM categorization unavailable: %s", exc)
        for k in keys:
            for t in pending[k]:
                t.category_id, t.category_source = None, None
        return

    assigner.result.llm_merchants = len(keys)
    existing_patterns = {" ".join(r.words) for r in rules}
    uncategorized_id = idx.by_path.get(UNCATEGORIZED)
    for i, k in enumerate(keys):
        path = answers.get(i, UNCATEGORIZED)
        category_id = idx.by_path.get(path, uncategorized_id)
        if category_id is None:
            continue
        for t in pending[k]:
            assigner.assign(t, category_id, CategorySource.llm)
        merchant = pending_info[k][0]
        # Cache real answers as rules; "Uncategorized" is not worth remembering.
        if path != UNCATEGORIZED and merchant not in existing_patterns:
            db.add(
                MerchantRule(
                    user_id=user_id,  # cached answers stay private to their user
                    pattern=merchant,
                    category_id=category_id,
                    source=RuleSource.llm,
                    priority=PRIORITY_LLM,
                )
            )
            existing_patterns.add(merchant)


def apply_user_correction(
    db: Session, txn: Transaction, category_id: int, *, apply_to_similar: bool = True
) -> int:
    """Set a category by hand, remember it as a user rule, and optionally apply it to other
    non-user transactions with the same merchant. Returns how many other rows changed."""
    user_id = db.scalar(select(Account.user_id).where(Account.id == txn.account_id))
    merchant = txn.cleaned_merchant or clean_merchant(txn.raw_narration).merchant
    txn.cleaned_merchant = merchant
    txn.category_id = category_id
    txn.category_source = CategorySource.user

    if merchant == "UNKNOWN":
        txn.rules_version = current_rules_version(db)
        db.flush()
        return 0

    # Replace this user's own rule for the merchant (never a shared seed rule).
    old = db.scalar(
        select(MerchantRule).where(
            MerchantRule.user_id == user_id, MerchantRule.pattern == merchant
        )
    )
    if old is not None:
        db.delete(old)
        db.flush()
    db.add(
        MerchantRule(
            user_id=user_id,
            pattern=merchant,
            category_id=category_id,
            source=RuleSource.user,
            priority=PRIORITY_USER,
        )
    )
    db.flush()
    version = current_rules_version(db)
    txn.rules_version = version

    changed = 0
    assigner = _Assigner(load_category_index(db, user_id), version, CategorizeResult())
    if apply_to_similar:
        others = db.scalars(
            select(Transaction).where(
                Transaction.account_id.in_(select(Account.id).where(Account.user_id == user_id)),
                Transaction.cleaned_merchant == merchant,
                Transaction.id != txn.id,
                Transaction.is_transfer.is_(False),
                or_(
                    Transaction.category_source.is_(None),
                    Transaction.category_source != CategorySource.user,
                ),
            )
        )
        for other in others:
            assigner.assign(other, category_id, CategorySource.rule)
            changed += 1
    db.flush()
    return changed
