"""Application settings, loaded from environment variables and the repo-root `.env` file."""

from __future__ import annotations

from functools import lru_cache
from pathlib import Path
from typing import Literal

from pydantic import Field, SecretStr
from pydantic_settings import BaseSettings, SettingsConfigDict

BACKEND_DIR = Path(__file__).resolve().parent.parent
REPO_ROOT = BACKEND_DIR.parent


class Settings(BaseSettings):
    """Runtime configuration. Every field can be overridden by an env var of the same name."""

    model_config = SettingsConfigDict(
        env_file=(REPO_ROOT / ".env", BACKEND_DIR / ".env"),
        env_file_encoding="utf-8",
        extra="ignore",
    )

    database_url: str = f"sqlite:///{(BACKEND_DIR / 'ledger.db').as_posix()}"

    #: "none" turns automatic detection off (manual column mapping, rule-based categories).
    llm_provider: Literal["anthropic", "fake", "none"] = "anthropic"
    anthropic_api_key: SecretStr | None = None
    llm_model: str = "claude-opus-5-5"
    llm_effort: Literal["low", "medium", "high", "xhigh", "max"] = "medium"
    llm_timeout_seconds: float = 60.0

    max_upload_mb: int = Field(default=20, ge=1, le=200)

    # --- accounts & sessions
    #: Only this email may create the very first (admin) account. Leave unset for local use,
    #: where the first sign-up becomes admin. Always set it on a public server.
    admin_email: str | None = None
    #: Send the session cookie over HTTPS only. Must be true when deployed.
    cookie_secure: bool = False
    session_days: int = Field(default=30, ge=1, le=365)

    demo_mode: bool = False
    samples_dir: Path = REPO_ROOT / "samples" / "synthetic"
    #: Built React app. Served at "/" when present (production/Docker); dev uses Vite on :5173.
    frontend_dist: Path = REPO_ROOT / "frontend" / "dist"
    log_level: str = "INFO"

    @property
    def max_upload_bytes(self) -> int:
        return self.max_upload_mb * 1024 * 1024


@lru_cache
def get_settings() -> Settings:
    return Settings()
