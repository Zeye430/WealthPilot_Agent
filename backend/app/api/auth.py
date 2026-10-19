"""登录 / 退出 / 当前用户。会话令牌只通过 httpOnly Cookie 传递，前端脚本读不到。"""

import hmac
from datetime import datetime

from fastapi import APIRouter, Depends, HTTPException, Request, Response
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from app.api.deps import SESSION_COOKIE, get_current_user, get_now
from app.auth.service import CurrentUser, authenticate, create_session, revoke_session
from app.core.config import get_settings
from app.core.i18n import L
from app.core.ratelimit import login_limit
from app.db.session import get_session

router = APIRouter(prefix="/api/v1/auth", tags=["auth"])


class LoginRequest(BaseModel):
    username: str = Field(min_length=1, max_length=64)
    password: str = Field(min_length=1, max_length=128)
    access_code: str | None = Field(default=None, max_length=64)


def _display_name(username: str, fallback: str) -> str:
    """演示账号的显示名按当前语言返回（账号表只存中文名）。"""
    account = next((a for a in get_settings().demo_accounts if a["username"] == username), None)
    if account is None:
        return fallback
    return L(account["display_name"], account.get("display_name_en") or account["display_name"])


def user_view(user: CurrentUser) -> dict:
    return {
        "username": user.username,
        "display_name": _display_name(user.username, user.display_name),
        "role": user.role,
    }


@router.get("/config")
def login_config():
    """登录页需要的信息：是否需要访问码、可用的演示账号（不含密码）。"""
    settings = get_settings()
    return {
        "access_code_required": settings.demo_access_code is not None,
        "hint": L(settings.demo_login_hint, settings.demo_login_hint_en)
        if settings.demo_login_hint
        else None,
        "demo_accounts": [
            {
                "username": a["username"],
                "display_name": _display_name(a["username"], a["display_name"]),
                "role": a["role"],
            }
            for a in settings.demo_accounts
        ],
    }


@router.post("/login")
def login(
    req: LoginRequest,
    request: Request,
    response: Response,
    db: Session = Depends(get_session),
    now: datetime = Depends(get_now),
):
    login_limit(request, req.username)
    settings = get_settings()
    if settings.demo_access_code is not None:
        expected = settings.demo_access_code.get_secret_value()
        if not hmac.compare_digest((req.access_code or "").strip(), expected):
            raise HTTPException(status_code=401, detail=L("访问码不正确", "Incorrect access code"))
    user = authenticate(db, req.username, req.password)
    if user is None:
        # 不区分「账号不存在」和「密码错误」，避免被用来探测账号
        raise HTTPException(
            status_code=401, detail=L("账号或密码不正确", "Incorrect username or password")
        )
    token = create_session(db, user, now)
    response.set_cookie(
        SESSION_COOKIE,
        token,
        max_age=settings.session_ttl_hours * 3600,
        httponly=True,
        secure=settings.cookie_secure,
        samesite="lax",
        path="/",
    )
    return user_view(user)


@router.post("/logout", status_code=204)
def logout(
    request: Request,
    response: Response,
    db: Session = Depends(get_session),
    now: datetime = Depends(get_now),
):
    if token := request.cookies.get(SESSION_COOKIE):
        revoke_session(db, token, now)
    response.delete_cookie(SESSION_COOKIE, path="/")


@router.get("/me")
def me(user: CurrentUser = Depends(get_current_user)):
    return user_view(user)
