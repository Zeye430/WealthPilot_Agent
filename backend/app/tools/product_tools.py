"""产品类 LLM 工具：只在客户完成测评后绑定（见 app/compliance/policy.py）。

客户风险评级通过 InjectedState 从流程状态读取，对 LLM 不可见、不可修改。
工具返回给 LLM 的是事实与适当性结论；给前端的 UI 块不经 LLM 改写。
"""

import json
from decimal import Decimal
from typing import Annotated

from langchain_core.tools import ToolException, tool
from langgraph.prebuilt import InjectedState
from pydantic import Field

from app.assessment.scoring import load_questionnaire
from app.compliance.suitability import REASON_LABELS, RISK_EXCEEDS, CustomerContext, evaluate
from app.products import presenter
from app.products.catalog import (
    METRIC_LABELS,
    MetricType,
    ProductType,
    load_catalog,
)
from app.products.service import SearchFilters, search

TYPE_HELP = (
    "产品类型，可多选：CASH_MANAGEMENT 现金管理类、FIXED_INCOME 固定收益类、"
    "FIXED_INCOME_PLUS 固收+、MIXED 混合类、EQUITY 权益类"
)
NOT_ADVICE = (
    "以下为您风险等级范围内的产品信息，不构成投资建议；业绩比较基准不是预期收益率，不代表实际收益。"
)


def _context(state: dict, amount: float | None = None, horizon_months: int | None = None):
    rating = state.get("risk_rating")
    if not rating:
        # 理论上不会发生：未测评时这些工具不会绑定给 LLM。防御性检查。
        raise ToolException("客户尚未完成有效的风险测评，无法查询产品。")
    return CustomerContext(
        risk_rating=rating,
        investment_amount=Decimal(str(amount)) if amount else None,
        horizon_days=months_to_days(horizon_months) if horizon_months else None,
    )


def months_to_days(months: int) -> int:
    """12 个月 = 365 天：按 30 天换算会把「一年持有」误判为超过一年期限。"""
    return round(months * 365 / 12)


def _dump(data: dict) -> str:
    return json.dumps(data, ensure_ascii=False, default=str)


@tool(response_format="content_and_artifact")
def search_products(
    state: Annotated[dict, InjectedState],
    product_types: Annotated[list[ProductType] | None, Field(description=TYPE_HELP)] = None,
    max_lockup_days: Annotated[
        int | None, Field(description="客户能接受的最长持有或封闭天数；客户说「随时要用」填 0")
    ] = None,
    investment_amount: Annotated[
        float | None, Field(description="客户说明的计划投资金额（元），未说明不填")
    ] = None,
    horizon_months: Annotated[
        int | None, Field(description="客户说明的投资期限（月），未说明不填")
    ] = None,
    keyword: Annotated[str | None, Field(description="名称或投资范围关键词，如「纯债」")] = None,
) -> tuple[str, list[dict]]:
    """在客户风险等级范围内搜索理财产品，并按期限匹配、流动性、费用排序。

    超出客户风险等级、已到期、起购金额或期限不符的产品会被自动排除。
    客户想了解有哪些产品、要求筛选或推荐时使用。
    """
    ctx = _context(state, investment_amount, horizon_months)
    result = search(
        load_catalog(),
        ctx,
        SearchFilters(
            product_types=product_types, max_lockup_days=max_lockup_days, keyword=keyword
        ),
    )
    items = [
        {**presenter.card(r.product), "rank": i + 1, "rank_factors": r.explanation()}
        for i, r in enumerate(result.ranked)
    ] + [{**presenter.card(p), "rank": None, "warnings": e.messages} for p, e in result.unranked]
    excluded = [{"reason": REASON_LABELS[code], "count": n} for code, n in result.excluded.items()]
    band = load_questionnaire().band(ctx.risk_rating)
    content = {
        "customer_rating": f"{ctx.risk_rating} {band.name}，可购买 {band.max_product_risk} 及以下",
        "products": [
            {k: item[k] for k in ("code", "name", "type_label", "risk_level", "lockup", "minimum")}
            | {
                "metric": f"{item['metric']['label']} {item['metric']['text']}",
                "rank": item["rank"],
            }
            for item in items
        ],
        "excluded": excluded,
        "rules": "只能介绍列表中的产品；不要说「适合您」「推荐购买」，"
        "可以说「在您的风险等级范围内」；排序依据是期限匹配、流动性和费用，不是收益。",
    }
    artifact = {
        "type": "product_list",
        "title": f"您的风险等级范围内的产品（{band.max_product_risk} 及以下）",
        "items": items,
        "excluded": excluded,
        "ranking_note": "排序依据：期限匹配、流动性、费用；不按收益排序。",
        "disclaimer": NOT_ADVICE,
    }
    return _dump(content), [artifact]


