"""产品浏览 API：全部在售产品可查看，能否买入由代码判断。

与 LLM 工具共用同一套适当性规则：超出评级的产品在任何入口都不能买入（S11）。
"""

from datetime import datetime

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session

from app.api.deps import get_customer_id, get_now
from app.assessment.scoring import load_questionnaire
from app.assessment.service import latest_confirmed
from app.compliance.policy import Permission, evaluate_gate
from app.compliance.suitability import CustomerContext, evaluate
from app.db.session import get_session
from app.products import presenter
from app.products.catalog import ProductStatus, ProductType, load_catalog
from app.products.service import SearchFilters, browse, upcoming
from app.purchases.service import blocking_reasons
from app.reminders.service import ReminderError, check_remindable, reminded_codes

router = APIRouter(prefix="/api/v1/products", tags=["products"])


def customer_rating(
    db: Session = Depends(get_session),
    customer_id: str = Depends(get_customer_id),
    now: datetime = Depends(get_now),
) -> str | None:
    """有效测评的评级；未测评或已过期时为 None（仍可浏览，但不能买入）。"""
    gate = evaluate_gate(latest_confirmed(db, customer_id), now)
    return gate.risk_rating if gate.permission is Permission.ASSESSED else None


def _remind_state(product, rating: str | None, reminded: set[str]) -> dict:
    try:
        check_remindable(product, rating)
        return {"allowed": True, "reminded": product.code in reminded, "reason": None}
    except ReminderError as exc:
        return {"allowed": False, "reminded": False, "reason": str(exc)}


@router.get("")
def list_products(
    product_type: list[ProductType] | None = Query(default=None),
    max_lockup_days: int | None = None,
    rating: str | None = Depends(customer_rating),
    db: Session = Depends(get_session),
    customer_id: str = Depends(get_customer_id),
):
    """全部在售产品。可买入的排在前面；超出评级或未测评的标注原因，只能查看。另列即将发售的新品。"""
    catalog = load_catalog()
    reminded = reminded_codes(db, customer_id)
    result = browse(
        catalog, rating, SearchFilters(product_types=product_type, max_lockup_days=max_lockup_days)
    )
    band = load_questionnaire().band(rating) if rating else None
    return {
        "catalog_version": catalog.catalog_version,
        "rating": {
            "code": band.rating,
            "name": band.name,
            "max_product_risk": band.max_product_risk,
        }
        if band
        else None,
        "items": [
            {
                **presenter.card(r.product),
                "purchasable": True,
                "rank": i + 1,
                "highlights": r.highlights(),
            }
            for i, r in enumerate(result.ranked)
        ]
        + [
            {
                **presenter.card(p),
                "purchasable": not blocking_reasons(p, rating),
                "rank": None,
                "warnings": messages,
            }
            for p, messages in result.other
        ],
        "upcoming": [
            {**presenter.card(p), "remind": _remind_state(p, rating, reminded)}
            for p in upcoming(catalog, None)
            if not product_type or p.product_type in product_type
        ],
        "ranking_note": "排序依据：流动性、费用；不按收益排序。",
    }


@router.get("/{code}")
def product_detail(
    code: str,
    rating: str | None = Depends(customer_rating),
    db: Session = Depends(get_session),
    customer_id: str = Depends(get_customer_id),
):
    """产品详情对所有客户开放（客观条款）；能否买入由代码判断并说明原因。"""
    product = load_catalog().get(code)
    if product is None:
        raise HTTPException(status_code=404, detail="产品不存在")
    blocked = blocking_reasons(product, rating)
    eligibility = evaluate(product, CustomerContext(risk_rating=rating)) if rating else None
    return {
        **presenter.detail(product),
        "eligible": eligibility.eligible if eligibility else False,
        "eligibility_messages": eligibility.messages if eligibility else [],
        "purchase": {"allowed": not blocked, "reasons": blocked},
        "remind": _remind_state(product, rating, reminded_codes(db, customer_id))
        if product.status is ProductStatus.UPCOMING
        else None,
    }
