from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import delete, func, select, update
from sqlalchemy.orm import Session

from app.db import get_db
from app.models import Account, Category, MerchantRule, Transaction
from app.schemas.api import (
    AccountCreate,
    AccountOut,
    CategoryCreate,
    CategoryDeleteOut,
    CategoryOut,
    CategoryRename,
)

router = APIRouter(tags=["accounts"])


@router.post("/accounts", response_model=AccountOut, status_code=status.HTTP_201_CREATED)
def create_account(body: AccountCreate, db: Session = Depends(get_db)) -> Account:
    account = Account(**body.model_dump())
    db.add(account)
    db.commit()
    return account


@router.get("/accounts", response_model=list[AccountOut])
def list_accounts(db: Session = Depends(get_db)) -> list[Account]:
    return list(db.scalars(select(Account).order_by(Account.id)))


@router.get("/categories", response_model=list[CategoryOut])
def list_categories(db: Session = Depends(get_db)) -> list[Category]:
    return list(db.scalars(select(Category).order_by(Category.parent_id, Category.id)))


def _name_taken(
    db: Session, name: str, parent_id: int | None, exclude_id: int | None = None
) -> bool:
    # Explicit check: SQL UNIQUE treats NULL parents as distinct, so it wouldn't catch
    # duplicate top-level groups.
    stmt = select(Category.id).where(
        func.lower(Category.name) == name.lower(),
        Category.parent_id.is_(None) if parent_id is None else Category.parent_id == parent_id,
    )
    if exclude_id is not None:
        stmt = stmt.where(Category.id != exclude_id)
    return db.scalar(stmt) is not None


@router.post("/categories", response_model=CategoryOut, status_code=status.HTTP_201_CREATED)
def create_category(body: CategoryCreate, db: Session = Depends(get_db)) -> Category:
    """Add a category under an existing group (inherits its kind), or a new top-level group."""
    kind = body.kind
    if body.parent_id is not None:
        parent = db.get(Category, body.parent_id)
        if parent is None or parent.parent_id is not None:
            raise HTTPException(
                status.HTTP_422_UNPROCESSABLE_CONTENT, "Parent must be a top-level group"
            )
        kind = parent.kind
    if _name_taken(db, body.name, body.parent_id):
        raise HTTPException(
            status.HTTP_409_CONFLICT, "A category with this name already exists there"
        )
    cat = Category(name=body.name, parent_id=body.parent_id, kind=kind, is_custom=True)
    db.add(cat)
    db.commit()
    return cat


def _custom_or_403(db: Session, category_id: int) -> Category:
    cat = db.get(Category, category_id)
    if cat is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Category not found")
    if not cat.is_custom:
        raise HTTPException(status.HTTP_403_FORBIDDEN, "Built-in categories can't be changed")
    return cat


@router.patch("/categories/{category_id}", response_model=CategoryOut)
def rename_category(
    category_id: int, body: CategoryRename, db: Session = Depends(get_db)
) -> Category:
    cat = _custom_or_403(db, category_id)
    if _name_taken(db, body.name, cat.parent_id, exclude_id=cat.id):
        raise HTTPException(
            status.HTTP_409_CONFLICT, "A category with this name already exists there"
        )
    cat.name = body.name
    db.commit()
    return cat


@router.delete("/categories/{category_id}", response_model=CategoryDeleteOut)
def delete_category(category_id: int, db: Session = Depends(get_db)) -> dict[str, int]:
    """Delete a custom category (and its children, for a group). Its transactions become
    uncategorized and its merchant rules are removed."""
    cat = _custom_or_403(db, category_id)
    ids = [cat.id, *db.scalars(select(Category.id).where(Category.parent_id == cat.id))]
    txns = (
        db.scalar(
            select(func.count()).select_from(Transaction).where(Transaction.category_id.in_(ids))
        )
        or 0
    )
    rules = (
        db.scalar(
            select(func.count()).select_from(MerchantRule).where(MerchantRule.category_id.in_(ids))
        )
        or 0
    )
    # Explicit rather than relying on ON DELETE, so behaviour doesn't depend on the database
    # enforcing foreign keys.
    db.execute(
        update(Transaction)
        .where(Transaction.category_id.in_(ids))
        .values(category_id=None, category_source=None, rules_version=None)
    )
    db.execute(delete(MerchantRule).where(MerchantRule.category_id.in_(ids)))
    db.execute(delete(Category).where(Category.parent_id == cat.id))
    db.delete(cat)
    db.commit()
    return {"transactions_uncategorized": txns, "rules_removed": rules}
