"""根据产品要素生成虚构产品说明书（Markdown）。

说明书是 products.yaml 的派生物：要素只写一次，说明书由此生成，保证产品卡片、对比表与 RAG 检索到的
条款完全一致。章节结构参考公开说明书的常见结构，文字为本系统编写。
"""

from app.products import presenter
from app.products.catalog import (
    DISTRIBUTOR,
    METRIC_LABELS,
    Catalog,
    MetricType,
    OperationMode,
    Product,
    ProductType,
)

FICTION_NOTICE = (
    "【虚构演示文件】本文件为 WealthPilot 演示系统虚构，机构与产品均不存在，"
    "不构成任何要约或投资建议。"
)

COMMON_RISKS = [
    ("市场风险", "利率、汇率、证券价格等市场因素变化，可能导致产品所投资产价值下跌、净值波动。"),
    ("信用风险", "所投资产的发行人或交易对手违约，可能导致产品资产损失。"),
    ("流动性风险", "在约定的开放日以外不能赎回；发生巨额赎回时，赎回申请可能被延期办理。"),
    ("政策风险", "国家法律法规及监管政策变化，可能影响产品的投资运作与收益。"),
    ("管理风险", "管理人的投资判断与实际市场走势不一致，可能影响产品收益。"),
    (
        "提前终止风险",
        "发生说明书约定的情形时，产品可能提前终止，投资者可能无法获得预期的持有期限。",
    ),
]
EQUITY_RISK = (
    "股票市场风险",
    "产品投资股票等权益类资产，股票价格大幅波动可能导致产品净值明显回撤。",
)


def _min_rating(product: Product) -> str:
    return "C" + product.effective_risk_level[2:]


def _risk_statement(product: Product) -> str:
    risk = product.effective_risk_level
    text = f"本产品风险等级为 {risk}"
    if product.distributor_risk_level and risk != product.issuer_risk_level:
        text += (
            f"（管理人评级 {product.issuer_risk_level}，销售机构{DISTRIBUTOR}评级 "
            f"{product.distributor_risk_level}，按较高者认定）"
        )
    return text + f"，适合风险承受能力为 {_min_rating(product)} 及以上的投资者。"


def _trading_rules(product: Product) -> list[str]:
    days = product.lockup_days
    rules = {
        OperationMode.OPEN: ["本产品每个交易日开放申购和赎回。"],
        OperationMode.MIN_HOLDING: [
            f"每笔份额自申购确认之日起需持有满 {days} 天，持有期满后可在开放日申请赎回。"
        ],
        OperationMode.CLOSED: [
            f"本产品成立后封闭运作 {days} 天，封闭期内不开放申购和赎回，到期后自动兑付。"
        ],
        OperationMode.PERIODIC_OPEN: [
            f"本产品每 {days} 天开放一次申购与赎回，非开放期内不能赎回。"
        ],
    }[product.operation_mode]
    rules.append(f"赎回资金到账时间：{product.redemption_settlement}。")
    rules.append(f"起购金额：{presenter.format_money(product.minimum_investment)}。")
    if product.product_type is ProductType.CASH_MANAGEMENT:
        rules.append(
            "单个投资者在单个销售渠道持有本产品，单个自然日当日可取得的赎回金额不高于 1 万元，"
            "其余部分按上述到账时间办理。"
        )
    return rules


def _metric_section(product: Product) -> list[str]:
    lines = []
    for m in product.metrics:
        label = METRIC_LABELS[m.type]
        text = presenter.metric_text(product, m.type)
        lines.append(f"- **{label}**：{text}")
        if m.type is MetricType.PERFORMANCE_BENCHMARK:
            lines.append(f"  - 测算依据：{m.basis}")
            lines.append(
                "  - 业绩比较基准不是预期收益率，不代表产品的未来表现和实际收益，"
                "不构成对产品收益的承诺。"
            )
        if m.type is MetricType.SEVEN_DAY_ANNUALIZED:
            lines.append("  - 七日年化收益率反映过去七日的收益水平，不代表未来收益。")
        if m.type is MetricType.ANNUAL_PERFORMANCE:
            lines.append("  - 过往业绩按完整会计年度列示，不代表未来表现。")
    if product.product_type is ProductType.CASH_MANAGEMENT:
        lines.append(
            "- **估值与披露**：每个开放日结束后两个工作日内披露每万份收益和七日年化收益率。"
        )
    else:
        lines.append(
            "- **估值与披露**：所投资产以公允价值计量，在每个开放日结束后 2 日内披露份额净值。"
        )
    return lines


