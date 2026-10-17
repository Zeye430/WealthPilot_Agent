"""API 集成测试：真实数据库 + 假模型。数据库未启动时自动跳过（docker compose up -d db）。"""

import pytest
from fastapi.testclient import TestClient
from langchain_core.messages import AIMessage
from sqlalchemy import select, text

from app.agent.graph import build_graph
from app.api.chat import get_agent
from app.db.models import ToolCallLog
from app.db.session import get_engine
from app.main import app
from tests.fakes import ScriptedChatModel, tool_call


def _db_available() -> bool:
    try:
        with get_engine().connect() as conn:
            conn.execute(text("SELECT 1"))
        return True
    except Exception:
        return False


pytestmark = pytest.mark.skipif(not _db_available(), reason="数据库未启动")


@pytest.fixture
def client_with(request):
    def make(responses):
        model = ScriptedChatModel(responses=responses)
        app.dependency_overrides[get_agent] = lambda: build_graph(model)
        return TestClient(app)

    yield make
    app.dependency_overrides.clear()


def test_chat_round_trip_persists_messages_and_tool_calls(client_with):
    client = client_with(
        [
            tool_call("calculate_growth", {"principal": 1000000, "annual_rate": 0.05, "years": 10}),
            AIMessage("10 年后约 1,628,894.63 元。"),
        ]
    )
    resp = client.post("/api/v1/chat", json={"message": "100万5%复利10年"})
    assert resp.status_code == 200
    body = resp.json()
    assert [b["type"] for b in body["reply"]["ui_blocks"]] == ["calculation_result", "line_chart"]

    conv = client.get(f"/api/v1/conversations/{body['conversation_id']}").json()
    assert [m["role"] for m in conv["messages"]] == ["user", "assistant"]
    assert conv["messages"][1]["ui_blocks"][0]["type"] == "calculation_result"

    with get_engine().connect() as conn:
        logs = conn.execute(
            select(ToolCallLog.tool_name, ToolCallLog.status).where(
                ToolCallLog.conversation_id == body["conversation_id"]
            )
        ).all()
    assert logs == [("calculate_growth", "success")]


def test_follow_up_message_reuses_conversation(client_with):
    client = client_with([AIMessage("您好"), AIMessage("好的")])
    first = client.post("/api/v1/chat", json={"message": "你好"}).json()
    second = client.post(
        "/api/v1/chat", json={"conversation_id": first["conversation_id"], "message": "继续"}
    ).json()
    assert second["conversation_id"] == first["conversation_id"]
    conv = client.get(f"/api/v1/conversations/{first['conversation_id']}").json()
    assert len(conv["messages"]) == 4


def test_unknown_conversation_returns_404(client_with):
    client = client_with([])
    resp = client.post("/api/v1/chat", json={"conversation_id": "nope", "message": "hi"})
    assert resp.status_code == 404


def test_empty_message_rejected(client_with):
    client = client_with([])
    assert client.post("/api/v1/chat", json={"message": ""}).status_code == 422


def test_health():
    resp = TestClient(app).get("/health")
    assert resp.json()["database"] == "ok"
