"""Rate limiting: in-memory sliding window counting per "bucket + key" (the key is a user ID or IP).

Enough for a single instance; counts aren't shared across instances, so use Redis then (same
interface).
Over the limit returns 429 with Retry-After, so customers get a clear message instead of waiting.
"""

import time
from collections import defaultdict, deque
from threading import Lock

from fastapi import HTTPException, Request

from app.auth.service import CurrentUser
from app.core.config import get_settings
from app.core.i18n import L


class SlidingWindowLimiter:
    def __init__(self):
        self._hits: dict[tuple[str, str, int], deque[float]] = defaultdict(deque)
        self._lock = Lock()

    def check(self, bucket: str, key: str, limit: int, window_seconds: int) -> int | None:
        """Under the limit, record one hit and return None; over it, return the seconds to wait."""
        now = time.monotonic()
        with self._lock:
            hits = self._hits[(bucket, key, window_seconds)]
            while hits and hits[0] <= now - window_seconds:
                hits.popleft()
            if len(hits) >= limit:
                return max(int(hits[0] + window_seconds - now) + 1, 1)
            hits.append(now)
            return None

    def reset(self) -> None:
        with self._lock:
            self._hits.clear()


limiter = SlidingWindowLimiter()


def enforce(bucket: str, key: str, rules: list[tuple[int, int]]) -> None:
    """rules: [(max hits, window seconds)]; exceeding any of them rejects the request."""
    if not get_settings().rate_limit_enabled:
        return
    for limit, window in rules:
        if (wait := limiter.check(bucket, key, limit, window)) is not None:
            raise HTTPException(
                status_code=429,
                detail=L("操作太频繁，请稍后再试", "Too many requests. Please try again shortly."),
                headers={"Retry-After": str(wait)},
            )


def client_ip(request: Request) -> str:
    # Behind a reverse proxy, the proxy writes X-Forwarded-For; take only the first address
    forwarded = request.headers.get("x-forwarded-for")
    if forwarded:
        return forwarded.split(",")[0].strip()
    return request.client.host if request.client else "unknown"


def chat_limit(user: CurrentUser) -> None:
    s = get_settings()
    enforce(
        "chat", user.id, [(s.rate_limit_chat_per_minute, 60), (s.rate_limit_chat_per_day, 86400)]
    )


def speech_limit(user: CurrentUser) -> None:
    enforce("speech", user.id, [(get_settings().rate_limit_speech_per_minute, 60)])


def login_limit(request: Request, username: str) -> None:
    per_minute = get_settings().rate_limit_login_per_minute
    enforce("login-ip", client_ip(request), [(per_minute, 60)])
    # against brute force on one account
    enforce("login-user", username.strip().lower(), [(per_minute, 900)])
