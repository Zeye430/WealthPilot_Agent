"""API 集成测试：真实数据库 + 假模型。数据库未启动时自动跳过（docker compose up -d db）。

使用专用的 pytest_customer，测试前后清空其数据，不影响演示账号。
"""

from datetime import UTC, datetime, timedelta

import pytest
from fastapi.testclient import TestClient
from langchain_core.messages import AIMessage
from sqlalchemy import select, text

from app.agent.graph import build_graph
from app.api.chat import get_agent
from app.api.deps import get_now
from app.core.config import get_settings
from app.db.models import PolicyDecisionLog, ToolCallLog
from app.db.session import get_engine
from app.main import app
from tests.fakes import ScriptedChatModel, tool_call

CUSTOMER = "pytest_customer"
HEADERS = {"X-Demo-User": CUSTOMER}
MAIN_SCENARIO = dict(zip([f"q{i}" for i in range(1, 11)], "CCCBBBBBCB", strict=True))  # 51 分 C2


def _db_available() -> bool:
    try:
        with get_engine().connect() as conn:
            conn.execute(text("SELECT 1"))
        return True
    except Exception:
        return False


pytestmark = pytest.mark.skipif(not _db_available(), reason="数据库未启动")


@pytest.fixture
def client(monkeypatch):
    monkeypatch.setattr(get_settings(), "demo_users", ["demo_customer_1", CUSTOMER])
    c = TestClient(app, headers=HEADERS)
    c.post("/api/v1/demo/reset")
    yield c
    c.post("/api/v1/demo/reset")
    app.dependency_overrides.clear()


def use_models(*, main: list, router: list):
    app.dependency_overrides[get_agent] = lambda: build_graph(
        ScriptedChatModel(responses=main),
        ScriptedChatModel(responses=[AIMessage(label) for label in router]),
    )


def freeze(now: datetime):
    app.dependency_overrides[get_now] = lambda: now


def complete_assessment(client) -> dict:
    sub = client.post("/api/v1/assessment", json={"answers": MAIN_SCENARIO})
    assert sub.status_code == 200, sub.text
    return client.post(f"/api/v1/assessment/{sub.json()['assessment_id']}/confirm").json()


def policy_log(conversation_id: str):
    with get_engine().connect() as conn:
        return conn.execute(
            select(PolicyDecisionLog.checkpoint, PolicyDecisionLog.decision).where(
                PolicyDecisionLog.conversation_id == conversation_id
            )
        ).all()


# ---------- 测评流程 ----------


def test_questionnaire_hides_scores(client):
    body = client.get("/api/v1/assessment/questionnaire").json()
    assert len(body["questions"]) == 10
    assert "score" not in str(body)


def test_new_customer_requires_assessment(client):
    state = client.get("/api/v1/me").json()
    assert state["permission"] == "ASSESSMENT_REQUIRED"
    assert state["gate_reasons"] == ["ASSESSMENT_MISSING"]
    assert state["assessment"] is None


def test_submit_then_confirm_activates_rating(client):
    sub = client.post("/api/v1/assessment", json={"answers": MAIN_SCENARIO}).json()
    assert sub["result"]["rating"] == "C2" and sub["result"]["score"] == 51
    # 确认前评级不生效
    assert client.get("/api/v1/me").json()["permission"] == "ASSESSMENT_REQUIRED"

    state = client.post(f"/api/v1/assessment/{sub['assessment_id']}/confirm").json()
    assert state["permission"] == "ASSESSED"
    assert state["assessment"]["rating"] == "C2"
    assert state["assessment"]["max_product_risk"] == "PR2"


def test_retake_before_confirm_supersedes_previous(client):
    first = client.post("/api/v1/assessment", json={"answers": MAIN_SCENARIO}).json()
    client.post("/api/v1/assessment", json={"answers": MAIN_SCENARIO})
    resp = client.post(f"/api/v1/assessment/{first['assessment_id']}/confirm")
    assert resp.status_code == 409


