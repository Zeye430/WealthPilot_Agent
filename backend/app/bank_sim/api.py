"""模拟手机银行接口：登录（银行自己的账号）、首页数据、签发理财助手进入凭证、退出。

会话用银行自己的 Cookie（zabank_session，HMAC 签名、httpOnly），与 WealthPilot 的会话完全独立。
"""

import hashlib
import hmac
import secrets
import time
from datetime import datetime

from fastapi import APIRouter, Depends, HTTPException, Request, Response
from pydantic import BaseModel, Field

from app.api.deps import get_now
from app.auth import app_ticket
from app.benefits.service import tier_status
from app.core.config import get_settings
from app.core.i18n import L, current
from app.core.ratelimit import login_limit
from app.customers.base import get_customer_info_system

router = APIRouter(prefix="/bank-sim/api", tags=["bank-sim（模拟手机银行）"])

BANK_COOKIE = "zabank_session"
SESSION_SECONDS = 30 * 60
# 银行自己的会话签名密钥：与凭证密钥无关；每次启动随机生成（演示环境重启后需重新登录手机银行）
_BANK_KEY = secrets.token_bytes(32)


class BankLogin(BaseModel):
    username: str = Field(min_length=1, max_length=64)
    password: str = Field(min_length=1, max_length=128)


def _enabled() -> None:
    if not get_settings().bank_sim_enabled:
        raise HTTPException(status_code=404)


def _sign(value: str) -> str:
    return hmac.new(_BANK_KEY, value.encode(), hashlib.sha256).hexdigest()


def _bank_customers() -> dict[str, str]:
    """银行的客户账号（演示：与演示账号同名的客户）。真实环境是银行的统一身份认证。"""
    return {
        a["username"]: a["customer_id"]
        for a in get_settings().demo_accounts
        if a["role"] == "customer"
    }


def bank_customer(request: Request) -> str:
    """当前登录手机银行的客户编号（来自银行会话 Cookie）。"""
    _enabled()
    raw = request.cookies.get(BANK_COOKIE, "")
    try:
        customer_id, expires, signature = raw.split("|")
        valid = hmac.compare_digest(signature, _sign(f"{customer_id}|{expires}"))
        if valid and int(expires) > time.time():
            return customer_id
    except ValueError:
        pass
    raise HTTPException(
        status_code=401, detail=L("请先登录手机银行", "Please sign in to the banking app")
    )


@router.post("/login")
def bank_login(req: BankLogin, request: Request, response: Response):
    _enabled()
    login_limit(request, f"bank:{req.username}")
    customer_id = _bank_customers().get(req.username.strip().lower())
    password_ok = hmac.compare_digest(req.password, get_settings().demo_password.get_secret_value())
    if customer_id is None or not password_ok:
        raise HTTPException(
            status_code=401,
            detail=L("账号或密码不正确", "Incorrect username or password"),
        )
    expires = str(int(time.time()) + SESSION_SECONDS)
    value = f"{customer_id}|{expires}"
    response.set_cookie(
        BANK_COOKIE,
        f"{value}|{_sign(value)}",
        max_age=SESSION_SECONDS,
        httponly=True,
        secure=get_settings().cookie_secure,
        samesite="lax",
        path="/",
    )
    return {"ok": True}


@router.post("/logout", status_code=204)
def bank_logout(response: Response):
    response.delete_cookie(BANK_COOKIE, path="/")


@router.get("/home")
def bank_home(customer_id: str = Depends(bank_customer)):
    """手机银行首页：账户概览（来自银行核心系统）。"""
    base = get_customer_info_system().get(customer_id)
    if base is None:
        raise HTTPException(status_code=404)
    assets = base.assets_at_bank
    status = tier_status(base)
    return {
        "name": base.localized_name,
        "tier": status.tier.display_name,
        "card": status.tier.display_card,
        # 虚构的卡号尾号（由客户编号派生，固定不变）
        "card_tail": f"{int(hashlib.sha256(customer_id.encode()).hexdigest(), 16) % 10000:04d}",
        "demand_deposit": float(assets.demand_deposit),
        "time_deposit": float(assets.time_deposit),
        "wealth": float(sum((h.amount for h in assets.wealth_products), start=0)),
        "total": float(assets.total),
    }


@router.post("/assistant-ticket")
def assistant_ticket(customer_id: str = Depends(bank_customer), now: datetime = Depends(get_now)):
    """客户点击「AI 理财助手」：银行后台签发一次性进入凭证（默认 60 秒有效）。"""
    ticket = app_ticket.issue(customer_id, now, current())
    return {"ticket": ticket, "expires_in": get_settings().app_ticket_ttl_seconds}
