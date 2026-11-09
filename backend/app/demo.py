"""Build a demo database from the synthetic corpus only (safe for public demos).

    python -m app.demo            # creates backend/demo.db
    python -m app.demo --reset    # delete and rebuild it

It uses the offline fake LLM, so it makes no network calls. It always writes to its own fixed
file (backend/demo.db) and never to DATABASE_URL, so demo data cannot mix with your real ledger.
"""

from __future__ import annotations

import argparse
import json
import secrets
from pathlib import Path

from alembic import command
from alembic.config import Config
from sqlalchemy.orm import Session

from app.auth import hash_password
from app.config import BACKEND_DIR, get_settings
from app.db import make_engine
from app.ingestion.pipeline import DuplicateFileError, ingest
from app.models import Account, User
from app.services.llm import FakeLLMClient

DEMO_DB = BACKEND_DIR / "demo.db"
DEMO_URL = f"sqlite:///{DEMO_DB.as_posix()}"


def build_demo(samples_dir: Path, url: str = DEMO_URL) -> list[tuple[str, str]]:
    cfg = Config(str(BACKEND_DIR / "alembic.ini"))
    cfg.set_main_option("script_location", str(BACKEND_DIR / "alembic"))
    cfg.attributes["database_url"] = url
    cfg.attributes["configure_logger"] = False
    command.upgrade(cfg, "head")

    llm = FakeLLMClient.from_samples_dir(samples_dir)
    engine = make_engine(url)
    results: list[tuple[str, str]] = []
    with Session(engine, expire_on_commit=False) as db:
        # Everyone using demo mode is signed in as this user (see api/deps.current_user).
        demo_user = User(
            email="demo@example.com",
            password_hash=hash_password(secrets.token_urlsafe(24)),
            is_admin=False,
        )
        db.add(demo_user)
        db.flush()
        for truth_path in sorted(samples_dir.glob("*.truth.json")):
            truth = json.loads(truth_path.read_text(encoding="utf-8"))
            currency = truth["mapping"]["currency"]
            account = Account(
                bank_name="Synthetic Bank",
                nickname=truth["layout"],
                currency=currency,
                user_id=demo_user.id,
            )
            db.add(account)
            db.commit()
            data = (samples_dir / truth["file"]).read_bytes()
            try:
                imp = ingest(db, llm, account, data, truth["file"])
                results.append((truth["layout"], imp.status.value))
            except DuplicateFileError:
                results.append((truth["layout"], "duplicate"))
    engine.dispose()
    return results


def main() -> None:
    parser = argparse.ArgumentParser(description="Build the synthetic demo database.")
    parser.add_argument("--reset", action="store_true", help="delete demo.db first")
    args = parser.parse_args()

    settings = get_settings()
    if args.reset and DEMO_DB.exists():
        DEMO_DB.unlink()
    if DEMO_DB.exists():
        raise SystemExit(f"{DEMO_DB} already exists; use --reset to rebuild it")

    for layout, status in build_demo(settings.samples_dir):
        print(f"  {status:13s} {layout}")
    print(f"\nDemo database ready: {DEMO_DB}")
    print("Run the API against it with:  .\\scripts\\dev.ps1 demo")


if __name__ == "__main__":
    main()
