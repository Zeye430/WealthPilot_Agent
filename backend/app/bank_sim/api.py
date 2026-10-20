"""Simulated mobile banking API: sign-in (the bank's own accounts), home screen data, issuing
assistant entry tickets, sign-out.

Sessions use the bank's own cookie (zabank_session, HMAC-signed, httpOnly), fully separate from
WealthPilot's session.
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
# The bank's own session signing key: unrelated to the ticket key; random at every start (the demo
# bank app needs a new sign-in after a restart)
_BANK_KEY = secrets.token_bytes(32)


class BankLogin(BaseModel):
    username: str = Field(min_length=1, max_length=64)
    password: str = Field(min_length=1, max_length=128)
    access_code: str | None = Field(default=None, max_length=64)


def _enabled() -> None:
    if not get_settings().bank_sim_enabled:
        raise HTTPException(status_code=404)


def _sign(value: str) -> str:
    return hmac.new(_BANK_KEY, value.encode(), hashlib.sha256).hexdigest()


def _bank_customers() -> dict[str, str]:
    """The bank's customer accounts (demo: customers with the same names as the demo accounts).
    In reality, the bank's single sign-on."""
    return {
        a["username"]: a["customer_id"]
        for a in get_settings().demo_accounts
        if a["role"] == "customer"
    }


def bank_customer(request: Request) -> str:
    """Customer ID of the customer signed in to the banking app (from the bank session cookie)."""
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
    # When the public demo sets an access code, the simulated banking app requires it too
    # (otherwise it could be used to bypass the code, reach the assistant and burn model credits)
    code = get_settings().demo_access_code
    if code is not None and not hmac.compare_digest(
        (req.access_code or "").strip(), code.get_secret_value()
    ):
        raise HTTPException(status_code=401, detail=L("访问码不正确", "Incorrect access code"))
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
    """Banking app home screen: account overview (from the bank's core system)."""
    base = get_customer_info_system().get(customer_id)
    if base is None:
        raise HTTPException(status_code=404)
    assets = base.assets_at_bank
    status = tier_status(base)
    return {
        "name": base.localized_name,
        "tier": status.tier.display_name,
        "card": status.tier.display_card,
        # Fictional card-number suffix (derived from the customer ID, stable)
        "card_tail": f"{int(hashlib.sha256(customer_id.encode()).hexdigest(), 16) % 10000:04d}",
        "demand_deposit": float(assets.demand_deposit),
        "time_deposit": float(assets.time_deposit),
        "wealth": float(sum((h.amount for h in assets.wealth_products), start=0)),
        "total": float(assets.total),
    }


@router.post("/assistant-ticket")
def assistant_ticket(customer_id: str = Depends(bank_customer), now: datetime = Depends(get_now)):
    """The customer taps "AI wealth assistant": the bank's back end issues a one-time entry
    ticket (valid for 60 s by default)."""
    ticket = app_ticket.issue(customer_id, now, current())
    return {"ticket": ticket, "expires_in": get_settings().app_ticket_ttl_seconds}
