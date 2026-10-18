"""买入确认（演示）：校验能否买入，生成确认页内容。不下单、不扣款、不记录持仓。

能否买入完全由代码判断，与对话中的 AI 无关：AI 只能引导客户打开产品，最终由客户本人确认。
产品负责人决定（2026-10-18）：买入流程只做到确认页。
"""

from decimal import Decimal

from pydantic import BaseModel

from app.assessment.scoring import load_questionnaire, rating_allows
from app.calculations.core import subscription_fee
from app.products.catalog import Product, ProductStatus
from app.products.presenter import format_money, format_rate

DOCUMENTS = [
    {"id": "prospectus", "name": "产品说明书"},
    {"id": "risk_disclosure", "name": "风险揭示书"},
    {"id": "sales_agreement", "name": "理财产品销售协议书"},
]
RISK_DISCLOSURE = (
    "理财非存款、产品有风险、投资须谨慎。本产品不保证本金和收益，"
    "您的本金可能因市场变动而蒙受损失。业绩比较基准不是预期收益率，不代表产品的未来表现和实际收益。"
)
DEMO_RESULT = "演示系统：已完成买入确认流程，未实际下单，未发生任何资金变动。"


class PurchaseCheck(BaseModel):
    allowed: bool
    errors: list[str]
    product_code: str
    product_name: str
    risk_level: str
    amount: Decimal | None = None
    subscription_fee: Decimal | None = None
    available_balance: Decimal


def blocking_reasons(product: Product, rating: str | None) -> list[str]:
    """与金额无关的买入限制：产品详情页据此决定「买入」按钮是否可用。"""
    reasons = []
    if rating is None:
        reasons.append("请先完成风险承受能力测评，测评结果有效后才能买入。")
    elif not rating_allows(rating, product.effective_risk_level):
        band = load_questionnaire().band(rating)
        reasons.append(
            f"该产品风险等级为 {product.effective_risk_level}，超出您的风险承受能力"
            f"（{rating} {band.name}，可购买 {band.max_product_risk} 及以下），无法买入。"
        )
    if product.status is not ProductStatus.ON_SALE:
        reasons.append("该产品已到期或暂停销售，无法买入。")
    if product.fees.subscription is None:
        reasons.append("该产品申购费率尚未核实，暂不支持买入。")
    return reasons


def check_purchase(
    product: Product, amount: Decimal, rating: str | None, available_balance: Decimal
) -> PurchaseCheck:
    errors = blocking_reasons(product, rating)
    if amount < product.minimum_investment:
        errors.append(f"起购金额为 {format_money(product.minimum_investment)}。")
    if amount > available_balance:
        errors.append(f"超出可用活期余额（{format_money(available_balance)}）。")
    fee = None
    if product.fees.subscription is not None:
        fee, _ = subscription_fee(amount, product.fees.subscription)
    return PurchaseCheck(
        allowed=not errors,
        errors=errors,
        product_code=product.code,
        product_name=product.name,
        risk_level=product.effective_risk_level,
        amount=amount,
        subscription_fee=fee,
        available_balance=available_balance,
    )


def confirmation_view(check: PurchaseCheck, product: Product) -> dict:
    """确认页内容：金额、费用、需要阅读确认的文件与风险揭示。"""
    return {
        "allowed": check.allowed,
        "errors": check.errors,
        "product_code": check.product_code,
        "product_name": check.product_name,
        "risk_level": check.risk_level,
        "amount": format_money(check.amount) if check.amount is not None else None,
        "subscription_fee": format_money(check.subscription_fee)
        if check.subscription_fee is not None
        else None,
        "subscription_rate": format_rate(product.fees.subscription),
        "available_balance": format_money(check.available_balance),
        "documents": DOCUMENTS,
        "risk_disclosure": RISK_DISCLOSURE,
    }
