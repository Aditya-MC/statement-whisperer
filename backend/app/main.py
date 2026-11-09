"""FastAPI application factory."""

from __future__ import annotations

import logging
from collections.abc import Awaitable, Callable
from urllib.parse import urlsplit

from fastapi import FastAPI, Request, Response
from fastapi.responses import JSONResponse
from fastapi.staticfiles import StaticFiles

from app import __version__
from app.api import accounts, analytics, auth, imports, transactions
from app.config import get_settings

_UNSAFE = {"POST", "PUT", "PATCH", "DELETE"}


def create_app() -> FastAPI:
    settings = get_settings()
    logging.basicConfig(
        level=settings.log_level.upper(),
        format="%(asctime)s %(levelname)s %(name)s: %(message)s",
    )
    app = FastAPI(
        title="Statement Whisperer",
        version=__version__,
        description="Bank-agnostic statement ingestion and personal finance ledger.",
    )

    @app.middleware("http")
    async def same_origin_writes(
        request: Request, call_next: Callable[[Request], Awaitable[Response]]
    ) -> Response:
        """Reject state-changing requests sent by another website (CSRF), on top of the
        SameSite=Lax session cookie. Browsers always send Origin on cross-site POSTs."""
        origin = request.headers.get("origin")
        cross_site = origin and urlsplit(origin).netloc != request.headers.get("host", "")
        if request.method in _UNSAFE and cross_site:
            return JSONResponse({"detail": "Cross-site request blocked"}, status_code=403)
        response = await call_next(request)
        response.headers.setdefault("X-Content-Type-Options", "nosniff")
        response.headers.setdefault("Referrer-Policy", "same-origin")
        response.headers.setdefault("X-Frame-Options", "DENY")
        return response

    for router in (
        auth.router,
        accounts.router,
        imports.router,
        transactions.router,
        analytics.router,
    ):
        app.include_router(router, prefix="/api")

    @app.get("/api/health", tags=["meta"])
    def health() -> dict[str, object]:
        return {"status": "ok", "version": __version__, "demo_mode": settings.demo_mode}

    # Mounted last so /api/* routes always win. The frontend has no client-side routes,
    # so plain static serving with index.html is enough.
    if (settings.frontend_dist / "index.html").is_file():
        app.mount("/", StaticFiles(directory=settings.frontend_dist, html=True), name="frontend")

    return app


app = create_app()
