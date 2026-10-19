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
from app.api.deps import get_current_user, get_now
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
    c = TestClient(app, headers=HEADERS)
    c.post("/api/v1/demo/reset")
    yield c
    c.post("/api/v1/demo/reset")
    for dep in [d for d in app.dependency_overrides if d is not get_current_user]:
        app.dependency_overrides.pop(dep)  # 保留身份替身，由 conftest 负责清理


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
    use_models(main=[], router=[])  # 不依赖本地是否配置了 Kimi Key（CI 中没有）
    assert client.post("/api/v1/chat", json={"message": ""}).status_code == 422


def test_reset_clears_assessment(client):
    complete_assessment(client)
    client.post("/api/v1/demo/reset")
    assert client.get("/api/v1/me").json()["permission"] == "ASSESSMENT_REQUIRED"


def test_health():
    assert TestClient(app).get("/health").json()["database"] == "ok"


# ---------- 产品 API（Phase 3） ----------


def test_products_browsable_before_assessment(client):  # 产品负责人决定：全部可看
    body = client.get("/api/v1/products").json()
    assert body["rating"] is None
    codes = {i["code"] for i in body["items"]}
    assert len(codes) == 15 and "ZA-F05" not in codes  # 已到期产品不展示
    assert not any(i["purchasable"] for i in body["items"])
    detail = client.get("/api/v1/products/ZA-F01").json()
    assert detail["purchase"]["allowed"] is False
    assert "测评" in detail["purchase"]["reasons"][0]


def test_products_api_marks_purchasable_by_rating(client):  # S11
    complete_assessment(client)  # C2
    body = client.get("/api/v1/products").json()
    assert body["rating"] == {"code": "C2", "name": "稳健型", "max_product_risk": "PR2"}
    buyable = [i for i in body["items"] if i["purchasable"]]
    view_only = [i for i in body["items"] if not i["purchasable"]]
    assert {i["risk_level"] for i in buyable} <= {"PR1", "PR2"}
    assert {i["risk_level"] for i in view_only} == {"PR3", "PR4", "PR5"}
    assert body["items"][: len(buyable)] == buyable  # 可买入的排在前面
    assert "超出您的风险承受能力" in view_only[0]["warnings"][0]
    assert "随时可取" in body["items"][0]["highlights"]


def test_products_api_type_filter(client):
    complete_assessment(client)
    body = client.get("/api/v1/products", params={"product_type": "CASH_MANAGEMENT"}).json()
    assert {i["code"] for i in body["items"]} == {"ZA-C01", "HY-C01"}


def test_product_detail_over_rating_has_warning(client):  # S04b
    complete_assessment(client)
    body = client.get("/api/v1/products/ZA-M01").json()
    assert body["eligible"] is False
    assert "无权限购买" in body["eligibility_messages"][0]
    assert body["purchase"]["allowed"] is False
    assert client.get("/api/v1/products/NOPE").status_code == 404


# ---------- 买入确认（演示，只做到确认页） ----------

ALL_DOCS = ["prospectus", "risk_disclosure", "sales_agreement"]


def preview(client, code, amount):
    return client.post(
        "/api/v1/purchases/preview", json={"product_code": code, "amount": amount}
    ).json()


def test_purchase_preview_within_rating(client):
    complete_assessment(client)
    body = preview(client, "ZA-F01", 10000)
    assert body["allowed"] is True and body["errors"] == []
    assert body["amount"] == "1 万元" and body["subscription_fee"] == "0 元"
    assert body["available_balance"] == "5 万元"  # 基础画像中的活期存款
    assert [d["id"] for d in body["documents"]] == ALL_DOCS
    assert "理财非存款" in body["risk_disclosure"]


def test_purchase_blocked_by_code_rules(client):
    assert "测评" in preview(client, "ZA-F01", 10000)["errors"][0]  # 未测评
    complete_assessment(client)  # C2
    assert "超出您的风险承受能力" in preview(client, "ZA-M01", 10000)["errors"][0]
    assert "起购金额" in preview(client, "HY-F03", 10000)["errors"][0]  # 起购 30 万
    assert "可用活期余额" in preview(client, "ZA-F01", 60000)["errors"][0]
    assert "已到期" in preview(client, "ZA-F05", 10000)["errors"][0]


