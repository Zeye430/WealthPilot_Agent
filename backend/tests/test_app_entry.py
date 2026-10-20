"""Entry from mobile banking (app ticket): the customer signs in to the simulated banking app and
taps "AI wealth assistant" to enter without a password.

Checks two things: (1) the normal flow works and the two sessions stay independent; (2) tampered,
expired, replayed or wrong-audience tickets are always rejected.
"""

from datetime import UTC, datetime, timedelta

import pytest
from fastapi.testclient import TestClient

from app.api.deps import get_current_user
from app.auth import app_ticket
from app.main import app
from tests.test_api_chat import _db_available

pytestmark = pytest.mark.skipif(not _db_available(), reason="数据库未启动")
CUSTOMER = "pytest_customer"


@pytest.fixture
def client():
    # This file tests the real authentication path: remove the test identity double and restore it
    # afterwards
    override = app.dependency_overrides.pop(get_current_user, None)
    with TestClient(app) as c:
        yield c
    if override:
        app.dependency_overrides[get_current_user] = override


def now() -> datetime:
    return datetime.now(UTC)


def test_bank_app_entry_flow(client):
    # (1) Sign in to mobile banking (the bank's own account and session)
    assert (
        client.post("/bank-sim/api/login", json={"username": "wang", "password": "x"}).status_code
        == 401
    )
    assert (
        client.post(
            "/bank-sim/api/login", json={"username": "wang", "password": "wealthpilot-demo"}
        ).status_code
        == 200
    )
    home = client.get("/bank-sim/api/home").json()
    assert home["total"] > 0
    # The banking session can't be used to access WealthPilot
    assert client.get("/api/v1/me").status_code == 401
    # (2) Tap the assistant: the bank issues a one-time ticket
    ticket = client.post("/bank-sim/api/assistant-ticket").json()["ticket"]
    # (3) WealthPilot verifies the ticket and creates its own session
    entered = client.post("/api/v1/auth/app-ticket", json={"ticket": ticket})
    assert entered.status_code == 200
    assert entered.json()["role"] == "customer" and entered.json()["entry"] == "bank_app"
    assert client.get("/api/v1/me").status_code == 200
    # (4) The same ticket can't be used again (replay)
    client.cookies.clear()
    replay = client.post("/api/v1/auth/app-ticket", json={"ticket": ticket})
    assert replay.status_code == 401
    assert "重新进入" in replay.json()["detail"]


def test_app_only_account_cannot_password_login(client):
    ticket = app_ticket.issue(CUSTOMER, now())
    user = client.post("/api/v1/auth/app-ticket", json={"ticket": ticket}).json()
    assert user["username"] == f"app:{CUSTOMER}"  # account created on first entry
    resp = client.post(
        "/api/v1/auth/login", json={"username": f"app:{CUSTOMER}", "password": "!app-entry-only"}
    )
    assert resp.status_code == 401


def test_ticket_requires_bank_session(client):
    assert client.post("/bank-sim/api/assistant-ticket").status_code == 401


@pytest.mark.parametrize(
    "mutate",
    [
        lambda t: t[:-2] + ("AA" if not t.endswith("AA") else "BB"),  # tampered signature
        lambda t: "x" + t,  # tampered payload
        lambda t: t.split(".")[0],  # missing signature
        lambda t: "not-a-ticket-at-all-xxxxxxxx",
    ],
)
def test_tampered_ticket_rejected(client, mutate):
    ticket = mutate(app_ticket.issue(CUSTOMER, now()))
    assert client.post("/api/v1/auth/app-ticket", json={"ticket": ticket}).status_code in (401, 422)


def test_expired_ticket_rejected(client):
    old = app_ticket.issue(CUSTOMER, now() - timedelta(minutes=5))
    assert client.post("/api/v1/auth/app-ticket", json={"ticket": old}).status_code == 401


def test_ticket_for_unknown_customer_rejected(client):
    ticket = app_ticket.issue("no_such_customer", now())
    assert client.post("/api/v1/auth/app-ticket", json={"ticket": ticket}).status_code == 401


def test_wrong_audience_rejected():
    import base64
    import json

    token = app_ticket.issue(CUSTOMER, now())
    body = json.loads(base64.urlsafe_b64decode(token.split(".")[0] + "=="))
    body["aud"] = "another-app"
    raw = json.dumps(body, separators=(",", ":"), sort_keys=True).encode()
    # rejected for the wrong audience even with a valid signature
    forged = f"{app_ticket._b64(raw)}.{app_ticket._sign(raw)}"
    with pytest.raises(app_ticket.TicketError):
        app_ticket.verify(forged, now())


def test_bank_login_requires_access_code_when_configured(client, monkeypatch):
    from pydantic import SecretStr

    from app.core.config import get_settings

    monkeypatch.setattr(get_settings(), "demo_access_code", SecretStr("open-sesame"))
    creds = {"username": "wang", "password": "wealthpilot-demo"}
    assert client.post("/bank-sim/api/login", json=creds).status_code == 401
    ok = client.post("/bank-sim/api/login", json={**creds, "access_code": "open-sesame"})
    assert ok.status_code == 200


def test_bank_sim_can_be_disabled(client, monkeypatch):
    from app.core.config import get_settings

    monkeypatch.setattr(get_settings(), "bank_sim_enabled", False)
    assert (
        client.post(
            "/bank-sim/api/login", json={"username": "wang", "password": "wealthpilot-demo"}
        ).status_code
        == 404
    )
