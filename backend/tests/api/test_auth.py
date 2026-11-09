"""Sign-up, invites, login/logout, sessions, account deletion, and the CSRF guard."""

from __future__ import annotations

from datetime import timedelta

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.auth import COOKIE_NAME
from app.config import Settings
from app.models import Account, User
from app.models import Session as LoginSession
from app.models._types import utcnow
from tests.conftest import TEST_PASSWORD, make_user, signed_in

PW = "a-long-enough-password"


def signup(client: TestClient, email: str, invite: str | None = None, password: str = PW):  # type: ignore[no-untyped-def]
    return client.post(
        "/api/auth/signup", json={"email": email, "password": password, "invite_code": invite}
    )


def test_status_and_first_signup_becomes_admin_and_claims_existing_data(
    anon_client: TestClient, db: Session
) -> None:
    db.add(Account(bank_name="Old", nickname="Pre multi-user", currency="INR"))  # no owner yet
    db.commit()
    status = anon_client.get("/api/auth/status").json()
    assert status["has_users"] is False and status["demo_mode"] is False
    assert isinstance(status["ai_enabled"], bool)

    r = signup(anon_client, "  Me@Example.COM ")
    assert r.status_code == 201, r.text
    assert r.json()["email"] == "me@example.com" and r.json()["is_admin"] is True
    assert COOKIE_NAME in r.cookies
    # Signed in immediately, and the old single-user ledger now belongs to the admin.
    assert [a["nickname"] for a in anon_client.get("/api/accounts").json()] == ["Pre multi-user"]
    assert anon_client.get("/api/auth/status").json()["has_users"] is True


