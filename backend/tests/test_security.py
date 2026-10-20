"""LLM 相关的越权与注入防护。

其余已覆盖的威胁见：
- 测评前调用产品工具被拦截：test_agent_graph.py（BLOCK_TOOL）
- 文档中的提示注入：test_rag.py::test_prompt_injection_in_document_is_caught
- 跨客户读取会话 / 理财经理越权：test_api_chat.py
- 伪造身份、会话、限流、跨站写请求：test_auth.py
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
    """客户评级、身份由系统注入（InjectedState），不出现在模型可见的参数里，模型无法伪造。"""
    visible = set(tool.tool_call_schema.model_json_schema().get("properties", {}))
    assert not visible & HIDDEN_FIELDS, f"{tool.name} 暴露了 {visible & HIDDEN_FIELDS}"


def test_message_length_is_bounded():
    # 注入假模型：不依赖本地是否配置了 Kimi Key（CI 中没有）
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
