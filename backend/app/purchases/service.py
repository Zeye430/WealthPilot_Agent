"""买入确认（演示）：校验能否买入，生成确认页内容。不下单、不扣款、不记录持仓。

能否买入完全由代码判断，与对话中的 AI 无关：AI 只能引导客户打开产品，最终由客户本人确认。
产品负责人决定（2026-10-18）：买入流程只做到确认页。
"""

from decimal import Decimal

from pydantic import BaseModel

from app.assessment.scoring import load_questionnaire, rating_allows
from app.calculations.core import subscription_fee
from app.core.i18n import L
from app.products.catalog import Product, ProductStatus
from app.products.presenter import format_money, format_rate, sale_window


def documents() -> list[dict]:
    return [
        {"id": "prospectus", "name": L("产品说明书", "Prospectus")},
        {"id": "risk_disclosure", "name": L("风险揭示书", "Risk disclosure")},
        {"id": "sales_agreement", "name": L("理财产品销售协议书", "Sales agreement")},
    ]


def risk_disclosure() -> str:
    return L(
        "理财非存款、产品有风险、投资须谨慎。本产品不保证本金和收益，"
        "您的本金可能因市场变动而蒙受损失。业绩比较基准不是预期收益率，不代表产品的未来表现和实际收益。",
        "Wealth products are not deposits and carry risk; invest with care. This product does "
        "not guarantee principal or returns, and you may lose money if markets move against "
        "you. A performance benchmark is not an expected return and does not represent future "
        "or actual performance.",
    )


def demo_result() -> str:
    return L(
        "演示系统：已完成买入确认流程，未实际下单，未发生任何资金变动。",
        "Demo: purchase confirmation complete. No order was placed and no money moved.",
    )


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
    risk = product.effective_risk_level
    if rating is None:
        reasons.append(
            L(
                "请先完成风险承受能力测评，测评结果有效后才能买入。",
                "Complete your risk tolerance profile first. You can buy once it's valid.",
            )
        )
    elif not rating_allows(rating, risk):
        band = load_questionnaire().band(rating)
        reasons.append(
            L(
                f"该产品风险等级为 {risk}，超出您的风险承受能力"
                f"（{rating} {band.name}，可购买 {band.max_product_risk} 及以下），无法买入。",
                f"This product is rated {risk}, above your risk tolerance ({rating} "
                f"{band.name_en}, eligible for {band.max_product_risk} and below), so you "
                "can't buy it.",
            )
        )
    if product.status is ProductStatus.UPCOMING:
        reasons.append(
            L(
                f"该产品尚未开售（募集期 {sale_window(product)}），可以预约开售提醒。",
                f"Not on sale yet (subscription period {sale_window(product)}). You can set a "
                "sale reminder.",
            )
        )
    elif product.status is not ProductStatus.ON_SALE:
        reasons.append(
            L(
                "该产品已到期或暂停销售，无法买入。",
                "This product has matured or is suspended and can't be bought.",
            )
        )
    if product.fees.subscription is None:
        reasons.append(
            L(
                "该产品申购费率尚未核实，暂不支持买入。",
                "The subscription fee isn't verified yet, so this product can't be bought.",
            )
        )
    return reasons


def check_purchase(
    product: Product, amount: Decimal, rating: str | None, available_balance: Decimal
) -> PurchaseCheck:
    errors = blocking_reasons(product, rating)
    if amount < product.minimum_investment:
        minimum = format_money(product.minimum_investment)
        errors.append(L(f"起购金额为 {minimum}。", f"The minimum is {minimum}."))
    if amount > available_balance:
        balance = format_money(available_balance)
        errors.append(
            L(f"超出可用活期余额（{balance}）。", f"More than your available balance ({balance}).")
        )
    fee = None
    if product.fees.subscription is not None:
        fee, _ = subscription_fee(amount, product.fees.subscription)
    return PurchaseCheck(
        allowed=not errors,
        errors=errors,
        product_code=product.code,
        product_name=product.display_name,
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
        "documents": documents(),
        "risk_disclosure": risk_disclosure(),
    }
