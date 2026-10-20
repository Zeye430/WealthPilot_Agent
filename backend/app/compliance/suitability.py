"""Product-level suitability: whether a product may enter a customer's candidate list.

Every product gets reason codes, not just a verdict, so excluded products can explain why.
"""

from decimal import Decimal

from pydantic import BaseModel

from app.assessment.scoring import load_questionnaire, rating_allows
from app.core.i18n import L, is_en
from app.products.catalog import DataQuality, Product, ProductStatus
from app.products.presenter import format_money, lockup_text, sale_window

# Reasons a product can't enter the candidate list (hard filter)
RISK_EXCEEDS = "PRODUCT_RISK_EXCEEDS_RATING"
NOT_ON_SALE = "PRODUCT_NOT_ON_SALE"
BELOW_MINIMUM = "BELOW_MINIMUM_INVESTMENT"
HORIZON_MISMATCH = "HORIZON_MISMATCH"
# Can be shown but isn't ranked
UNVERIFIED = "UNVERIFIED_PRODUCT_DATA"

REASON_LABELS = {
    RISK_EXCEEDS: "风险等级超出您的风险承受能力",
    NOT_ON_SALE: "已到期或非在售",
    BELOW_MINIMUM: "起购金额高于计划投资金额",
    HORIZON_MISMATCH: "持有或封闭期超过投资期限",
    UNVERIFIED: "部分要素未核实",
}
REASON_LABELS_EN = {
    RISK_EXCEEDS: "Risk level above your risk tolerance",
    NOT_ON_SALE: "Matured or not on sale",
    BELOW_MINIMUM: "Minimum above your planned amount",
    HORIZON_MISMATCH: "Holding or lock-up period longer than your horizon",
    UNVERIFIED: "Some terms unverified",
}


def reason_label(code: str) -> str:
    return L(REASON_LABELS[code], REASON_LABELS_EN[code])


class CustomerContext(BaseModel):
    risk_rating: str
    investment_amount: Decimal | None = None
    horizon_days: int | None = None


class Eligibility(BaseModel):
    code: str
    eligible: bool  # may enter the candidate list
    rankable: bool  # may be ranked
    reason_codes: list[str]
    messages: list[str]  # explanations shown to the customer


def evaluate(product: Product, ctx: CustomerContext) -> Eligibility:
    reasons: list[str] = []
    messages: list[str] = []

    risk = product.effective_risk_level
    if not rating_allows(ctx.risk_rating, risk):
        band = load_questionnaire().band(ctx.risk_rating)
        reasons.append(RISK_EXCEEDS)
        messages.append(
            L(
                f"该产品风险等级为 {risk}，超出您的风险承受能力（{ctx.risk_rating} {band.name}，"
                f"可购买 {band.max_product_risk} 及以下），不作推荐，您亦无权限购买。",
                f"This product is rated {risk}, above your risk tolerance ({ctx.risk_rating} "
                f"{band.name_en}, eligible for {band.max_product_risk} and below). It isn't "
                "recommended and you can't buy it.",
            )
        )
    if product.status is ProductStatus.UPCOMING:
        reasons.append(NOT_ON_SALE)
        messages.append(
            L(
                f"该产品尚未开售（募集期 {sale_window(product)}），"
                "开售后可买入，现在可以预约开售提醒。",
                f"This product isn't on sale yet (subscription period {sale_window(product)}). "
                "You can buy it once the sale opens, and set a reminder now.",
            )
        )
    elif product.status is not ProductStatus.ON_SALE:
        reasons.append(NOT_ON_SALE)
        messages.append(
            L(
                "该产品已到期，不可购买，仅供资料查询。",
                "This product has matured and can't be bought; details are for reference only.",
            )
        )
    if ctx.investment_amount is not None and ctx.investment_amount < product.minimum_investment:
        reasons.append(BELOW_MINIMUM)
        messages.append(
            L(
                f"起购金额为 {format_money(product.minimum_investment)}，"
                f"高于您计划投资的 {format_money(ctx.investment_amount)}。",
                f"The minimum is {format_money(product.minimum_investment)}, more than the "
                f"{format_money(ctx.investment_amount)} you plan to invest.",
            )
        )
    if ctx.horizon_days is not None and product.lockup_days > ctx.horizon_days:
        reasons.append(HORIZON_MISMATCH)
        messages.append(
            L(
                f"该产品{lockup_text(product)}，超过您的投资期限（约 {ctx.horizon_days} 天）。",
                f"Liquidity terms ({lockup_text(product).lower()}) exceed your time horizon "
                f"(about {ctx.horizon_days} days).",
            )
        )

    eligible = not reasons
    if product.data_quality is DataQuality.UNVERIFIED:
        reasons.append(UNVERIFIED)
        if is_en():
            missing = ", ".join(FEE_LABELS_EN[n] for n in product.fees.missing) or "Some terms"
            messages.append(
                f"{missing[:1].upper()}{missing[1:]} not verified; for reference only and "
                "not ranked."
            )
        else:
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
FEE_LABELS_EN = {
    "management": "management fee",
    "custody": "custody fee",
    "sales_service": "sales service fee",
}
