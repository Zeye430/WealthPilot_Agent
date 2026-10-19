"""手机银行 App 进入凭证（app ticket）：客户在银行 App 中已登录，点击「AI 理财助手」时，
银行后台签发一张短期、一次性的凭证，WealthPilot 核验后建立自己的会话，客户无需再次输入密码。

格式：base64url(载荷 JSON) + "." + base64url(HMAC-SHA256 签名)
载荷：iss 签发方、aud 接收方、sub 客户编号、iat / exp 签发与过期时间、jti 唯一编号、locale 界面语言

核验项：签名（常数时间比较）、签发方、接收方、有效期（允许 10 秒时钟偏差）、一次性（jti 写入数据库，
重复使用即拒绝，多实例部署同样有效）。

演示用双方共享的 HMAC 密钥；生产中常见做法是银行用私钥签名（如 RS256 / ES256 的 JWT），
WealthPilot 只持有公钥，即使 WealthPilot 被攻破也无法伪造凭证。
"""

import base64
import hashlib
import hmac
import json
import secrets
from dataclasses import dataclass
from datetime import datetime, timedelta

from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.db.models import UsedAppTicket

ISSUER = "zhian-bank-app"
AUDIENCE = "wealthpilot"
CLOCK_SKEW = timedelta(seconds=10)


class TicketError(ValueError):
    """凭证无效。原因只写日志，不返回给前端细节（避免帮助攻击者调试）。"""


@dataclass(frozen=True)
class AppTicket:
    customer_id: str
    jti: str
    expires_at: datetime
    locale: str


def _b64(data: bytes) -> str:
    return base64.urlsafe_b64encode(data).rstrip(b"=").decode()


def _unb64(text: str) -> bytes:
    return base64.urlsafe_b64decode(text + "=" * (-len(text) % 4))


def _sign(payload: bytes) -> str:
    key = get_settings().app_ticket_secret.get_secret_value().encode()
    return _b64(hmac.new(key, payload, hashlib.sha256).digest())


def issue(customer_id: str, now: datetime, locale: str = "zh") -> str:
    """签发凭证。生产中由银行后台执行，这里供模拟的银行系统（app/bank_sim）与测试使用。"""
    ttl = get_settings().app_ticket_ttl_seconds
    payload = {
        "iss": ISSUER,
        "aud": AUDIENCE,
        "sub": customer_id,
        "iat": int(now.timestamp()),
        "exp": int(now.timestamp()) + ttl,
        "jti": secrets.token_hex(16),
        "locale": locale if locale in ("zh", "en") else "zh",
    }
    body = json.dumps(payload, separators=(",", ":"), sort_keys=True).encode()
    return f"{_b64(body)}.{_sign(body)}"


def verify(token: str, now: datetime) -> AppTicket:
    try:
        body_part, signature = token.split(".")
        body = _unb64(body_part)
    except (ValueError, TypeError) as exc:
        raise TicketError("malformed") from exc
    if not hmac.compare_digest(signature, _sign(body)):
        raise TicketError("bad signature")
    try:
        payload = json.loads(body)
        issued = datetime.fromtimestamp(int(payload["iat"]), now.tzinfo)
        expires = datetime.fromtimestamp(int(payload["exp"]), now.tzinfo)
        ticket = AppTicket(
            customer_id=str(payload["sub"]),
            jti=str(payload["jti"]),
            expires_at=expires,
            locale=payload.get("locale", "zh"),
        )
    except (ValueError, KeyError, TypeError) as exc:
        raise TicketError("bad payload") from exc
    if payload.get("iss") != ISSUER or payload.get("aud") != AUDIENCE:
        raise TicketError("wrong issuer or audience")
    if now > expires + CLOCK_SKEW or issued > now + CLOCK_SKEW:
        raise TicketError("expired or not yet valid")
    return ticket


def consume(db: Session, ticket: AppTicket, now: datetime) -> None:
    """标记凭证已使用；同一凭证第二次使用时主键冲突，视为重放。"""
    db.add(UsedAppTicket(jti=ticket.jti, used_at=now, expires_at=ticket.expires_at))
    try:
        db.flush()
    except IntegrityError as exc:
        db.rollback()
        raise TicketError("replayed") from exc
