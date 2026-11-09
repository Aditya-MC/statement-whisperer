"""Sign-up (invite-only), login, logout, account deletion and admin invites."""

from __future__ import annotations

import secrets

from fastapi import APIRouter, Depends, HTTPException, Request, Response, status
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.api.deps import admin_user, current_user
from app.auth import (
    COOKIE_NAME,
    check_login,
    claim_unowned_data,
    create_session,
    hash_password,
    normalize_email,
    revoke_session,
    verify_password,
)
from app.config import get_settings
from app.db import get_db
from app.models import Invite, User
from app.models._types import utcnow
from app.schemas.api import (
    AuthStatusOut,
    DeleteMeIn,
    InviteCreate,
    InviteOut,
    LoginIn,
    SignupIn,
    UserOut,
)

router = APIRouter(tags=["auth"])


def _set_cookie(response: Response, token: str) -> None:
    s = get_settings()
    response.set_cookie(
        COOKIE_NAME,
        token,
        max_age=s.session_days * 86400,
        httponly=True,  # not readable by JavaScript
        secure=s.cookie_secure,  # HTTPS only when deployed
        samesite="lax",  # not sent on cross-site POSTs (CSRF)
        path="/",
    )


@router.get("/auth/status", response_model=AuthStatusOut)
def auth_status(db: Session = Depends(get_db)) -> dict[str, object]:
    """Public: whether anyone has signed up yet (the first sign-up creates the admin)."""
    has_users = (db.scalar(select(func.count()).select_from(User)) or 0) > 0
    return {"has_users": has_users, "demo_mode": get_settings().demo_mode}


@router.post("/auth/signup", response_model=UserOut, status_code=status.HTTP_201_CREATED)
def signup(body: SignupIn, response: Response, db: Session = Depends(get_db)) -> User:
    try:
        email = normalize_email(body.email)
    except ValueError as exc:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_CONTENT, str(exc)) from exc
    if db.scalar(select(User.id).where(User.email == email)) is not None:
        raise HTTPException(status.HTTP_409_CONFLICT, "An account with this email already exists")

    first = (db.scalar(select(func.count()).select_from(User)) or 0) == 0
    invite: Invite | None = None
    if first:
        admin_email = get_settings().admin_email
        if admin_email and email != admin_email.strip().lower():
            raise HTTPException(status.HTTP_403_FORBIDDEN, "This app isn't open for sign-ups yet")
    else:
        code = (body.invite_code or "").strip()
        invite = db.scalar(select(Invite).where(Invite.code == code)) if code else None
        if invite is None or invite.used_by is not None:
            raise HTTPException(status.HTTP_403_FORBIDDEN, "A valid invite code is required")

    user = User(email=email, password_hash=hash_password(body.password), is_admin=first)
    db.add(user)
    db.flush()
    if first:
        claim_unowned_data(db, user)  # an existing single-user ledger becomes the admin's
    if invite is not None:
        invite.used_by, invite.used_at = user.id, utcnow()
    token = create_session(db, user, get_settings().session_days)
    db.commit()
    _set_cookie(response, token)
    return user


@router.post("/auth/login", response_model=UserOut)
def login(body: LoginIn, response: Response, db: Session = Depends(get_db)) -> User:
    user = check_login(db, body.email, body.password)
    if user is None:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Wrong email or password")
    token = create_session(db, user, get_settings().session_days)
    db.commit()
    _set_cookie(response, token)
    return user


@router.post("/auth/logout", status_code=status.HTTP_204_NO_CONTENT)
def logout(request: Request, response: Response, db: Session = Depends(get_db)) -> None:
    revoke_session(db, request.cookies.get(COOKIE_NAME))
    db.commit()
    response.delete_cookie(COOKIE_NAME, path="/")


@router.get("/auth/me", response_model=UserOut)
def me(user: User = Depends(current_user)) -> User:
    return user


@router.delete("/auth/me", status_code=status.HTTP_204_NO_CONTENT)
def delete_me(
    body: DeleteMeIn,
    response: Response,
    user: User = Depends(current_user),
    db: Session = Depends(get_db),
) -> None:
    """Permanently delete your account and ALL your data (accounts, imports, transactions,
    custom categories, rules, sessions). Requires your password."""
    if not verify_password(user.password_hash, body.password):
        raise HTTPException(status.HTTP_403_FORBIDDEN, "Wrong password")
    db.delete(user)  # ON DELETE CASCADE removes everything owned
    db.commit()
    response.delete_cookie(COOKIE_NAME, path="/")


@router.post("/admin/invites", response_model=InviteOut, status_code=status.HTTP_201_CREATED)
def create_invite(
    body: InviteCreate, admin: User = Depends(admin_user), db: Session = Depends(get_db)
) -> Invite:
    invite = Invite(code=secrets.token_urlsafe(9), note=body.note, created_by=admin.id)
    db.add(invite)
    db.commit()
    return invite


@router.get("/admin/invites", response_model=list[InviteOut])
def list_invites(admin: User = Depends(admin_user), db: Session = Depends(get_db)) -> list[Invite]:
    return list(db.scalars(select(Invite).order_by(Invite.id.desc())))
