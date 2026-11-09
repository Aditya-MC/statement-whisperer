"""Shared FastAPI dependencies (overridable in tests)."""

from __future__ import annotations

from functools import lru_cache

from fastapi import Depends, HTTPException, Request, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.auth import COOKIE_NAME, user_for_token
from app.config import get_settings
from app.db import get_db
from app.models import Account, User
from app.services.llm import LLMClient, build_llm_client


@lru_cache
def _cached_llm() -> LLMClient:
    return build_llm_client(get_settings())


def get_llm() -> LLMClient:
    return _cached_llm()


def current_user(request: Request, db: Session = Depends(get_db)) -> User:
    """The signed-in user, or 401. In demo mode everyone is the demo user (synthetic data)."""
    if get_settings().demo_mode:
        demo = db.scalar(select(User).order_by(User.id))
        if demo is not None:
            return demo
    user = user_for_token(db, request.cookies.get(COOKIE_NAME))
    if user is None:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Please sign in")
    return user


def admin_user(user: User = Depends(current_user)) -> User:
    if not user.is_admin:
        raise HTTPException(status.HTTP_403_FORBIDDEN, "Admins only")
    return user


def owned_account(db: Session, user: User, account_id: int) -> Account:
    """The account if it belongs to `user`. Someone else's account is reported as not found,
    so ids can't be probed."""
    account = db.get(Account, account_id)
    if account is None or account.user_id != user.id:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Account not found")
    return account


def user_account_ids(db: Session, user: User) -> list[int]:
    return list(db.scalars(select(Account.id).where(Account.user_id == user.id)))
