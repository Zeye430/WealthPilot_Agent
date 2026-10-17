"""客户基础画像、上下文组装与配置模拟测试（不依赖数据库）。"""

from decimal import Decimal as D

import pytest

from app.customers.base import age_option, get_customer_info_system
from app.customers.context import prompt_section
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


# ---------- 基础画像 ----------


def test_base_profile_is_read_from_bank_system():
    base = get_customer_info_system().get("demo_customer_1")
    assert base.age == 52 and base.kyc_verified
    # 活期 15 万 + 每日开放的知岸活钱宝 5 万；定期不计入
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


# ---------- 配置模拟 ----------


def test_main_scenario_allocation_passes_with_target_warning():  # S14
    r = simulate(MAIN_PLAN, CATALOG, "C2", MAIN_NEEDS, existing_liquid=D(200000))
    assert r.passed
    assert sum(s.pct for s in r.slices) == 1
    assert status(r, "流动性") == [OK]
    assert status(r, "目标收益") == [WARN]  # 3.20% 上限低于 5% 目标
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
