from __future__ import annotations

import importlib.util
import sys
from collections.abc import Iterator
from pathlib import Path
from types import ModuleType

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import Engine
from sqlalchemy.orm import Session, sessionmaker

import app.models  # noqa: F401
from app.api.deps import get_llm
from app.auth import COOKIE_NAME, create_session, hash_password
from app.categories import seed_categories
from app.categorization.seed_rules import seed_merchant_rules
from app.config import REPO_ROOT
from app.db import Base, get_db, make_engine
from app.models import Account, User
from app.services.llm import FakeLLMClient, LLMClient

SAMPLES_DIR = REPO_ROOT / "samples" / "synthetic"
GENERATOR_PATH = REPO_ROOT / "samples" / "generate.py"

CORPUS_KEY = pytest.StashKey[list[tuple[str, bool]]]()


# ------------------------------------------------------------------ corpus report


def pytest_configure(config: pytest.Config) -> None:
    config.stash[CORPUS_KEY] = []


def pytest_terminal_summary(terminalreporter, exitstatus, config: pytest.Config) -> None:  # type: ignore[no-untyped-def]
    results = config.stash.get(CORPUS_KEY, [])
    if not results:
        return
    passed = sum(1 for _, ok in results if ok)
    tr = terminalreporter
    tr.section("synthetic statement corpus")
    for name, ok in sorted(results):
        tr.write_line(f"  {'PASS' if ok else 'FAIL'}  {name}")
    tr.write_line(f"  pass rate: {passed}/{len(results)} ({passed / len(results):.0%})")


@pytest.fixture
def corpus_results(request: pytest.FixtureRequest) -> list[tuple[str, bool]]:
    return request.config.stash[CORPUS_KEY]


# ------------------------------------------------------------------------ db/app


@pytest.fixture
def engine() -> Iterator[Engine]:
    eng = make_engine("sqlite://")
    Base.metadata.create_all(eng)
    with Session(eng) as s:
        seed_categories(s)
        seed_merchant_rules(s)
        s.commit()
    yield eng
    eng.dispose()


@pytest.fixture
def db(engine: Engine) -> Iterator[Session]:
    with Session(engine, expire_on_commit=False) as session:
        yield session


TEST_PASSWORD = "correct-horse-battery"


def make_user(db: Session, email: str, *, is_admin: bool = False) -> User:
    user = User(email=email, password_hash=hash_password(TEST_PASSWORD), is_admin=is_admin)
    db.add(user)
    db.commit()
    return user


@pytest.fixture
def user(db: Session) -> User:
    """The owner used by most tests (the first, admin user)."""
    return make_user(db, "owner@example.com", is_admin=True)


@pytest.fixture
def account(db: Session, user: User) -> Account:
    acct = Account(
        bank_name="Example Bank", nickname="Main", currency="USD", last4="1234", user_id=user.id
    )
    db.add(acct)
    db.commit()
    return acct


@pytest.fixture
def fake_llm() -> FakeLLMClient:
    return FakeLLMClient.from_samples_dir(SAMPLES_DIR)


@pytest.fixture
def llm_override(fake_llm: FakeLLMClient) -> dict[str, LLMClient]:
    """Mutable holder so a test can swap the LLM client used by the API."""
    return {"client": fake_llm}


@pytest.fixture
def anon_client(engine: Engine, llm_override: dict[str, LLMClient]) -> Iterator[TestClient]:
    """API client with no session (for auth tests)."""
    from app.main import app

    factory = sessionmaker(bind=engine, expire_on_commit=False)

    def _db() -> Iterator[Session]:
        with factory() as s:
            yield s

    app.dependency_overrides[get_db] = _db
    app.dependency_overrides[get_llm] = lambda: llm_override["client"]
    with TestClient(app) as c:
        yield c
    app.dependency_overrides.clear()


def signed_in(client: TestClient, db: Session, user: User) -> TestClient:
    """Put a fresh session cookie for `user` on `client`."""
    token = create_session(db, user, days=1)
    db.commit()
    client.cookies.set(COOKIE_NAME, token)
    return client


@pytest.fixture
def client(anon_client: TestClient, db: Session, user: User) -> TestClient:
    """API client signed in as `user` (the owner)."""
    return signed_in(anon_client, db, user)


@pytest.fixture
def other_client(engine: Engine, db: Session, client: TestClient) -> Iterator[TestClient]:
    """A second, independent client signed in as a different (non-admin) user."""
    from app.main import app

    other = make_user(db, "other@example.com")
    with TestClient(app) as c:
        yield signed_in(c, db, other)


@pytest.fixture(scope="session")
def generator() -> ModuleType:
    """The samples/generate.py module (it lives outside the backend package)."""
    spec = importlib.util.spec_from_file_location("sample_generator", GENERATOR_PATH)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module  # dataclasses resolve annotations via sys.modules
    spec.loader.exec_module(module)
    return module


def truth_files() -> list[Path]:
    return sorted(SAMPLES_DIR.glob("*.truth.json"))


@pytest.fixture(autouse=True)
def _reset_rate_limits() -> Iterator[None]:
    """Rate limits are process-wide; give every test a clean slate."""
    from app.ratelimit import auth_limiter, upload_limiter

    auth_limiter.reset()
    upload_limiter.reset()
    yield
