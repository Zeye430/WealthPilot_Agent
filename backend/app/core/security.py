"""HTTP 层安全：跨站写请求检查、安全响应头、日志脱敏。"""

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
    # 只允许本站使用麦克风（语音输入），禁用摄像头、定位等
    "Permissions-Policy": "microphone=(self), camera=(), geolocation=()",
    "Cache-Control": "no-store",  # 接口返回客户数据，不允许缓存
}


class SecurityMiddleware(BaseHTTPMiddleware):
    """写请求若带有 Origin，必须来自允许的前端来源（配合 SameSite Cookie 防 CSRF）。"""

    async def dispatch(self, request: Request, call_next) -> Response:
        origin = request.headers.get("origin")
        if (
            request.method in UNSAFE_METHODS
            and origin
            and origin not in get_settings().cors_origins
        ):
            return JSONResponse({"detail": "来源不被允许"}, status_code=403)
        response = await call_next(request)
        for name, value in SECURITY_HEADERS.items():
            response.headers.setdefault(name, value)
        return response


# 日志脱敏：手机号、身份证号、银行卡号（演示系统不采集这些信息，这里是防御性措施）
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
        # 先按原格式拼好完整消息再脱敏，避免破坏第三方库的 %d 等格式化参数
        record.msg = redact(record.getMessage())
        record.args = None
        return True
