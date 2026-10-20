"""Product LLM tools: bound only after the customer completes a risk assessment (see
app/compliance/policy.py).

The customer's risk rating is read from the flow state via InjectedState, invisible to the LLM and
unchangeable by it.
Tools return facts and suitability conclusions to the LLM; UI blocks for the frontend aren't
rewritten by the LLM. Tool docstrings are the tool descriptions sent to the model, so they stay in
Chinese like the prompts.
"""

import json
from decimal import Decimal
from typing import Annotated

from langchain_core.tools import ToolException, tool
from langgraph.prebuilt import InjectedState
from pydantic import Field

from app.assessment.scoring import load_questionnaire
from app.compliance.suitability import RISK_EXCEEDS, CustomerContext, evaluate, reason_label
from app.core.i18n import L
from app.products import presenter
from app.products.catalog import (
    MetricType,
    ProductType,
    issuer_label,
    load_catalog,
    metric_label,
)
from app.products.service import SearchFilters, search, upcoming
from app.reminders.service import CHAT, ReminderError, create_reminder, reminded_codes


def _session():
    from sqlalchemy.orm import sessionmaker

    from app.db.session import get_engine

    return sessionmaker(bind=get_engine(), expire_on_commit=False)()


def _reminded(customer_id: str | None) -> set[str]:
    if not customer_id:
        return set()
    try:
        with _session() as db:
            return reminded_codes(db, customer_id)
    except Exception:
        return set()


def upcoming_note() -> str:
    return L(
        "新品尚未开售，可预约开售提醒；开售后需由您本人确认买入。",
        "Not on sale yet. You can set a sale reminder; once it opens, you confirm any "
        "purchase yourself.",
    )


def upcoming_block(products, reminded: set[str]) -> dict:
    return {
        "type": "upcoming_products",
        "items": [{**presenter.card(p), "reminded": p.code in reminded} for p in products],
        "note": upcoming_note(),
        "disclaimer": product_disclaimer(),
    }


def _recorded_needs(customer_id: str | None):
    """Read recorded current needs; None without a customer identity or if the database is down
    (the query still works)."""
    if not customer_id:
        return None
    try:
        from sqlalchemy.orm import sessionmaker

        from app.customers.needs import get_needs
        from app.db.session import get_engine

        with sessionmaker(bind=get_engine())() as db:
            return get_needs(db, customer_id)
    except Exception:
        return None


TYPE_HELP = (
    "产品类型，可多选：CASH_MANAGEMENT 现金管理类、FIXED_INCOME 固定收益类、"
    "FIXED_INCOME_PLUS 固收+、MIXED 混合类、EQUITY 权益类"
)


def product_disclaimer() -> str:
    return L(
        "理财非存款、产品有风险、投资须谨慎。匹配依据为您的风险等级、期限和流动性需求，"
        "不构成收益承诺；业绩比较基准不是预期收益率，不代表实际收益。",
        "Wealth products are not deposits and carry risk; invest with care. Matches are based "
        "on your risk level, time horizon and liquidity needs, not a promise of returns. A "
        "performance benchmark is not an expected return.",
    )


def _context(state: dict, amount: float | None = None, horizon_months: int | None = None):
    rating = state.get("risk_rating")
    if not rating:
        # Shouldn't happen: these tools aren't bound to the LLM without an assessment. Defensive
        # check.
        raise ToolException("客户尚未完成有效的风险测评，无法查询产品。")
    if amount is None or horizon_months is None:
        # Needs the customer already gave in chat don't have to be passed again by the model
        needs = _recorded_needs(state.get("customer_id"))
        if needs:
            amount = amount or (float(needs.investment_amount) if needs.investment_amount else None)
            horizon_months = horizon_months or needs.horizon_months
    return CustomerContext(
        risk_rating=rating,
        investment_amount=Decimal(str(amount)) if amount else None,
        horizon_days=months_to_days(horizon_months) if horizon_months else None,
    )


