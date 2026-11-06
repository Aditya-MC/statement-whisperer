"""FastAPI application factory."""

from __future__ import annotations

import logging

from fastapi import FastAPI

from app import __version__
from app.api import accounts, imports, transactions
from app.config import get_settings


def create_app() -> FastAPI:
    settings = get_settings()
    logging.basicConfig(
        level=settings.log_level.upper(),
        format="%(asctime)s %(levelname)s %(name)s: %(message)s",
    )
    app = FastAPI(
        title="Bank Statement Analyzer",
        version=__version__,
        description="Bank-agnostic statement ingestion and personal finance ledger.",
    )
    for router in (accounts.router, imports.router, transactions.router):
        app.include_router(router, prefix="/api")

    @app.get("/api/health", tags=["meta"])
    def health() -> dict[str, object]:
        return {"status": "ok", "version": __version__, "demo_mode": settings.demo_mode}

    return app


app = create_app()