def test_purchase_confirm_requires_documents_and_never_places_order(client):
    complete_assessment(client)
    req = {"product_code": "ZA-F01", "amount": 10000}
    missing = client.post("/api/v1/purchases/confirm", json={**req, "acknowledged": ALL_DOCS[:1]})
    assert missing.status_code == 422 and "风险揭示书" in missing.json()["detail"]
    done = client.post("/api/v1/purchases/confirm", json={**req, "acknowledged": ALL_DOCS}).json()
    assert done["status"] == "DEMO_NOT_PLACED"
    assert "未实际下单" in done["message"]
    # 服务端重新校验：绕过前端直接确认超评级产品也会被拒绝
    over = {"product_code": "ZA-M01", "amount": 10000, "acknowledged": ALL_DOCS}
    assert client.post("/api/v1/purchases/confirm", json=over).status_code == 409


# ---------- 新品与开售提醒（2026-10-18） ----------


def test_products_api_lists_upcoming_with_remind_state(client):
    before = {u["code"]: u["remind"] for u in client.get("/api/v1/products").json()["upcoming"]}
    assert set(before) == {"ZA-F06", "HY-P02"}
    assert before["ZA-F06"]["allowed"] is False  # 未测评不能预约
    complete_assessment(client)  # C2
    after = {u["code"]: u for u in client.get("/api/v1/products").json()["upcoming"]}
    assert after["ZA-F06"]["remind"] == {
        "allowed": True,
        "reminded": False,
        "reason": None,
        "needs_assessment": False,
    }
    assert after["ZA-F06"]["sale_window"] == "10 月 26 日–10 月 30 日"
    assert after["ZA-F06"]["raise_limit"] == "5 亿元"
    assert "超出您的风险承受能力" in after["HY-P02"]["remind"]["reason"]  # PR3 新品


def test_upcoming_product_cannot_be_bought(client):
    complete_assessment(client)
    detail = client.get("/api/v1/products/ZA-F06").json()
    assert detail["purchase"]["allowed"] is False
    assert "尚未开售" in detail["purchase"]["reasons"][0]
    assert detail["remind"]["allowed"] is True
    body = client.post(
        "/api/v1/purchases/preview", json={"product_code": "ZA-F06", "amount": 10000}
    ).json()
    assert body["allowed"] is False


def test_reminder_create_list_cancel(client):
    complete_assessment(client)
    created = client.post("/api/v1/reminders", json={"product_code": "ZA-F06"}).json()
    again = client.post("/api/v1/reminders", json={"product_code": "ZA-F06"}).json()
    assert again["id"] == created["id"]  # 不重复创建
    rows = client.get("/api/v1/reminders").json()
    assert [r["product"]["code"] for r in rows] == ["ZA-F06"]
    assert "演示环境不发送" in rows[0]["delivery_note"]
    detail = client.get("/api/v1/products/ZA-F06").json()
    assert detail["remind"]["reminded"] is True
    assert client.delete(f"/api/v1/reminders/{created['id']}").status_code == 204
    assert client.get("/api/v1/reminders").json() == []


def test_reminder_rules_enforced_by_code(client):
    assert client.post("/api/v1/reminders", json={"product_code": "ZA-F06"}).status_code == 409
    complete_assessment(client)  # C2
    over = client.post("/api/v1/reminders", json={"product_code": "HY-P02"})
    assert over.status_code == 409 and "超出" in over.json()["detail"]
    on_sale = client.post("/api/v1/reminders", json={"product_code": "ZA-F01"})
    assert on_sale.status_code == 409  # 在售产品无需预约


