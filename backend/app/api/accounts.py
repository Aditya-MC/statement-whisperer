"""Bank accounts and the category tree, scoped to the signed-in user.

Everything here only ever reads or changes the current user's own rows. Built-in categories
are shared: they can't be renamed, and "deleting" one only hides it for you. Someone else's
row is reported as "not found" rather than "forbidden", so ids can't be probed.
"""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import delete, func, select, update
from sqlalchemy.orm import Session

from app.api.deps import current_user, user_account_ids
from app.categorization.categorizer import visible_categories
from app.db import get_db
from app.models import Account, Category, HiddenCategory, MerchantRule, Transaction, User
from app.schemas.api import (
    AccountCreate,
    AccountOut,
    CategoryCreate,
    CategoryDeleteOut,
    CategoryOut,
    CategoryRename,
    CategoryRestoreOut,
)

router = APIRouter(tags=["accounts"])


@router.post("/accounts", response_model=AccountOut, status_code=status.HTTP_201_CREATED)
def create_account(
    body: AccountCreate, user: User = Depends(current_user), db: Session = Depends(get_db)
) -> Account:
    account = Account(**body.model_dump(), user_id=user.id)
    db.add(account)
    db.commit()
    return account


@router.get("/accounts", response_model=list[AccountOut])
def list_accounts(
    user: User = Depends(current_user), db: Session = Depends(get_db)
) -> list[Account]:
    return list(db.scalars(select(Account).where(Account.user_id == user.id).order_by(Account.id)))


def _visible(user: User):  # type: ignore[no-untyped-def]
    return visible_categories(user.id)


@router.get("/categories", response_model=list[CategoryOut])
def list_categories(
    user: User = Depends(current_user), db: Session = Depends(get_db)
) -> list[Category]:
    """Built-in categories (minus the ones you deleted) plus your own."""
    return list(
        db.scalars(select(Category).where(_visible(user)).order_by(Category.parent_id, Category.id))
    )


def _name_taken(
    db: Session, user: User, name: str, parent_id: int | None, exclude_id: int | None = None
) -> bool:
    # Checked here rather than by a UNIQUE index: names must be unique among what *this* user
    # sees (built-ins + theirs), and SQL treats NULL parents/owners as distinct.
    stmt = select(Category.id).where(
        _visible(user),
        func.lower(Category.name) == name.lower(),
        Category.parent_id.is_(None) if parent_id is None else Category.parent_id == parent_id,
    )
    if exclude_id is not None:
        stmt = stmt.where(Category.id != exclude_id)
    return db.scalar(stmt) is not None


@router.post("/categories", response_model=CategoryOut, status_code=status.HTTP_201_CREATED)
def create_category(
    body: CategoryCreate, user: User = Depends(current_user), db: Session = Depends(get_db)
) -> Category:
    """Add a category under an existing group (inherits its kind), or a new top-level group."""
    kind = body.kind
    if body.parent_id is not None:
        parent = db.get(Category, body.parent_id)
        visible = db.scalar(
            select(Category.id).where(Category.id == body.parent_id, _visible(user))
        )
        if parent is None or parent.parent_id is not None or visible is None:
            raise HTTPException(
                status.HTTP_422_UNPROCESSABLE_CONTENT, "Parent must be a top-level group"
            )
        kind = parent.kind
    if _name_taken(db, user, body.name, body.parent_id):
        raise HTTPException(
            status.HTTP_409_CONFLICT, "A category with this name already exists there"
        )
    cat = Category(
        name=body.name, parent_id=body.parent_id, kind=kind, is_custom=True, user_id=user.id
    )
    db.add(cat)
    db.commit()
    return cat


def _own_custom(db: Session, user: User, category_id: int) -> Category:
    cat = db.get(Category, category_id)
    if cat is None or cat.user_id not in (None, user.id):
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Category not found")
    if not cat.is_custom or cat.user_id != user.id:
        raise HTTPException(status.HTTP_403_FORBIDDEN, "Built-in categories can't be changed")
    return cat


@router.patch("/categories/{category_id}", response_model=CategoryOut)
def rename_category(
    category_id: int,
    body: CategoryRename,
    user: User = Depends(current_user),
    db: Session = Depends(get_db),
) -> Category:
    cat = _own_custom(db, user, category_id)
    if _name_taken(db, user, body.name, cat.parent_id, exclude_id=cat.id):
        raise HTTPException(
            status.HTTP_409_CONFLICT, "A category with this name already exists there"
        )
    cat.name = body.name
    db.commit()
    return cat


@router.delete("/categories/{category_id}", response_model=CategoryDeleteOut)
def delete_category(
    category_id: int, user: User = Depends(current_user), db: Session = Depends(get_db)
) -> dict[str, int]:
    """Delete a category (and its children, for a group). Its transactions become
    uncategorized and your merchant rules for it are removed. Your own categories are deleted
    for good; built-in ones are shared, so they're only hidden for you (restorable)."""
    cat = db.get(Category, category_id)
    visible = db.scalar(select(Category.id).where(Category.id == category_id, _visible(user)))
    if cat is None or visible is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Category not found")
    children = list(
        db.scalars(select(Category).where(Category.parent_id == cat.id, _visible(user)))
    )
    ids = [cat.id, *(c.id for c in children)]
    own_accounts = user_account_ids(db, user)
    in_scope = (Transaction.category_id.in_(ids), Transaction.account_id.in_(own_accounts))
    txns = db.scalar(select(func.count()).select_from(Transaction).where(*in_scope)) or 0
    rules_q = (MerchantRule.category_id.in_(ids), MerchantRule.user_id == user.id)
    rules = db.scalar(select(func.count()).select_from(MerchantRule).where(*rules_q)) or 0
    # Explicit rather than relying on ON DELETE, so behaviour doesn't depend on the database
    # enforcing foreign keys.
    db.execute(
        update(Transaction)
        .where(*in_scope)
        .values(category_id=None, category_source=None, rules_version=None)
    )
    db.execute(delete(MerchantRule).where(*rules_q))
    for c in [*children, cat]:
        if c.user_id == user.id:
            db.delete(c)  # yours: gone for good
        else:
            db.add(HiddenCategory(user_id=user.id, category_id=c.id))  # shared: hide for you
    db.commit()
    return {"transactions_uncategorized": txns, "rules_removed": rules}


@router.post("/categories/restore", response_model=CategoryRestoreOut)
def restore_categories(
    user: User = Depends(current_user), db: Session = Depends(get_db)
) -> dict[str, int]:
    """Bring back every built-in category you deleted. Transactions stay as they are; run
    "Re-categorize" to let the rules use them again."""
    n = db.scalar(
        select(func.count()).select_from(HiddenCategory).where(HiddenCategory.user_id == user.id)
    )
    db.execute(delete(HiddenCategory).where(HiddenCategory.user_id == user.id))
    db.commit()
    return {"restored": n or 0}