def test_cooldown_blocks_reassessment_within_24h(client):  # S06
    complete_assessment(client)
    resp = client.post("/api/v1/assessment", json={"answers": MAIN_SCENARIO})
    assert resp.status_code == 409
    assert "24 小时" in resp.json()["detail"]


def test_cooldown_lifts_after_24h(client):
    complete_assessment(client)
    freeze(datetime.now(UTC) + timedelta(hours=25))
    assert client.post("/api/v1/assessment", json={"answers": MAIN_SCENARIO}).status_code == 200


def test_assessment_expires_after_12_months(client):  # S03
    complete_assessment(client)
    freeze(datetime.now(UTC) + timedelta(days=366))
    state = client.get("/api/v1/me").json()
    assert state["permission"] == "ASSESSMENT_REQUIRED"
    assert state["gate_reasons"] == ["ASSESSMENT_EXPIRED"]


def test_incomplete_answers_rejected(client):
    partial = {k: v for k, v in MAIN_SCENARIO.items() if k != "q10"}
    assert client.post("/api/v1/assessment", json={"answers": partial}).status_code == 422


def test_unknown_demo_user_forbidden(client):
    resp = client.get("/api/v1/me", headers={"X-Demo-User": "intruder"})
    assert resp.status_code == 403


# ---------- 对话 + 门禁 ----------


def test_product_request_blocked_until_assessed(client):  # S01 端到端
    use_models(main=[], router=["PRODUCT_OR_ADVICE"])
    body = client.post("/api/v1/chat", json={"message": "推荐一款理财"}).json()
    assert body["reply"]["ui_blocks"][0]["type"] == "assessment_prompt"
    assert body["state"]["permission"] == "ASSESSMENT_REQUIRED"
    assert ("GATE", "BLOCK_PRODUCT_REQUEST") in policy_log(body["conversation_id"])


def test_gate_opens_mid_conversation_after_assessment(client):
    use_models(main=[], router=["PRODUCT_OR_ADVICE"])
    first = client.post("/api/v1/chat", json={"message": "推荐一款理财"}).json()

    complete_assessment(client)
    use_models(main=[AIMessage("产品查询功能即将开放。")], router=["PRODUCT_OR_ADVICE"])
    second = client.post(
        "/api/v1/chat",
        json={"conversation_id": first["conversation_id"], "message": "现在可以推荐了吗？"},
    ).json()
    assert second["state"]["permission"] == "ASSESSED"
    assert second["reply"]["content"] == "产品查询功能即将开放。"
    assert ("GATE", "ASSESSED") in policy_log(first["conversation_id"])


def test_calculation_round_trip_logs_tool_call(client):
    complete_assessment(client)
    use_models(
        main=[
            tool_call("calculate_growth", {"principal": 1000000, "annual_rate": 0.05, "years": 10}),
            AIMessage("约 1,628,894.63 元。"),
        ],
        router=["CALCULATION"],
    )
    body = client.post("/api/v1/chat", json={"message": "100万5%复利10年"}).json()
    types = [b["type"] for b in body["reply"]["ui_blocks"]]
    assert types == ["calculation_result", "line_chart"]

    conv = client.get(f"/api/v1/conversations/{body['conversation_id']}").json()
    assert [m["role"] for m in conv["messages"]] == ["user", "assistant"]
    with get_engine().connect() as conn:
        logs = conn.execute(
            select(ToolCallLog.tool_name, ToolCallLog.status).where(
                ToolCallLog.conversation_id == body["conversation_id"]
            )
        ).all()
    assert logs == [("calculate_growth", "success")]


def test_other_customer_cannot_read_conversation(client):
    use_models(main=[AIMessage("您好")], router=["SERVICE"])
    body = client.post("/api/v1/chat", json={"message": "你好"}).json()
    resp = client.get(
        f"/api/v1/conversations/{body['conversation_id']}",
        headers={"X-Demo-User": "demo_customer_1"},
    )
    assert resp.status_code == 404


def test_empty_message_rejected(client):
    assert client.post("/api/v1/chat", json={"message": ""}).status_code == 422


def test_reset_clears_assessment(client):
    complete_assessment(client)
    client.post("/api/v1/demo/reset")
    assert client.get("/api/v1/me").json()["permission"] == "ASSESSMENT_REQUIRED"