def test_search_tool_returns_matching_upcoming_and_chat_reminder(client):
    complete_assessment(client)  # C2
    use_models(
        main=[
            tool_call("search_products", {"horizon_months": 12}),
            AIMessage("在您的风险等级范围内有以下产品；另有一款新品 10 月 26 日开售。"),
        ],
        router=["PRODUCT_OR_ADVICE"],
    )
    body = client.post("/api/v1/chat", json={"message": "一年内不用，有什么产品？"}).json()
    block = next(b for b in body["reply"]["ui_blocks"] if b["type"] == "upcoming_products")
    assert [i["code"] for i in block["items"]] == ["ZA-F06"]  # PR3 新品不展示给 C2
    assert block["items"][0]["reminded"] is False

    use_models(
        main=[
            tool_call("set_sale_reminder", {"product": "知岸定享 365 天第 15 期"}),
            AIMessage("已为您预约开售提醒，开售后需要您本人确认买入。"),
        ],
        router=["PRODUCT_OR_ADVICE"],
    )
    conv = body["conversation_id"]
    client.post("/api/v1/chat", json={"conversation_id": conv, "message": "好的，帮我设个提醒"})
    assert [r["product"]["code"] for r in client.get("/api/v1/reminders").json()] == ["ZA-F06"]
    # 之后的轮次再说「已预约」：客户资料中有提醒记录，不算虚假宣称
    use_models(main=[AIMessage("已为您预约了开售提醒，开售当天会通知您。")], router=["SERVICE"])
    later = client.post("/api/v1/chat", json={"conversation_id": conv, "message": "提醒设好了吗"})
    assert later.json()["reply"]["content"].startswith("已为您预约")


def test_reminder_claim_without_tool_is_blocked(client):  # 场景评估 N02
    complete_assessment(client)
    claim = "好的，已为您预约知岸定享 365 天第 15 期的开售提醒。"
    # 两次都是新消息对象：同一个对象 id 相同，LangGraph 会覆盖而不是追加
    use_models(main=[AIMessage(claim), AIMessage(claim)], router=["PRODUCT_OR_ADVICE"])
    body = client.post("/api/v1/chat", json={"message": "帮我设个开售提醒"}).json()
    assert (
        body["reply"]["content"]
        == "这个问题我暂时无法给出合适的回答。如需进一步帮助，您可以咨询理财经理。"
    )
    assert client.get("/api/v1/reminders").json() == []


# ---------- 客户等级与权益（2026-10-18） ----------


def test_benefits_tool_available_before_assessment(client):
    use_models(
        main=[
            tool_call("get_customer_benefits", {"planned_amount": 450000}),
            AIMessage("您目前是金卡客户……"),
        ],
        router=["SERVICE"],
    )
    body = client.post("/api/v1/chat", json={"message": "我转钱进来有什么奖励？"}).json()
    block = next(b for b in body["reply"]["ui_blocks"] if b["type"] == "tier_benefits")
    assert block["tier"]["name"] == "金卡客户"  # 测试客户 5 万
    assert (
        block["projection"]["reaches_next"] is True
        and block["projection"]["tier_name"] == "财富客户"
    )
    # 活动是否在期内由 test_campaigns_filtered_by_period_and_tier 用固定日期覆盖，这里不依赖当天日期


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


def test_reset_clears_reminders(client):
    complete_assessment(client)
    client.post("/api/v1/reminders", json={"product_code": "ZA-F06"})
    client.post("/api/v1/demo/reset")
    assert client.get("/api/v1/reminders").json() == []


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
            AIMessage("已将您的咨询要点同步给李经理，您可以通过下方名片直接联系他。"),
        ],
        router=["HANDOFF"],
    )
    body = client.post("/api/v1/chat", json={"message": "我要找理财经理"}).json()
    card = next(b for b in body["reply"]["ui_blocks"] if b["type"] == "rm_contact")
    return body, card


def rm_list(client):
    """只看测试客户的交接：同一理财经理名下可能还有演示客户的数据。"""
    rows = client.get("/api/v1/rm/handoffs", headers=RM_HEADERS).json()
    return [r for r in rows if r["customer_name"] == "测试客户（虚构）"]


