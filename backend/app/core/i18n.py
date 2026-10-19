"""界面语言：中文 / English。

每个请求的语言由中间件从 Cookie `wp_locale`（前端切换语言时写入）或 Accept-Language 读出，
放进上下文变量；展示层函数用 `L(中文, English)` 取当前语言的文字，不必层层传参。
Agent 在同一请求上下文中运行，工具输出也随之切换语言。
"""

from collections.abc import Iterator
from contextlib import contextmanager
from contextvars import ContextVar
from typing import Literal

Locale = Literal["zh", "en"]
COOKIE = "wp_locale"

_current: ContextVar[Locale] = ContextVar("locale", default="zh")


def current() -> Locale:
    return _current.get()


def is_en() -> bool:
    return _current.get() == "en"


def L(zh: str, en: str) -> str:  # noqa: N802  与界面文案对照阅读时更直观
    return en if _current.get() == "en" else zh


@contextmanager
def use_locale(locale: Locale) -> Iterator[None]:
    token = _current.set(locale)
    try:
        yield
    finally:
        _current.reset(token)


def parse_locale(cookie: str | None, accept_language: str | None) -> Locale:
    if cookie in ("zh", "en"):
        return cookie  # type: ignore[return-value]
    if accept_language and accept_language.lower().startswith("en"):
        return "en"
    return "zh"


class LocaleMiddleware:
    """纯 ASGI 中间件：在调用下游之前设置上下文变量，同步接口在线程池中运行时也能读到。"""

    def __init__(self, app):
        self.app = app

    async def __call__(self, scope, receive, send):
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return
        headers = {k.decode().lower(): v.decode() for k, v in scope.get("headers", [])}
        cookies = dict(
            part.strip().split("=", 1)
            for part in headers.get("cookie", "").split(";")
            if "=" in part
        )
        with use_locale(parse_locale(cookies.get(COOKIE), headers.get("accept-language"))):
            await self.app(scope, receive, send)


# 模块级常量的英文对照：常量本身保持中文（测试、比较都基于它），使用处用 localized() 取当前语言
_EN: dict[str, str] = {}


def register(zh: str, en: str) -> str:
    """登记一对中英文，返回中文原文（作为常量值）。"""
    _EN[zh] = en
    return zh


def localized(text: str) -> str:
    return _EN.get(text, text) if is_en() else text


def all_versions(text: str) -> set[str]:
    """某个常量的所有语言版本（用于判断回答是否为固定话术）。"""
    return {text, _EN.get(text, text)}
