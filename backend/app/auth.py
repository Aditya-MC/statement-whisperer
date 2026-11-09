"""Passwords, sessions and ownership hand-over.

* Passwords are hashed with argon2id (argon2-cffi defaults) and never stored or logged.
* A session is a random 256-bit token in an HttpOnly cookie. The database stores only its
  SHA-256, so a database leak does not yield usable sessions. Logout and account deletion
  revoke sessions server-side.
* `claim_unowned_data` gives rows created before multi-user support (user_id NULL) to the
  first admin, so an existing single-user ledger carries over to its owner.
"""

from __future__ import annotations

import hashlib
import re
import secrets
from datetime import timedelta

from argon2 import PasswordHasher
from argon2.exceptions import InvalidHashError, VerificationError, VerifyMismatchError
from sqlalchemy import Update, delete, select, update
from sqlalchemy.orm import Session as DbSession

from app.models import Account, Category, MerchantRule, RuleSource, Session, User
from app.models._types import utcnow

COOKIE_NAME = "sw_session"
MIN_PASSWORD = 10
MAX_PASSWORD = 256
_EMAIL = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")
_hasher = PasswordHasher()


def normalize_email(email: str) -> str:
    e = email.strip().lower()
    if len(e) > 254 or not _EMAIL.match(e):
        raise ValueError("Enter a valid email address")
    return e


def hash_password(password: str) -> str:
    return _hasher.hash(password)


def verify_password(password_hash: str, password: str) -> bool:
    try:
        return _hasher.verify(password_hash, password)
    except (VerifyMismatchError, VerificationError, InvalidHashError):
        return False


# Verifying against a throwaway hash when the email is unknown keeps login timing similar for
# existing and non-existing accounts (no easy account enumeration).
_DUMMY_HASH = _hasher.hash(secrets.token_urlsafe(16))


def check_login(db: DbSession, email: str, password: str) -> User | None:
    try:
        e = normalize_email(email)
    except ValueError:
        return None
    user = db.scalar(select(User).where(User.email == e))
    if user is None:
        verify_password(_DUMMY_HASH, password)
        return None
    return user if verify_password(user.password_hash, password) else None


def _token_hash(token: str) -> str:
    return hashlib.sha256(token.encode()).hexdigest()


def create_session(db: DbSession, user: User, days: int) -> str:
    """Create a session and return the raw token (only ever sent to the browser)."""
    token = secrets.token_urlsafe(32)
    db.add(
        Session(
            user_id=user.id,
            token_hash=_token_hash(token),
            expires_at=utcnow() + timedelta(days=days),
        )
    )
    user.last_login_at = utcnow()
    db.flush()
    return token


def user_for_token(db: DbSession, token: str | None) -> User | None:
    if not token:
        return None
    s = db.scalar(select(Session).where(Session.token_hash == _token_hash(token)))
    if s is None:
        return None
    if s.expires_at <= utcnow():
        db.delete(s)
        db.commit()
        return None
    return db.get(User, s.user_id)


def revoke_session(db: DbSession, token: str | None) -> None:
    if token:
        db.execute(delete(Session).where(Session.token_hash == _token_hash(token)))


def claim_unowned_data(db: DbSession, user: User) -> dict[str, int]:
    """Assign pre-multi-user data (no owner) to `user`. Built-in categories and seed rules
    stay shared, because they are not personal."""

    def changed(stmt: Update) -> int:
        result = db.execute(stmt)
        return int(getattr(result, "rowcount", 0) or 0)  # UPDATE results are CursorResults

    return {
        "accounts": changed(
            update(Account).where(Account.user_id.is_(None)).values(user_id=user.id)
        ),
        "categories": changed(
            update(Category)
            .where(Category.user_id.is_(None), Category.is_custom.is_(True))
            .values(user_id=user.id)
        ),
        "rules": changed(
            update(MerchantRule)
            .where(MerchantRule.user_id.is_(None), MerchantRule.source != RuleSource.seed)
            .values(user_id=user.id)
        ),
    }
