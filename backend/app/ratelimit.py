"""Small in-memory sliding-window rate limits (enough for one server instance).

Used to slow down password guessing on login/sign-up and to cap upload bursts. The limits
live in process memory, so they reset on restart. That's acceptable for a single-instance
beta; several instances would need a shared store (e.g. Redis).
"""

from __future__ import annotations

import threading
import time
from collections import deque

from fastapi import Depends, HTTPException, Request, status

from app.api.deps import current_user
from app.models import User


class RateLimiter:
    def __init__(self, limit: int, window_seconds: float) -> None:
        self.limit = limit
        self.window = window_seconds
        self._hits: dict[str, deque[float]] = {}
        self._lock = threading.Lock()

    def allow(self, key: str, now: float | None = None) -> bool:
        now = time.monotonic() if now is None else now
        cutoff = now - self.window
        with self._lock:
            q = self._hits.setdefault(key, deque())
            while q and q[0] <= cutoff:
                q.popleft()
            if len(q) >= self.limit:
                return False
            q.append(now)
            if len(self._hits) > 10_000:  # forget idle keys so memory stays bounded
                for k in [k for k, v in self._hits.items() if not v or v[-1] <= cutoff]:
                    del self._hits[k]
            return True

    def reset(self) -> None:
        with self._lock:
            self._hits.clear()


#: Password attempts per client IP (login + sign-up).
auth_limiter = RateLimiter(limit=10, window_seconds=15 * 60)
#: Statement uploads per user.
upload_limiter = RateLimiter(limit=60, window_seconds=60 * 60)


def _too_many(message: str) -> HTTPException:
    return HTTPException(status.HTTP_429_TOO_MANY_REQUESTS, message, headers={"Retry-After": "900"})


def limit_auth(request: Request) -> None:
    # Behind Render's proxy, uvicorn --proxy-headers puts the real client IP here.
    ip = request.client.host if request.client else "unknown"
    if not auth_limiter.allow(ip):
        raise _too_many("Too many attempts. Please wait a few minutes and try again.")


def limit_upload(user: User = Depends(current_user)) -> None:
    if not upload_limiter.allow(str(user.id)):
        raise _too_many("Upload limit reached for now. Please try again later.")
