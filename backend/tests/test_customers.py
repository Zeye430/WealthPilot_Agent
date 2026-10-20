"""Customer base profile, context assembly and allocation simulation tests (no database)."""

from decimal import Decimal as D

import pytest

from app.benefits.service import active_campaigns, load_benefits, tier_status
from app.customers.base import age_option, get_customer_info_system
from app.customers.context import (
    age_conflict_note,
    prompt_section,
    tier_lines,
    tier_upgrade_note,
)
from app.customers.needs import Needs
from app.products.allocation import FAIL, OK, WARN, AllocationError, simulate
from app.products.catalog import load_catalog

CATALOG = load_catalog()
MAIN_NEEDS = Needs(
    investment_amount=D(1000000),
    horizon_months=24,
    liquidity_reserve=D(200000),
    target_annual_return=D("0.05"),
)
MAIN_PLAN = [
    ("知岸活钱宝", D(200000)),
    ("知岸稳享一年持有", D(400000)),
    ("知岸定享 180 天第 12 期", D(250000)),
    ("鸿屿安盈 60 天持有", D(150000)),
]


def status(result, label):
    return [c.status for c in result.checks if c.label == label]


# ---------- Base profile ----------


def test_base_profile_is_read_from_bank_system():
    base = get_customer_info_system().get("demo_customer_1")
    assert base.age == 52 and base.kyc_verified
    # ¥150,000 checking + ¥50,000 in daily-open Zhian Ready Cash; time deposits don't count
    assert base.assets_at_bank.liquid_total() == D(200000)
    summary = base.summary()
    assert summary["source"] == "知岸银行客户信息系统（模拟）"
    assert summary["assets"]["holdings"][0]["name"] == "知岸活钱宝"


def test_unknown_customer_has_no_base_profile():
    assert get_customer_info_system().get("nobody") is None


@pytest.mark.parametrize(("age", "option"), [(25, "A"), (31, "B"), (52, "C"), (60, "D"), (70, "E")])
def test_age_prefill_matches_questionnaire_bands(age, option):
    assert age_option(age) == option


def test_prompt_section_layers_base_and_needs():
    base = get_customer_info_system().get("demo_customer_1")
    text = prompt_section(base, Needs(investment_amount=D(1000000)))
    assert "来自知岸银行客户信息系统，只读" in text
    assert "52 岁" in text and "李经理（虚构）" in text
    assert "计划投资金额：100 万元" in text
    assert "投资期限：未提供" in text
    assert "不要再向客户询问" in text


# ---------- Allocation simulation ----------


def test_main_scenario_allocation_passes_with_target_warning():  # S14
    r = simulate(MAIN_PLAN, CATALOG, "C2", MAIN_NEEDS, existing_liquid=D(200000))
    assert r.passed
    assert sum(s.pct for s in r.slices) == 1
    assert status(r, "流动性") == [OK]
    assert status(r, "目标收益") == [WARN]  # 3.20% ceiling is below the 5% target
    assert r.annual_fee == D("5405.00")  # 640 + 2520 + 1300 + 945


def test_insufficient_liquidity_fails():
    plan = [("知岸稳享一年持有", D(900000)), ("知岸活钱宝", D(100000))]
    assert status(simulate(plan, CATALOG, "C2", MAIN_NEEDS), "流动性") == [FAIL]


def test_over_rating_product_fails():
    plan = [("知岸均衡配置", D(500000)), ("知岸活钱宝", D(500000))]
    r = simulate(plan, CATALOG, "C2", MAIN_NEEDS)
    assert not r.passed
    assert any("无权限购买" in c.message for c in r.checks if c.status == FAIL)


def test_total_mismatch_fails_and_concentration_warns():
    r = simulate(
        [("知岸稳享一年持有", D(600000)), ("活期存款", D(300000))], CATALOG, "C2", MAIN_NEEDS
    )
    assert status(r, "合计金额") == [FAIL]
    assert status(r, "集中度") == [WARN]


