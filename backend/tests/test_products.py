"""产品目录、适当性规则、排序与说明书测试。"""

import json
from decimal import Decimal
from pathlib import Path

import pytest
import yaml
from pydantic import ValidationError

from app.compliance.suitability import (
    BELOW_MINIMUM,
    HORIZON_MISMATCH,
    NOT_ON_SALE,
    RISK_EXCEEDS,
    UNVERIFIED,
    CustomerContext,
    evaluate,
)
from app.products.catalog import CATALOG_PATH, Catalog, MetricType, load_catalog, parse_rate
from app.products.documents import render
from app.products.ranking import rank
from app.products.service import SearchFilters, search, upcoming
from app.tools.product_tools import compare_products, get_product_details, months_to_days

CATALOG = load_catalog()
C2 = CustomerContext(risk_rating="C2")
DOCS_DIR = Path(__file__).resolve().parents[2] / "data/products/docs"


def p(code):
    return CATALOG.get(code)


def raw_catalog() -> dict:
    return yaml.safe_load(CATALOG_PATH.read_text(encoding="utf-8"))


# ---------- 目录与校验 ----------


def test_catalog_distribution_matches_product_catalog_doc():
    levels = sorted(p.effective_risk_level for p in CATALOG.products)
    assert len(levels) == 18  # 16 款在售 / 已到期 + 2 款即将发售
    assert {lv: levels.count(lv) for lv in set(levels)} == {
        "PR1": 2,
        "PR2": 10,
        "PR3": 3,
        "PR4": 2,
        "PR5": 1,
    }
    assert all(p.data_origin == "SYNTHETIC" for p in CATALOG.products)


def test_parse_rate_is_exact():
    assert parse_rate("0.10%") == Decimal("0.001")
    with pytest.raises(ValueError):
        parse_rate("0.10")


def test_effective_risk_takes_higher_rating():  # 评级取高
    assert p("HY-P01").issuer_risk_level == "PR2"
    assert p("HY-P01").effective_risk_level == "PR3"


def test_missing_fee_cannot_be_marked_verified():
    data = raw_catalog()
    hy_f04 = next(x for x in data["products"] if x["code"] == "HY-F04")
    hy_f04["data_quality"] = "VERIFIED"
    with pytest.raises(ValidationError, match="费率缺失"):
        Catalog.model_validate(data)


def test_cash_product_requires_seven_day_yield():
    data = raw_catalog()
    cash = next(x for x in data["products"] if x["code"] == "ZA-C01")
    cash["metrics"] = [{"type": "PERFORMANCE_BENCHMARK", "low": "1%", "high": "2%", "basis": "x"}]
    with pytest.raises(ValidationError, match="七日年化"):
        Catalog.model_validate(data)


def test_code_prefix_must_match_issuer():
    data = raw_catalog()
    data["products"][0]["issuer"] = "鸿屿理财"
    with pytest.raises(ValidationError, match="前缀"):
        Catalog.model_validate(data)


def test_find_by_partial_name():
    assert CATALOG.find_by_name("活钱宝").code == "ZA-C01"
    assert CATALOG.find_by_name("za-f03").code == "ZA-F03"
    assert CATALOG.find_by_name("不存在的产品") is None


# ---------- 适当性规则 ----------


def test_c2_cannot_buy_pr3_and_above():  # S04
    for product in CATALOG.products:
        allowed = int(product.effective_risk_level[2:]) <= 2
        assert (RISK_EXCEEDS not in evaluate(product, C2).reason_codes) is allowed


def test_over_rating_product_message():  # S04b
    result = evaluate(p("ZA-M01"), C2)
    assert not result.eligible
    assert "无权限购买" in result.messages[0]


def test_below_minimum_investment():  # S08
    ctx = CustomerContext(risk_rating="C2", investment_amount=Decimal("100000"))
    assert BELOW_MINIMUM in evaluate(p("HY-F03"), ctx).reason_codes
    assert evaluate(p("ZA-F04"), ctx).eligible


def test_horizon_mismatch():  # S09
    ctx = CustomerContext(risk_rating="C2", horizon_days=months_to_days(12))
    assert HORIZON_MISMATCH in evaluate(p("HY-F02"), ctx).reason_codes
    assert evaluate(p("ZA-F03"), ctx).eligible  # 一年持有 ≤ 12 个月


def test_ended_product_not_eligible():  # S12 类
    assert NOT_ON_SALE in evaluate(p("ZA-F05"), C2).reason_codes


def test_unverified_product_shown_but_not_ranked():  # S13
    result = evaluate(p("HY-F04"), C2)
    assert result.eligible and not result.rankable
    assert UNVERIFIED in result.reason_codes
    assert "托管费" in result.messages[0]


def test_c5_sees_everything_on_sale():
    result = search(CATALOG, CustomerContext(risk_rating="C5"), SearchFilters())
    assert len(result.ranked) + len(result.unranked) == 15
    assert result.excluded == {NOT_ON_SALE: 1}


