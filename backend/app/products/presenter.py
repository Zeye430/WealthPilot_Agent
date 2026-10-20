"""Display formats for product terms. Product cards, comparison tables and tool output for the
LLM all use these, so wording stays consistent."""

from decimal import Decimal

from app.core.i18n import L, is_en
from app.products.catalog import (
    DISTRIBUTOR,
    DISTRIBUTOR_EN,
    MetricType,
    OperationMode,
    Product,
    ProductStatus,
    metric_label,
)

CURRENT_METRIC_ORDER = [
    MetricType.SEVEN_DAY_ANNUALIZED,
    MetricType.PERFORMANCE_BENCHMARK,
    MetricType.ANNUAL_PERFORMANCE,
]


def format_rate(rate: Decimal | None) -> str:
    if rate is None:
        return L("未核实", "Unverified")
    if rate == 0:
        return "0%"
    # Financial documents conventionally show two decimals: 0.40%, 4.00%
    return f"{(rate * 100).quantize(Decimal('0.01'))}%"


def format_money(amount: Decimal) -> str:
    if is_en():
        # English reads large amounts in millions / billions (¥500 million)
        for unit, name in ((Decimal(10) ** 9, "billion"), (Decimal(10) ** 6, "million")):
            if amount >= unit and amount % (unit / 10) == 0:
                return f"¥{(amount / unit).normalize():f} {name}"
        return f"¥{amount.normalize():,f}"
    if amount >= 100000000 and amount % 10000000 == 0:
        return f"{(amount / 100000000).normalize():f} 亿元"
    if amount >= 10000 and amount % 10000 == 0:
        return f"{(amount / 10000).normalize():f} 万元"
    return f"{amount.normalize():f} 元"


def sale_window(product: Product) -> str | None:
    """Subscription period of a new product, e.g. "Oct 26 - Oct 30"."""
    if product.sale_start is None or product.sale_end is None:
        return None
    start, end = product.sale_start, product.sale_end
    if is_en():
        return f"{start:%b} {start.day} – {end:%b} {end.day}"
    return f"{start.month} 月 {start.day} 日–{end.month} 月 {end.day} 日"


def lockup_text(product: Product) -> str:
    days = product.lockup_days
    match product.operation_mode:
        case OperationMode.OPEN:
            return L("每日开放", "Open daily")
        case OperationMode.MIN_HOLDING:
            return L(f"最短持有 {days} 天", f"{days}-day minimum holding")
        case OperationMode.CLOSED:
            return L(f"封闭 {days} 天", f"Closed for {days} days")
        case OperationMode.PERIODIC_OPEN:
            return L(f"每 {days} 天开放一次", f"Opens every {days} days")


def settlement_text(product: Product) -> str:
    """When redemption proceeds arrive, e.g. "paid T+2 after maturity"."""
    text = product.redemption_settlement
    if not is_en():
        return text
    t = text.split()[-2] if text.endswith("兑付") else text.split()[-1]
    if text.startswith("到期后"):
        return f"Paid {t} after maturity"
    if text.startswith("开放日后"):
        return f"{t} after the open day"
    return text


def redemption_fee_text(product: Product) -> str:
    tiers = [t for t in product.fees.redemption if t.rate > 0]
    if not tiers:
        return L("无", "None")
    if is_en():
        return "; ".join(f"{format_rate(t.rate)} if held under {t.max_days} days" for t in tiers)
    return "；".join(f"持有不足 {t.max_days} 天 {format_rate(t.rate)}" for t in tiers)