def test_amount_below_product_minimum_fails():
    plan = [("鸿屿臻享一年封闭第 8 期", D(100000)), ("活期存款", D(900000))]
    r = simulate(plan, CATALOG, "C2", MAIN_NEEDS)
    assert any("起购金额" in c.message for c in r.checks)


def test_unverified_fee_cannot_be_estimated():
    plan = [("鸿屿安享半年定开", D(500000)), ("活期存款", D(500000))]
    r = simulate(plan, CATALOG, "C2", MAIN_NEEDS)
    assert status(r, "固定费用") == [WARN] and r.annual_fee is None


def test_invalid_items_raise():
    with pytest.raises(AllocationError):
        simulate([("不存在的产品", D(1000))], CATALOG, "C2", MAIN_NEEDS)
    with pytest.raises(AllocationError):
        simulate([("知岸活钱宝", D(0))], CATALOG, "C2", MAIN_NEEDS)


def test_age_conflict_note_when_reply_ignores_bank_record():  # P7 scenario M02
    base = get_customer_info_system().get("demo_customer_1")  # age 52
    note = age_conflict_note("我今年35岁，帮我看看产品", "以下是产品……", base)
    assert note and "52 岁" in note and "网点更新" in note
    assert age_conflict_note("我今年35岁", "根据登记，您的年龄为 52 岁……", base) is None
    assert age_conflict_note("我52岁", "以下是产品……", base) is None
    assert age_conflict_note("我想买理财", "以下是产品……", base) is None


# ---------- Customer tiers and campaigns (2026-10-18) ----------


def test_bank_recorded_tier_matches_benefit_thresholds():
    """The tier in the base profile (bank records) must match the tier rules, so demo data stays
    consistent."""
    system = get_customer_info_system()
    for cid in ("demo_customer_1", "demo_customer_2", "pytest_customer", "eval_customer"):
        base = system.get(cid)
        assert tier_status(base).tier.name == base.customer_tier, cid


def test_tier_gap_and_projection_with_new_money():
    chen = get_customer_info_system().get("demo_customer_2")  # ¥80,000, Gold
    status = tier_status(chen, D(450000))
    assert status.tier.name == "金卡客户" and status.next_tier.name == "财富客户"
    assert status.gap == D(420000)
    assert status.reaches_next_with_plan and status.projected_tier.name == "财富客户"
    assert not tier_status(chen, D(100000)).reaches_next_with_plan


def test_tier_hint_only_when_plan_reaches_next_tier():
    chen = get_customer_info_system().get("demo_customer_2")
    hinted = "\n".join(tier_lines(chen, Needs(investment_amount=D(450000))))
    assert "由系统在回答末尾自动补充" in hinted
    assert "自动补充" not in "\n".join(tier_lines(chen, Needs()))


def test_campaigns_filtered_by_period_and_tier():
    config = load_benefits()
    wealth = next(t for t in config.tiers if t.code == "WEALTH")
    gold = next(t for t in config.tiers if t.code == "GOLD")
    from datetime import date

    assert {c.id for c in active_campaigns(gold, date(2026, 10, 18))} == {
        "NEW_ASSET_2026Q4",
        "FIRST_WEALTH_2026Q4",
    }
    assert {c.id for c in active_campaigns(wealth, date(2026, 10, 18))} == {"NEW_ASSET_2026Q4"}
    assert active_campaigns(gold, date(2027, 1, 5)) == []  # campaign has ended


def test_tier_upgrade_note_once_per_conversation():  # scenario V02
    chen = get_customer_info_system().get("demo_customer_2")
    needs = Needs(investment_amount=D(450000))
    note = tier_upgrade_note(chen, needs, "为您推荐以下产品……", history="")
    assert note and "财富客户" in note and "新转入" in note and "以银行评定结果为准" in note
    assert tier_upgrade_note(chen, needs, "……可达到财富客户标准", history="") is None
    assert tier_upgrade_note(chen, needs, "……", history="之前提过财富客户") is None
    assert tier_upgrade_note(chen, Needs(investment_amount=D(100000)), "……", history="") is None
