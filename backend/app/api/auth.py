"""Sign-up (invite-only), login, logout, account deletion and admin invites."""

from __future__ import annotations

import json
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
from app.models import Account, Category, Import, Invite, MerchantRule, Transaction, User
from app.models._types import utcnow
from app.ratelimit import limit_auth
from app.schemas.api import (
    AccountOut,
    AuthStatusOut,
    CategoryOut,
    DeleteMeIn,
    ImportOut,
    InviteCreate,
    InviteOut,
    LoginIn,
    MerchantRuleOut,
    SignupIn,
    TransactionOut,
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
    s = get_settings()
    key = s.anthropic_api_key.get_secret_value() if s.anthropic_api_key else ""
    ai = not s.demo_mode and s.llm_provider == "anthropic" and bool(key)
    return {"has_users": has_users, "demo_mode": s.demo_mode, "ai_enabled": ai}


@router.post(
    "/auth/signup",
    response_model=UserOut,
    status_code=status.HTTP_201_CREATED,
    dependencies=[Depends(limit_auth)],
)
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


@router.post("/auth/login", response_model=UserOut, dependencies=[Depends(limit_auth)])
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


@router.get("/auth/me/export")
def export_my_data(user: User = Depends(current_user), db: Session = Depends(get_db)) -> Response:
    """Everything stored about you, as one JSON file: accounts, imports, transactions, your
    categories and rules. Statement files were never stored, so they aren't included."""
    accounts = list(db.scalars(select(Account).where(Account.user_id == user.id)))
    ids = [a.id for a in accounts]
    imports = db.scalars(select(Import).where(Import.account_id.in_(ids)).order_by(Import.id))
    txns = db.scalars(
        select(Transaction)
        .where(Transaction.account_id.in_(ids))
        .order_by(Transaction.date, Transaction.id)
    )
    data = {
        "exported_at": utcnow().isoformat(),
        "user": {"email": user.email, "created_at": user.created_at.isoformat()},
        "accounts": [AccountOut.model_validate(a).model_dump(mode="json") for a in accounts],
        "imports": [ImportOut.model_validate(i).model_dump(mode="json") for i in imports],
        "transactions": [TransactionOut.model_validate(t).model_dump(mode="json") for t in txns],
        "custom_categories": [
            CategoryOut.model_validate(c).model_dump(mode="json")
            for c in db.scalars(select(Category).where(Category.user_id == user.id))
        ],
        "merchant_rules": [
            MerchantRuleOut.model_validate(r).model_dump(mode="json")
            for r in db.scalars(select(MerchantRule).where(MerchantRule.user_id == user.id))
        ],
    }
    filename = f"statement-whisperer-export-{utcnow():%Y-%m-%d}.json"
    return Response(
        content=json.dumps(data, ensure_ascii=False, indent=1),
        media_type="application/json",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )


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
