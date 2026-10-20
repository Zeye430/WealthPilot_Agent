"""UI language: Chinese / English.

Middleware reads each request's language from the `wp_locale` cookie (set when the frontend switches
language) or Accept-Language
and puts it in a context variable; presentation code picks text with `L(Chinese, English)` instead
of passing the language around.
The agent runs in the same request context, so tool output switches language too.
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


def L(zh: str, en: str) -> str:  # noqa: N802  short name reads naturally next to the UI copy
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
    """Pure ASGI middleware: sets the context variable before calling downstream, so sync
    endpoints running in the thread pool can read it."""

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


# English counterparts of module-level constants: the constants stay Chinese (tests and comparisons
# rely on them); use localized() at the point of use
_EN: dict[str, str] = {}


def register(zh: str, en: str) -> str:
    """Register a Chinese/English pair and return the Chinese text (used as the constant value)."""
    _EN[zh] = en
    return zh


def localized(text: str) -> str:
    return _EN.get(text, text) if is_en() else text


def all_versions(text: str) -> set[str]:
    """All language versions of a constant (used to tell whether a reply is a fixed reply)."""
    return {text, _EN.get(text, text)}