def test_handoff_shows_rm_card_without_customer_data(client):  # H01
    body, card = request_handoff_in_chat(client)
    assert card["rm_name"] == "李经理（虚构）"  # 来自基础画像的专属理财经理
    assert card["rm_title"] == "高级理财经理"
    assert {"phone", "wecom_url"} <= card.keys()
    assert "同步" in card["notice"]
    # 客户界面的名片不含客户资料（测评、需求、资产等）
    assert not {"preview", "scope", "assessment", "needs"} & card.keys()
    assert body["handoff"]["status"] == "PENDING"
    assert [h["id"] for h in rm_list(client)] == [card["handoff_id"]]  # 要点已同步到看板


def test_rm_follow_up_lifecycle_and_ai_keeps_replying(client):  # H03 + H04
    body, card = request_handoff_in_chat(client)
    conv, hid = body["conversation_id"], card["handoff_id"]
    accept = client.post(f"/api/v1/rm/handoffs/{hid}/accept", headers=RM_HEADERS)
    assert accept.json()["status"] == "ACCEPTED"
    # 不再有应用内人工服务：理财经理跟进期间 AI 照常回复
    use_models(main=[AIMessage("七日年化是现金管理类产品的收益口径。")], router=["SERVICE"])
    reply = client.post("/api/v1/chat", json={"conversation_id": conv, "message": "什么是七日年化"})
    assert reply.json()["reply"]["content"].startswith("七日年化")
    resolve = client.post(f"/api/v1/rm/handoffs/{hid}/resolve", headers=RM_HEADERS)
    assert resolve.json()["status"] == "RESOLVED"
    detail = client.get(f"/api/v1/rm/handoffs/{hid}", headers=RM_HEADERS).json()
    assert [e["to"] for e in detail["events"]] == [
        "咨询要点已同步，等待理财经理跟进",
        "理财经理跟进中",
        "已结束",
    ]
    assert client.post(f"/api/v1/rm/handoffs/{hid}/accept", headers=RM_HEADERS).status_code == 409


def test_summary_is_built_from_structured_data(client):  # H05
    complete_assessment(client)
    client.patch("/api/v1/needs", json={"investment_amount": 1000000, "horizon_months": 24})
    _, card = request_handoff_in_chat(
        client, reason="HIGH_COMPLEXITY", questions=["退休后现金流规划"]
    )
    detail = client.get(f"/api/v1/rm/handoffs/{card['handoff_id']}", headers=RM_HEADERS).json()
    summary = detail["summary"]
    assert summary["reason"].startswith("专业复杂度高")
    assert summary["assessment"].startswith("C2 稳健型")
    assert {n["label"] for n in summary["needs"]} == {"计划投资金额", "投资期限"}
    assert summary["open_questions"] == ["退休后现金流规划"]
    assert "本次对话记录" in detail["sync_scope"]


def test_suitability_conflict_handoff_keeps_limits(client):  # H06
    complete_assessment(client)
    request_handoff_in_chat(client, reason="SUITABILITY_CONFLICT")
    # 联系理财经理不会解除限制：超评级产品仍不能买入
    body = client.get("/api/v1/products").json()
    assert {i["risk_level"] for i in body["items"] if i["purchasable"]} <= {"PR1", "PR2"}


def test_handoff_allowed_before_assessment(client):  # H07
    _, card = request_handoff_in_chat(client)
    summary = client.get(f"/api/v1/rm/handoffs/{card['handoff_id']}", headers=RM_HEADERS).json()
    assert summary["summary"]["assessment"] == "尚未完成风险测评"


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
            AIMessage("您可以通过下方名片联系李经理。"),
        ],
        router=["HANDOFF"],
    )
    again = client.post(
        "/api/v1/chat", json={"conversation_id": body["conversation_id"], "message": "再转一次"}
    ).json()
    shown = next(b for b in again["reply"]["ui_blocks"] if b["type"] == "rm_contact")
    assert shown["handoff_id"] == card["handoff_id"]  # 再次展示名片，不重复创建
    assert len(rm_list(client)) == 1


def test_rm_access_control(client):
    _, card = request_handoff_in_chat(client)
    other = {"X-Demo-User": "rm_zhou"}  # 不是该客户的专属理财经理
    assert client.get(f"/api/v1/rm/handoffs/{card['handoff_id']}", headers=other).status_code == 404
    assert client.get("/api/v1/rm/handoffs").status_code == 403  # 客户身份不能访问看板


