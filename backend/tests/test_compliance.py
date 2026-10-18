from datetime import UTC, datetime, timedelta

import pytest

from app.compliance.output_guard import check_output, describe, remove_steering
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
    # 测评后同样不输出个性化推荐结论（Phase 5 起）
    assert check_output(text, Permission.ASSESSED) == ["O-PERSONALIZED_ADVICE"]


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


# ---------- 诱导调高评级与个性化推荐（Phase 5 端到端测试中发现） ----------


@pytest.mark.parametrize(
    "text",
    [
        "如果 5% 收益目标优先，可能需要承担更高波动（PR3 及以上），如需调整需重新测评。",
        "想要更高收益的话，您可以重新评估风险承受能力。",
        # P7 场景评估 S01：把重新测评当作了解更高等级产品的途径
        "如果您希望了解权益类产品，需要重新完成风险测评且结果达到相应等级。",
    ],
)
def test_reassessment_steering_blocked(text):
    for permission in Permission:
        assert "O-REASSESSMENT_STEERING" in check_output(text, permission)


def test_reassessment_allowed_when_circumstances_change():
    text = "如果您的收入或资产情况发生了变化，可以重新测评。"
    assert check_output(text, Permission.ASSESSED) == []


def test_neutral_reassessment_mentions_pass():
    for text in (
        "如果您的情况确实发生了变化（如收入、资产规模有重大改变），可以重新进行风险测评。",
        "如果您希望重新测评，我可以为您打开测评入口。",
    ):
        assert check_output(text, Permission.ASSESSED) == []


def test_remove_steering_keeps_rest_of_reply():
    reply = (
        "您当前评级为 C2，可购买 PR2 及以下产品。\n\n"
        "如果您希望了解权益类产品，需要重新完成风险测评且结果达到相应等级。"
        "我可以为您查找 PR2 及以下的产品。"
    )
    redacted = remove_steering(reply)
    assert (
        redacted == "您当前评级为 C2，可购买 PR2 及以下产品。\n\n我可以为您查找 PR2 及以下的产品。"
    )
    assert check_output(redacted, Permission.ASSESSED) == []


def test_rewrite_feedback_quotes_steering_sentence():
    reply = "想要更高收益的话，您可以重新评估风险承受能力。"
    assert "想要更高收益的话" in describe(["O-REASSESSMENT_STEERING"], reply)


def test_personalized_advice_blocked_after_assessment():
    assert "O-PERSONALIZED_ADVICE" in check_output("建议配置现金管理类产品。", Permission.ASSESSED)
    assert "O-PERSONALIZED_ADVICE" in check_output("这款很适合您。", Permission.ASSESSED)
    neutral = "在您的风险等级范围内的产品包括现金管理类和固定收益类。"
    assert check_output(neutral, Permission.ASSESSED) == []


# ---------- 虚构真人接入（Phase 6） ----------


@pytest.mark.parametrize(
    "text",
    ["已为您接通理财经理。", "已为您联系了李经理，请稍候。", "理财经理已接入，正在为您服务。"],
)
def test_false_handoff_claim_blocked(text):
    assert "O-FALSE_HANDOFF_CLAIM" in check_output(text, Permission.ASSESSED)


@pytest.mark.parametrize(
    "text",
    [
        "已生成转人工请求，请在下方确认分享的信息。",
        "已提交，等待理财经理接单。",
        "理财经理尚未接单。",
    ],
)
def test_accurate_handoff_status_passes(text):
    assert check_output(text, Permission.ASSESSED) == []


# ---------- 场景评估中发现的问题（2026-10-17） ----------


def test_quoted_warning_is_not_a_claim():
    text = "如果销售人员说某款产品“保本”“肯定能赚”，这属于违规宣传，不应相信。"
    assert check_output(text, Permission.ASSESSED) == []


def test_quoted_claim_without_warning_is_still_blocked():
    # 不能靠加引号绕过：没有警示语境的引号内承诺仍然拦截
    assert "O-PROHIBITED_CLAIM" in check_output("这款产品“稳赚”，放心买。", Permission.ASSESSED)


def test_steering_via_rm_to_higher_risk_level_blocked():
    text = "建议联系理财经理评估是否需要更高的风险等级，以达到 5% 的目标。"
    assert "O-REASSESSMENT_STEERING" in check_output(text, Permission.ASSESSED)


def test_stating_tradeoff_without_steering_passes():
    text = "若收益目标较为刚性，需承担更高波动风险（PR3 及以上），但这超出当前风险等级。"
    assert check_output(text, Permission.ASSESSED) == []


def test_tradeoff_with_limitation_passes_but_reassessment_option_blocked():
    ok = "若坚持该收益预期，可能需要考虑更高风险等级的产品，但这与您的风险测评结果不匹配。"
    assert check_output(ok, Permission.ASSESSED) == []
    bad = "如果您希望更接近 5% 的目标，可能需要提升风险等级（需重新测评）或接受更大波动。"
    assert "O-REASSESSMENT_STEERING" in check_output(bad, Permission.ASSESSED)


@pytest.mark.parametrize(
    "text",
    [
        "目前没有任何一款理财产品是保本保收益的。",
        "银行理财中不存在保证收益的产品。",
        "监管禁止机构承诺稳赚不赔。",
    ],
)
def test_distant_negation_in_same_clause_passes(text):
    assert check_output(text, Permission.ASSESSED) == []


@pytest.mark.parametrize(
    "text",
    [
        "这款产品不仅保本保收益，而且流动性好。",  # 「不仅」不是否定
        "它不会亏，保证收益。",  # 否定词在前一个分句
    ],
)
def test_negation_does_not_leak_across_clauses_or_from_buzhi(text):
    assert "O-PROHIBITED_CLAIM" in check_output(text, Permission.ASSESSED)
