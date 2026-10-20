"""Candidate ranking: only products that passed the suitability hard filter and have verified data
are ranked.

Deliberately **does not use** benchmarks or past returns: a benchmark isn't an expected return, and
ranking by it would effectively push
products with higher benchmarks and usually higher risk. Sales commission isn't a ranking input
either.
"""

from decimal import Decimal

from pydantic import BaseModel

from app.core.i18n import L
from app.products.catalog import Product

# Weights are configurable; without an investment horizon, horizon fit is skipped and the other
# weights scale up proportionally
WEIGHTS = {"horizon_fit": Decimal("0.4"), "liquidity": Decimal("0.3"), "cost": Decimal("0.3")}
FACTOR_LABELS = {"horizon_fit": "期限匹配", "liquidity": "流动性", "cost": "费用"}
HIGHLIGHT_THRESHOLD = Decimal("0.8")


class RankedProduct(BaseModel):
    product: Product
    score: Decimal
    factors: dict[str, Decimal]  # score per factor (0-1)

    def explanation(self) -> str:
        parts = [f"{FACTOR_LABELS[k]} {v:.2f}" for k, v in self.factors.items()]
        return "，".join(parts)

    def highlights(self) -> list[str]:
        """Match reasons shown to the customer: only from ranking factors (horizon, liquidity,
        fees), never returns."""
        tags = []
        if self.product.lockup_days == 0:
            tags.append(L("随时可取", "Withdraw anytime"))
        if self.factors.get("horizon_fit", Decimal(0)) >= HIGHLIGHT_THRESHOLD:
            tags.append(L("期限与您的计划匹配", "Fits your time horizon"))
        if self.factors["cost"] >= HIGHLIGHT_THRESHOLD:
            tags.append(L("候选中费用较低", "Lower fees among matches"))
        return tags


def _scale_inverse(value: Decimal, low: Decimal, high: Decimal) -> Decimal:
    """Map a lower-is-better factor to 0-1; if all candidates are equal, all get 1."""
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
            # The closer the holding period is to (without exceeding) the horizon, the better;
            # longer products are already filtered out
            factors["horizon_fit"] = min(lockup / Decimal(max(horizon_days, 1)), Decimal(1))
        score = sum(weights[k] * v for k, v in factors.items()) / total_weight
        ranked.append(RankedProduct(product=p, score=score, factors=factors))
    # Break ties by code so results are reproducible
    return sorted(ranked, key=lambda r: (-r.score, r.product.code))
