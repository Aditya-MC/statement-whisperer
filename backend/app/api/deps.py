"""Shared FastAPI dependencies (overridable in tests)."""

from __future__ import annotations

from functools import lru_cache

from app.config import get_settings
from app.services.llm import LLMClient, build_llm_client


@lru_cache
def _cached_llm() -> LLMClient:
    return build_llm_client(get_settings())


def get_llm() -> LLMClient:
    return _cached_llm()