STATUS_TEXT = {"ON_SALE": "在售", "ENDED": "已到期", "UPCOMING": "即将发售"}


def render(product: Product, catalog: Catalog) -> str:
    risks = list(COMMON_RISKS)
    if product.product_type in (
        ProductType.FIXED_INCOME_PLUS,
        ProductType.MIXED,
        ProductType.EQUITY,
    ):
        risks.insert(1, EQUITY_RISK)
    base_rows = [
        ("产品名称", product.name),
        ("产品代码", product.code),
        ("管理人", product.issuer),
        ("销售机构", DISTRIBUTOR),
        ("产品类型", f"{product.type_label}，公募，非保本浮动收益型"),
        ("运作模式", presenter.lockup_text(product)),
        ("风险等级", product.effective_risk_level),
        ("起购金额", presenter.format_money(product.minimum_investment)),
        ("成立日", str(product.inception_date)),
        ("到期日", str(product.maturity_date) if product.maturity_date else "无固定期限"),
        ("产品状态", STATUS_TEXT[product.status.value]),
    ]
    if product.status.value == "UPCOMING":
        base_rows.append(("募集期", presenter.sale_window(product)))
        if product.raise_limit:
            base_rows.append(
                ("募集规模上限", f"{presenter.format_money(product.raise_limit)}，额满提前结束募集")
            )
    fee = product.fees
    fee_rows = [(row["label"], row["value"]) for row in presenter.detail(product)["fees"]]

    out = [
        FICTION_NOTICE,
        "",
        f"# {product.name} 产品说明书",
        "",
        f"> 产品代码 {product.code}，目录版本 {catalog.catalog_version}，数据日期 {catalog.as_of}",
        "",
        "## 重要须知",
        "",
        "1. 理财非存款、产品有风险、投资须谨慎。",
        "2. 本产品为非保本浮动收益型产品，不保证本金和收益，投资者可能损失部分或全部本金。",
        "3. 业绩比较基准不是预期收益率，不代表产品的未来表现和实际收益，不构成对产品收益的承诺。",
        "4. 产品过往业绩不代表其未来表现，不等于产品实际收益。",
        f"5. {_risk_statement(product)}投资者适当性评估由销售机构{DISTRIBUTOR}负责。",
        "",
        "## 一、产品基本信息",
        "",
        "| 项目 | 内容 |",
        "|---|---|",
        *[f"| {k} | {v} |" for k, v in base_rows],
        "",
        "## 二、投资范围与投资比例",
        "",
        f"投资范围：{product.investment_scope}",
        "",
        f"投资策略：{product.strategy}",
        "",
        "## 三、申购与赎回",
        "",
        *[f"- {r}" for r in _trading_rules(product)],
        "",
        "## 四、产品费用",
        "",
        "| 费用项目 | 费率 |",
        "|---|---|",
        *[f"| {k} | {v} |" for k, v in fee_rows],
        "",
        "固定管理费、托管费、销售服务费按前一日产品资产净值和年化费率逐日计提，已体现在产品净值中；"
        "申购费、赎回费在交易时收取。",
    ]
    if fee.missing:
        out += ["", "注：标注「未核实」的费用项目暂未取得确认数据，以管理人后续公告为准。"]
    out += [
        "",
        "## 五、收益指标与估值",
        "",
        *_metric_section(product),
        "",
        "## 六、提前终止",
        "",
        "发生法律法规或监管要求、所投资产出现重大不利变化、产品规模过小等说明书约定的情形时，"
        "管理人可提前终止本产品，并按约定提前公告。",
        "",
        "## 七、风险揭示",
        "",
        *[f"- **{name}**：{text}" for name, text in risks],
        "",
        "最不利情形：所投资产价格大幅下跌或发生违约时，投资者可能损失部分甚至全部本金。",
        "",
        "## 八、信息披露",
        "",
        "管理人通过销售机构渠道披露产品净值（或每万份收益、七日年化收益率）、定期报告、"
        "业绩比较基准调整及其他重大事项。",
        "",
    ]
    return "\n".join(out)
