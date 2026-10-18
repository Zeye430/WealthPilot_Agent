"""限流：内存滑动窗口，按「桶 + 键」计数（键为用户编号或 IP）。

单实例部署足够；多实例时计数不共享，应换成 Redis（接口保持不变）。
超限返回 429 与 Retry-After，客户看到明确提示，而不是一直等待。
"""

import time
from collections import defaultdict, deque
from threading import Lock

from fastapi import HTTPException, Request

from app.auth.service import CurrentUser
from app.core.config import get_settings


class SlidingWindowLimiter:
    def __init__(self):
        self._hits: dict[tuple[str, str, int], deque[float]] = defaultdict(deque)
        self._lock = Lock()

    def check(self, bucket: str, key: str, limit: int, window_seconds: int) -> int | None:
        """未超限时记一次并返回 None；超限时返回需要等待的秒数。"""
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
    """rules: [(次数上限, 窗口秒数)]，任一超限即拒绝。"""
    if not get_settings().rate_limit_enabled:
        return
    for limit, window in rules:
        if (wait := limiter.check(bucket, key, limit, window)) is not None:
            raise HTTPException(
                status_code=429,
                detail="操作太频繁，请稍后再试",
                headers={"Retry-After": str(wait)},
            )


def client_ip(request: Request) -> str:
    # 部署在反向代理后时，由代理写入 X-Forwarded-For；这里只取第一个地址
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
    enforce("login-user", username.strip().lower(), [(per_minute, 900)])  # 防针对单个账号的暴力破解