@tool(response_format="content_and_artifact")
def get_product_details(
    state: Annotated[dict, InjectedState],
    product: Annotated[str, Field(description="产品代码（如 ZA-F03）或名称（如「活钱宝」）")],
) -> tuple[str, list[dict]]:
    """查询某一款产品的完整要素：投资范围、费用、收益指标、适当性结论。

    客户点名询问某款产品时使用。超出客户风险等级的产品也可查看条款，但会附风险提示。
    """
    ctx = _context(state)
    found = load_catalog().find_by_name(product)
    if found is None:
        raise ToolException(
            f"未找到产品「{product}」。产品目录中只有知岸理财、鸿屿理财的虚构产品。"
        )
    eligibility = evaluate(found, ctx)
    detail = {
        **presenter.detail(found),
        "eligible": eligibility.eligible,
        "eligibility_messages": eligibility.messages,
    }
    content = {
        **{
            k: detail[k]
            for k in (
                "code",
                "name",
                "issuer",
                "type_label",
                "risk_level",
                "lockup",
                "minimum",
                "investment_scope",
                "fees",
                "metrics",
            )
        },
        "eligible_for_customer": eligibility.eligible,
        "eligibility_messages": eligibility.messages,
        "rules": "如实转述条款；eligible_for_customer 为 false 时必须说明原因，不得推荐。",
    }
    return _dump(content), [{"type": "product_detail", **detail}]


@tool(response_format="content_and_artifact")
def compare_products(
    state: Annotated[dict, InjectedState],
    products: Annotated[list[str], Field(description="2–4 个产品代码或名称")],
) -> tuple[str, list[dict]]:
    """对比 2–4 款产品的要素。收益指标按口径分列，不同口径不做高低比较。

    超出客户风险等级的产品不纳入对比。
    """
    ctx = _context(state)
    catalog = load_catalog()
    if not 2 <= len(products) <= 4:
        raise ToolException("请提供 2 到 4 个产品进行对比。")
    found, missing, left_out = [], [], []
    for name in products:
        p = catalog.find_by_name(name)
        if p is None:
            missing.append(name)
        elif RISK_EXCEEDS in evaluate(p, ctx).reason_codes:
            left_out.append(f"{p.name}（{p.effective_risk_level}，超出您的风险等级）")
        else:
            found.append(p)
    if missing:
        raise ToolException(f"未找到产品：{'、'.join(missing)}")
    if len(found) < 2:
        raise ToolException("可对比的产品不足 2 款：" + "；".join(left_out))

    metric_rows = [
        t
        for t in (
            MetricType.SEVEN_DAY_ANNUALIZED,
            MetricType.PERFORMANCE_BENCHMARK,
            MetricType.ANNUAL_PERFORMANCE,
        )
        if any(p.metric(t) for p in found)
    ]
    rows = [
        {"label": "发行机构", "values": [p.issuer for p in found]},
        {"label": "产品类型", "values": [p.type_label for p in found]},
        {"label": "风险等级", "values": [p.effective_risk_level for p in found]},
        {"label": "流动性", "values": [presenter.lockup_text(p) for p in found]},
        {
            "label": "起购金额",
            "values": [presenter.format_money(p.minimum_investment) for p in found],
        },
        {
            "label": "年化固定费用合计",
            "values": [presenter.format_rate(p.fees.annual_total) for p in found],
        },
        {"label": "赎回费", "values": [presenter.redemption_fee_text(p) for p in found]},
    ] + [
        {
            "label": METRIC_LABELS[t],
            "values": [presenter.metric_text(p, t) or "—" for p in found],
            "metric": True,
        }
        for t in metric_rows
    ]
    mixed = len({p.product_type is ProductType.CASH_MANAGEMENT for p in found}) > 1
    notes = []
    if mixed:
        notes.append("七日年化收益率与业绩比较基准口径不同，不能直接比较高低。")
    if left_out:
        notes.append("未纳入对比：" + "；".join(left_out) + "。可单独查看其条款。")
    artifact = {
        "type": "comparison_table",
        "columns": [{"code": p.code, "name": p.name} for p in found],
        "rows": rows,
        "notes": notes,
        "disclaimer": NOT_ADVICE,
    }
    content = {
        "columns": [p.name for p in found],
        "rows": {r["label"]: r["values"] for r in rows},
        "notes": notes,
        "rules": "如实转述对比结果；不同收益口径不得比较高低；不要给出「哪款更好」的结论。",
    }
    return _dump(content), [artifact]


PRODUCT_TOOLS = [search_products, get_product_details, compare_products]
for _t in PRODUCT_TOOLS:
    _t.handle_tool_error = True
    _t.handle_validation_error = True