def months_to_days(months: int) -> int:
    """12 months = 365 days: converting at 30 days a month would treat a "one-year holding"
    product as longer than a one-year horizon."""
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
    """在客户风险等级范围内，按需求（期限、流动性、费用）匹配理财产品。

    超出客户风险等级、已到期、起购金额或期限不符的产品会被自动排除。
    客户想了解有哪些产品、要求筛选或推荐时使用。
    """
    ctx = _context(state, investment_amount, horizon_months)
    upcoming_matches = [
        p
        for p in upcoming(load_catalog(), ctx)
        if not product_types or p.product_type in product_types
        if max_lockup_days is None or p.lockup_days <= max_lockup_days
    ]
    result = search(
        load_catalog(),
        ctx,
        SearchFilters(
            product_types=product_types, max_lockup_days=max_lockup_days, keyword=keyword
        ),
    )
    items = [
        {
            **presenter.card(r.product),
            "rank": i + 1,
            "rank_factors": r.explanation(),
            "highlights": r.highlights(),
            "purchasable": True,
        }
        for i, r in enumerate(result.ranked)
    ] + [
        {**presenter.card(p), "rank": None, "warnings": e.messages, "purchasable": True}
        for p, e in result.unranked
    ]
    excluded = [{"reason": reason_label(code), "count": n} for code, n in result.excluded.items()]
    band = load_questionnaire().band(ctx.risk_rating)
    content = {
        "customer_rating": L(
            f"{ctx.risk_rating} {band.name}，可购买 {band.max_product_risk} 及以下",
            f"{ctx.risk_rating} {band.name_en}, eligible for {band.max_product_risk} and below",
        ),
        "products": [
            {k: item[k] for k in ("code", "name", "type_label", "risk_level", "lockup", "minimum")}
            | {
                "metric": f"{item['metric']['label']} {item['metric']['text']}",
                "rank": item["rank"],
                "highlights": item.get("highlights", []),
            }
            for item in items
        ],
        "excluded": excluded,
        "upcoming": [
            {k: c[k] for k in ("code", "name", "type_label", "risk_level", "lockup", "minimum")}
            | {"sale_window": c["sale_window"], "raise_limit": c["raise_limit"]}
            for c in (presenter.card(p) for p in upcoming_matches)
        ],
        "rules": "只能介绍列表中的产品。从排序靠前的产品中挑选 1–3 款，结合客户需求说明匹配点"
        "（期限、流动性、费用、起购金额）；不得以收益高低为理由，不得承诺收益或制造紧迫感。"
        "排序依据是期限匹配、流动性和费用，不是收益。"
        "upcoming 是符合客户条件、即将发售的新品：可如实说明募集期和募集规模上限，"
        "并询问是否预约开售提醒；"
        "不要说「高收益」「很多人抢」「赶紧」，客户明确同意后才调用 set_sale_reminder。",
    }
    artifact = {
        "type": "product_list",
        "title": L(
            f"为您匹配的产品（{band.max_product_risk} 及以下）",
            f"Matched for you ({band.max_product_risk} and below)",
        ),
        "items": items,
        "excluded": excluded,
        "ranking_note": L(
            "排序依据：期限匹配、流动性、费用；不按收益排序。",
            "Ranked by horizon fit, liquidity and fees, never by returns.",
        ),
        "disclaimer": product_disclaimer(),
    }
    artifacts = [artifact]
    if upcoming_matches:
        artifacts.append(upcoming_block(upcoming_matches, _reminded(state.get("customer_id"))))
    return _dump(content), artifacts


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
            L(
                f"未找到产品「{product}」。产品目录中只有知岸理财、鸿屿理财的虚构产品。",
                f'Product "{product}" not found. The catalog only has fictional products from '
                "Zhian Wealth Management and Hongyu Wealth Management.",
            )
        )
    eligibility = evaluate(found, ctx)
    detail = {
        **presenter.detail(found),
        "eligible": eligibility.eligible,
        "eligibility_messages": eligibility.messages,
        "reason_codes": eligibility.reason_codes,
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
        "rules": "如实转述条款；eligible_for_customer 为 false 时必须说明原因，"
        "不得推荐，客户也无法买入；为 true 时可以结合客户需求说明匹配点，并提示可在卡片中买入。",
    }
    detail["purchasable"] = eligibility.eligible
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
        raise ToolException(
            L("请提供 2 到 4 个产品进行对比。", "Provide 2 to 4 products to compare.")
        )
    found, missing, left_out = [], [], []
    for name in products:
        p = catalog.find_by_name(name)
        if p is None:
            missing.append(name)
        elif RISK_EXCEEDS in evaluate(p, ctx).reason_codes:
            left_out.append(
                L(
                    f"{p.name}（{p.effective_risk_level}，超出您的风险等级）",
                    f"{p.name_en} ({p.effective_risk_level}, above your risk level)",
                )
            )
        else:
            found.append(p)
    sep = L("；", "; ")
    if missing:
        raise ToolException(L("未找到产品：", "Products not found: ") + L("、", ", ").join(missing))
    if len(found) < 2:
        raise ToolException(
            L("可对比的产品不足 2 款：", "Fewer than 2 products can be compared: ")
            + sep.join(left_out)
        )

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
        {"label": L("发行机构", "Issuer"), "values": [issuer_label(p.issuer) for p in found]},
        {"label": L("产品类型", "Type"), "values": [p.type_label for p in found]},
        {"label": L("风险等级", "Risk level"), "values": [p.effective_risk_level for p in found]},
        {"label": L("流动性", "Liquidity"), "values": [presenter.lockup_text(p) for p in found]},
        {
            "label": L("起购金额", "Minimum"),
            "values": [presenter.format_money(p.minimum_investment) for p in found],
        },
        {
            "label": L("年化固定费用合计", "Total annual fees"),
            "values": [presenter.format_rate(p.fees.annual_total) for p in found],
        },
        {
            "label": L("赎回费", "Redemption fee"),
            "values": [presenter.redemption_fee_text(p) for p in found],
        },
    ] + [
        {
            "label": metric_label(t),
            "values": [presenter.metric_text(p, t) or "—" for p in found],
            "metric": True,
        }
        for t in metric_rows
    ]
    mixed = len({p.product_type is ProductType.CASH_MANAGEMENT for p in found}) > 1
    notes = []
    if mixed:
        notes.append(
            L(
                "七日年化收益率与业绩比较基准口径不同，不能直接比较高低。",
                "A 7-day annualized yield and a performance benchmark are different measures "
                "and can't be compared directly.",
            )
        )
    if left_out:
        notes.append(
            L("未纳入对比：", "Not compared: ")
            + sep.join(left_out)
            + L("。可单独查看其条款。", ". You can still view their terms separately.")
        )
    artifact = {
        "type": "comparison_table",
        "columns": [{"code": p.code, "name": p.display_name} for p in found],
        "rows": rows,
        "notes": notes,
        "disclaimer": product_disclaimer(),
    }
    content = {
        "columns": [p.display_name for p in found],
        "rows": {r["label"]: r["values"] for r in rows},
        "notes": notes,
        "rules": "如实转述对比结果；不同收益口径不得比较高低；不要给出「哪款更好」的结论。",
    }
    return _dump(content), [artifact]


