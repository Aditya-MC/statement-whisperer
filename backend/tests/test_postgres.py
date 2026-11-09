"""Full cycle against a real Postgres database (e.g. a Neon database), opt-in.

Set TEST_POSTGRES_URL (environment, or a line in the repo-root .env) to an EMPTY database:

    TEST_POSTGRES_URL=postgresql://user:pass@ep-....neon.tech/neondb?sslmode=require

The test refuses to run if the database already has tables, so it can't touch real data. It
migrates to head, checks the schema matches the models, runs sign-up -> import -> dashboard
-> isolation through the real API, then downgrades to base so the database is left empty.
"""

from __future__ import annotations

import os
from collections.abc import Iterator

import pytest
from alembic import command
from alembic.autogenerate import compare_metadata
from alembic.config import Config
from alembic.migration import MigrationContext
from dotenv import dotenv_values
from fastapi.testclient import TestClient
from sqlalchemy import inspect, text
from sqlalchemy.orm import Session, sessionmaker

from app.api.deps import get_llm
from app.config import BACKEND_DIR, REPO_ROOT
from app.db import Base, get_db, make_engine
from app.services.llm import UnavailableLLMClient
from tests.api.test_api import MAPPING, statement

URL = os.environ.get("TEST_POSTGRES_URL") or dotenv_values(REPO_ROOT / ".env").get(
    "TEST_POSTGRES_URL"
)
pytestmark = pytest.mark.skipif(
    not URL, reason="set TEST_POSTGRES_URL to an empty Postgres database"
)


def _config() -> Config:
    cfg = Config(str(BACKEND_DIR / "alembic.ini"))
    cfg.set_main_option("script_location", str(BACKEND_DIR / "alembic"))
    cfg.attributes["database_url"] = URL
    cfg.attributes["configure_logger"] = False
    return cfg


@pytest.fixture
def pg() -> Iterator[object]:
    engine = make_engine(URL)  # type: ignore[arg-type]
    existing = inspect(engine).get_table_names()
    if existing:
        engine.dispose()
        pytest.skip(f"refusing to run: database already has {len(existing)} table(s)")
    cfg = _config()
    try:
        command.upgrade(cfg, "head")
        yield engine
    finally:
        command.downgrade(cfg, "base")
        with engine.begin() as conn:
            conn.execute(text("DROP TABLE IF EXISTS alembic_version"))
        engine.dispose()


def test_postgres_full_cycle(pg) -> None:  # type: ignore[no-untyped-def]
    engine = pg
    with engine.connect() as conn:
        diff = compare_metadata(
            MigrationContext.configure(conn, opts={"compare_type": True}), Base.metadata
        )
    assert diff == [], diff

    from app.main import app

    factory = sessionmaker(bind=engine, expire_on_commit=False)

    def _db() -> Iterator[Session]:
        with factory() as s:
            yield s

    app.dependency_overrides[get_db] = _db
    app.dependency_overrides[get_llm] = lambda: UnavailableLLMClient("off")
    try:
        admin, tester = TestClient(app), TestClient(app)
        r = admin.post(
            "/api/auth/signup", json={"email": "admin@example.com", "password": "admin-password-1"}
        )
        assert r.status_code == 201 and r.json()["is_admin"]
        code = admin.post("/api/admin/invites", json={}).json()["code"]
        r = tester.post(
            "/api/auth/signup",
            json={"email": "t@example.com", "password": "tester-pass-12", "invite_code": code},
        )
        assert r.status_code == 201

        acct = admin.post(
            "/api/accounts", json={"bank_name": "B", "nickname": "Main", "currency": "USD"}
        ).json()
        r = admin.post(
            "/api/imports",
            data={"account_id": str(acct["id"]), "mapping": MAPPING.model_dump_json()},
            files={"file": ("s.csv", statement(0, 9), "text/csv")},
        )
        assert r.status_code == 201 and r.json()["status"] == "completed", r.text
        assert admin.get("/api/transactions").json()["total"] == 9
        dash = admin.get("/api/analytics/dashboard").json()
        assert dash["summary"]["transactions"] == 9 and dash["currency"] == "USD"
        assert admin.post("/api/categories", json={"name": "Pets"}).status_code == 201

        assert tester.get("/api/transactions").json()["total"] == 0
        assert tester.get(f"/api/imports/{r.json()['id']}").status_code == 404
        assert (
            tester.request(
                "DELETE", "/api/auth/me", json={"password": "tester-pass-12"}
            ).status_code
            == 204
        )
        assert admin.get("/api/transactions").json()["total"] == 9
    finally:
        app.dependency_overrides.clear()
