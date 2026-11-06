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
from app.categorization.categorizer import load_category_index
from app.categorization.seed_rules import SEED_RULES
from app.config import BACKEND_DIR
from app.db import Base, make_engine
from app.models import Category, MerchantRule, RuleSource


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

        # Seed merchant rules in migration 0003 match app/categorization/seed_rules.py.
        idx = load_category_index(s)
        path_by_id = {i: p for p, i in idx.by_path.items()}
        seeded = {
            (r.pattern, path_by_id[r.category_id])
            for r in s.scalars(select(MerchantRule).where(MerchantRule.source == RuleSource.seed))
        }
        assert seeded == set(SEED_RULES)
    engine.dispose()

    command.downgrade(cfg, "base")


def test_upgrades_preserve_existing_data(tmp_path: Path) -> None:
    """Batch migrations rebuild SQLite tables; existing rows and links must survive.

    Regression test: with foreign keys enforced during the rebuild, adding categories.is_custom
    (0005) cascade-deleted every sub-category and merchant rule.
    """
    from sqlalchemy import text

    url = f"sqlite:///{(tmp_path / 'existing.db').as_posix()}"
    cfg = _config(url)
    command.upgrade(cfg, "0004")
    engine = make_engine(url)
    with engine.begin() as conn:
        conn.execute(
            text(
                "INSERT INTO accounts (id, bank_name, nickname, currency, created_at) "
                "VALUES (1, 'B', 'N', 'INR', '2026-11-06')"
            )
        )
        conn.execute(
            text(
                "INSERT INTO imports (id, account_id, file_hash, file_type, status, parser_version,"
                " row_count, inserted_count, duplicate_count, created_at) "
                "VALUES (1, 1, 'h', 'csv', 'completed', 't', 1, 1, 0, '2026-11-06')"
            )
        )
        groceries = conn.execute(
            text(
                "SELECT c.id FROM categories c JOIN categories p ON c.parent_id = p.id "
                "WHERE p.name = 'Food' AND c.name = 'Groceries'"
            )
        ).scalar_one()
        conn.execute(
            text(
                "INSERT INTO transactions (account_id, import_id, date, amount, type, currency,"
                " raw_narration, row_index, dedupe_hash, category_id, category_source, is_transfer,"
                " transfer_dismissed, created_at) VALUES (1, 1, '2026-10-01', -10, 'debit', 'INR',"
                f" 'X', 0, 'd1', {groceries}, 'user', 0, 0, '2026-11-06')"
            )
        )
        before = {
            "categories": conn.execute(text("SELECT COUNT(*) FROM categories")).scalar_one(),
            "rules": conn.execute(text("SELECT COUNT(*) FROM merchant_rules")).scalar_one(),
        }
    engine.dispose()

    command.upgrade(cfg, "head")

    engine = make_engine(url)
    with engine.connect() as conn:
        assert (
            conn.execute(text("SELECT COUNT(*) FROM categories")).scalar_one()
            == before["categories"]
        )
        assert (
            conn.execute(text("SELECT COUNT(*) FROM merchant_rules")).scalar_one()
            == before["rules"]
        )
        assert conn.execute(text("SELECT category_id FROM transactions")).scalar_one() == groceries
        assert conn.execute(text("PRAGMA foreign_keys")).scalar_one() == 1  # re-enabled
    engine.dispose()