def metric_text(product: Product, metric_type: MetricType) -> str | None:
    """Text for one return measure; None if the product doesn't have it (the comparison table
    shows "-" rather than filling from another measure)."""
    m = product.metric(metric_type)
    if m is None:
        return None
    match metric_type:
        case MetricType.SEVEN_DAY_ANNUALIZED:
            return L(
                f"{format_rate(m.value)}（截至 {m.as_of:%m-%d}）",
                f"{format_rate(m.value)} (as of {m.as_of:%b} {m.as_of.day})",
            )
        case MetricType.TEN_THOUSAND_UNIT_INCOME:
            return L(
                f"{m.value_yuan} 元（截至 {m.as_of:%m-%d}）",
                f"¥{m.value_yuan} (as of {m.as_of:%b} {m.as_of.day})",
            )
        case MetricType.PERFORMANCE_BENCHMARK:
            if m.formula:
                return m.display_formula
            return f"{format_rate(m.low)}–{format_rate(m.high)}"
        case MetricType.ANNUAL_PERFORMANCE:
            sep = L("；", "; ")
            return sep.join(f"{p.display_label} {format_rate(p.value)}" for p in m.periods)


def headline_metric(product: Product) -> dict:
    """Main return metric shown on the card, always labeled with its measure."""
    for t in CURRENT_METRIC_ORDER:
        if (text := metric_text(product, t)) is not None:
            return {"type": t.value, "label": metric_label(t), "text": text}
    raise AssertionError(f"{product.code} 没有可展示的收益指标")


def card(product: Product) -> dict:
    risk = product.effective_risk_level
    risk_note = None
    if product.distributor_risk_level and risk != product.issuer_risk_level:
        risk_note = L(
            f"发行机构评级 {product.issuer_risk_level}，{DISTRIBUTOR}销售评级 "
            f"{product.distributor_risk_level}，按较高者认定为 {risk}",
            f"Issuer rating {product.issuer_risk_level}, {DISTRIBUTOR_EN} rating "
            f"{product.distributor_risk_level}; the higher one applies: {risk}",
        )
    return {
        "code": product.code,
        "name": product.display_name,
        "issuer": product.display_issuer,
        "type_label": product.type_label,
        "risk_level": risk,
        "risk_note": risk_note,
        "lockup": lockup_text(product),
        "minimum": format_money(product.minimum_investment),
        "annual_fee": format_rate(product.fees.annual_total),
        "metric": headline_metric(product),
        "status": product.status.value,
        "data_quality": product.data_quality.value,
        "synthetic": True,
        **(
            {
                "sale_window": sale_window(product),
                "raise_limit": format_money(product.raise_limit) if product.raise_limit else None,
            }
            if product.status is ProductStatus.UPCOMING
            else {}
        ),
    }


def detail(product: Product) -> dict:
    """Product details: card fields + investment scope, fee breakdown, every return measure
    (including how the benchmark was set)."""
    fees = product.fees
    fee_rows = [
        {
            "label": L("固定管理费（年化）", "Management fee (annual)"),
            "value": format_rate(fees.management),
        },
        {"label": L("托管费（年化）", "Custody fee (annual)"), "value": format_rate(fees.custody)},
        {
            "label": L("销售服务费（年化）", "Sales service fee (annual)"),
            "value": format_rate(fees.sales_service),
        },
        {"label": L("申购费", "Subscription fee"), "value": format_rate(fees.subscription)},
        {"label": L("赎回费", "Redemption fee"), "value": redemption_fee_text(product)},
    ]
    if fees.performance_fee:
        pf = fees.performance_fee
        fee_rows.append(
            {
                "label": L("业绩报酬", "Performance fee"),
                "value": L(
                    f"{pf.condition}的 {format_rate(pf.rate)}",
                    f"{format_rate(pf.rate)} of {pf.display_condition}",
                ),
            }
        )
    return {
        **card(product),
        "investment_scope": product.display_scope,
        "strategy": product.display_strategy,
        "redemption_settlement": settlement_text(product),
        "inception_date": str(product.inception_date),
        "maturity_date": str(product.maturity_date) if product.maturity_date else None,
        "fees": fee_rows,
        "metrics": [
            {
                "label": metric_label(m.type),
                "text": metric_text(product, m.type),
                "basis": m.display_basis,
            }
            for m in product.metrics
        ],
    }