# ---------- 排序与查询 ----------


def test_search_excludes_and_counts():
    result = search(CATALOG, C2, SearchFilters())
    codes = [r.product.code for r in result.ranked]
    assert all(int(CATALOG.get(c).effective_risk_level[2:]) <= 2 for c in codes)
    assert [prod.code for prod, _ in result.unranked] == ["HY-F04"]
    assert result.excluded == {RISK_EXCEEDS: 5, NOT_ON_SALE: 1}


def test_upcoming_products_follow_same_suitability_rules():
    assert [x.code for x in upcoming(CATALOG, C2)] == ["ZA-F06"]  # PR3 新品对 C2 不展示
    assert {x.code for x in upcoming(CATALOG, CustomerContext(risk_rating="C3"))} == {
        "ZA-F06",
        "HY-P02",
    }
    short = CustomerContext(risk_rating="C3", horizon_days=90)
    assert upcoming(CATALOG, short) == []  # 封闭 365 天、持有 180 天都超过 90 天期限
    message = evaluate(p("ZA-F06"), C2).messages[0]
    assert "尚未开售" in message and "10 月 26 日" in message


def test_upcoming_product_requires_sale_window():
    data = raw_catalog()
    za_f06 = next(x for x in data["products"] if x["code"] == "ZA-F06")
    del za_f06["sale_start"]
    with pytest.raises(ValidationError, match="募集期"):
        Catalog.model_validate(data)


def test_filters_apply_before_suitability():
    result = search(CATALOG, C2, SearchFilters(max_lockup_days=0))
    assert {r.product.code for r in result.ranked} == {"ZA-C01", "HY-C01", "ZA-F01"}


def test_ranking_ignores_benchmark():
    # 两个仅业绩比较基准不同的产品，排序结果不应改变
    a, b = p("ZA-F02"), p("HY-F01")
    boosted = b.model_copy(deep=True)
    boosted.metrics[0].high = Decimal("0.10")
    assert [r.product.code for r in rank([a, b])] == [r.product.code for r in rank([a, boosted])]


def test_ranking_is_deterministic_and_explainable():
    first = rank([p(c) for c in ("ZA-F01", "ZA-F02", "HY-F01")], horizon_days=90)
    second = rank([p(c) for c in ("HY-F01", "ZA-F02", "ZA-F01")], horizon_days=90)
    assert [r.product.code for r in first] == [r.product.code for r in second]
    assert "期限匹配" in first[0].explanation()


# ---------- 工具（风险评级来自注入的状态） ----------


def test_tools_hide_rating_from_llm():
    for t in (get_product_details, compare_products):
        assert "state" not in t.tool_call_schema.model_json_schema()["properties"]


def test_compare_splits_metrics_and_leaves_out_over_rating():
    content, [block] = compare_products.func(
        state={"risk_rating": "C2"}, products=["活钱宝", "ZA-F01", "ZA-M01"]
    )
    rows = {r["label"]: r["values"] for r in block["rows"]}
    assert rows["七日年化收益率"] == ["1.42%（截至 10-16）", "—"]
    assert rows["业绩比较基准"] == ["—", "1.90%–2.50%"]
    assert any("口径不同" in n for n in block["notes"])
    assert any("知岸均衡配置" in n for n in block["notes"])
    assert "知岸均衡配置" not in json.loads(content)["columns"]


def test_detail_of_over_rating_product_is_viewable_with_warning():  # S04b
    content, [block] = get_product_details.func(state={"risk_rating": "C2"}, product="ZA-E01")
    assert block["eligible"] is False
    assert block["investment_scope"]
    assert json.loads(content)["eligible_for_customer"] is False


def test_tool_rejects_missing_rating():
    from langchain_core.tools import ToolException

    with pytest.raises(ToolException):
        get_product_details.func(state={}, product="ZA-F01")


# ---------- 说明书 ----------


def test_generated_docs_are_up_to_date():
    """说明书是要素的派生物：改了 products.yaml 必须重新生成。"""
    for product in CATALOG.products:
        path = DOCS_DIR / f"{product.code}.md"
        assert path.exists(), f"缺少 {path.name}，请运行 scripts/generate_product_docs.py"
        assert path.read_text(encoding="utf-8") == render(product, CATALOG), (
            f"{path.name} 与 products.yaml 不一致，请运行 scripts/generate_product_docs.py"
        )


def test_docs_have_fiction_notice_and_sections():
    doc = render(p("ZA-F03"), CATALOG)
    assert doc.startswith("【虚构演示文件】")
    for section in ("## 四、产品费用", "## 七、风险揭示"):
        assert section in doc
    assert "2025 年度" in doc  # 过往业绩按会计年度展示


def test_cash_doc_mentions_same_day_redemption_limit():
    assert "不高于 1 万元" in render(p("ZA-C01"), CATALOG)
    assert p("ZA-C01").metric(MetricType.SEVEN_DAY_ANNUALIZED) is not None
