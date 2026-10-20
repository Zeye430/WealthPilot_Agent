"""Real authentication and HTTP-layer security (no identity double), covering the authentication
and HTTP controls in the threat model."""

from datetime import UTC, datetime, timedelta

import pytest
from fastapi.testclient import TestClient
from langchain_core.messages import AIMessage
from pydantic import SecretStr
from sqlalchemy import select, update
from sqlalchemy.orm import sessionmaker

from app.agent.graph import build_graph
from app.api.chat import get_agent
from app.api.deps import get_current_user, get_now
from app.auth.passwords import verify_password
from app.auth.service import ensure_demo_accounts
from app.core.config import get_settings
from app.core.ratelimit import limiter
from app.core.security import redact
from app.db.models import User
from app.db.session import get_engine
from app.main import app
from tests.fakes import ScriptedChatModel

PASSWORD = get_settings().demo_password.get_secret_value()


def _db_available() -> bool:
    try:
        with get_engine().connect():
            return True
    except Exception:
        return False


pytestmark = pytest.mark.skipif(not _db_available(), reason="需要 PostgreSQL")


@pytest.fixture
def client():
    app.dependency_overrides.pop(get_current_user, None)  # use real session authentication
    with sessionmaker(bind=get_engine())() as db:
        ensure_demo_accounts(db)
        db.execute(update(User).values(disabled=False))
        db.commit()
    limiter.reset()
    yield TestClient(app)
    app.dependency_overrides.pop(get_now, None)
    app.dependency_overrides.pop(get_agent, None)
    limiter.reset()


def login(client, username="wang", password=PASSWORD, **extra):
    return client.post(
        "/api/v1/auth/login", json={"username": username, "password": password, **extra}
    )


# ---------- Sign-in and sessions ----------


def test_login_sets_httponly_session_cookie(client):
    resp = login(client)
    assert resp.status_code == 200
    assert resp.json() == {"username": "wang", "display_name": "王先生（虚构）", "role": "customer"}
    cookie = resp.headers["set-cookie"].lower()
    assert "wp_session=" in cookie and "httponly" in cookie and "samesite=lax" in cookie
    assert client.get("/api/v1/auth/me").json()["username"] == "wang"
    assert client.get("/api/v1/me").json()["customer_id"] == "demo_customer_1"


def test_wrong_password_and_unknown_user_look_the_same(client):
    wrong = login(client, password="nope")
    unknown = login(client, username="nobody")
    assert wrong.status_code == unknown.status_code == 401
    assert wrong.json() == unknown.json() == {"detail": "账号或密码不正确"}


def test_header_identity_is_not_trusted(client):
    # The old X-Demo-User header let anyone impersonate anyone; now only the session cookie counts
    resp = client.get("/api/v1/me", headers={"X-Demo-User": "demo_customer_1"})
    assert resp.status_code == 401


def test_logout_revokes_session_immediately(client):
    login(client)
    token = client.cookies.get("wp_session")
    client.post("/api/v1/auth/logout")
    stolen = TestClient(app, cookies={"wp_session": token})
    assert stolen.get("/api/v1/me").status_code == 401


def test_idle_and_absolute_expiry(client):
    login(client)
    settings = get_settings()
    later = datetime.now(UTC) + timedelta(minutes=settings.session_idle_minutes + 1)
    app.dependency_overrides[get_now] = lambda: later
    assert client.get("/api/v1/me").status_code == 401


def test_disabled_account_loses_access(client):
    login(client)
    with sessionmaker(bind=get_engine())() as db:
        db.execute(update(User).where(User.username == "wang").values(disabled=True))
        db.commit()
    assert client.get("/api/v1/me").status_code == 401
    assert login(client).status_code == 401


def test_passwords_are_hashed(client):
    with sessionmaker(bind=get_engine())() as db:
        user = db.scalars(select(User).where(User.username == "wang")).one()
    assert user.password_hash.startswith("scrypt$") and PASSWORD not in user.password_hash
    assert verify_password(PASSWORD, user.password_hash)
    assert not verify_password("wrong", user.password_hash)


def test_access_code_required_when_configured(client, monkeypatch):
    monkeypatch.setattr(get_settings(), "demo_access_code", SecretStr("open-sesame"))
    assert client.get("/api/v1/auth/config").json()["access_code_required"] is True
    assert login(client).status_code == 401
    assert login(client, access_code="wrong").status_code == 401
    assert login(client, access_code="open-sesame").status_code == 200


# ---------- Role isolation ----------


def test_customer_cannot_use_rm_dashboard(client):
    login(client, "wang")
    assert client.get("/api/v1/rm/handoffs").status_code == 403


def test_rm_cannot_use_customer_endpoints(client):
    login(client, "li")
    assert client.get("/api/v1/rm/handoffs").status_code == 200
    assert client.get("/api/v1/me").status_code == 403
    assert client.post("/api/v1/chat", json={"message": "你好"}).status_code == 403


# ---------- Rate limiting ----------


def test_login_brute_force_is_rate_limited(client, monkeypatch):
    monkeypatch.setattr(get_settings(), "rate_limit_enabled", True)
    monkeypatch.setattr(get_settings(), "rate_limit_login_per_minute", 3)
    codes = [login(client, password="guess").status_code for _ in range(4)]
    assert codes == [401, 401, 401, 429]
    blocked = login(client)
    assert blocked.status_code == 429 and int(blocked.headers["retry-after"]) >= 1


def test_chat_is_rate_limited_per_user(client, monkeypatch):
    monkeypatch.setattr(get_settings(), "rate_limit_enabled", True)
    monkeypatch.setattr(get_settings(), "rate_limit_chat_per_minute", 2)
    login(client)
    app.dependency_overrides[get_agent] = lambda: build_graph(
        ScriptedChatModel(responses=[AIMessage("您好")] * 3),
        ScriptedChatModel(responses=[AIMessage("SERVICE")] * 3),
    )
    codes = [client.post("/api/v1/chat", json={"message": "你好"}).status_code for _ in range(3)]
    assert codes == [200, 200, 429]


# ---------- HTTP layer ----------


def test_cross_origin_writes_are_rejected(client):
    evil = client.post(
        "/api/v1/auth/login",
        json={"username": "wang", "password": PASSWORD},
        headers={"Origin": "https://evil.example"},
    )
    assert evil.status_code == 403
    ok = client.post(
        "/api/v1/auth/login",
        json={"username": "wang", "password": PASSWORD},
        headers={"Origin": "http://localhost:3000"},
    )
    assert ok.status_code == 200


def test_security_headers_present(client):
    headers = client.get("/api/v1/auth/config").headers
    assert headers["x-content-type-options"] == "nosniff"
    assert headers["x-frame-options"] == "DENY"
    assert headers["cache-control"] == "no-store"
    assert "microphone=(self)" in headers["permissions-policy"]


def test_log_redaction():
    assert (
        redact("客户手机 13812345678，卡号 6222020000000000001") == "客户手机 [手机号]，卡号 [卡号]"
    )