def test_health():
    assert TestClient(app).get("/health").json()["database"] == "ok"


# ---------- 产品 API（Phase 3） ----------


def test_products_api_requires_assessment(client):  # S11
    assert client.get("/api/v1/products").status_code == 403
    assert client.get("/api/v1/products/ZA-F01").status_code == 403


def test_products_api_filters_by_rating(client):  # S11
    complete_assessment(client)  # C2
    body = client.get("/api/v1/products").json()
    levels = {i["risk_level"] for i in body["items"]}
    assert levels <= {"PR1", "PR2"}
    assert body["rating"] == {"code": "C2", "name": "稳健型", "max_product_risk": "PR2"}
    assert {"reason": "风险等级超出您的风险承受能力", "count": 5} in body["excluded"]


def test_products_api_type_filter(client):
    complete_assessment(client)
    body = client.get("/api/v1/products", params={"product_type": "CASH_MANAGEMENT"}).json()
    assert {i["code"] for i in body["items"]} == {"ZA-C01", "HY-C01"}


def test_product_detail_over_rating_has_warning(client):  # S04b
    complete_assessment(client)
    body = client.get("/api/v1/products/ZA-M01").json()
    assert body["eligible"] is False
    assert "无权限购买" in body["eligibility_messages"][0]
    assert client.get("/api/v1/products/NOPE").status_code == 404


# ---------- 客户画像（Phase 5） ----------


def test_me_returns_base_profile_and_empty_needs(client):
    profile = client.get("/api/v1/me").json()["profile"]
    assert profile["base"]["display_name"] == "测试客户（虚构）"
    assert all(row["value"] is None for row in profile["needs"])


def test_questionnaire_prefills_age_from_bank_system(client):
    assert client.get("/api/v1/assessment/questionnaire").json()["prefill"] == {"q1": "B"}  # 40 岁


def test_needs_edit_validation_and_clear(client):
    body = client.patch("/api/v1/needs", json={"investment_amount": 1000000}).json()
    rows = {r["field"]: r for r in body["profile"]["needs"]}
    assert rows["investment_amount"]["value"] == "100 万元"
    assert rows["investment_amount"]["source"] == "客户修改"
    bad = client.patch("/api/v1/needs", json={"liquidity_reserve": 2000000})
    assert bad.status_code == 422
    cleared = client.delete("/api/v1/needs").json()
    assert all(r["value"] is None for r in cleared["profile"]["needs"])


def test_needs_recorded_in_chat_narrow_product_search(client):
    complete_assessment(client)
    # 第 1 轮：模型记录客户说的「10 万元、12 个月」
    use_models(
        main=[
            tool_call("update_needs", {"investment_amount": 100000, "horizon_months": 12}),
            AIMessage("已记录您的需求。"),
        ],
        router=["SERVICE"],
    )
    first = client.post("/api/v1/chat", json={"message": "我有10万，一年内不用"}).json()
    assert [b["type"] for b in first["reply"]["ui_blocks"]] == ["needs_update"]
    needs = {r["field"]: r for r in first["state"]["profile"]["needs"]}
    assert needs["investment_amount"]["source"] == "对话中提供"

    # 第 2 轮：模型搜索时没传金额和期限，工具自动使用已记录的需求
    use_models(
        main=[tool_call("search_products", {}), AIMessage("以下是符合条件的产品。")],
        router=["PRODUCT_OR_ADVICE"],
    )
    second = client.post(
        "/api/v1/chat",
        json={"conversation_id": first["conversation_id"], "message": "有哪些产品？"},
    ).json()
    block = next(b for b in second["reply"]["ui_blocks"] if b["type"] == "product_list")
    codes = {i["code"] for i in block["items"]}
    assert "HY-F03" not in codes  # 30 万元起购 > 10 万元
    assert "HY-F02" not in codes  # 两年持有 > 12 个月
    reasons = {e["reason"] for e in block["excluded"]}
    assert {"起购金额高于计划投资金额", "持有或封闭期超过投资期限"} <= reasons


