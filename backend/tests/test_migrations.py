"""Alembic migrations must build exactly the schema the ORM models describe."""

from __future__ import annotations

from pathlib import Path

from alembic import command
from alembic.autogenerate import compare_metadata
from alembic.config import Config
from alembic.migration import MigrationContext
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.categories import CATEGORY_TREE
from app.config import BACKEND_DIR
from app.db import Base, make_engine
from app.models import Category


def _config(url: str) -> Config:
    cfg = Config(str(BACKEND_DIR / "alembic.ini"))
    cfg.set_main_option("script_location", str(BACKEND_DIR / "alembic"))
    cfg.attributes["database_url"] = url
    cfg.attributes["configure_logger"] = False
    return cfg


def test_upgrade_matches_models_and_seeds_categories(tmp_path: Path) -> None:
    url = f"sqlite:///{(tmp_path / 'm.db').as_posix()}"
    cfg = _config(url)
    command.upgrade(cfg, "head")

    engine = make_engine(url)
    with engine.connect() as conn:
        ctx = MigrationContext.configure(conn, opts={"compare_type": True})
        diff = compare_metadata(ctx, Base.metadata)
    assert diff == [], diff

    with Session(engine) as s:
        groups = s.scalars(select(Category).where(Category.parent_id.is_(None))).all()
        assert {g.name for g in groups} == {name for name, _, _ in CATEGORY_TREE}
        total = len(s.scalars(select(Category)).all())
        assert total == sum(1 + len(children) for _, _, children in CATEGORY_TREE)
    engine.dispose()

    command.downgrade(cfg, "base")