# ---------- 历史会话 ----------


def test_conversation_history_lists_recent_first(client):
    use_models(main=[AIMessage("您好"), AIMessage("好的")], router=["SERVICE", "SERVICE"])
    first = client.post("/api/v1/chat", json={"message": "第一个会话"}).json()
    second = client.post("/api/v1/chat", json={"message": "第二个会话"}).json()
    rows = client.get("/api/v1/conversations").json()
    assert [r["id"] for r in rows][:2] == [second["conversation_id"], first["conversation_id"]]
    assert rows[0]["title"] == "第二个会话" and rows[0]["message_count"] == 2
    other = client.get("/api/v1/conversations", headers={"X-Demo-User": "demo_customer_1"}).json()
    assert first["conversation_id"] not in {r["id"] for r in other}


# ---------- 英文界面（P8-2b） ----------


def english(client):
    client.cookies.set("wp_locale", "en")


def test_english_fixed_replies_and_assessment_card(client):
    english(client)
    use_models(main=[], router=["OUT_OF_SCOPE"])
    body = client.post("/api/v1/chat", json={"message": "Who won the World Cup?"}).json()
    assert body["reply"]["content"].startswith("Sorry, I'm a wealth assistant")
    use_models(main=[], router=["PRODUCT_OR_ADVICE"])
    body = client.post("/api/v1/chat", json={"message": "Which product should I buy?"}).json()
    assert body["reply"]["content"].startswith("Suitability rules")
    card = body["reply"]["ui_blocks"][0]
    assert card["type"] == "assessment_prompt" and card["title"] == "Risk tolerance profile"


def test_english_tool_output_and_code_notes(client):
    """工具在 Agent 内部执行，语言上下文要一路传到工具与代码追加的说明。"""
    complete_assessment(client)
    english(client)
    use_models(
        main=[
            tool_call("calculate_growth", {"principal": 1000000, "annual_rate": 0.05, "years": 10}),
            AIMessage("About ¥1,628,894.63."),
        ],
        router=["CALCULATION"],
    )
    body = client.post("/api/v1/chat", json={"message": "1M at 5% for 10 years"}).json()
    result = body["reply"]["ui_blocks"][0]
    assert result["title"] == "10-year growth estimate"
    assert result["items"][0] == {"label": "Ending balance", "value": "1628894.63", "unit": "CNY"}
    assert body["reply"]["content"].endswith("is not a promise of returns.")


def test_english_products_and_questionnaire(client):
    english(client)
    items = client.get("/api/v1/products").json()["items"]
    cash = next(i for i in items if i["code"] == "ZA-C01")
    assert cash["name"] == "Zhian Ready Cash"
    assert cash["issuer"] == "Zhian Wealth Management"
    assert cash["lockup"] == "Open daily"
    assert cash["metric"]["label"] == "7-day annualized yield"
    detail = client.get("/api/v1/products/ZA-F04").json()
    assert detail["redemption_settlement"] == "Paid T+2 after maturity"
    assert detail["purchase"]["needs_assessment"] is True
    q = client.get("/api/v1/assessment/questionnaire").json()
    assert q["questions"][0]["text"] == "What is your age?"


def test_handoff_summary_follows_rm_locale(client):
    complete_assessment(client)
    english(client)
    _, card = request_handoff_in_chat(client, reason="HIGH_COMPLEXITY")
    assert card["rm_name"] == "RM Li (fictional)"
    assert card["notice"].startswith("Your request summary has been shared")
    hid = card["handoff_id"]
    en = client.get(f"/api/v1/rm/handoffs/{hid}", headers=RM_HEADERS).json()
    assert en["summary"]["assessment"].startswith("C2 Steady")
    assert en["status_label"] == "Summary shared; waiting for RM follow-up"
    client.cookies.set("wp_locale", "zh")
    zh = client.get(f"/api/v1/rm/handoffs/{hid}", headers=RM_HEADERS).json()
    assert zh["summary"]["assessment"].startswith("C2 稳健型")
    assert "en" not in zh["summary"]