def test_reset_clears_needs(client):
    client.patch("/api/v1/needs", json={"investment_amount": 50000})
    client.post("/api/v1/demo/reset")
    rows = client.get("/api/v1/me").json()["profile"]["needs"]
    assert all(r["value"] is None for r in rows)


# ---------- 人工交接（Phase 6，用例编号对应 EVALUATION_PLAN §5） ----------

RM_HEADERS = {"X-Demo-User": "rm_li"}  # pytest_customer 的专属理财经理是 RM001（李经理）


def request_handoff_in_chat(client, reason="USER_REQUEST", questions=("确认可接受的最大亏损",)):
    use_models(
        main=[
            tool_call("request_handoff", {"reason": reason, "open_questions": list(questions)}),
            AIMessage("已为您生成转人工请求，请在下方确认分享的信息。"),
        ],
        router=["HANDOFF"],
    )
    body = client.post("/api/v1/chat", json={"message": "我要找理财经理"}).json()
    card = next(b for b in body["reply"]["ui_blocks"] if b["type"] == "handoff_consent")
    return body, card


def rm_list(client):
    """只看测试客户的交接：同一理财经理名下可能还有演示客户的数据。"""
    rows = client.get("/api/v1/rm/handoffs", headers=RM_HEADERS).json()
    return [r for r in rows if r["customer_name"] == "测试客户（虚构）"]


def test_handoff_requires_consent_before_rm_sees_it(client):  # H01
    body, card = request_handoff_in_chat(client)
    assert card["status"] == "AWAITING_CONSENT"
    assert card["rm_name"] == "李经理（虚构）"  # 来自基础画像的专属理财经理
    assert "本次对话记录" in card["scope"]
    assert body["handoff"]["status"] == "AWAITING_CONSENT"
    assert rm_list(client) == []  # 客户同意前，理财经理看不到


def test_declined_handoff_never_reaches_rm(client):  # H02
    _, card = request_handoff_in_chat(client)
    assert client.post(f"/api/v1/handoffs/{card['id']}/cancel").json()["status"] == "CANCELLED"
    assert rm_list(client) == []
    assert client.post(f"/api/v1/handoffs/{card['id']}/consent").status_code == 409


def test_full_handoff_lifecycle(client):  # H03 + H04
    body, card = request_handoff_in_chat(client)
    conv = body["conversation_id"]
    assert client.post(f"/api/v1/handoffs/{card['id']}/consent").json()["status"] == "PENDING"
    assert [h["id"] for h in rm_list(client)] == [card["id"]]

    # 待接单期间 AI 仍可回复，且只能描述为「等待接单」
    use_models(main=[AIMessage("已提交，等待李经理接单。")], router=["SERVICE"])
    waiting = client.post(
        "/api/v1/chat", json={"conversation_id": conv, "message": "好了吗"}
    ).json()
    assert waiting["handoff"]["status"] == "PENDING"

    # 理财经理接单后 AI 暂停：模型若被调用会抛错
    assert (
        client.post(f"/api/v1/rm/handoffs/{card['id']}/accept", headers=RM_HEADERS).json()["status"]
        == "ACCEPTED"
    )
    use_models(main=[], router=[])
    relayed = client.post(
        "/api/v1/chat", json={"conversation_id": conv, "message": "李经理您好"}
    ).json()
    assert relayed["reply"]["ui_blocks"] == [{"type": "handoff_relay", "rm_name": "李经理（虚构）"}]
    assert relayed["handoff"]["ai_paused"] is True

    # 理财经理首次回复 → 服务中；客户端增量拉取能拿到回复
    total = client.get(f"/api/v1/conversations/{conv}/messages").json()["total"]
    reply = client.post(
        f"/api/v1/rm/handoffs/{card['id']}/messages",
        headers=RM_HEADERS,
        json={"text": "您好，我是李经理"},
    )
    assert reply.json()["status"] == "IN_PROGRESS"
    since = client.get(f"/api/v1/conversations/{conv}/messages", params={"after": total}).json()
    assert [(m["role"], m["content"]) for m in since["messages"]] == [("rm", "您好，我是李经理")]

    # 结束后 AI 恢复回复
    assert (
        client.post(f"/api/v1/rm/handoffs/{card['id']}/resolve", headers=RM_HEADERS).json()[
            "status"
        ]
        == "RESOLVED"
    )
    use_models(main=[AIMessage("欢迎回来，还有什么可以帮您？")], router=["SERVICE"])
    back = client.post("/api/v1/chat", json={"conversation_id": conv, "message": "谢谢"}).json()
    assert back["reply"]["content"] == "欢迎回来，还有什么可以帮您？"

    detail = client.get(f"/api/v1/rm/handoffs/{card['id']}", headers=RM_HEADERS).json()
    assert [e["to"] for e in detail["events"]] == [
        "待客户确认",
        "已提交，等待理财经理接单",
        "理财经理已接单",
        "理财经理服务中",
        "已结束",
    ]


