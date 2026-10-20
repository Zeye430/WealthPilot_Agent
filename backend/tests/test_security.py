"""LLM-related privilege-escalation and injection defenses.

Other threats are covered in:
- Product tools called before an assessment are blocked: test_agent_graph.py (BLOCK_TOOL)
- Prompt injection in documents: test_rag.py::test_prompt_injection_in_document_is_caught
- Reading another customer's conversations / RM overreach: test_api_chat.py
- Forged identity, sessions, rate limits, cross-site writes: test_auth.py
"""

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import text

from app.agent.graph import ALL_TOOLS, build_graph
from app.api.chat import get_agent
from app.db.session import get_engine
from app.main import app
from tests.fakes import ScriptedChatModel

HIDDEN_FIELDS = {"state", "risk_rating", "customer_id", "conversation_id", "permission"}


def _db_available() -> bool:
    try:
        with get_engine().connect() as conn:
            conn.execute(text("SELECT 1"))
        return True
    except Exception:
        return False


db_required = pytest.mark.skipif(not _db_available(), reason="数据库未启动")


@pytest.mark.parametrize("tool", ALL_TOOLS, ids=lambda t: t.name)
def test_llm_cannot_supply_identity_or_rating(tool):
    """Customer rating and identity are injected by the system (InjectedState), never among the
    model-visible arguments, so the model can't forge them."""
    visible = set(tool.tool_call_schema.model_json_schema().get("properties", {}))
    assert not visible & HIDDEN_FIELDS, f"{tool.name} 暴露了 {visible & HIDDEN_FIELDS}"


def test_message_length_is_bounded():
    # Inject a fake model: independent of whether a Kimi key is configured locally (CI has none)
    app.dependency_overrides[get_agent] = lambda: build_graph(
        ScriptedChatModel(responses=[]), ScriptedChatModel(responses=[])
    )
    try:
        c = TestClient(app, headers={"X-Demo-User": "pytest_customer"})
        assert c.post("/api/v1/chat", json={"message": "啊" * 2001}).status_code == 422
    finally:
        app.dependency_overrides.pop(get_agent, None)


@db_required
def test_customer_cannot_cancel_another_customers_reminder():
    owner = TestClient(app, headers={"X-Demo-User": "eval_customer"})
    other = TestClient(app, headers={"X-Demo-User": "pytest_customer"})
    owner.post("/api/v1/demo/reset")
    answers = {f"q{i + 1}": a for i, a in enumerate("CCCBBBBBCB")}  # C2
    sub = owner.post("/api/v1/assessment", json={"answers": answers}).json()
    owner.post(f"/api/v1/assessment/{sub['assessment_id']}/confirm")
    reminder = owner.post("/api/v1/reminders", json={"product_code": "ZA-F06"}).json()
    assert other.delete(f"/api/v1/reminders/{reminder['id']}").status_code == 404
    assert [r["id"] for r in owner.get("/api/v1/reminders").json()] == [reminder["id"]]
    owner.post("/api/v1/demo/reset")