def test_admin_email_locks_the_first_signup(
    anon_client: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    locked = Settings(admin_email="boss@example.com", _env_file=None)  # type: ignore[call-arg]
    monkeypatch.setattr("app.api.auth.get_settings", lambda: locked)
    assert signup(anon_client, "stranger@example.com").status_code == 403
    assert signup(anon_client, "BOSS@example.com").status_code == 201


def test_later_signups_need_a_single_use_invite(
    client: TestClient, anon_client: TestClient
) -> None:
    invite = client.post("/api/admin/invites", json={"note": "for Priya"}).json()
    client.cookies.clear()  # act as a stranger
    assert signup(anon_client, "new@example.com").status_code == 403
    assert signup(anon_client, "new@example.com", invite="nope").status_code == 403
    r = signup(anon_client, "new@example.com", invite=invite["code"])
    assert r.status_code == 201 and r.json()["is_admin"] is False
    anon_client.cookies.clear()
    assert (
        signup(anon_client, "third@example.com", invite=invite["code"]).status_code == 403
    )  # used


def test_only_admins_manage_invites(other_client: TestClient) -> None:
    assert other_client.post("/api/admin/invites", json={}).status_code == 403
    assert other_client.get("/api/admin/invites").status_code == 403


@pytest.mark.parametrize(
    ("body", "status"),
    [
        ({"email": "x@example.com", "password": "short"}, 422),
        ({"email": "not-an-email", "password": PW}, 422),
        ({"email": "owner@example.com", "password": PW}, 409),
    ],
)
def test_signup_validation(
    client: TestClient, anon_client: TestClient, body: dict, status: int
) -> None:  # type: ignore[type-arg]
    anon_client.cookies.clear()
    assert anon_client.post("/api/auth/signup", json=body).status_code == status


def test_login_logout_and_me(anon_client: TestClient, user: User) -> None:
    assert anon_client.get("/api/auth/me").status_code == 401
    bad = anon_client.post(
        "/api/auth/login", json={"email": user.email, "password": "wrong-password"}
    )
    assert bad.status_code == 401 and bad.json()["detail"] == "Wrong email or password"
    unknown = anon_client.post(
        "/api/auth/login", json={"email": "nobody@example.com", "password": "x"}
    )
    assert unknown.json()["detail"] == "Wrong email or password"  # same message: no enumeration

    ok = anon_client.post(
        "/api/auth/login", json={"email": "OWNER@example.com", "password": TEST_PASSWORD}
    )
    assert ok.status_code == 200
    assert anon_client.get("/api/auth/me").json()["email"] == "owner@example.com"
    token = anon_client.cookies.get(COOKIE_NAME)

    assert anon_client.post("/api/auth/logout").status_code == 204
    anon_client.cookies.set(COOKIE_NAME, token)  # replaying the old cookie must not work
    assert anon_client.get("/api/auth/me").status_code == 401


def test_session_token_is_stored_hashed_and_expires(client: TestClient, db: Session) -> None:
    token = client.cookies.get(COOKIE_NAME)
    stored = db.scalars(select(LoginSession.token_hash)).all()
    assert token not in stored
    for s in db.scalars(select(LoginSession)):
        s.expires_at = utcnow() - timedelta(seconds=1)
    db.commit()
    assert client.get("/api/auth/me").status_code == 401


ENDPOINTS = [
    ("GET", "/api/accounts", None),
    ("POST", "/api/accounts", {"bank_name": "X", "nickname": "Y", "currency": "INR"}),
    ("GET", "/api/categories", None),
    ("POST", "/api/categories", {"name": "Pets"}),
    ("PATCH", "/api/categories/1", {"name": "Pets"}),
    ("DELETE", "/api/categories/1", None),
    ("GET", "/api/imports", None),
    ("GET", "/api/imports/1", None),
    ("GET", "/api/transactions", None),
    ("PATCH", "/api/transactions/1", {"category_id": 1}),
    ("POST", "/api/categorize", {}),
    ("GET", "/api/merchant-rules", None),
    ("DELETE", "/api/merchant-rules/1", None),
    ("GET", "/api/analytics/dashboard", None),
    ("GET", "/api/auth/me", None),
    ("DELETE", "/api/auth/me", {"password": "whatever-password"}),
    ("POST", "/api/admin/invites", {}),
    ("GET", "/api/admin/invites", None),
]


@pytest.mark.parametrize(("method", "path", "body"), ENDPOINTS)
def test_everything_requires_sign_in(
    anon_client: TestClient,
    method: str,
    path: str,
    body: dict | None,  # type: ignore[type-arg]
) -> None:
    r = anon_client.request(method, path, json=body)
    assert r.status_code == 401, (method, path, r.status_code, r.text)


def test_uploads_require_sign_in(anon_client: TestClient) -> None:
    r = anon_client.post(
        "/api/imports", data={"account_id": "1"}, files={"file": ("s.csv", b"a,b\n", "text/csv")}
    )
    assert r.status_code == 401


def test_cross_site_writes_are_blocked(client: TestClient) -> None:
    evil = client.post(
        "/api/accounts",
        json={"bank_name": "X", "nickname": "Y", "currency": "INR"},
        headers={"Origin": "https://evil.example"},
    )
    assert evil.status_code == 403
    same = client.post(
        "/api/accounts",
        json={"bank_name": "X", "nickname": "Y", "currency": "INR"},
        headers={"Origin": "http://testserver"},
    )
    assert same.status_code == 201


def test_delete_my_account_removes_all_my_data_only(
    client: TestClient, other_client: TestClient, db: Session
) -> None:
    client.post("/api/accounts", json={"bank_name": "A", "nickname": "Mine", "currency": "INR"})
    client.post("/api/categories", json={"name": "Pets"})
    other_client.post(
        "/api/accounts", json={"bank_name": "B", "nickname": "Theirs", "currency": "INR"}
    )

    assert (
        client.request("DELETE", "/api/auth/me", json={"password": "wrong-password"}).status_code
        == 403
    )
    assert (
        client.request("DELETE", "/api/auth/me", json={"password": TEST_PASSWORD}).status_code
        == 204
    )

    db.expire_all()
    assert db.scalar(select(User).where(User.email == "owner@example.com")) is None
    assert [a.nickname for a in db.scalars(select(Account))] == ["Theirs"]
    assert client.get("/api/accounts").status_code == 401  # session gone too
    assert [a["nickname"] for a in other_client.get("/api/accounts").json()] == ["Theirs"]


def test_signed_in_helper_matches_login(anon_client: TestClient, db: Session) -> None:
    u = make_user(db, "helper@example.com")
    signed_in(anon_client, db, u)
    assert anon_client.get("/api/auth/me").json()["email"] == "helper@example.com"
