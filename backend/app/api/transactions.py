"""Transactions, corrections, re-categorization and merchant rules, scoped to the signed-in user.

Someone else's transaction or rule is reported as "not found", so ids can't be probed.
"""

from __future__ import annotations

from datetime import date

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import func, or_, select
from sqlalchemy.orm import Session

from app.api.deps import current_user, get_llm, owned_account, user_account_ids
from app.categorization.categorizer import (
    apply_user_correction,
    categorize_transactions,
    visible_categories,
)
from app.categorization.transfers import link_transfers
from app.db import get_db
from app.models import Category, CategorySource, MerchantRule, Transaction, User
from app.schemas.api import (
    CategorizeOut,
    CategorizeRequest,
    MerchantRuleOut,
    TransactionOut,
    TransactionPage,
    TransactionUpdate,
    TransactionUpdateOut,
)
from app.services.llm import LLMClient

router = APIRouter(tags=["transactions"])


@router.get("/transactions", response_model=TransactionPage)
def list_transactions(
    account_id: int | None = None,
    import_id: int | None = None,
    date_from: date | None = None,
    date_to: date | None = None,
    category_id: int | None = Query(default=None, description="Category or any of its children"),
    uncategorized: bool = False,
    is_transfer: bool | None = None,
    q: str | None = Query(default=None, max_length=100, description="Search narration/merchant"),
    limit: int = Query(default=100, ge=1, le=1000),
    offset: int = Query(default=0, ge=0),
    user: User = Depends(current_user),
    db: Session = Depends(get_db),
) -> dict[str, object]:
    stmt = select(Transaction).where(Transaction.account_id.in_(user_account_ids(db, user)))
    if account_id is not None:
        stmt = stmt.where(Transaction.account_id == account_id)
    if import_id is not None:
        stmt = stmt.where(Transaction.import_id == import_id)
    if date_from is not None:
        stmt = stmt.where(Transaction.date >= date_from)
    if date_to is not None:
        stmt = stmt.where(Transaction.date <= date_to)
    if category_id is not None:
        children = select(Category.id).where(Category.parent_id == category_id)
        stmt = stmt.where(
            or_(Transaction.category_id == category_id, Transaction.category_id.in_(children))
        )
    if uncategorized:
        stmt = stmt.where(Transaction.category_id.is_(None))
    if is_transfer is not None:
        stmt = stmt.where(Transaction.is_transfer.is_(is_transfer))
    if q:
        needle = q.strip().lower()
        stmt = stmt.where(
            or_(
                func.lower(Transaction.raw_narration).contains(needle, autoescape=True),
                func.lower(Transaction.cleaned_merchant).contains(needle, autoescape=True),
            )
        )
    total = db.scalar(select(func.count()).select_from(stmt.subquery())) or 0
    items = db.scalars(
        stmt.order_by(
            Transaction.date.desc(), Transaction.import_id.desc(), Transaction.row_index.desc()
        )
        .limit(limit)
        .offset(offset)
    ).all()
    return {"total": total, "items": items}


def _owned_txn(db: Session, user: User, txn_id: int) -> Transaction:
    txn = db.get(Transaction, txn_id)
    if txn is None or txn.account_id not in user_account_ids(db, user):
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Transaction not found")
    return txn


@router.patch("/transactions/{txn_id}", response_model=TransactionUpdateOut)
def update_transaction(
    txn_id: int,
    body: TransactionUpdate,
    user: User = Depends(current_user),
    db: Session = Depends(get_db),
    llm: LLMClient = Depends(get_llm),
) -> dict[str, object]:
    """Correct a category (saved as a merchant rule) and/or unlink a detected transfer."""
    txn = _owned_txn(db, user, txn_id)

    if body.is_transfer is False and txn.is_transfer:
        peer = db.get(Transaction, txn.transfer_peer_id) if txn.transfer_peer_id else None
        unlinked = [t for t in (txn, peer) if t is not None]
        for t in unlinked:
            t.is_transfer = False
            t.transfer_peer_id = None
            t.transfer_dismissed = True  # don't auto-link this pair again
            if t.category_source != CategorySource.user:
                t.category_id, t.category_source = None, None
        db.flush()
        categorize_transactions(db, llm, unlinked, user_id=user.id)

    updated = 0
    if body.category_id is not None:
        cat = db.scalar(
            select(Category).where(Category.id == body.category_id, visible_categories(user.id))
        )
        if cat is None:
            raise HTTPException(status.HTTP_422_UNPROCESSABLE_CONTENT, "Unknown category")
        updated = apply_user_correction(
            db, txn, body.category_id, apply_to_similar=body.apply_to_similar
        )
    db.commit()
    return {"transaction": TransactionOut.model_validate(txn), "updated_similar": updated}


@router.post("/categorize", response_model=CategorizeOut)
def recategorize(
    body: CategorizeRequest,
    user: User = Depends(current_user),
    db: Session = Depends(get_db),
    llm: LLMClient = Depends(get_llm),
) -> dict[str, object]:
    """Re-run categorization (never touches manually categorized rows) and transfer linking."""
    if body.account_id is not None:
        owned_account(db, user, body.account_id)
    result = categorize_transactions(
        db,
        llm,
        user_id=user.id,
        account_id=body.account_id,
        only_uncategorized=body.only_uncategorized,
    )
    pairs = link_transfers(db, user.id)
    db.commit()
    return {**result.as_dict(), "transfers_linked": pairs}


@router.get("/merchant-rules", response_model=list[MerchantRuleOut])
def list_rules(
    source: str | None = None, user: User = Depends(current_user), db: Session = Depends(get_db)
) -> list[MerchantRule]:
    """Shared built-in rules plus your own corrections and remembered AI answers."""
    stmt = (
        select(MerchantRule)
        .where(or_(MerchantRule.user_id.is_(None), MerchantRule.user_id == user.id))
        .order_by(MerchantRule.priority.desc(), MerchantRule.pattern)
    )
    if source is not None:
        stmt = stmt.where(MerchantRule.source == source)
    return list(db.scalars(stmt))


@router.delete("/merchant-rules/{rule_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_rule(
    rule_id: int, user: User = Depends(current_user), db: Session = Depends(get_db)
) -> None:
    rule = db.get(MerchantRule, rule_id)
    if rule is None or rule.user_id not in (None, user.id):
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Rule not found")
    if rule.user_id is None:
        raise HTTPException(
            status.HTTP_403_FORBIDDEN, "Built-in rules are shared and can't be deleted"
        )
    db.delete(rule)
    db.commit()
