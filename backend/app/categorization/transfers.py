"""Link transfers between the user's own accounts so they don't count as income or expense.

A debit in one account and a credit of exactly the same amount in a *different* account,
within a few days, are linked as a pair. Both are marked `is_transfer`, point at each other via
`transfer_peer_id`, and get "Transfers > Self Transfer" (unless the user categorized them by
hand). Each debit is matched with the credit closest in date. Rows the user unlinked
(`transfer_dismissed`) are never linked again. Paying a credit card from a bank
account shows up the same way, which is correct: it moves money between your own accounts.
"""

from __future__ import annotations

from collections import defaultdict
from decimal import Decimal

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.categorization.categorizer import SELF_TRANSFER, current_rules_version, load_category_index
from app.models import Account, CategorySource, Transaction

DEFAULT_WINDOW_DAYS = 3


def link_transfers(db: Session, user_id: int | None, window_days: int = DEFAULT_WINDOW_DAYS) -> int:
    """Find and link new transfer pairs between `user_id`'s own accounts (never across users).
    Returns the number of pairs linked. Flushes only."""
    own_accounts = select(Account.id).where(Account.user_id == user_id)
    if (db.scalar(select(func.count()).select_from(own_accounts.subquery())) or 0) < 2:
        return 0
    candidates = list(
        db.scalars(
            select(Transaction)
            .where(
                Transaction.account_id.in_(own_accounts),
                Transaction.is_transfer.is_(False),
                Transaction.transfer_dismissed.is_(False),
            )
            .order_by(Transaction.date, Transaction.id)
        )
    )
    credits: dict[Decimal, list[Transaction]] = defaultdict(list)
    for t in candidates:
        if t.amount > 0:
            credits[t.amount].append(t)

    idx = load_category_index(db, user_id)
    self_transfer = idx.by_path.get(SELF_TRANSFER)
    version = current_rules_version(db)
    used: set[int] = set()
    pairs = 0
    for debit in (t for t in candidates if t.amount < 0):
        best: Transaction | None = None
        best_gap = window_days + 1
        for credit in credits.get(-debit.amount, []):
            if credit.id in used or credit.account_id == debit.account_id:
                continue
            gap = abs((credit.date - debit.date).days)
            if gap <= window_days and gap < best_gap:
                best, best_gap = credit, gap
        if best is None:
            continue
        used.add(best.id)
        for a, b in ((debit, best), (best, debit)):
            a.is_transfer = True
            a.transfer_peer_id = b.id
            if a.category_source != CategorySource.user and self_transfer is not None:
                a.category_id = self_transfer
                a.category_source = CategorySource.rule
                a.rules_version = version
        pairs += 1
    db.flush()
    return pairs