def test_summary_is_built_from_structured_data(client):  # H05
    complete_assessment(client)
    client.patch("/api/v1/needs", json={"investment_amount": 1000000, "horizon_months": 24})
    _, card = request_handoff_in_chat(
        client, reason="HIGH_COMPLEXITY", questions=["退休后现金流规划"]
    )
    client.post(f"/api/v1/handoffs/{card['id']}/consent")
    summary = client.get(f"/api/v1/rm/handoffs/{card['id']}", headers=RM_HEADERS).json()["summary"]
    assert summary["reason"].startswith("专业复杂度高")
    assert summary["assessment"].startswith("C2 稳健型")
    assert {n["label"] for n in summary["needs"]} == {"计划投资金额", "投资期限"}
    assert summary["open_questions"] == ["退休后现金流规划"]


def test_suitability_conflict_handoff_keeps_limits(client):  # H06
    complete_assessment(client)
    _, card = request_handoff_in_chat(client, reason="SUITABILITY_CONFLICT")
    assert card["reason"] == "客户诉求与风险等级存在冲突"
    client.post(f"/api/v1/handoffs/{card['id']}/consent")
    # 转人工不会解除限制：产品接口仍按 C2 过滤
    levels = {i["risk_level"] for i in client.get("/api/v1/products").json()["items"]}
    assert levels <= {"PR1", "PR2"}


def test_handoff_allowed_before_assessment(client):  # H07
    _, card = request_handoff_in_chat(client)
    assert card["preview"]["assessment"] == "尚未完成风险测评"


def test_ordinary_question_creates_no_handoff(client):  # H08
    use_models(
        main=[AIMessage("七日年化是现金管理类产品的收益口径。")], router=["FINANCE_KNOWLEDGE"]
    )
    body = client.post("/api/v1/chat", json={"message": "什么是七日年化"}).json()
    assert body["handoff"] is None


def test_duplicate_request_returns_existing_handoff(client):
    body, card = request_handoff_in_chat(client)
    use_models(
        main=[
            tool_call("request_handoff", {"reason": "USER_REQUEST"}),
            AIMessage("已有请求，待您确认。"),
        ],
        router=["HANDOFF"],
    )
    again = client.post(
        "/api/v1/chat", json={"conversation_id": body["conversation_id"], "message": "再转一次"}
    ).json()
    # 仍待确认的请求：再次展示同一张确认卡片，不重复创建
    shown = next(b for b in again["reply"]["ui_blocks"] if b["type"] == "handoff_consent")
    assert shown["id"] == card["id"]


def test_rm_access_control(client):
    _, card = request_handoff_in_chat(client)
    client.post(f"/api/v1/handoffs/{card['id']}/consent")
    other = {"X-Demo-User": "rm_zhou"}  # 不是该客户的专属理财经理
    assert client.get(f"/api/v1/rm/handoffs/{card['id']}", headers=other).status_code == 404
    assert client.get("/api/v1/rm/handoffs").status_code == 403  # 客户身份不能访问看板
    assert (
        client.post(
            f"/api/v1/rm/handoffs/{card['id']}/messages", headers=RM_HEADERS, json={"text": "hi"}
        ).status_code
        == 409
    )  # 未接单不能回复
