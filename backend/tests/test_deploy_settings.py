"""Settings and plumbing used when deployed: Postgres URLs, AI off, rate limits, export."""

from __future__ import annotations

import json

import pytest
from fastapi.testclient import TestClient

from app.config import Settings
from app.db import make_engine, normalize_postgres_url
from app.ratelimit import RateLimiter
from app.services.llm import LLMError, UnavailableLLMClient, build_llm_client
from app.services.masking import build_masked_sample
from tests.api.test_api import HEADER, MAPPING, statement, upload


@pytest.mark.parametrize(
    ("url", "expected", "tls"),
    [
        (
            "postgresql://u:p@ep-x.aws.neon.tech/ledger?sslmode=require&channel_binding=require",
            "postgresql+pg8000://u:p@ep-x.aws.neon.tech/ledger",
            True,
        ),
        (
            "postgres://u:p@db.example.com:5432/ledger",
            "postgresql+pg8000://u:p@db.example.com:5432/ledger",
            True,
        ),
        ("postgresql://u:p@localhost/ledger", "postgresql+pg8000://u:p@localhost/ledger", False),
        (
            "postgresql://u:p@db.example.com/l?sslmode=disable",
            "postgresql+pg8000://u:p@db.example.com/l",
            False,
        ),
        (
            "postgresql://u:p@db.example.com/l?application_name=sw",
            "postgresql+pg8000://u:p@db.example.com/l?application_name=sw",
            True,
        ),
    ],
)
def test_normalize_postgres_url(url: str, expected: str, tls: bool) -> None:
    assert normalize_postgres_url(url) == (expected, tls)


def test_postgres_engine_uses_pg8000_with_tls_and_pre_ping() -> None:
    engine = make_engine("postgresql://u:p@ep-x.aws.neon.tech/ledger?sslmode=require")
    assert engine.dialect.driver == "pg8000"
    assert engine.pool._pre_ping is True  # type: ignore[attr-defined]
    engine.dispose()  # never connected


def test_llm_provider_none_means_manual_mapping() -> None:
    client = build_llm_client(
        Settings(llm_provider="none", anthropic_api_key="sk-unused", _env_file=None)
    )  # type: ignore[call-arg]
    assert isinstance(client, UnavailableLLMClient)
    with pytest.raises(LLMError, match="turned off"):
        client.infer_schema(build_masked_sample(["A", "B", "C"], []))


def test_rate_limiter_sliding_window() -> None:
    rl = RateLimiter(limit=2, window_seconds=10)
    assert rl.allow("ip", now=0) and rl.allow("ip", now=1)
    assert not rl.allow("ip", now=2)
    assert rl.allow("other", now=2)  # per key
    assert rl.allow("ip", now=10.5)  # first hit expired


def test_login_attempts_are_rate_limited(anon_client: TestClient) -> None:
    body = {"email": "nobody@example.com", "password": "wrong-password"}
    codes = [anon_client.post("/api/auth/login", json=body).status_code for _ in range(11)]
    assert codes[:10] == [401] * 10
    assert codes[10] == 429


def test_export_my_data(client: TestClient, fake_llm) -> None:  # type: ignore[no-untyped-def]
    fake_llm.register(HEADER, MAPPING)
    acct = client.post(
        "/api/accounts", json={"bank_name": "A", "nickname": "Mine", "currency": "USD"}
    ).json()
    upload(client, acct["id"], statement(0, 5))
    client.post("/api/categories", json={"name": "Pets"})
    r = client.get("/api/auth/me/export")
    assert r.status_code == 200
    assert "attachment" in r.headers["content-disposition"]
    data = json.loads(r.content)
    assert data["user"]["email"] == "owner@example.com"
    assert [a["nickname"] for a in data["accounts"]] == ["Mine"]
    assert len(data["transactions"]) == 5 and len(data["imports"]) == 1
    assert [c["name"] for c in data["custom_categories"]] == ["Pets"]
    assert "password" not in r.text.lower()


def test_export_contains_only_my_data(client: TestClient, other_client: TestClient) -> None:
    client.post("/api/accounts", json={"bank_name": "A", "nickname": "Mine", "currency": "USD"})
    data = json.loads(other_client.get("/api/auth/me/export").content)
    assert data["accounts"] == [] and data["user"]["email"] == "other@example.com"
