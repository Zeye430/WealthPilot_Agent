"""候选排序：只对通过适当性硬过滤、且数据已核实的产品排序。

刻意**不使用**业绩比较基准或历史收益排序：业绩比较基准不是预期收益率，按它排序等于变相推荐
「基准更高、通常风险也更高」的产品。销售佣金同样不参与排序。
"""

from decimal import Decimal

from pydantic import BaseModel

from app.core.i18n import L
from app.products.catalog import Product

# 权重可配置；未提供投资期限时，期限匹配度不参与，其余权重按比例放大
WEIGHTS = {"horizon_fit": Decimal("0.4"), "liquidity": Decimal("0.3"), "cost": Decimal("0.3")}
FACTOR_LABELS = {"horizon_fit": "期限匹配", "liquidity": "流动性", "cost": "费用"}
HIGHLIGHT_THRESHOLD = Decimal("0.8")


class RankedProduct(BaseModel):
    product: Product
    score: Decimal
    factors: dict[str, Decimal]  # 各因素得分（0–1）

    def explanation(self) -> str:
        parts = [f"{FACTOR_LABELS[k]} {v:.2f}" for k, v in self.factors.items()]
        return "，".join(parts)

    def highlights(self) -> list[str]:
        """给客户看的匹配理由：只来自排序因素（期限、流动性、费用），不涉及收益。"""
        tags = []
        if self.product.lockup_days == 0:
            tags.append(L("随时可取", "Withdraw anytime"))
        if self.factors.get("horizon_fit", Decimal(0)) >= HIGHLIGHT_THRESHOLD:
            tags.append(L("期限与您的计划匹配", "Fits your time horizon"))
        if self.factors["cost"] >= HIGHLIGHT_THRESHOLD:
            tags.append(L("候选中费用较低", "Lower fees among matches"))
        return tags


def _scale_inverse(value: Decimal, low: Decimal, high: Decimal) -> Decimal:
    """越小越好的因素映射到 0–1；所有候选相同时都记 1。"""
    if high == low:
        return Decimal(1)
    return (high - value) / (high - low)


def rank(products: list[Product], horizon_days: int | None = None) -> list[RankedProduct]:
    if not products:
        return []
    weights = dict(WEIGHTS)
    if horizon_days is None:
        weights.pop("horizon_fit")
    total_weight = sum(weights.values())

    fees = [p.fees.annual_total for p in products]
    lockups = [Decimal(p.lockup_days) for p in products]
    ranked = []
    for p, fee, lockup in zip(products, fees, lockups, strict=True):
        factors = {
            "liquidity": _scale_inverse(lockup, min(lockups), max(lockups)),
            "cost": _scale_inverse(fee, min(fees), max(fees)),
        }
        if horizon_days is not None:
            # 持有期越接近（但不超过）投资期限越匹配；超过的产品已被硬过滤
            factors["horizon_fit"] = min(lockup / Decimal(max(horizon_days, 1)), Decimal(1))
        score = sum(weights[k] * v for k, v in factors.items()) / total_weight
        ranked.append(RankedProduct(product=p, score=score, factors=factors))
    # 同分按代码排序，保证结果可复现
    return sorted(ranked, key=lambda r: (-r.score, r.product.code))
