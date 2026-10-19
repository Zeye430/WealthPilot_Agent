"""可观测性（P8-3）：请求编号、每轮指标、模型遥测、Prometheus 指标、运维看板权限、结构化日志。"""

import json
import logging

import pytest
from fastapi.testclient import TestClient
from langchain_core.messages import AIMessage
from sqlalchemy import select

from app.api.deps import get_current_user
from app.core.config import get_settings
from app.core.observability import METRICS, JsonFormatter, Metrics, RequestIdFilter
from app.db.models import TurnMetric
from app.db.session import get_engine
from app.main import app
from tests.fakes import tool_call
from tests.test_api_chat import HEADERS, _db_available, complete_assessment, use_models

pytestmark = pytest.mark.skipif(not _db_available(), reason="数据库未启动")
OPS = {"X-Demo-User": "ops_oncall"}


@pytest.fixture
def client():
    c = TestClient(app, headers=HEADERS)
    c.post("/api/v1/demo/reset")
    with get_engine().begin() as conn:
        conn.execute(TurnMetric.__table__.delete())
    yield c
    c.post("/api/v1/demo/reset")
    for dep in [d for d in app.dependency_overrides if d is not get_current_user]:
        app.dependency_overrides.pop(dep)


def usage(text: str, prompt: int = 1000, completion: int = 50) -> AIMessage:
    return AIMessage(
        text,
        usage_metadata={
            "input_tokens": prompt,
            "output_tokens": completion,
            "total_tokens": prompt + completion,
        },
    )


def turns() -> list[TurnMetric]:
    with get_engine().connect() as conn:
        return list(conn.execute(select(TurnMetric).order_by(TurnMetric.created_at)).all())


def test_request_id_header_is_generated_or_propagated(client):
    generated = client.get("/health").headers["X-Request-ID"]
    assert len(generated) == 32
    given = client.get("/health", headers={"X-Request-ID": "lb-abc12345"})
    assert given.headers["X-Request-ID"] == "lb-abc12345"
    # 不合法的编号（可能用于日志注入）不沿用
    bad = client.get("/health", headers={"X-Request-ID": "x\nforged log line"})
    assert bad.headers["X-Request-ID"] != "x\nforged log line"


def test_chat_turn_records_metrics_with_request_id(client):
    complete_assessment(client)
    use_models(
        main=[
            tool_call("calculate_growth", {"principal": 1000000, "annual_rate": 0.05, "years": 10}),
            usage("10 年后约 1,628,894.63 元。"),
        ],
        router=["CALCULATION"],
    )
    resp = client.post("/api/v1/chat", json={"message": "100万5%复利10年"})
    rows = turns()
    assert len(rows) == 1
    m = rows[0]
    assert m.request_id == resp.headers["X-Request-ID"]
    assert m.conversation_id == resp.json()["conversation_id"]
    assert (m.outcome, m.intent, m.guard_decision) == ("ANSWERED", "CALCULATION", "PASS")
    assert m.llm_calls == 3  # 路由 + 两次主模型（调用工具、作答）
    assert m.prompt_tokens == 1000 and m.completion_tokens == 50
    assert m.tools == [{"name": "calculate_growth", "status": "success"}]
    assert m.cost_usd > 0
    assert METRICS.value("wealthpilot_chat_turns_total", {"outcome": "ANSWERED"}) >= 1


def test_guard_rewrite_is_recorded_with_rule_codes(client):
    use_models(
        main=[AIMessage("这类产品稳赚不赔。"), AIMessage("理财产品不保本，可能亏损。")],
        router=["FINANCE_KNOWLEDGE"],
    )
    client.post("/api/v1/chat", json={"message": "理财稳吗"})
    m = turns()[-1]
    assert m.guard_decision == "REWRITE"
    assert m.violation_codes == ["O-PROHIBITED_CLAIM"]


def test_out_of_scope_outcome(client):
    use_models(main=[], router=["OUT_OF_SCOPE"])
    client.post("/api/v1/chat", json={"message": "写首诗"})
    m = turns()[-1]
    assert (m.outcome, m.guard_decision, m.llm_calls) == ("OUT_OF_SCOPE", None, 1)


def test_ops_overview_requires_ops_role_and_aggregates(client):
    use_models(
        main=[AIMessage("这类产品稳赚。"), AIMessage("理财不保本。")], router=["FINANCE_KNOWLEDGE"]
    )
    client.post("/api/v1/chat", json={"message": "理财稳吗"})
    assert client.get("/api/v1/ops/overview").status_code == 403  # 客户不能看
    assert client.get("/api/v1/ops/overview", headers={"X-Demo-User": "rm_li"}).status_code == 403
    body = client.get("/api/v1/ops/overview?hours=1", headers=OPS).json()
    assert body["kpis"]["turns"] == 1
    assert body["kpis"]["rewrite_rate"] == 1.0
    assert body["guard"]["rules"] == {"O-PROHIBITED_CLAIM": 1}
    assert body["health"]["checks"]["database"]["ok"] is True
    # 近 1 小时按 5 分钟分桶，没有对话的时间段补 0，延迟留空
    assert body["bucket_seconds"] == 300
    assert 12 <= len(body["series"]) <= 13
    assert sum(b["turns"] for b in body["series"]) == 1
    assert any(b["p50_ms"] is None for b in body["series"])
    # 看板不含对话内容
    assert "理财稳吗" not in json.dumps(body, ensure_ascii=False)


def test_metrics_endpoint_requires_token(client, monkeypatch):
    assert client.get("/metrics").status_code == 404  # 未配置令牌时关闭
    monkeypatch.setattr(
        get_settings(), "metrics_token", type(get_settings().demo_password)("t0ken")
    )
    assert client.get("/metrics").status_code == 401
    body = client.get("/metrics", headers={"Authorization": "Bearer t0ken"}).text
    assert "# TYPE wealthpilot_http_requests_total counter" in body
    assert 'route="/health"' in body  # 按路由模板归类


def test_prometheus_histogram_format():
    m = Metrics()
    m.observe("wealthpilot_chat_turn_duration_seconds", 0.3)
    m.observe("wealthpilot_chat_turn_duration_seconds", 7)
    text = m.render()
    assert 'wealthpilot_chat_turn_duration_seconds_bucket{le="0.5"} 1' in text
    assert 'wealthpilot_chat_turn_duration_seconds_bucket{le="+Inf"} 2' in text
    assert "wealthpilot_chat_turn_duration_seconds_count 2" in text


def test_json_log_line_carries_request_id():
    record = logging.LogRecord("app.test", logging.INFO, "", 0, "turn done", None, None)
    record.conversation_id = "c1"
    RequestIdFilter().filter(record)
    line = json.loads(JsonFormatter().format(record))
    assert line["msg"] == "turn done"
    assert line["conversation_id"] == "c1"
    assert "request_id" in line


def test_readiness_reports_database_down(client, monkeypatch):
    from sqlalchemy import create_engine

    import app.api.health as health

    broken = create_engine(
        "postgresql+psycopg://x:y@127.0.0.1:1/none", connect_args={"connect_timeout": 1}
    )
    monkeypatch.setattr(health, "get_engine", lambda: broken)
    resp = client.get("/health/ready")
    assert resp.status_code == 503
    assert resp.json()["checks"]["database"]["ok"] is False
    assert client.get("/health").status_code == 200  # 存活检查不依赖数据库
