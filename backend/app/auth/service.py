"""账号与服务端会话。

- 会话令牌是 32 字节随机数，只在 Cookie 中出现；数据库只存 SHA-256，泄露也无法冒用。
- 会话有绝对有效期和闲置超时；退出登录、账号停用都会立即失效（JWT 做不到即时吊销）。
- 演示账号在启动时按配置创建；真实系统应对接银行统一身份认证（SSO），并增加多因素认证。
"""

import hashlib
import secrets
from dataclasses import dataclass
from datetime import datetime, timedelta

from sqlalchemy import select, update
from sqlalchemy.orm import Session

from app.auth.passwords import DUMMY_HASH, hash_password, verify_password
from app.core.config import get_settings
from app.db.models import AuthSession, User

CUSTOMER = "customer"
RM = "rm"
OPS = "ops"  # 运维 / 合规值班：只看汇总指标与审计编号，不看对话内容与客户资料


@dataclass(frozen=True)
class CurrentUser:
    id: str
    username: str
    display_name: str
    role: str
    customer_id: str | None = None
    rm_id: str | None = None


def _digest(token: str) -> str:
    return hashlib.sha256(token.encode()).hexdigest()


def _current(user: User) -> CurrentUser:
    return CurrentUser(
        id=user.id,
        username=user.username,
        display_name=user.display_name,
        role=user.role,
        customer_id=user.customer_id,
        rm_id=user.rm_id,
    )


def ensure_demo_accounts(db: Session) -> None:
    """按配置创建缺失的演示账号（已存在的不改动）。"""
    settings = get_settings()
    existing = set(db.scalars(select(User.username)))
    for account in settings.demo_accounts:
        if account["username"] in existing:
            continue
        db.add(
            User(
                username=account["username"],
                display_name=account["display_name"],
                role=account["role"],
                customer_id=account.get("customer_id"),
                rm_id=account.get("rm_id"),
                password_hash=hash_password(settings.demo_password.get_secret_value()),
            )
        )
    db.commit()


def authenticate(db: Session, username: str, password: str) -> CurrentUser | None:
    user = db.scalars(select(User).where(User.username == username.strip().lower())).first()
    if user is None or user.disabled:
        verify_password(password, DUMMY_HASH)  # 与真实校验同等耗时
        return None
    return _current(user) if verify_password(password, user.password_hash) else None


APP_USER_PREFIX = "app:"
APP_ONLY_PASSWORD = "!app-entry-only"  # 不是合法哈希，任何密码都无法通过校验


def app_customer(db: Session, customer_id: str) -> CurrentUser:
    """经手机银行进入的客户：首次进入时自动开户（JIT provisioning），账号没有密码，只能经 App 进入。

    客户身份由银行核验（凭证签名），WealthPilot 不接触客户的银行登录密码。
    """
    from app.customers.base import get_customer_info_system

    base = get_customer_info_system().get(customer_id)
    if base is None:
        raise ValueError(f"unknown customer {customer_id}")
    username = f"{APP_USER_PREFIX}{customer_id}"
    user = db.scalars(select(User).where(User.username == username)).first()
    if user is None:
        user = User(
            username=username,
            display_name=base.display_name,
            role=CUSTOMER,
            customer_id=customer_id,
            password_hash=APP_ONLY_PASSWORD,
        )
        db.add(user)
        db.flush()
    if user.disabled:
        raise ValueError(f"disabled customer {customer_id}")
    return _current(user)


def create_session(db: Session, user: CurrentUser, now: datetime) -> str:
    token = secrets.token_urlsafe(32)
    ttl = timedelta(hours=get_settings().session_ttl_hours)
    db.add(
        AuthSession(
            id=_digest(token),
            user_id=user.id,
            created_at=now,
            last_seen_at=now,
            expires_at=now + ttl,
        )
    )
    db.commit()
    return token


def resolve_session(db: Session, token: str, now: datetime) -> CurrentUser | None:
    """校验会话并刷新最近活动时间；过期、闲置超时、已吊销或账号停用都返回 None。"""
    session = db.get(AuthSession, _digest(token))
    if session is None or session.revoked_at is not None or session.expires_at <= now:
        return None
    idle = timedelta(minutes=get_settings().session_idle_minutes)
    if session.last_seen_at + idle <= now:
        return None
    user = db.get(User, session.user_id)
    if user is None or user.disabled:
        return None
    session.last_seen_at = now
    db.commit()
    return _current(user)


def revoke_session(db: Session, token: str, now: datetime) -> None:
    db.execute(
        update(AuthSession)
        .where(AuthSession.id == _digest(token), AuthSession.revoked_at.is_(None))
        .values(revoked_at=now)
    )
    db.commit()