@tool(response_format="content_and_artifact")
def set_sale_reminder(
    state: Annotated[dict, InjectedState],
    product: Annotated[str, Field(description="即将发售的新品代码或名称")],
) -> tuple[str, list[dict]]:
    """为客户预约新品开售提醒。只有客户明确表示「要提醒 / 帮我预约」时才调用。

    提醒不等于购买：开售后需客户本人确认买入。只能预约风险等级范围内、即将发售的新品。
    """
    found = load_catalog().find_by_name(product)
    if found is None:
        raise ToolException(L(f"未找到产品「{product}」。", f'Product "{product}" not found.'))
    customer_id = state.get("customer_id")
    if not customer_id:
        raise ToolException(L("无法识别客户。", "Customer not identified."))
    from datetime import UTC, datetime

    with _session() as db:
        try:
            create_reminder(
                db, customer_id, found, state.get("risk_rating"), CHAT, datetime.now(UTC)
            )
        except ReminderError as exc:
            raise ToolException(str(exc)) from exc
        db.commit()
    content = {
        "status": L("已预约开售提醒", "Sale reminder set"),
        "product": found.display_name,
        "sale_window": presenter.sale_window(found),
        "metric": "{label} {text}".format(**presenter.headline_metric(found)),
        "next_step": "开售当天会提醒客户；购买需客户本人在开售后确认，"
        "不要说已为客户购买或锁定额度。",
    }
    return _dump(content), [upcoming_block([found], {found.code})]


PRODUCT_TOOLS = [search_products, get_product_details, compare_products, set_sale_reminder]
for _t in PRODUCT_TOOLS:
    _t.handle_tool_error = True
    _t.handle_validation_error = True
