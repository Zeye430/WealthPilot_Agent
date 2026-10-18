"""产品要素的展示格式。产品卡片、对比表、工具返回给 LLM 的文本都用这里的函数，保证口径一致。"""

from decimal import Decimal

from app.products.catalog import (
    METRIC_LABELS,
    MetricType,
    OperationMode,
    Product,
    ProductStatus,
)

CURRENT_METRIC_ORDER = [
    MetricType.SEVEN_DAY_ANNUALIZED,
    MetricType.PERFORMANCE_BENCHMARK,
    MetricType.ANNUAL_PERFORMANCE,
]


def format_rate(rate: Decimal | None) -> str:
    if rate is None:
        return "未核实"
    if rate == 0:
        return "0%"
    # 金融文件惯例保留两位小数：0.40%、4.00%
    return f"{(rate * 100).quantize(Decimal('0.01'))}%"


def format_money(amount: Decimal) -> str:
    if amount >= 100000000 and amount % 10000000 == 0:
        return f"{(amount / 100000000).normalize():f} 亿元"
    if amount >= 10000 and amount % 10000 == 0:
        return f"{(amount / 10000).normalize():f} 万元"
    return f"{amount.normalize():f} 元"


def sale_window(product: Product) -> str | None:
    """新发产品的募集期，如「10 月 26 日–10 月 30 日」。"""
    if product.sale_start is None or product.sale_end is None:
        return None
    start, end = product.sale_start, product.sale_end
    return f"{start.month} 月 {start.day} 日–{end.month} 月 {end.day} 日"


def lockup_text(product: Product) -> str:
    days = product.lockup_days
    match product.operation_mode:
        case OperationMode.OPEN:
            return "每日开放"
        case OperationMode.MIN_HOLDING:
            return f"最短持有 {days} 天"
        case OperationMode.CLOSED:
            return f"封闭 {days} 天"
        case OperationMode.PERIODIC_OPEN:
            return f"每 {days} 天开放一次"


def redemption_fee_text(product: Product) -> str:
    tiers = [t for t in product.fees.redemption if t.rate > 0]
    if not tiers:
        return "无"
    return "；".join(f"持有不足 {t.max_days} 天 {format_rate(t.rate)}" for t in tiers)


def metric_text(product: Product, metric_type: MetricType) -> str | None:
    """某一口径的收益指标文字；产品没有该口径时返回 None（对比表显示「—」，不跨口径填充）。"""
    m = product.metric(metric_type)
    if m is None:
        return None
    match metric_type:
        case MetricType.SEVEN_DAY_ANNUALIZED:
            return f"{format_rate(m.value)}（截至 {m.as_of:%m-%d}）"
        case MetricType.TEN_THOUSAND_UNIT_INCOME:
            return f"{m.value_yuan} 元（截至 {m.as_of:%m-%d}）"
        case MetricType.PERFORMANCE_BENCHMARK:
            if m.formula:
                return m.formula
            return f"{format_rate(m.low)}–{format_rate(m.high)}"
        case MetricType.ANNUAL_PERFORMANCE:
            return "；".join(f"{p.label} {format_rate(p.value)}" for p in m.periods)


def headline_metric(product: Product) -> dict:
    """卡片上展示的主要收益指标：始终带口径标签。"""
    for t in CURRENT_METRIC_ORDER:
        if (text := metric_text(product, t)) is not None:
            return {"type": t.value, "label": METRIC_LABELS[t], "text": text}
    raise AssertionError(f"{product.code} 没有可展示的收益指标")


def card(product: Product) -> dict:
    risk = product.effective_risk_level
    risk_note = None
    if product.distributor_risk_level and risk != product.issuer_risk_level:
        risk_note = (
            f"发行机构评级 {product.issuer_risk_level}，知岸银行销售评级 "
            f"{product.distributor_risk_level}，按较高者认定为 {risk}"
        )
    return {
        "code": product.code,
        "name": product.name,
        "issuer": product.issuer,
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
    """产品详情：卡片字段 + 投资范围、费用明细、各口径收益指标（含业绩比较基准测算依据）。"""
    fees = product.fees
    fee_rows = [
        {"label": "固定管理费（年化）", "value": format_rate(fees.management)},
        {"label": "托管费（年化）", "value": format_rate(fees.custody)},
        {"label": "销售服务费（年化）", "value": format_rate(fees.sales_service)},
        {"label": "申购费", "value": format_rate(fees.subscription)},
        {"label": "赎回费", "value": redemption_fee_text(product)},
    ]
    if fees.performance_fee:
        fee_rows.append(
            {
                "label": "业绩报酬",
                "value": f"{fees.performance_fee.condition}的"
                f" {format_rate(fees.performance_fee.rate)}",
            }
        )
    return {
        **card(product),
        "investment_scope": product.investment_scope,
        "strategy": product.strategy,
        "redemption_settlement": product.redemption_settlement,
        "inception_date": str(product.inception_date),
        "maturity_date": str(product.maturity_date) if product.maturity_date else None,
        "fees": fee_rows,
        "metrics": [
            {"label": METRIC_LABELS[m.type], "text": metric_text(product, m.type), "basis": m.basis}
            for m in product.metrics
        ],
    }
