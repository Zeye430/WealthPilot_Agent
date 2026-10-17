"""产品级适当性规则：判断某个产品对某位客户是否可进入候选。规则见 docs/COMPLIANCE_DESIGN.md §3。

每个产品都返回原因代码，而不是只给结果——被排除的产品也能说清「为什么」。
"""

from decimal import Decimal

from pydantic import BaseModel

from app.assessment.scoring import load_questionnaire, rating_allows
from app.products.catalog import DataQuality, Product, ProductStatus
from app.products.presenter import format_money, lockup_text

# 不可进入候选的原因（硬过滤）
RISK_EXCEEDS = "PRODUCT_RISK_EXCEEDS_RATING"
NOT_ON_SALE = "PRODUCT_NOT_ON_SALE"
BELOW_MINIMUM = "BELOW_MINIMUM_INVESTMENT"
HORIZON_MISMATCH = "HORIZON_MISMATCH"
# 可展示但不参与排序
UNVERIFIED = "UNVERIFIED_PRODUCT_DATA"

REASON_LABELS = {
    RISK_EXCEEDS: "风险等级超出您的风险承受能力",
    NOT_ON_SALE: "已到期或非在售",
    BELOW_MINIMUM: "起购金额高于计划投资金额",
    HORIZON_MISMATCH: "持有或封闭期超过投资期限",
    UNVERIFIED: "部分要素未核实",
}


class CustomerContext(BaseModel):
    risk_rating: str
    investment_amount: Decimal | None = None
    horizon_days: int | None = None


class Eligibility(BaseModel):
    code: str
    eligible: bool  # 可进入候选
    rankable: bool  # 可参与排序
    reason_codes: list[str]
    messages: list[str]  # 给客户看的说明


def evaluate(product: Product, ctx: CustomerContext) -> Eligibility:
    reasons: list[str] = []
    messages: list[str] = []

    risk = product.effective_risk_level
    if not rating_allows(ctx.risk_rating, risk):
        band = load_questionnaire().band(ctx.risk_rating)
        reasons.append(RISK_EXCEEDS)
        messages.append(
            f"该产品风险等级为 {risk}，超出您的风险承受能力（{ctx.risk_rating} {band.name}，"
            f"可购买 {band.max_product_risk} 及以下），不作推荐，您亦无权限购买。"
        )
    if product.status is not ProductStatus.ON_SALE:
        reasons.append(NOT_ON_SALE)
        messages.append("该产品已到期，不可购买，仅供资料查询。")
    if ctx.investment_amount is not None and ctx.investment_amount < product.minimum_investment:
        reasons.append(BELOW_MINIMUM)
        messages.append(
            f"起购金额为 {format_money(product.minimum_investment)}，"
            f"高于您计划投资的 {format_money(ctx.investment_amount)}。"
        )
    if ctx.horizon_days is not None and product.lockup_days > ctx.horizon_days:
        reasons.append(HORIZON_MISMATCH)
        messages.append(
            f"该产品{lockup_text(product)}，超过您的投资期限（约 {ctx.horizon_days} 天）。"
        )

    eligible = not reasons
    if product.data_quality is DataQuality.UNVERIFIED:
        reasons.append(UNVERIFIED)
        missing = "、".join(FEE_LABELS[n] for n in product.fees.missing) or "部分要素"
        messages.append(f"{missing}未核实，仅供参考，不参与排序。")

    return Eligibility(
        code=product.code,
        eligible=eligible,
        rankable=eligible and product.data_quality is DataQuality.VERIFIED,
        reason_codes=reasons,
        messages=messages,
    )


FEE_LABELS = {"management": "固定管理费", "custody": "托管费", "sales_service": "销售服务费"}
