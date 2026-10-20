"""HTTP-layer security: cross-site write checks, security response headers, log redaction."""

import logging
import re

from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import JSONResponse, Response

from app.core.config import get_settings

UNSAFE_METHODS = {"POST", "PUT", "PATCH", "DELETE"}

SECURITY_HEADERS = {
    "X-Content-Type-Options": "nosniff",
    "X-Frame-Options": "DENY",
    "Referrer-Policy": "strict-origin-when-cross-origin",
    # Only this site may use the microphone (voice input); camera, location, etc. are disabled
    "Permissions-Policy": "microphone=(self), camera=(), geolocation=()",
    "Cache-Control": "no-store",  # responses contain customer data and must not be cached
}


class SecurityMiddleware(BaseHTTPMiddleware):
    """A write request with an Origin header must come from an allowed frontend origin (with
    SameSite cookies, this blocks CSRF)."""

    async def dispatch(self, request: Request, call_next) -> Response:
        origin = request.headers.get("origin")
        if (
            request.method in UNSAFE_METHODS
            and origin
            and origin not in get_settings().cors_origins
        ):
            return JSONResponse({"detail": "来源不被允许 / Origin not allowed"}, status_code=403)
        response = await call_next(request)
        for name, value in SECURITY_HEADERS.items():
            response.headers.setdefault(name, value)
        return response


# Log redaction: phone numbers, national ID numbers, bank card numbers (the demo doesn't collect
# them; this is defensive)
PII_PATTERNS = [
    (re.compile(r"(?<!\d)1[3-9]\d{9}(?!\d)"), "[手机号]"),
    (re.compile(r"(?<!\d)\d{17}[\dXx](?!\d)"), "[身份证号]"),
    (re.compile(r"(?<!\d)\d{16,19}(?!\d)"), "[卡号]"),
]


def redact(text: str) -> str:
    for pattern, label in PII_PATTERNS:
        text = pattern.sub(label, text)
    return text


class RedactingFilter(logging.Filter):
    def filter(self, record: logging.LogRecord) -> bool:
        # Format the full message first, then redact, so third-party %d-style arguments aren't
        # broken
        record.msg = redact(record.getMessage())
        record.args = None
        return True
