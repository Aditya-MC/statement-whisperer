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
from app.categories import seed_categories
from app.categorization.seed_rules import seed_merchant_rules
from app.config import REPO_ROOT
from app.db import Base, get_db, make_engine
from app.models import Account
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


@pytest.fixture
def account(db: Session) -> Account:
    acct = Account(bank_name="Example Bank", nickname="Main", currency="USD", last4="1234")
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
def client(engine: Engine, llm_override: dict[str, LLMClient]) -> Iterator[TestClient]:
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
