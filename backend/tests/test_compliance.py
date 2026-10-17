from datetime import UTC, datetime, timedelta

import pytest

from app.compliance.output_guard import check_output
from app.compliance.policy import Permission, evaluate_gate, tool_allowed
from app.db.models import RiskAssessment

NOW = datetime(2026, 10, 17, 12, 0, tzinfo=UTC)


def confirmed(rating="C2", expires_in_days=300):
    return RiskAssessment(rating=rating, expires_at=NOW + timedelta(days=expires_in_days))


# ---------- 门禁 ----------


def test_gate_requires_assessment_when_missing():  # S01
    d = evaluate_gate(None, NOW)
    assert d.permission is Permission.ASSESSMENT_REQUIRED
    assert d.reason_codes == ["ASSESSMENT_MISSING"]
    assert d.risk_rating is None


def test_gate_requires_assessment_when_expired():  # S03
    d = evaluate_gate(confirmed(expires_in_days=-1), NOW)
    assert d.permission is Permission.ASSESSMENT_REQUIRED
    assert d.reason_codes == ["ASSESSMENT_EXPIRED"]


def test_gate_passes_with_valid_assessment():
    d = evaluate_gate(confirmed("C3"), NOW)
    assert d.permission is Permission.ASSESSED
    assert d.risk_rating == "C3"


def test_pre_assessment_tool_whitelist():
    assert tool_allowed(Permission.ASSESSMENT_REQUIRED, "start_risk_assessment")
    assert tool_allowed(Permission.ASSESSMENT_REQUIRED, "calculate_growth")
    assert not tool_allowed(Permission.ASSESSMENT_REQUIRED, "calculate_fees")
    assert not tool_allowed(Permission.ASSESSMENT_REQUIRED, "search_products")
    assert tool_allowed(Permission.ASSESSED, "search_products")


# ---------- 输出审查 ----------


@pytest.mark.parametrize(
    "text",
    [
        "这款产品保证年化收益 5%。",
        "放心，稳赚不赔。",
        "这是一款零风险的产品。",
        "坚持持有一定能赚钱。",
        "我们承诺保本保收益。",
    ],
)
def test_prohibited_claims_detected(text):
    assert "O-PROHIBITED_CLAIM" in check_output(text, Permission.ASSESSED)


@pytest.mark.parametrize(
    "text",
    [
        "银行理财产品不保证收益，可能亏损本金。",
        "理财不是存款，并非无风险。",
        "世界上没有零风险的高收益产品。",
        "资管新规之后，理财产品不会保本保收益。",
        "按 5% 的假设测算，10 年后约为 162.89 万元。",
    ],
)
def test_negated_or_factual_statements_pass(text):
    assert check_output(text, Permission.ASSESSED) == []


def test_recommendation_blocked_before_assessment():  # S02e
    text = "我建议您购买一款固收类理财。"
    assert check_output(text, Permission.ASSESSMENT_REQUIRED) == ["O-PERMISSION_LEAK"]
    assert check_output(text, Permission.ASSESSED) == []


def test_negated_recommendation_passes_before_assessment():
    text = "在您完成风险测评之前，我不能推荐您购买任何产品。"
    assert check_output(text, Permission.ASSESSMENT_REQUIRED) == []


# ---------- 产品相关的输出审查 ----------


def test_real_institution_name_blocked():
    assert "O-REAL_INSTITUTION" in check_output("招银理财有一款类似产品。", Permission.ASSESSED)


def test_ungrounded_product_blocked_after_assessment():
    reply = "您可以看看知岸权益精选。"
    assert "O-UNGROUNDED_PRODUCT" in check_output(reply, Permission.ASSESSED, grounding="")
    tool_result = '{"name": "知岸权益精选", "code": "ZA-E01"}'
    assert check_output(reply, Permission.ASSESSED, grounding=tool_result) == []


def test_product_mention_before_assessment_is_leak_unless_customer_named_it():
    reply = "关于知岸活钱宝，需要您先完成风险测评。"
    assert check_output(reply, Permission.ASSESSMENT_REQUIRED) == ["O-PERMISSION_LEAK"]
    assert check_output(reply, Permission.ASSESSMENT_REQUIRED, grounding="知岸活钱宝怎么样") == []
